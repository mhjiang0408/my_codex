"""Job launch planning and submission — plan/execute pattern.

Two-phase workflow:
1. build_launch_plan() — create run state, load template, render entrypoint
2. submit_launch_plan() — upload script to remote, submit job via qz SDK

The entrypoint script supports two launcher modes:
- direct: run the command directly (default)
- ray_job: bootstrap a Ray cluster, submit via ``ray job submit``

Ray support includes: node rank detection (PET_* env), NCCL NVLS auto-detect,
master address DNS resolution, runtime env propagation.

Adapt: DEFAULT_QZ_JOB_NAME_PREFIX, default_command(), template context keys.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from qzx.context import resolve_workspace
from qzx.remote import upload_remote_text_file
from qzx.runs import prepare_run, slugify, update_run_state
from qzx.templates import load_template
from qzx.venv import remote_workspace_venv_path

DEFAULT_QZ_JOB_NAME_PREFIX = os.environ.get("QZX_QZ_JOB_PREFIX", "qzx")
DEFAULT_QZ_JOB_NAME_MAX_LENGTH = 63


def build_launch_plan(
    name: str,
    *,
    worktree: str | None = None,
    repo_root: Path | None = None,
    runs_root: Path | None = None,
    start: Path | None = None,
    note: str | None = None,
    run_id: str | None = None,
    command: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    script_name: str = "launch.sh",
    template: str | None = None,
    template_root: Path | None = None,
    template_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a launch plan: prepare run state, load template, render entrypoint."""
    workspace = resolve_workspace(worktree=worktree, repo_root=repo_root, runs_root=runs_root, start=start)
    prepared = prepare_run(
        name, worktree=worktree, repo_root=repo_root, runs_root=runs_root,
        start=start, note=note, run_id=run_id,
    )
    template_payload = _load_launch_template(
        template, repo_root=workspace.workspace_root, template_root=template_root,
        overrides=template_overrides, prepared=prepared, workspace=workspace, name=name,
    )
    command_argv, shell_command = _resolve_launch_command(command, template_payload)
    remote_launcher = _resolve_remote_launcher(template_payload, command_argv=command_argv, shell_command=shell_command)
    ray_num_gpus = _int_or_none((template_payload or {}).get("platform", {}).get("ray_num_gpus_per_node")) or 8

    env = {
        "PYTHONUNBUFFERED": "1",
        "QZX_RUN_ID": prepared["run_id"],
        "QZX_RUN_NAME": name,
        "QZX_SORTED_DIR": prepared["sorted_dir"],
        "QZX_SOURCE_ROOT": str(workspace.source_root),
        "QZX_STATE_FILE": prepared["state_file"],
        "QZX_WORKSPACE": workspace.workspace_name,
        "QZX_WORKSPACE_ROOT": str(workspace.workspace_root),
    }
    env.update(_stringify_env((template_payload or {}).get("env", {})))
    if extra_env:
        env.update(_stringify_env(extra_env))

    job_config = (template_payload or {}).get("platform") or {}

    # Render local entrypoint script.
    script_asset_path = Path(prepared["script_dir"]) / script_name
    script_path = Path(prepared["sorted_dir"]) / script_name
    script_asset_path.write_text(
        _render_pod_entrypoint(
            workspace_root=str(workspace.workspace_root),
            activate_path=str(workspace.workspace_root / ".venv" / "bin" / "activate"),
            state_file=Path(prepared["state_file"]),
            env=env,
            command=command_argv,
            shell_command=shell_command,
        )
    )
    script_asset_path.chmod(script_asset_path.stat().st_mode | 0o111)
    # Relative symlink so it survives rsync to remote.
    rel_script = os.path.relpath(script_asset_path, script_path.parent)
    if script_path.is_symlink() or script_path.exists():
        script_path.unlink()
    script_path.symlink_to(rel_script)

    update_run_state(
        Path(prepared["state_file"]), status="ready",
        command=command_argv or shell_command,
        env=env,
        remote_launcher=remote_launcher,
        script_path=str(script_path),
    )

    prepared["command"] = shell_command or shlex.join(command_argv or [])
    prepared["command_argv"] = command_argv or []
    prepared["cwd"] = str(workspace.workspace_root)
    prepared["env"] = env
    prepared["job_config"] = job_config
    prepared["ray_num_gpus_per_node"] = ray_num_gpus
    prepared["remote_launcher"] = remote_launcher
    prepared["script_path"] = str(script_path)
    prepared["shell_command"] = shell_command
    prepared["template_name"] = (template_payload or {}).get("template", {}).get("name", "")
    prepared["template_path"] = (template_payload or {}).get("template", {}).get("path", "")
    prepared["workspace"] = workspace.workspace_name
    prepared["workspace_root"] = str(workspace.workspace_root)
    return prepared


def submit_launch_plan(
    plan: dict[str, Any],
    *,
    remote_host: str = "qz-cpu",
    remote_root: str = "~/ag",
    remote_venv: str | None = None,
    pool: str | None = None,
    pool_type: str | None = None,
    nodes: int | None = None,
    image: str | None = None,
    image_type: str | None = None,
    priority: int | None = None,
    shm_size: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Submit a launch plan: upload entrypoint, create QZ job."""
    import qz.api
    import qz.avail

    remote_spec = _build_remote_plan_spec(plan, remote_root=remote_root, remote_venv=remote_venv)

    # Re-render entrypoint with remote paths.
    remote_env = _build_remote_launch_env(
        plan["env"], remote_spec,
        workspace_root=str(plan["workspace_root"]),
        source_root=str(plan["source_root"]),
    )
    remote_script = _render_pod_entrypoint(
        workspace_root=remote_spec["remote_workspace_root"],
        activate_path=remote_spec["remote_activate_path"],
        env=remote_env,
        command=list(plan.get("command_argv") or []),
        shell_command=plan.get("shell_command") or None,
        launcher_kind=str(plan.get("remote_launcher") or "direct"),
        ray_num_gpus_per_node=_int_or_none(plan.get("ray_num_gpus_per_node")),
    )
    upload_remote_text_file(
        remote_host=remote_host,
        remote_path=remote_spec["remote_entrypoint_path"],
        content=remote_script,
    )

    # Resolve platform config from template + CLI overrides.
    job_config = dict(plan.get("job_config") or {})
    resolved_nodes = int(nodes or job_config.get("nodes") or 1)
    resolved_pool = pool if pool is not None else job_config.get("pool")
    resolved_pool_type = pool_type or job_config.get("pool_type")
    resolved_image = image if image is not None else job_config.get("image")
    resolved_image_type = image_type if image_type is not None else job_config.get("image_type")
    resolved_priority = priority if priority is not None else _int_or_none(job_config.get("priority"))
    resolved_shm_size = shm_size if shm_size is not None else _int_or_none(job_config.get("shm_size"))

    # Resolve pool via qz SDK.
    pool_cfg = qz.avail.resolve_pool(
        alias=resolved_pool,
        nodes=resolved_nodes,
        pool_type=resolved_pool_type,
    )
    submitted_job_name = build_qz_job_name(str(plan["name"]))
    payload = qz.api.build_job_payload(
        name=submitted_job_name,
        command=f"bash {remote_spec['remote_entrypoint_path']}",
        pool=pool_cfg,
        nodes=resolved_nodes,
        image=resolved_image,
        image_type=resolved_image_type,
        priority=resolved_priority,
        shm_size=resolved_shm_size,
        timeout=_int_or_none(job_config.get("timeout")),
    )
    job_result = qz.api.create_job(payload)["result"]

    backend = {
        "command": f"bash {remote_spec['remote_entrypoint_path']}",
        "kind": "qz_job",
        "job_id": job_result["job_id"],
        "job_name": submitted_job_name,
        "pool": resolved_pool or "",
        "pool_type": resolved_pool_type or "",
        "remote_entrypoint_path": remote_spec["remote_entrypoint_path"],
        "remote_host": remote_host,
        "remote_venv": remote_spec["remote_venv"],
        "remote_workspace_root": remote_spec["remote_workspace_root"],
    }
    state = update_run_state(
        Path(plan["state_file"]),
        status="queued",
        backend=backend,
        job_id=job_result["job_id"],
        job_name=submitted_job_name,
    )
    state["backend"] = backend
    state["job"] = job_result
    return state


def run_local_launch(plan: dict[str, Any], *, wait: bool = True) -> dict[str, Any]:
    """Execute a launch plan locally (for testing)."""
    script_path = Path(plan["script_path"])
    cwd = Path(plan["cwd"])
    state_file = Path(plan["state_file"])
    if wait:
        completed = subprocess.run(["bash", str(script_path)], cwd=cwd, check=False)
        state = update_run_state(state_file, local_returncode=completed.returncode)
        state["returncode"] = completed.returncode
        return state
    proc = subprocess.Popen(["bash", str(script_path)], cwd=cwd)
    state = update_run_state(state_file, status="queued", pid=proc.pid)
    state["pid"] = proc.pid
    return state


def build_qz_job_name(
    name: str,
    *,
    prefix: str | None = None,
    max_length: int = DEFAULT_QZ_JOB_NAME_MAX_LENGTH,
) -> str:
    """Build a QZ-safe job name with optional hash truncation."""
    prefix_token = slugify(prefix or DEFAULT_QZ_JOB_NAME_PREFIX).lower() or "qzx"
    name_token = slugify(name).lower() or "run"
    candidate = f"{prefix_token}-{name_token}"
    if len(candidate) <= max_length:
        return candidate
    digest = hashlib.sha1(candidate.encode("utf-8")).hexdigest()[:8]
    available = max_length - len(prefix_token) - len(digest) - 2
    if available <= 0:
        shortened = prefix_token[: max(1, max_length - len(digest) - 1)].rstrip("-") or "qzx"
        return f"{shortened}-{digest}"
    trimmed = name_token[:available].rstrip("-") or "run"
    return f"{prefix_token}-{trimmed}-{digest}"


def default_command() -> list[str]:
    """Default command — override per project."""
    return [os.environ.get("PYTHON", "python"), "train.py"]


# --- Entrypoint rendering ---

def _render_pod_entrypoint(
    *,
    workspace_root: str,
    env: dict[str, str],
    command: list[str] | None = None,
    shell_command: str | None = None,
    activate_path: str | None = None,
    state_file: Path | None = None,
    launcher_kind: str = "direct",
    ray_num_gpus_per_node: int | None = None,
) -> str:
    """Render a bash entrypoint script for a QZ job pod."""
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"cd {_quote_shell_path(workspace_root)}",
    ]
    if activate_path:
        lines.extend([
            f"if [ -f {_quote_shell_path(activate_path)} ]; then",
            f"  source {_quote_shell_path(activate_path)}",
            "fi",
        ])
    for key, value in env.items():
        lines.append(f"export {key}={shlex.quote(value)}")

    # Expand ~ in env vars containing tilde paths.
    expanduser_keys = [k for k in env if k.startswith("QZX_")]
    for key, value in env.items():
        if (value == "~" or value.startswith("~/")) and key not in expanduser_keys:
            expanduser_keys.append(key)
    lines.extend(_render_expanduser_env_block(expanduser_keys))
    lines.extend(_render_persistent_log_block())

    if launcher_kind == "ray_job":
        lines.extend(_render_ray_job_block(
            env=env, command=command, shell_command=shell_command,
            ray_num_gpus_per_node=ray_num_gpus_per_node,
        ))
    else:
        # Direct launcher.
        if state_file is not None:
            lines.append(_state_update_block("'running'", state_file, started=True))
        lines.extend([
            'printf "[qzx] workspace=%s\\n" "$QZX_WORKSPACE"',
            'printf "[qzx] run_id=%s\\n" "$QZX_RUN_ID"',
            "set +e",
        ])
        if shell_command:
            lines.append(shell_command.rstrip("\n"))
        else:
            lines.append(shlex.join(command or default_command()))
        lines.extend(["rc=$?", "set -e"])
        if state_file is not None:
            lines.extend([
                'export QZX_RC="$rc"',
                _state_update_block('"succeeded" if rc == 0 else "failed"', state_file, finished=True, include_rc=True),
            ])

    lines.extend(['exit "$rc"', ""])
    return "\n".join(lines)


def _render_persistent_log_block() -> list[str]:
    """Tee all output to a persistent log file on the pod."""
    return [
        'QZX_POD_LOG_ROOT="${QZX_WORKSPACE_ROOT}"',
        'case "$QZX_POD_LOG_ROOT" in',
        '  "~") QZX_POD_LOG_ROOT="$HOME" ;;',
        '  "~/"*) QZX_POD_LOG_ROOT="$HOME/${QZX_POD_LOG_ROOT:2}" ;;',
        "esac",
        'QZX_POD_LOG_DIR="${QZX_POD_LOG_ROOT}/runs/logs/${QZX_RUN_NAME}/pod-logs"',
        'mkdir -p "$QZX_POD_LOG_DIR"',
        'QZX_POD_LOG="${QZX_POD_LOG_DIR}/${QZX_RUN_ID}-${HOSTNAME:-local}.log"',
        'exec > >(tee -a "$QZX_POD_LOG") 2>&1',
        'printf "[qzx] file_log=%s\\n" "$QZX_POD_LOG"',
    ]


def _render_expanduser_env_block(keys: list[str]) -> list[str]:
    """Expand ~ in exported env vars (needed for Ray workers)."""
    lines: list[str] = []
    for key in keys:
        lines.extend([
            f'if [ -n "${{{key}:-}}" ]; then',
            f'  case "${{{key}}}" in',
            f'    "~") export {key}="$HOME" ;;',
            f'    "~/"*) export {key}="$HOME/${{{key}:2}}" ;;',
            "  esac",
            "fi",
        ])
    return lines


# --- Ray job launcher ---

def _render_ray_job_block(
    *,
    env: dict[str, str],
    command: list[str] | None,
    shell_command: str | None,
    ray_num_gpus_per_node: int | None,
) -> list[str]:
    """Render Ray cluster bootstrap + job submission block.

    Handles: master/worker detection via PET_* env, NCCL NVLS auto-detect,
    DNS resolution loop for master address, runtime env propagation.
    """
    runtime_env_keys = sorted({
        key for key in env if not key.startswith("QZX_")
    } | {"MASTER_ADDR", "NCCL_NVLS_ENABLE", "QZX_RUN_ID", "QZX_RUN_NAME", "QZX_WORKSPACE", "QZX_WORKSPACE_ROOT", "no_proxy"})

    if shell_command:
        submitted_command = shlex.join(["bash", "-lc", shell_command])
    else:
        submitted_command = shlex.join(command or default_command())

    join_address = '${MASTER_ADDR}:${QZX_RAY_PORT}'
    lines = [
        'printf "[qzx] workspace=%s\\n" "$QZX_WORKSPACE"',
        'printf "[qzx] run_id=%s\\n" "$QZX_RUN_ID"',
        # Node rank detection: PET_* (PyTorch Elastic) or direct env.
        'export MASTER_ADDR="${PET_MASTER_ADDR:-${MASTER_ADDR:-127.0.0.1}}"',
        'export NUM_NODES="${PET_NNODES:-${NUM_NODES:-1}}"',
        'export NODE_RANK="${PET_NODE_RANK:-${NODE_RANK:-0}}"',
        'export QZX_RAY_PORT="${QZX_RAY_PORT:-6379}"',
        'export QZX_RAY_DASHBOARD_PORT="${QZX_RAY_DASHBOARD_PORT:-8265}"',
        f'export QZX_RAY_NUM_GPUS_PER_NODE="${{QZX_RAY_NUM_GPUS_PER_NODE:-{int(ray_num_gpus_per_node or 8)}}}"',
        # NCCL NVLS auto-detection: enable if NVLink topology detected.
        'if [ -z "${NCCL_NVLS_ENABLE:-}" ] && command -v nvidia-smi >/dev/null 2>&1; then',
        "  if nvidia-smi topo -m 2>/dev/null | grep -q -o 'NV[0-9][0-9]*'; then",
        "    export NCCL_NVLS_ENABLE=1",
        "  else",
        "    export NCCL_NVLS_ENABLE=0",
        "  fi",
        "fi",
        # DNS resolution loop for master address.
        "while :; do",
        "  MASTER_IP=$(getent hosts \"$MASTER_ADDR\" | awk '{print $1}' || true)",
        '  if [ -n "$MASTER_IP" ]; then',
        '    MASTER_ADDR="$MASTER_IP"',
        "    break",
        "  fi",
        "  sleep 1",
        "done",
        # no_proxy for master address.
        'if [ -n "${no_proxy:-}" ]; then',
        '  export no_proxy="127.0.0.1,localhost,${MASTER_ADDR},${no_proxy}"',
        "else",
        '  export no_proxy="127.0.0.1,localhost,${MASTER_ADDR}"',
        "fi",
        'printf "[qzx] master_addr=%s rank=%s nodes=%s\\n" "$MASTER_ADDR" "$NODE_RANK" "$NUM_NODES"',
        "ray stop --force >/dev/null 2>&1 || true",
        "pkill -9 ray >/dev/null 2>&1 || true",
        # Head node: start Ray head, submit job, wait.
        'if [ "$NODE_RANK" = "0" ]; then',
        "  trap 'ray stop --force >/dev/null 2>&1 || true' EXIT",
        '  ray start --head --node-ip-address "$MASTER_ADDR" --port "$QZX_RAY_PORT"'
        ' --num-gpus "$QZX_RAY_NUM_GPUS_PER_NODE" --disable-usage-stats'
        ' --dashboard-host=0.0.0.0 --dashboard-port "$QZX_RAY_DASHBOARD_PORT"',
        '  until curl -sf "http://127.0.0.1:${QZX_RAY_DASHBOARD_PORT}/api/version" >/dev/null; do sleep 1; done',
    ]
    # Build runtime-env JSON from env vars.
    python_code = (
        "import json, os; "
        f"keys = {runtime_env_keys!r}; "
        "env_vars = {key: os.path.expanduser(os.environ[key]) for key in keys if key in os.environ}; "
        "print(json.dumps({'env_vars': env_vars}))"
    )
    lines.append(f"  QZX_RUNTIME_ENV_JSON=$(python -c {shlex.quote(python_code)})")
    lines.extend([
        "  set +e",
        f'  ray job submit --address="http://127.0.0.1:${{QZX_RAY_DASHBOARD_PORT}}" --runtime-env-json="$QZX_RUNTIME_ENV_JSON" -- {submitted_command}',
        "  rc=$?",
        "  set -e",
        "  ray stop --force >/dev/null 2>&1 || true",
        # Worker node: join cluster, wait for head to finish.
        "else",
        '  WORKER_IP="${SLIME_HOST_IP:-$(hostname -I | awk \'{print $1}\')}"',
        "  until ray start --address=" + join_address
        + ' --num-gpus "$QZX_RAY_NUM_GPUS_PER_NODE" --node-ip-address "$WORKER_IP" --disable-usage-stats; do',
        "    sleep 2",
        "  done",
        "  trap 'ray stop --force >/dev/null 2>&1 || true' EXIT",
        "  while ray status --address=" + join_address + " >/dev/null 2>&1; do",
        "    sleep 5",
        "  done",
        "  rc=0",
        "fi",
    ]
    return lines


def _state_update_block(
    status_expr: str, state_file: Path, *,
    started: bool = False, finished: bool = False, include_rc: bool = False,
) -> str:
    """Inline Python block that updates the run state file from the pod."""
    lines = [
        "python - <<'PY'",
        "import os, json",
        "from datetime import UTC, datetime",
        "from pathlib import Path",
        f"path = Path({str(state_file)!r})",
        "data = json.loads(path.read_text())",
        'stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")',
    ]
    if include_rc:
        lines.append("rc = int(os.environ['QZX_RC'])")
    lines.extend([
        f"data['status'] = {status_expr}",
        "data['updated_at'] = stamp",
    ])
    if started:
        lines.append("data.setdefault('started_at', stamp)")
    if finished:
        lines.append("data['finished_at'] = stamp")
    if include_rc:
        lines.append("data['exit_code'] = rc")
    lines.extend([
        "path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\\n')",
        "PY",
    ])
    return "\n".join(lines)


# --- Helpers ---

def _load_launch_template(
    template, *, repo_root, template_root, overrides, prepared, workspace, name,
) -> dict[str, Any] | None:
    if not template:
        return None
    context = {
        "name": name,
        "run_id": prepared["run_id"],
        "sorted_dir": prepared["sorted_dir"],
        "source_root": str(workspace.source_root),
        "workspace": workspace.workspace_name,
        "workspace_root": str(workspace.workspace_root),
    }
    return load_template(template, repo_root=repo_root, template_root=template_root, overrides=overrides, context=context)


def _resolve_launch_command(command, template_payload) -> tuple[list[str] | None, str | None]:
    if command:
        return command, None
    if template_payload:
        top = template_payload.get("command")
        if isinstance(top, list):
            return [str(item) for item in top], None
        if isinstance(top, str):
            return None, top.strip()
    return default_command(), None


def _resolve_remote_launcher(template_payload, *, command_argv, shell_command) -> str:
    platform = (template_payload or {}).get("platform") or {}
    explicit = platform.get("launcher")
    if explicit:
        if str(explicit) not in {"direct", "ray_job"}:
            raise ValueError(f"unsupported launcher: {explicit}")
        return str(explicit)
    if platform.get("ray_job"):
        return "ray_job"
    return "direct"


def _build_remote_plan_spec(plan, *, remote_root, remote_venv):
    source_root = Path(plan["source_root"])
    workspace_root = Path(plan["workspace_root"])
    workspace_name = str(plan["workspace"])
    remote_source_root = posixpath.join(remote_root, source_root.name)
    remote_runs_root = posixpath.join(remote_root, f"{source_root.name}-runs")
    remote_workspace_root = (
        remote_source_root if workspace_root == source_root
        else posixpath.join(remote_runs_root, workspace_name)
    )
    resolved_venv = remote_workspace_venv_path(
        source_root_name=source_root.name,
        workspace_name=workspace_name,
        remote_venv=remote_venv,
    )
    remote_runtime_root = posixpath.join(remote_workspace_root, ".qzx", "runs", str(plan["run_id"]))
    return {
        "remote_activate_path": posixpath.join(resolved_venv, "bin", "activate"),
        "remote_entrypoint_path": posixpath.join(remote_runtime_root, "entrypoint.sh"),
        "remote_root": remote_root,
        "remote_runtime_root": remote_runtime_root,
        "remote_runs_root": remote_runs_root,
        "remote_source_root": remote_source_root,
        "remote_venv": resolved_venv,
        "remote_workspace_root": remote_workspace_root,
    }


def _build_remote_launch_env(env, remote_spec, *, workspace_root, source_root):
    rendered = {
        key: _remap_path(value, workspace_root, remote_spec["remote_workspace_root"],
                         source_root, remote_spec["remote_source_root"])
        for key, value in env.items()
        if key not in {"QZX_SORTED_DIR", "QZX_STATE_FILE", "QZX_SOURCE_ROOT", "QZX_WORKSPACE_ROOT"}
    }
    rendered["QZX_SOURCE_ROOT"] = remote_spec["remote_source_root"]
    rendered["QZX_WORKSPACE_ROOT"] = remote_spec["remote_workspace_root"]
    rendered["QZX_REMOTE_WORKSPACE_ROOT"] = remote_spec["remote_workspace_root"]
    rendered["QZX_REMOTE_VENV"] = remote_spec["remote_venv"]
    return rendered


def _remap_path(value, source_prefix, remote_source, ws_prefix, remote_ws):
    for src, dst in [(source_prefix, remote_source), (ws_prefix, remote_ws)]:
        src = str(src).rstrip("/")
        if not src:
            continue
        if value == src:
            return dst
        if value.startswith(f"{src}/"):
            return posixpath.join(dst, value[len(src) + 1:])
    return value


def _stringify_env(env):
    return {str(k): str(v) for k, v in env.items() if v is not None}


def _int_or_none(value):
    if value in (None, ""):
        return None
    return int(str(value))


def _quote_shell_path(path: str) -> str:
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
    if not prefix:
        return shlex.quote(path)
    body = "/".join(shlex.quote(part) for part in parts)
    if not body:
        return prefix.rstrip("/") or "."
    return f"{prefix}{body}"
