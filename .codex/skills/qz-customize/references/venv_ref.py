"""Virtual environment management for qzx workspaces.

Handles local venv setup (uv sync) and remote venv bootstrap (SSH + uv).
All paths use uv exclusively — no pip fallback.

Adapt: extras list, remote Python detection.
"""

from __future__ import annotations

import os
import posixpath
import shlex
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any


def remote_workspace_venv_path(*, source_root_name: str, workspace_name: str, remote_venv: str | None = None) -> str:
    """Compute remote venv path.  Convention: ~/venvs/<project>-<workspace>."""
    if remote_venv:
        return remote_venv
    return posixpath.join("~", "venvs", f"{source_root_name}-{workspace_name}")


def ensure_local_workspace_venv(
    workspace_root: Path,
    *,
    source_root: Path,
    include_dev: bool = True,
) -> dict[str, Any]:
    """Create or update a local .venv in the workspace using uv.

    If a pyproject.toml exists, uses ``uv sync``.  Also sets up the qzx
    tools venv if ``tools/qzx/pyproject.toml`` exists in the workspace.
    """
    root = Path(workspace_root).resolve()
    venv_root = root / ".venv"
    python_path = venv_root / "bin" / "python"
    qzx_info = ensure_local_qzx_venv(root, source_root=source_root)
    qzx_target = Path(qzx_info["qzx"]) if qzx_info else Path(source_root).resolve() / "tools" / "qzx" / ".venv" / "bin" / "qzx"

    if venv_root.is_symlink():
        venv_root.unlink()
    if not python_path.exists():
        _run_local(["uv", "venv", str(venv_root)], cwd=root)

    if (root / "pyproject.toml").is_file():
        sync_cmd = ["uv", "sync", "--active"]
        if (root / "uv.lock").is_file():
            sync_cmd.append("--frozen")
        for extra in _workspace_sync_extras(root, include_dev=include_dev):
            sync_cmd.extend(["--extra", extra])
        _run_local(sync_cmd, cwd=root, extra_env={"VIRTUAL_ENV": str(venv_root)})
    else:
        editable_target = str(root)
        if include_dev and _project_has_extra(root, "dev"):
            editable_target = f"{editable_target}[dev]"
        _run_local(["uv", "pip", "install", "--python", str(python_path), "-e", editable_target], cwd=root)

    qzx_link = venv_root / "bin" / "qzx"
    if qzx_target.exists():
        _replace_with_symlink(qzx_link, qzx_target)

    return {
        "python": str(python_path),
        "qzx": str(qzx_link) if qzx_link.exists() else "",
        "qzx_venv": str(qzx_info["venv"]) if qzx_info else "",
        "venv": str(venv_root),
    }


def ensure_local_qzx_venv(
    workspace_root: Path,
    *,
    source_root: Path,
) -> dict[str, str] | None:
    """Set up a dedicated qzx venv at tools/qzx/.venv in the workspace.

    Mirrors dependencies from the source root's qzx venv so all worktrees
    share the same package set.
    """
    root = Path(workspace_root).resolve()
    qzx_root = root / "tools" / "qzx"
    if not (qzx_root / "pyproject.toml").is_file():
        return None

    venv_root = qzx_root / ".venv"
    python_path = venv_root / "bin" / "python"
    if venv_root.is_symlink():
        venv_root.unlink()
    if not python_path.exists():
        _run_local(["uv", "venv", str(venv_root)], cwd=root)

    mirrored_requirements = _freeze_source_qzx_requirements(Path(source_root).resolve())
    if mirrored_requirements:
        _install_local_requirements(python_path, mirrored_requirements, cwd=root)

    _run_local(["uv", "pip", "install", "--python", str(python_path), "-e", str(qzx_root)], cwd=root)
    return {
        "python": str(python_path),
        "qzx": str(venv_root / "bin" / "qzx"),
        "venv": str(venv_root),
    }


def ensure_remote_workspace_venv(
    *,
    remote_host: str,
    remote_workspace_root: str,
    remote_venv_path: str,
) -> dict[str, str]:
    """Bootstrap a venv on the remote host via SSH + uv.

    Detects pyproject.toml on remote, creates venv with seed Python,
    runs uv sync.  Forwards UV_INDEX / UV_EXTRA_INDEX_URL from local env.
    """
    python_path = posixpath.join(remote_venv_path, "bin", "python")
    forwarded_env = _forwarded_uv_env()
    bootstrap_script = "\n".join([
        "set -euo pipefail",
        *[f"export {key}={shlex.quote(value)}" for key, value in forwarded_env.items()],
        f"cd {_quote_remote_path(remote_workspace_root)}",
        "seed_python=$(command -v python3 || command -v python || true)",
        'if [ -z "$seed_python" ]; then echo "no remote python interpreter found" >&2; exit 127; fi',
        f"if [ ! -x {_quote_remote_path(python_path)} ]; then",
        f"  rm -rf {_quote_remote_path(remote_venv_path)}",
        f'  env -u UV_VENV_SEED uv venv --no-config --no-project --python "$seed_python" {_quote_remote_path(remote_venv_path)}',
        "fi",
        f"if [ -f {_quote_remote_path(posixpath.join(remote_workspace_root, 'uv.lock'))} ]; then",
        f"  VIRTUAL_ENV={_quote_remote_path(remote_venv_path)} env -u UV_VENV_SEED uv sync --active --frozen --no-dev",
        "else",
        f"  VIRTUAL_ENV={_quote_remote_path(remote_venv_path)} env -u UV_VENV_SEED uv sync --active --no-dev",
        "fi",
        "",
    ])
    completed = subprocess.run(
        ["ssh", remote_host, f"bash -lc {shlex.quote(bootstrap_script)}"],
        check=False, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() if completed.stderr else ""
        raise RuntimeError(f"remote venv bootstrap failed (rc={completed.returncode})" + (f"\n{detail}" if detail else ""))
    return {"python": python_path, "remote_host": remote_host, "venv": remote_venv_path}


# --- Helpers ---

def _project_has_extra(project_root: Path, extra: str) -> bool:
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.is_file():
        return False
    payload = tomllib.loads(pyproject_path.read_text())
    return extra in payload.get("project", {}).get("optional-dependencies", {})


def _workspace_sync_extras(project_root: Path, *, include_dev: bool) -> list[str]:
    extras: list[str] = []
    if include_dev and _project_has_extra(project_root, "dev"):
        extras.append("dev")
    return extras


def _freeze_source_qzx_requirements(source_root: Path) -> list[str]:
    source_python = source_root / "tools" / "qzx" / ".venv" / "bin" / "python"
    if not source_python.exists():
        return []
    completed = subprocess.run(
        ["uv", "pip", "freeze", "--python", str(source_python)],
        cwd=source_root, capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"failed to inspect source qzx deps: {completed.stderr.strip()}")

    source_qzx_root = source_root / "tools" / "qzx"
    requirements: list[str] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if str(source_qzx_root.resolve()) in line or source_qzx_root.resolve().as_uri() in line:
            continue
        requirements.append(line)
    return requirements


def _install_local_requirements(python_path: Path, requirements: list[str], *, cwd: Path) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write("\n".join(requirements) + "\n")
        requirements_path = Path(handle.name)
    try:
        _run_local(["uv", "pip", "install", "--python", str(python_path), "-r", str(requirements_path)], cwd=cwd)
    finally:
        requirements_path.unlink(missing_ok=True)


def _forwarded_uv_env() -> dict[str, str]:
    keys = ("UV_INDEX", "UV_DEFAULT_INDEX", "UV_EXTRA_INDEX_URL", "UV_FIND_LINKS")
    return {key: value for key in keys if (value := os.environ.get(key))}


def _replace_with_symlink(link_path: Path, target: Path) -> None:
    if link_path.is_symlink() or link_path.exists():
        link_path.unlink()
    link_path.symlink_to(target, target_is_directory=target.is_dir())


def _run_local(args: list[str], *, cwd: Path, extra_env: dict[str, str] | None = None) -> None:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        args, cwd=cwd, env=env, check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() if completed.stderr else ""
        raise RuntimeError(f"command failed (rc={completed.returncode}): {' '.join(args)}" + (f"\n{detail}" if detail else ""))


def _quote_remote_path(path: str) -> str:
    if path == "~":
        return "~"
    prefix = ""
    remainder = path
    if path.startswith("~/"):
        prefix = "~/"
        remainder = path[2:]
    elif path.startswith("/"):
        prefix = "/"
        remainder = path[1:]
    parts = [part for part in remainder.split("/") if part]
    body = "/".join(shlex.quote(part) for part in parts)
    if not body:
        return prefix.rstrip("/") or "."
    return f"{prefix}{body}"
