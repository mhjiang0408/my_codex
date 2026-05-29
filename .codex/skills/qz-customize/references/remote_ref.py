"""SSH-based remote operations for qzx.

Provides remote path computation, file upload, and command execution.
All remote operations go through SSH — no QZ-specific API calls here.

Adapt: remote_root default, venv path convention.
"""

from __future__ import annotations

import posixpath
import shlex
import subprocess
from pathlib import Path
from typing import Any

from qzx.context import resolve_workspace
from qzx.venv import remote_workspace_venv_path


def build_remote_workspace_spec(
    *,
    worktree: str | None = None,
    repo_root: Path | None = None,
    runs_root: Path | None = None,
    start: Path | None = None,
    remote_root: str = "~/ag",
    remote_venv: str | None = None,
) -> dict[str, str]:
    """Compute remote paths for a workspace.

    Layout on remote:
        ~/ag/<project>/          — source root
        ~/ag/<project>-runs/<wt> — worktree roots
        ~/venvs/<project>-<wt>  — per-workspace venvs
    """
    workspace = resolve_workspace(worktree=worktree, repo_root=repo_root, runs_root=runs_root, start=start)
    remote_source_root = posixpath.join(remote_root, workspace.source_root.name)
    remote_runs_root = posixpath.join(remote_root, f"{workspace.source_root.name}-runs")
    remote_workspace_root = (
        remote_source_root if workspace.is_source_workspace else posixpath.join(remote_runs_root, workspace.workspace_name)
    )
    resolved_venv = remote_workspace_venv_path(
        source_root_name=workspace.source_root.name,
        workspace_name=workspace.workspace_name,
        remote_venv=remote_venv,
    )
    return {
        "remote_root": remote_root,
        "remote_runs_root": remote_runs_root,
        "remote_source_root": remote_source_root,
        "remote_venv": resolved_venv,
        "remote_workspace_root": remote_workspace_root,
        "source_root_name": workspace.source_root.name,
        "workspace": workspace.workspace_name,
    }


def build_exec_plan(
    command: list[str] | None,
    *,
    worktree: str | None = None,
    repo_root: Path | None = None,
    runs_root: Path | None = None,
    remote_host: str = "qz-cpu",
    remote_root: str = "~/ag",
    remote_venv: str | None = None,
    local: bool = False,
) -> dict[str, Any]:
    """Build a plan to execute a command in the remote workspace."""
    remote_spec = build_remote_workspace_spec(
        worktree=worktree, repo_root=repo_root, runs_root=runs_root,
        remote_root=remote_root, remote_venv=remote_venv,
    )
    remote_workspace_root = remote_spec["remote_workspace_root"]
    remote_venv_path = remote_spec["remote_venv"]

    if not command:
        raise ValueError("command is required")
    remote_command = shlex.join(command)

    remote_script = "\n".join([
        "set -euo pipefail",
        f"cd {_quote_remote_path(remote_workspace_root)}",
        f'if [ -f {_quote_remote_path(posixpath.join(remote_venv_path, "bin", "activate"))} ]; then',
        f"  source {_quote_remote_path(posixpath.join(remote_venv_path, 'bin', 'activate'))}",
        "fi",
        remote_command,
        "",
    ])
    command_line = (
        ["bash", "-lc", remote_script] if local
        else ["ssh", remote_host, f"bash -lc {shlex.quote(remote_script)}"]
    )
    return {
        "command": command,
        "command_line": command_line,
        "executor": "local" if local else "ssh",
        "remote_host": remote_host,
        "remote_script": remote_script,
        "remote_venv": remote_venv_path,
        "remote_workspace_root": remote_workspace_root,
        "workspace": remote_spec["workspace"],
    }


def execute_exec_plan(plan: dict[str, Any]) -> int:
    completed = subprocess.run(plan["command_line"], check=False)
    return completed.returncode


def upload_remote_text_file(
    *,
    remote_host: str,
    remote_path: str,
    content: str,
) -> dict[str, str]:
    """Upload text content to a remote file via SSH heredoc."""
    marker = "__QZX_REMOTE_FILE__"
    remote_dir = posixpath.dirname(remote_path)
    remote_script = "\n".join([
        "set -euo pipefail",
        f"mkdir -p {_quote_remote_path(remote_dir)}",
        f"cat > {_quote_remote_path(remote_path)} <<'{marker}'",
        content.rstrip("\n"),
        marker,
        f"chmod +x {_quote_remote_path(remote_path)}",
        "",
    ])
    completed = subprocess.run(
        ["ssh", remote_host, f"bash -lc {shlex.quote(remote_script)}"],
        check=False, stdin=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"remote file upload failed with exit code {completed.returncode}")
    return {"remote_host": remote_host, "remote_path": remote_path}


def remove_remote_paths(*, remote_host: str, paths: list[str]) -> dict[str, Any]:
    if not paths:
        return {"remote_host": remote_host, "paths": []}
    remote_script = "\n".join([
        "set -euo pipefail",
        "rm -rf " + " ".join(_quote_remote_path(path) for path in paths),
        "",
    ])
    completed = subprocess.run(
        ["ssh", remote_host, f"bash -lc {shlex.quote(remote_script)}"],
        check=False, stdin=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"remote cleanup failed with exit code {completed.returncode}")
    return {"remote_host": remote_host, "paths": paths}


def _quote_remote_path(path: str) -> str:
    """Quote path components for safe embedding in remote shell scripts."""
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
