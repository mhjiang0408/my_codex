#!/usr/bin/env python3
"""
Codex start-task hook for Linear registration.

Input:
    HookInput, assembled from CLI flags, optional hook JSON on stdin, environment,
    and the latest Codex session log when available.

Output:
    HookResult JSON on stdout.

Side effects:
    - Initialize .codex_record/<session_id>/ files.
    - Append progress/findings records.
    - Create or reuse one Linear issue unless --dry-run or --skip-linear is set.
    - Write .codex_record/<session_id>/hook_state.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PROJECT = "3a33cd7c7d0d"
DEFAULT_TEAM = "COD"
SKIP_REASON_NO_OBJECTIVE = "skip:no-objective"
STATE_FILE = "hook_state.json"


@dataclass(frozen=True)
class HookInput:
    workspace: Path
    session_id: str
    objective: str
    issue_title: str | None
    task_date: str
    team: str
    project: str
    due_date: str
    force: bool
    dry_run: bool
    skip_linear: bool
    fail_on_linear_error: bool
    stdin_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HookResult:
    status: str
    should_track: bool
    session_id: str
    issue_id: str | None
    chosen_action: str
    rationale: str
    task_date: str
    issue_title_candidate: str
    query_command: str | None
    exact_match_result: str
    record_dir: str

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "should_track": self.should_track,
            "session_id": self.session_id,
            "issue_id": self.issue_id,
            "chosen_action": self.chosen_action,
            "rationale": self.rationale,
            "task_date": self.task_date,
            "issue_title_candidate": self.issue_title_candidate,
            "query_command": self.query_command,
            "exact_match_result": self.exact_match_result,
            "record_dir": self.record_dir,
        }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    stdin_payload = _read_stdin_json()
    workspace = _resolve_workspace(Path(args.workspace))
    session_id = args.session_id or os.environ.get("CODEX_THREAD_ID") or "main"
    objective = _first_nonempty(
        args.objective,
        os.environ.get("CODEX_TASK_OBJECTIVE"),
        _objective_from_payload(stdin_payload),
        _latest_user_message(workspace, session_id),
    )
    task_date = args.task_date or date.today().isoformat()
    hook_input = HookInput(
        workspace=workspace,
        session_id=session_id,
        objective=objective,
        issue_title=args.issue_title,
        task_date=task_date,
        team=args.team,
        project=args.project,
        due_date=args.due_date or task_date,
        force=args.force,
        dry_run=args.dry_run,
        skip_linear=args.skip_linear,
        fail_on_linear_error=not args.soft_fail,
        stdin_payload=stdin_payload,
    )

    try:
        result = run(hook_input)
    except Exception as exc:  # pragma: no cover - defensive CLI hard block
        error = {
            "status": "BLOCKED",
            "error": str(exc),
            "session_id": session_id,
            "should_track": True,
        }
        print(json.dumps(error, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
    if result.status == "BLOCKED" and hook_input.fail_on_linear_error:
        return 1
    return 0


def run(hook_input: HookInput) -> HookResult:
    workspace = hook_input.workspace.resolve()
    record_dir = workspace / ".codex_record" / hook_input.session_id
    record_dir.mkdir(parents=True, exist_ok=True)
    _ensure_record_files(record_dir)

    title = hook_input.issue_title or _derive_chinese_title(hook_input.objective)
    should_track, rationale = should_track_task(
        hook_input.objective,
        hook_input.stdin_payload,
        force=hook_input.force,
    )

    existing_state = _read_state(record_dir)
    if _should_reuse_active_state(existing_state, hook_input.objective):
        result = HookResult(
            status="PASS",
            should_track=True,
            session_id=hook_input.session_id,
            issue_id=str(existing_state["issue_id"]),
            chosen_action="reuse_active_session",
            rationale="Active hook_state already contains a tracked Linear issue.",
            task_date=hook_input.task_date,
            issue_title_candidate=str(existing_state.get("issue_title_candidate") or title),
            query_command=str(existing_state.get("query_command") or ""),
            exact_match_result=str(existing_state.get("exact_match_result") or "active_state"),
            record_dir=_relativize(record_dir, workspace),
        )
        return result

    if not should_track:
        result = HookResult(
            status="PASS",
            should_track=False,
            session_id=hook_input.session_id,
            issue_id=None,
            chosen_action="skip",
            rationale=rationale,
            task_date=hook_input.task_date,
            issue_title_candidate=title,
            query_command=None,
            exact_match_result="not_required",
            record_dir=_relativize(record_dir, workspace),
        )
        _write_state(record_dir, result, hook_input.objective)
        _append_progress(record_dir, _format_result_note(result, hook_input.objective))
        return result

    _write_task_plan(record_dir, hook_input, title)
    query_command = (
        f'linear issue query --team {hook_input.team} --search "{title}" '
        f"--project {hook_input.project} --json"
    )

    if hook_input.dry_run or hook_input.skip_linear:
        issue_id = "DRY-RUN" if hook_input.dry_run else None
        status = "PASS" if issue_id else "BLOCKED"
        action = "dry_run_create_main_issue" if hook_input.dry_run else "blocked_skip_linear"
        result = HookResult(
            status=status,
            should_track=True,
            session_id=hook_input.session_id,
            issue_id=issue_id,
            chosen_action=action,
            rationale="Linear mutation skipped by explicit flag.",
            task_date=hook_input.task_date,
            issue_title_candidate=title,
            query_command=query_command,
            exact_match_result="not_queried",
            record_dir=_relativize(record_dir, workspace),
        )
        _write_state(record_dir, result, hook_input.objective)
        _append_progress(record_dir, _format_result_note(result, hook_input.objective))
        return result

    linear_result = _register_linear_issue(hook_input, title)
    result = HookResult(
        status=linear_result["status"],
        should_track=True,
        session_id=hook_input.session_id,
        issue_id=linear_result.get("issue_id"),
        chosen_action=linear_result["chosen_action"],
        rationale=linear_result["rationale"],
        task_date=hook_input.task_date,
        issue_title_candidate=title,
        query_command=query_command,
        exact_match_result=linear_result["exact_match_result"],
        record_dir=_relativize(record_dir, workspace),
    )
    _write_state(record_dir, result, hook_input.objective)
    _append_progress(record_dir, _format_result_note(result, hook_input.objective))
    _append_findings(record_dir, _format_finding_note(result))
    if result.issue_id and result.status == "PASS":
        _mirror_plan_to_linear(result.issue_id, record_dir, hook_input)
    return result


def should_track_task(
    objective: str, payload: dict[str, Any] | None = None, *, force: bool = False
) -> tuple[bool, str]:
    if force:
        return True, "force flag set"

    tool_input = (payload or {}).get("tool_input")
    text = " ".join(
        part
        for part in [
            objective,
            str((payload or {}).get("tool_name") or ""),
            json.dumps(tool_input, ensure_ascii=False) if tool_input else "",
        ]
        if part
    ).strip()
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    if not normalized:
        return False, SKIP_REASON_NO_OBJECTIVE

    casual_patterns = [
        r"^(hi|hello|hey|thanks|thank you|谢谢|你好|您好)[!.。！\s]*$",
        r"^(date|time|pwd|whoami)\s*$",
        r"(现在几点|今天几号|当前时间)",
    ]
    if any(re.search(pattern, normalized) for pattern in casual_patterns):
        return False, "skip:casual-or-one-shot"

    tracked_keywords = [
        "implement",
        "fix",
        "add",
        "update",
        "rewrite",
        "remove",
        "refactor",
        "review",
        "report",
        "hook",
        "linear",
        "codex_record",
        "code-review-with-logs",
        "test",
        "pytest",
        "skill",
        "agent",
        "实现",
        "修复",
        "新增",
        "更新",
        "重做",
        "去掉",
        "移除",
        "审查",
        "报告",
        "钩子",
        "任务",
        "测试",
    ]
    if any(keyword in normalized for keyword in tracked_keywords):
        return True, "tracked keyword matched"

    if len(normalized.split()) >= 8 or len(normalized) >= 24:
        return True, "non-trivial objective length"

    return False, "skip:non-tracked-short-request"


def _should_reuse_active_state(existing_state: dict[str, Any], objective: str) -> bool:
    if existing_state.get("should_track") is not True:
        return False
    if not existing_state.get("issue_id"):
        return False
    if existing_state.get("review_required") is not True:
        return False
    return True


def _register_linear_issue(hook_input: HookInput, title: str) -> dict[str, Any]:
    query_args = [
        "linear",
        "issue",
        "query",
        "--team",
        hook_input.team,
        "--search",
        title,
        "--project",
        hook_input.project,
        "--json",
    ]
    query = subprocess.run(
        query_args,
        cwd=hook_input.workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    if query.returncode != 0:
        return {
            "status": "BLOCKED",
            "issue_id": None,
            "chosen_action": "blocked_query_failed",
            "rationale": _clip(query.stderr.strip() or query.stdout.strip()),
            "exact_match_result": "query_failed",
        }

    exact = _find_exact_issue(query.stdout, title, hook_input.task_date)
    if exact is not None:
        issue_id = str(exact.get("identifier") or exact.get("id"))
        if _is_done_issue(exact):
            reopen = _reopen_issue(hook_input, issue_id)
            if reopen.returncode != 0:
                return {
                    "status": "BLOCKED",
                    "issue_id": issue_id,
                    "chosen_action": "blocked_reopen_failed",
                    "rationale": _clip(reopen.stderr.strip() or reopen.stdout.strip()),
                    "exact_match_result": issue_id,
                }
            _add_reopen_comment(hook_input, issue_id)
            return {
                "status": "PASS",
                "issue_id": issue_id,
                "chosen_action": "reopen_exact_issue",
                "rationale": (
                    "Found exact-title completed issue within the age gate and reopened it."
                ),
                "exact_match_result": issue_id,
            }
        return {
            "status": "PASS",
            "issue_id": issue_id,
            "chosen_action": "reuse_exact_issue",
            "rationale": "Found exact-title issue that is not blocked by the two-day age gate.",
            "exact_match_result": issue_id,
        }

    description = _build_linear_description(hook_input)
    create = subprocess.run(
        [
            "linear",
            "issue",
            "create",
            "--team",
            hook_input.team,
            "--project",
            hook_input.project,
            "--due-date",
            hook_input.due_date,
            "--state",
            "In Progress",
            "--title",
            title,
            "--description",
            description,
            "--no-interactive",
        ],
        cwd=hook_input.workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    if create.returncode != 0:
        return {
            "status": "BLOCKED",
            "issue_id": None,
            "chosen_action": "blocked_create_failed",
            "rationale": _clip(create.stderr.strip() or create.stdout.strip()),
            "exact_match_result": "none",
        }
    issue_id = _extract_issue_identifier(create.stdout)
    return {
        "status": "PASS" if issue_id else "BLOCKED",
        "issue_id": issue_id,
        "chosen_action": "create_new_main_issue" if issue_id else "blocked_parse_create_output",
        "rationale": "No exact current issue existed; created a new main issue."
        if issue_id
        else _clip(create.stdout),
        "exact_match_result": "none",
    }


def _find_exact_issue(raw_json: str, title: str, task_date: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if not isinstance(nodes, list):
        return None
    task_day = date.fromisoformat(task_date)
    for node in nodes:
        if not isinstance(node, dict) or node.get("title") != title:
            continue
        created_raw = str(node.get("createdAt") or "")[:10]
        try:
            created_day = date.fromisoformat(created_raw)
        except ValueError:
            continue
        if (task_day - created_day).days >= 2:
            continue
        return node
    return None


def _is_done_issue(issue: dict[str, Any]) -> bool:
    state = issue.get("state")
    if not isinstance(state, dict):
        return False
    return str(state.get("type") or "").lower() == "completed" or str(
        state.get("name") or ""
    ).lower() == "done"


def _reopen_issue(hook_input: HookInput, issue_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["linear", "issue", "update", issue_id, "--state", "In Progress"],
        cwd=hook_input.workspace,
        text=True,
        capture_output=True,
        check=False,
    )


def _add_reopen_comment(hook_input: HookInput, issue_id: str) -> None:
    body = "\n".join(
        [
            "Start-task hook reopened this issue for a same-task continuation.",
            "",
            f"- task_date: {hook_input.task_date}",
            f"- session_id: {hook_input.session_id}",
        ]
    )
    subprocess.run(
        ["linear", "issue", "comment", "add", issue_id, "--body", body],
        cwd=hook_input.workspace,
        text=True,
        capture_output=True,
        check=False,
    )


def _mirror_plan_to_linear(issue_id: str, record_dir: Path, hook_input: HookInput) -> None:
    task_plan = record_dir / "task_plan.md"
    if not task_plan.is_file():
        return
    description = task_plan.read_text(encoding="utf-8", errors="replace")
    subprocess.run(
        ["linear", "issue", "update", issue_id, "--description", description],
        cwd=hook_input.workspace,
        text=True,
        capture_output=True,
        check=False,
    )


def _ensure_record_files(record_dir: Path) -> None:
    defaults = {
        "task_plan.md": "# Task Plan\n\n## Hook Managed Task\n- Status: In Progress\n",
        "progress.md": "# Progress\n",
        "findings.md": "# Findings\n",
    }
    for name, content in defaults.items():
        path = record_dir / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def _write_state(record_dir: Path, result: HookResult, objective: str) -> None:
    state = result.to_json()
    state.update(
        {
            "objective": objective,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "review_required": result.should_track,
            "hook_failure_policy": "hard-blocking",
        }
    )
    (record_dir / STATE_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_state(record_dir: Path) -> dict[str, Any]:
    path = record_dir / STATE_FILE
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_progress(record_dir: Path, note: str) -> None:
    with (record_dir / "progress.md").open("a", encoding="utf-8") as handle:
        handle.write("\n" + note.rstrip() + "\n")


def _append_findings(record_dir: Path, note: str) -> None:
    with (record_dir / "findings.md").open("a", encoding="utf-8") as handle:
        handle.write("\n" + note.rstrip() + "\n")


def _format_result_note(result: HookResult, objective: str) -> str:
    return "\n".join(
        [
            f"## Start-Task Hook {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"- status: {result.status}",
            f"- should_track: {result.should_track}",
            f"- objective: {objective or '(not provided)'}",
            f"- chosen_action: {result.chosen_action}",
            f"- issue: {result.issue_id or '(none)'}",
            f"- rationale: {result.rationale}",
        ]
    )


def _format_finding_note(result: HookResult) -> str:
    return "\n".join(
        [
            "## Start-Task Hook Linear Decision",
            f"- task_date: {result.task_date}",
            f"- issue_title_candidate: {result.issue_title_candidate}",
            f"- chosen_action: {result.chosen_action}",
            f"- chosen_issue_id: {result.issue_id or '(none)'}",
            f"- exact_match_result: {result.exact_match_result}",
        ]
    )


def _build_linear_description(hook_input: HookInput) -> str:
    return "\n".join(
        [
            "## Hook-managed task",
            "",
            f"- task_date: {hook_input.task_date}",
            f"- session_id: {hook_input.session_id}",
            f"- objective: {hook_input.objective or '(not provided)'}",
            "- failure_policy: hard-blocking",
            "",
            "This issue was created by the Codex start-task Linear hook.",
        ]
    )


def _write_task_plan(record_dir: Path, hook_input: HookInput, title: str) -> None:
    path = record_dir / "task_plan.md"
    header = path.read_text(encoding="utf-8", errors="replace").rstrip()
    section = "\n".join(
        [
            "",
            "## Start-Task Hook",
            f"- task_date: {hook_input.task_date}",
            f"- session_id: {hook_input.session_id}",
            f"- issue_title_candidate: {title}",
            f"- objective: {hook_input.objective or '(not provided)'}",
            "- failure_policy: "
            f"{'hard-blocking' if hook_input.fail_on_linear_error else 'soft-fail'}",
            "- next_step: implement the requested task, then rely on the end-task review hook.",
        ]
    )
    path.write_text(header + section + "\n", encoding="utf-8")


def _derive_chinese_title(objective: str) -> str:
    text = objective.strip()
    if not text:
        return "记录新的自动化任务"
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        title = re.sub(r"\s+", " ", text)
        return _clip(title, limit=42).rstrip(".。")
    lowered = text.lower()
    if "hook" in lowered and "review" in lowered:
        return "将任务追踪与代码审查改为自动钩子"
    if "linear" in lowered:
        return "完善线性任务自动追踪流程"
    if "review" in lowered:
        return "完善代码审查自动收口流程"
    return "记录新的自动化任务"


def _latest_user_message(workspace: Path, session_id: str) -> str:
    session_files = sorted(
        (workspace / ".codex" / "sessions").glob(f"**/*{session_id}*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in session_files[:3]:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = _extract_user_text(payload)
            if message:
                return message
    return ""


def _extract_user_text(payload: dict[str, Any]) -> str:
    item = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    if not isinstance(item, dict):
        return ""
    if item.get("type") == "message" and item.get("role") == "user":
        return _content_to_text(item.get("content"))
    nested = item.get("payload")
    if (
        isinstance(nested, dict)
        and nested.get("type") == "message"
        and nested.get("role") == "user"
    ):
        return _content_to_text(nested.get("content"))
    return ""


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    return ""


def _objective_from_payload(payload: dict[str, Any]) -> str:
    for key in ["objective", "prompt", "user_prompt", "user_message", "message"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


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


def _extract_issue_identifier(text: str) -> str | None:
    match = re.search(r"/issue/([A-Z]+-\d+)(?:/|\\b)", text)
    if match:
        return match.group(1)
    match = re.search(r"\b[A-Z]+-\d+\b", text)
    return match.group(0) if match else None


def _first_nonempty(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _relativize(path: Path, workspace: Path) -> str:
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _clip(value: str, *, limit: int = 1200) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Codex start-task Linear hook.")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--objective", default=None)
    parser.add_argument("--issue-title", default=None)
    parser.add_argument("--task-date", default=None)
    parser.add_argument("--due-date", default=None)
    parser.add_argument("--team", default=DEFAULT_TEAM)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-linear", action="store_true")
    parser.add_argument("--soft-fail", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
