#!/usr/bin/env python3
"""
Codex end-task hook for code-review-with-logs.

Input:
    EndHookInput, assembled from CLI flags, optional hook JSON on stdin,
    environment, and .codex_record/<session_id>/hook_state.json.

Output:
    EndHookResult JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from code_review_with_logs import ReviewInput
    from code_review_with_logs import run as run_review
except ModuleNotFoundError:
    import importlib.util

    _RUNNER_PATH = Path(__file__).with_name("code_review_with_logs.py")
    _RUNNER_SPEC = importlib.util.spec_from_file_location("code_review_with_logs", _RUNNER_PATH)
    assert _RUNNER_SPEC is not None
    assert _RUNNER_SPEC.loader is not None
    _RUNNER_MODULE = importlib.util.module_from_spec(_RUNNER_SPEC)
    sys.modules["code_review_with_logs"] = _RUNNER_MODULE
    _RUNNER_SPEC.loader.exec_module(_RUNNER_MODULE)
    ReviewInput = _RUNNER_MODULE.ReviewInput
    run_review = _RUNNER_MODULE.run


@dataclass(frozen=True)
class EndHookInput:
    workspace: Path
    session_id: str
    review_id: str | None
    status_context: str
    objective: str | None
    permission_boundary: str | None
    task_completion_summary: str | None
    test_commands: list[str]
    changed_paths: list[str]
    log_paths: list[Path]
    skip_if_no_active_task: bool
    hard_block: bool
    stdin_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EndHookResult:
    status: str
    action: str
    review_id: str | None
    report_json: str | None
    summary: str | None
    rationale: str

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "review_id": self.review_id,
            "report_json": self.report_json,
            "summary": self.summary,
            "rationale": self.rationale,
        }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    stdin_payload = _read_stdin_json()
    workspace = _resolve_workspace(Path(args.workspace))
    session_id = args.session_id or os.environ.get("CODEX_THREAD_ID") or "main"
    state = _read_state(workspace, session_id)
    hook_input = EndHookInput(
        workspace=workspace,
        session_id=session_id,
        review_id=args.review_id,
        status_context=args.status_context,
        objective=(
            args.objective
            or os.environ.get("CODEX_TASK_OBJECTIVE")
            or state.get("objective")
        ),
        permission_boundary=args.permission_boundary or os.environ.get("CODEX_PERMISSION_BOUNDARY"),
        task_completion_summary=_resolve_task_completion_summary(
            workspace,
            inline=(
                args.task_completion_summary
                or os.environ.get("CODEX_TASK_COMPLETION_SUMMARY")
                or _completion_summary_from_payload(stdin_payload)
                or _string_or_none(state.get("task_completion_summary"))
            ),
            path=args.task_completion_summary_file
            or os.environ.get("CODEX_TASK_COMPLETION_SUMMARY_PATH"),
        ),
        test_commands=_merge_strings(
            args.test_command,
            _split_env("CODEX_REVIEW_TEST_COMMANDS"),
            state.get("test_commands"),
            _discover_test_commands(workspace, session_id),
        ),
        changed_paths=_merge_strings(
            args.changed_path,
            _split_env("CODEX_CHANGED_PATHS"),
            state.get("changed_paths") or state.get("task_owned_paths"),
            _discover_changed_paths(workspace, session_id),
        ),
        log_paths=[
            Path(path)
            for path in _merge_strings(
                [str(path) for path in args.log_path],
                _split_env("CODEX_REVIEW_LOG_PATHS"),
                state.get("log_paths"),
            )
        ],
        skip_if_no_active_task=not args.no_skip_if_no_active_task,
        hard_block=not args.soft_fail,
        stdin_payload=stdin_payload,
    )

    try:
        result = run(hook_input)
    except Exception as exc:  # pragma: no cover - defensive CLI hard block
        result = EndHookResult(
            status="BLOCKED",
            action="blocked_exception",
            review_id=None,
            report_json=None,
            summary=None,
            rationale=str(exc),
        )
    print(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
    if hook_input.hard_block and result.status in {"FAIL", "BLOCKED"}:
        return 1
    return 0


def run(hook_input: EndHookInput) -> EndHookResult:
    state = _read_state(hook_input.workspace, hook_input.session_id)
    if hook_input.skip_if_no_active_task and not state.get("review_required"):
        return EndHookResult(
            status="PASS",
            action="skip_no_active_task",
            review_id=None,
            report_json=None,
            summary=None,
            rationale="No active tracked task exists for this session.",
        )

    changed_paths = hook_input.changed_paths or _collect_git_changed_paths(hook_input.workspace)
    review_id = hook_input.review_id or _default_review_id(hook_input.session_id)
    output = run_review(
        ReviewInput(
            workspace=hook_input.workspace,
            session_id=hook_input.session_id,
            review_id=review_id,
            test_commands=hook_input.test_commands,
            log_paths=hook_input.log_paths,
            changed_paths=changed_paths,
            status_context=hook_input.status_context,
            objective=hook_input.objective,
            permission_boundary=hook_input.permission_boundary,
            task_completion_summary=hook_input.task_completion_summary,
        )
    )
    _update_state_after_review(
        hook_input.workspace, hook_input.session_id, output.status, output.review_id
    )
    return EndHookResult(
        status=output.status,
        action="ran_code_review_with_logs",
        review_id=output.review_id,
        report_json=_relativize(output.report_json_path, hook_input.workspace),
        summary=_relativize(output.summary_path, hook_input.workspace),
        rationale="code-review-with-logs completed with status " + output.status,
    )


def _collect_git_changed_paths(workspace: Path) -> list[str]:
    paths: list[str] = []
    commands = [
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    for command in commands:
        proc = subprocess.run(
            command,
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            continue
        paths.extend(line.strip() for line in proc.stdout.splitlines() if line.strip())
    return list(dict.fromkeys(paths))


def _read_state(workspace: Path, session_id: str) -> dict[str, Any]:
    path = workspace / ".codex_record" / session_id / "hook_state.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_task_completion_summary(
    workspace: Path,
    *,
    inline: str | None,
    path: str | None,
) -> str | None:
    for candidate in (inline, _read_summary_file(workspace, path)):
        cleaned = _clean_task_completion_summary(candidate)
        if cleaned:
            return cleaned
    return None


def _completion_summary_from_payload(payload: dict[str, Any]) -> str | None:
    for key in (
        "task_completion_summary",
        "final_response",
        "assistant_final_message",
        "last_assistant_message",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _read_summary_file(workspace: Path, path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    try:
        return candidate.read_text(encoding="utf-8")
    except OSError:
        return None


def _clean_task_completion_summary(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _redact_secret_text(value).strip()
    return cleaned or None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _redact_secret_text(text: str) -> str:
    redacted = re.sub(
        r"(?i)(api[_-]?key|authorization|bearer|token|secret)(\s*[=:]\s*)[^\s,;]+",
        r"\1\2[REDACTED]",
        text,
    )
    redacted = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", redacted)
    return redacted


def _update_state_after_review(
    workspace: Path, session_id: str, status: str, review_id: str
) -> None:
    state_path = workspace / ".codex_record" / session_id / "hook_state.json"
    state = _read_state(workspace, session_id)
    state.update(
        {
            "last_review_status": status,
            "last_review_id": review_id,
            "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "review_required": status != "PASS",
        }
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_review_id(session_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_session = "".join(char if char.isalnum() or char in "-_" else "-" for char in session_id)
    return f"{stamp}-{safe_session}-hook-closeout"


def _merge_strings(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = [str(item) for item in value if str(item).strip()]
        else:
            continue
        for item in items:
            stripped = item.strip()
            if stripped and stripped not in merged:
                merged.append(stripped)
    return merged


def _split_env(name: str) -> list[str]:
    value = os.environ.get(name)
    if not value:
        return []
    stripped = value.strip()
    if stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            return [str(item) for item in payload if str(item).strip()]
    return [part.strip() for part in stripped.replace("\n", ";").split(";") if part.strip()]


def _discover_test_commands(workspace: Path, session_id: str) -> list[str]:
    text = _read_record_text(workspace, session_id)
    commands: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if not any(token in lowered for token in ["pytest", "ruff", "mypy", "py_compile"]):
            continue
        commands.extend(_extract_backtick_commands(line))
    return commands


def _discover_changed_paths(workspace: Path, session_id: str) -> list[str]:
    text = _read_record_text(workspace, session_id)
    paths: list[str] = []
    for line in text.splitlines():
        stripped = line.strip().strip("-").strip()
        if not stripped or "*" in stripped:
            continue
        if stripped.startswith(
            ("AGENTS.md", ".codex/", ".codex_record/", "tests/", "src/", "scripts/")
        ):
            paths.append(stripped.strip("`"))
        paths.extend(
            item
            for item in _extract_backtick_commands(line)
            if item.startswith(
                ("AGENTS.md", ".codex/", ".codex_record/", "tests/", "src/", "scripts/")
            )
        )
    return list(dict.fromkeys(paths))


def _read_record_text(workspace: Path, session_id: str) -> str:
    record_dir = workspace / ".codex_record" / session_id
    parts: list[str] = []
    for name in ["task_plan.md", "progress.md", "findings.md"]:
        path = record_dir / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def _extract_backtick_commands(line: str) -> list[str]:
    return [match.strip() for match in re.findall(r"`([^`]+)`", line) if match.strip()]


def _read_stdin_json() -> dict[str, Any]:
    if sys.stdin is None or sys.stdin.closed or sys.stdin.isatty():
        return {}
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_stdin": raw}
    return payload if isinstance(payload, dict) else {"value": payload}


def _resolve_workspace(path: Path) -> Path:
    if path != Path("."):
        return path.resolve()
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return path.resolve()


def _relativize(path: Path, workspace: Path) -> str:
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Codex end-task review hook.")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--review-id", default=None)
    parser.add_argument(
        "--status-context",
        choices=["completed", "runtime_issue", "test_failure"],
        default="completed",
    )
    parser.add_argument("--objective", default=None)
    parser.add_argument("--permission-boundary", default=None)
    parser.add_argument("--task-completion-summary", default=None)
    parser.add_argument("--task-completion-summary-file", default=None)
    parser.add_argument("--test-command", action="append", default=[])
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--log-path", action="append", default=[])
    parser.add_argument("--no-skip-if-no-active-task", action="store_true")
    parser.add_argument("--soft-fail", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
