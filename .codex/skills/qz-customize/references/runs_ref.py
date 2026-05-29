"""Run state management, status tracking, and waiting.

Each run gets a state.json file under ``runs/state/<run_id>.json``.
The state tracks status, timestamps, backend metadata (job_id, etc.),
and asset directory paths.

Runs follow the lifecycle: planned → ready → queued → running → terminal
(succeeded | failed | stopped).

Adapt: RUN_ASSET_DIRS, refresh logic for additional backend kinds.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from qzx.context import REMOTE_ONLY_ASSET_DIRS, RUN_ASSET_DIRS, resolve_workspace

TERMINAL_RUN_STATUSES = {"succeeded", "failed", "stopped"}
DEFAULT_WAIT_RUN_TARGET = "running"
RUN_WAIT_TARGETS = ("planned", "ready", "queued", "running", "stopped", "failed", "succeeded")


def prepare_run(
    name: str,
    *,
    worktree: str | None = None,
    repo_root: Path | None = None,
    runs_root: Path | None = None,
    start: Path | None = None,
    note: str | None = None,
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create run directories, state file, and symlinks."""
    workspace = resolve_workspace(worktree=worktree, repo_root=repo_root, runs_root=runs_root, start=start)
    timestamp_token = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    runs_root_path = workspace.runs_root
    name = _resolve_name_conflict(name=name, runs_root=runs_root_path)
    run_identifier = run_id or slugify(name)

    workspace_runs_root = workspace.workspace_runs_root
    sorted_root = runs_root_path / "sorted"
    state_root = runs_root_path / "state"
    script_root = runs_root_path / "scripts" / run_identifier
    note_root = runs_root_path / "notes"
    for d in (sorted_root, state_root, script_root, note_root):
        d.mkdir(parents=True, exist_ok=True)

    # Create asset directories (logs, checkpoints, etc.)
    asset_paths: dict[str, str] = {}
    workspace_asset_paths: dict[str, str] = {}
    for dirname in RUN_ASSET_DIRS:
        actual_path = runs_root_path / dirname / name
        link_parent = workspace_runs_root / dirname
        link_path = link_parent / name
        if dirname not in REMOTE_ONLY_ASSET_DIRS:
            actual_path.mkdir(parents=True, exist_ok=True)
            link_parent.mkdir(parents=True, exist_ok=True)
            if link_path != actual_path:
                _replace_with_symlink(link_path, actual_path)
        asset_paths[dirname] = str(actual_path)
        workspace_asset_paths[dirname] = str(link_path)

    # Sorted directory for human-browsable run history.
    sorted_name = _next_sorted_name(sorted_root, f"{timestamp_token}_{slugify(name)}")
    sorted_dir = sorted_root / sorted_name
    sorted_dir.mkdir(parents=True, exist_ok=False)

    # Note file.
    note_text = " ".join((note or "").splitlines()).strip()[:400]
    note_file = note_root / f"{name}.txt"
    note_file.write_text(f"{note_text}\n")

    state_file = state_root / f"{run_identifier}.json"
    state = {
        "assets": asset_paths,
        "created_at": _utc_iso_now(),
        "metadata": metadata or {},
        "name": name,
        "note_file": str(note_file),
        "run_id": run_identifier,
        "script_dir": str(script_root),
        "sorted_dir": str(sorted_dir),
        "source_root": str(workspace.source_root),
        "state_file": str(state_file),
        "status": "planned",
        "updated_at": _utc_iso_now(),
        "workspace": workspace.workspace_name,
        "workspace_assets": workspace_asset_paths,
        "workspace_root": str(workspace.workspace_root),
    }
    _write_state(state_file, state)

    # Relative symlinks in sorted dir for easy browsing.
    for dirname in RUN_ASSET_DIRS:
        target = Path(asset_paths[dirname])
        link = sorted_dir / dirname
        rel_target = os.path.relpath(target, sorted_dir)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(rel_target, target_is_directory=True)
    _symlink_relative(sorted_dir / "note.txt", note_file)
    _symlink_relative(sorted_dir / "state.json", state_file)

    return state


def update_run_state(state_file: Path, *, status: str | None = None, **updates: Any) -> dict[str, Any]:
    state = json.loads(Path(state_file).read_text())
    if status is not None:
        state["status"] = status
    for key, value in updates.items():
        if value is not None:
            state[key] = value
    state["updated_at"] = _utc_iso_now()
    _write_state(Path(state_file), state)
    return state


FEATURED_MIN_RUNTIME = timedelta(minutes=15)
FEATURED_RECENCY = timedelta(hours=24)


def list_run_states(
    *,
    repo_root: Path | None = None,
    start: Path | None = None,
    run_id: str | None = None,
    name: str | None = None,
    workspace: str | None = None,
    current_workspace_only: bool = False,
    statuses: Iterable[str] | None = None,
    live: bool = True,
    featured_only: bool = False,
) -> dict[str, Any]:
    """Load and optionally refresh all run records.

    With ``live=True``, refreshes non-terminal runs from the QZ API.
    With ``featured_only=True``, hides old terminal runs.
    """
    workspace_ctx = resolve_workspace(repo_root=repo_root, start=start)
    state_root = workspace_ctx.source_root / "runs" / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    workspace_filter = workspace_ctx.workspace_name if current_workspace_only else workspace
    wanted_statuses = {item for item in (statuses or []) if item}
    now = datetime.now(UTC)

    records = _load_run_records(state_root=state_root, run_id=run_id)

    # Pre-filter by static fields.
    if name:
        records = [r for r in records if r.get("name") == name]
    if workspace_filter:
        records = [r for r in records if r.get("workspace") == workspace_filter]

    if live:
        records = [_refresh_run_record(r) for r in records]

    filtered: list[dict[str, Any]] = []
    hidden = 0
    for record in records:
        if wanted_statuses and record.get("status") not in wanted_statuses:
            continue
        if featured_only and not _is_featured(record, now=now):
            hidden += 1
            continue
        filtered.append(record)

    filtered.sort(key=lambda r: (r.get("created_at", ""), r.get("run_id", "")), reverse=True)
    summary: dict[str, Any] = {
        "by_status": _count_by_key(filtered, "status"),
        "by_workspace": _count_by_key(filtered, "workspace"),
        "current_workspace": workspace_ctx.workspace_name,
        "source_root": str(workspace_ctx.source_root),
        "total": len(filtered),
    }
    if hidden:
        summary["hidden"] = hidden
    return {"runs": filtered, "summary": summary}


def wait_for_run_state(
    *,
    repo_root: Path | None = None,
    start: Path | None = None,
    run_id: str | None = None,
    name: str | None = None,
    workspace: str | None = None,
    current_workspace_only: bool = False,
    until: str | None = None,
    statuses: Iterable[str] | None = None,
    timeout: float = 0,
    poll_interval: float = 1.0,
    live: bool = True,
) -> dict[str, Any]:
    """Poll until a run reaches the target status."""
    wait_target = until or DEFAULT_WAIT_RUN_TARGET
    if wait_target not in (*RUN_WAIT_TARGETS, "terminal"):
        raise ValueError(f"unsupported wait target: {wait_target}")

    start_time = time.monotonic()
    deadline = time.monotonic() + timeout if timeout > 0 else None

    while True:
        listing = list_run_states(
            repo_root=repo_root, start=start, run_id=run_id, name=name,
            workspace=workspace, current_workspace_only=current_workspace_only, live=live,
        )
        runs = listing["runs"]
        if runs:
            candidate = runs[0]
            current_status = str(candidate.get("status") or "").lower()
            if wait_target == "terminal":
                if current_status in TERMINAL_RUN_STATUSES:
                    candidate["waited_for"] = _format_wait_duration(time.monotonic() - start_time)
                    return candidate
            elif current_status == wait_target or current_status in TERMINAL_RUN_STATUSES:
                candidate["waited_for"] = _format_wait_duration(time.monotonic() - start_time)
                return candidate
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for {run_id or name or 'run'} to reach {wait_target}")
        time.sleep(max(0.1, poll_interval))


def cleanup_run(
    *,
    repo_root: Path | None = None,
    start: Path | None = None,
    run_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Stop a run's backend job and update state."""
    import qz.api

    listing = list_run_states(repo_root=repo_root, start=start, run_id=run_id, name=name, live=False)
    if not listing["runs"]:
        raise FileNotFoundError(f"could not find run state for {run_id or name or 'run'}")

    record = listing["runs"][0]
    backend = record.get("backend") or {}
    cleanup: dict[str, Any] = {"run_id": record["run_id"]}

    if backend.get("kind") == "qz_job" and record.get("job_id"):
        if record.get("status") not in TERMINAL_RUN_STATUSES:
            cleanup["job_stop"] = qz.api.stop_job(str(record["job_id"]))
        cleanup["status"] = "stopped"
    else:
        cleanup["status"] = record.get("status", "unknown")

    state = update_run_state(
        Path(record["state_file"]),
        status=str(cleanup["status"]),
        cleanup=cleanup,
        cleaned_at=_utc_iso_now(),
    )
    return {"cleanup": cleanup, "run": state}


# --- Summarization ---

def summarize_run_listing(listing: dict[str, Any], *, limit: int | None = None) -> dict[str, Any]:
    records = list(listing.get("runs") or [])
    shown = records if limit is None or limit <= 0 else records[:limit]
    summary = dict(listing.get("summary") or {})
    summary["shown"] = len(shown)
    return {"runs": [summarize_run_record(r) for r in shown], "summary": summary}


def summarize_run_record(record: dict[str, Any]) -> dict[str, Any]:
    backend = record.get("backend") or {}
    summary: dict[str, Any] = {
        "run_id": record.get("run_id"),
        "name": record.get("name"),
        "status": record.get("status"),
        "workspace": record.get("workspace"),
        "created_at": record.get("created_at"),
    }
    for key in ("started_at", "finished_at", "template_name"):
        value = record.get(key)
        if value not in (None, ""):
            summary[key] = value
    if backend.get("kind") == "qz_job":
        job_name = backend.get("job_name") or record.get("job_name")
        if job_name:
            summary["qz_job"] = job_name
    return summary


def summarize_launch_result(payload: dict[str, Any]) -> dict[str, Any]:
    run = payload.get("run") if isinstance(payload.get("run"), dict) else payload
    backend = run.get("backend") or {}
    summary: dict[str, Any] = {
        "run_id": run.get("run_id"),
        "name": run.get("name"),
        "status": run.get("status"),
    }
    if run.get("template_name"):
        summary["template"] = run["template_name"]
    for key in ("job_id", "job_name"):
        val = backend.get(key) or run.get(key)
        if val:
            summary[key] = val
    if isinstance(payload.get("sync"), dict):
        summary["sync_ok"] = payload["sync"].get("returncode", 0) == 0
    if isinstance(payload.get("wait"), dict):
        wait = payload["wait"]
        summary["status"] = wait.get("status") or summary.get("status")
        if wait.get("waited_for"):
            summary["waited_for"] = wait["waited_for"]
    if "logs" in payload:
        summary["logs"] = payload["logs"]
    return summary


def wait_result_exit_code(result: dict[str, Any] | None) -> int:
    if not isinstance(result, dict):
        return 0
    return 2 if result.get("status") == "failed" else 0


# --- Helpers ---

def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return slug or "run"


def _utc_iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_state(state_file: Path, state: dict[str, Any]) -> None:
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def _load_run_records(*, state_root: Path, run_id: str | None) -> list[dict[str, Any]]:
    if run_id:
        candidate = state_root / f"{run_id}.json"
        if not candidate.is_file():
            return []
        return [json.loads(candidate.read_text())]
    return [json.loads(path.read_text()) for path in sorted(state_root.glob("*.json"))]


def _refresh_run_record(record: dict[str, Any]) -> dict[str, Any]:
    """Refresh a run record from the QZ API."""
    backend = record.get("backend") or {}
    if backend.get("kind") != "qz_job":
        return record
    if record.get("status") in TERMINAL_RUN_STATUSES and record.get("cleaned_at"):
        return record

    try:
        import qz.api
        detail = qz.api.get_job_detail(str(record["job_id"]))
        record["job_status"] = detail.get("status", "")
        # Map QZ job statuses to qzx run statuses.
        qz_status = str(detail.get("status") or "").lower()
        status_map = {
            "running": "running", "succeeded": "succeeded", "failed": "failed",
            "stopped": "stopped", "pending": "queued", "waiting": "queued",
        }
        record["status"] = status_map.get(qz_status, record.get("status", "queued"))
    except Exception as exc:
        record["live_error"] = str(exc)

    record["updated_at"] = _utc_iso_now()
    _write_state(Path(record["state_file"]), record)
    return record


def _is_featured(record: dict[str, Any], *, now: datetime) -> bool:
    """Featured = running, or recent (<24h), or long-running (>15min)."""
    status = str(record.get("status") or "")
    if status not in TERMINAL_RUN_STATUSES:
        return True
    created_str = record.get("created_at") or ""
    if created_str:
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if now - created < FEATURED_RECENCY:
                return True
            end_str = record.get("finished_at") or record.get("updated_at") or ""
            if end_str:
                ended = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if ended - created >= FEATURED_MIN_RUNTIME:
                    return True
        except (ValueError, TypeError):
            pass
    return False


def _format_wait_duration(elapsed: float) -> str:
    total = max(0, int(elapsed))
    parts: list[str] = []
    for suffix, size in [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]:
        if size > 1:
            value, total = divmod(total, size)
            if value:
                parts.append(f"{value}{suffix}")
        elif not parts or total:
            parts.append(f"{total}{suffix}")
    return " ".join(parts)


def _count_by_key(records, key):
    counts: dict[str, int] = {}
    for r in records:
        v = str(r.get(key, "unknown"))
        counts[v] = counts.get(v, 0) + 1
    return dict(sorted(counts.items()))


def _next_sorted_name(sorted_root: Path, base: str) -> str:
    candidate = base
    index = 2
    while (sorted_root / candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _resolve_name_conflict(*, name: str, runs_root: Path) -> str:
    conflicts = [runs_root / d / name for d in RUN_ASSET_DIRS]
    conflicts.append(runs_root / "notes" / f"{name}.txt")
    if not any(p.exists() or p.is_symlink() for p in conflicts):
        return name
    candidate = name
    index = 2
    while any((runs_root / d / candidate).exists() for d in RUN_ASSET_DIRS):
        candidate = f"{name}-{index}"
        index += 1
    print(f"name conflict: using {candidate!r} instead of {name!r}", file=sys.stderr)
    return candidate


def _replace_with_symlink(link_path: Path, target: Path) -> None:
    if link_path.is_symlink() or link_path.exists():
        if link_path.is_dir() and not link_path.is_symlink():
            for child in link_path.iterdir():
                if child.is_dir() and not child.is_symlink():
                    raise RuntimeError(f"refusing to replace non-empty directory: {link_path}")
                child.unlink()
            link_path.rmdir()
        else:
            link_path.unlink()
    link_path.symlink_to(target, target_is_directory=target.is_dir())


def _symlink_relative(link_path: Path, target: Path) -> None:
    rel = os.path.relpath(target, link_path.parent)
    if link_path.is_symlink() or link_path.exists():
        link_path.unlink()
    link_path.symlink_to(rel)
