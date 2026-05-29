#!/usr/bin/env python3
"""
Responsibility:
    Run the rebuilt code-review-with-logs workflow for one session.

Input:
    ReviewInput

Output:
    ReviewOutput

Allowed side effects:
    - Execute caller-provided test commands inside the workspace.
    - Read task records, idea records, logs, and git diff metadata.
    - Write review artifacts under .codex/reviews/<review_id>/.

Forbidden:
    - Do not modify product source files.
    - Do not run benchmark commands.
    - Do not require .codex/review_spec.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from review_session import resolve_session_paths, sanitize_review_id, write_latest_index
except ModuleNotFoundError:
    import importlib.util

    _SESSION_PATH = Path(__file__).with_name("review_session.py")
    _SESSION_SPEC = importlib.util.spec_from_file_location("review_session", _SESSION_PATH)
    assert _SESSION_SPEC is not None
    assert _SESSION_SPEC.loader is not None
    _SESSION_MODULE = importlib.util.module_from_spec(_SESSION_SPEC)
    _SESSION_SPEC.loader.exec_module(_SESSION_MODULE)
    resolve_session_paths = _SESSION_MODULE.resolve_session_paths
    sanitize_review_id = _SESSION_MODULE.sanitize_review_id
    write_latest_index = _SESSION_MODULE.write_latest_index


REPORT_FIELDS = [
    "Field",
    "Why it matters",
    "Objective",
    "Permission boundary",
    "Plan changes",
    "command trace",
    "Diff summary",
    "Tests and evals",
    "Cost and retries",
    "Rollback path",
    "reliable check",
]

VALID_STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}

CHECK_DISPLAY_NAMES = {
    "codex_record_presence": "会话记录完整性",
    "codex_idea_presence": "科研记录适用性",
    "command_and_plan_alignment": "命令与计划一致性",
    "command_parameter_consistency": "命令参数一致性",
    "experiment_runtime_evidence": "实验运行证据",
    "diff_evidence": "差异证据",
}

STATUS_TEXT_ZH = {
    "PASS": "通过",
    "FAIL": "失败",
    "BLOCKED": "阻塞",
    "NOT_APPLICABLE": "不适用",
}

CONTEXT_FILE_LABELS_ZH = {
    "task_plan": "任务计划",
    "progress": "进度记录",
    "findings": "发现记录",
    "idea_plan": "科研计划",
    "idea_progress": "科研进度",
    "idea_findings": "科研发现",
}

CONTEXT_FILE_STATUS_TEXT_ZH = {
    "present": "已读取",
    "missing_required": "缺少必需文件",
    "missing_optional": "缺少可选文件",
}

PARAMETER_REQUIREMENT_MARKERS = (
    "命令参数要求",
    "训练参数要求",
    "部署参数要求",
    "tau bench 参数要求",
    "tau2 参数要求",
    "benchmark 参数要求",
    "参数要求",
    "required command",
    "required parameters",
    "required params",
    "experiment command",
    "实验命令",
    "运行命令",
    "blocking command",
)

PATH_REQUIREMENT_MARKERS = (
    "预期修改路径",
    "期望修改路径",
    "owned paths",
    "changed paths",
    "修改模块",
    "修改路径",
    "expected paths",
)

CHANGE_METHOD_MARKERS = (
    "预期修改方式",
    "期望修改方式",
    "修改方式",
    "怎么修改",
    "怎么改",
    "implementation",
    "implementation plan",
    "change method",
    "expected change",
)

ALIGNMENT_STOP_TOKENS = {
    "019e3a15",
    "7aa0",
    "8b19",
    "bb8c",
    "cached",
    "check",
    "compile",
    "code",
    "codex",
    "creator",
    "git",
    "logs",
    "goal",
    "hook",
    "immediate",
    "current",
    "plan",
    "task",
    "python",
    "pytest",
    "quick",
    "record",
    "references",
    "review",
    "script",
    "scripts",
    "skill",
    "skills",
    "spec",
    "specs",
    "status",
    "state",
    "state.json",
    "summary",
    "system",
    "test",
    "tests",
    "unit",
    "validate",
    "validation",
    "with",
}

CJK_ALIGNMENT_TERMS = (
    "证据",
    "说明",
    "参数",
    "路径",
    "模块",
    "审计",
    "数据",
    "质量",
    "训练",
    "报告",
    "实验",
    "科研",
    "假设",
    "目标",
    "一致性",
    "通过",
    "失败",
)

IDEA_METADATA_LINE_MARKERS = (
    "reliable check status",
    "idea check",
    "code mapping check",
    "experiment check",
    "conclusion check",
)

RUNTIME_EVIDENCE_FILENAMES = {
    "events.jsonl",
    "artifacts.json",
    "state.json",
    "controller_state.json",
    "live_context_report.json",
    "live_preflight_report.json",
    "train_submit_payload.json",
    "deploy_submit_payload.json",
    "launch_manifest.json",
    "runtime_resolved_manifest.json",
    "tau2-command.json",
    "summary.json",
    "report.json",
    "results.txt",
}

RUNTIME_EVIDENCE_PATH_RE = re.compile(
    r"(?P<path>(?:[./~]|/|runs/|logs/|artifacts/|Agentic-Evaluation-infra/)[^\s`'\"，。；,]+(?:"
    + "|".join(re.escape(name) for name in sorted(RUNTIME_EVIDENCE_FILENAMES))
    + r"))"
)

QZ_TRAIN_PARAM_NAMES = {
    "--model-name",
    "--dataset-path",
    "--run-tag",
    "--save-suffix",
    "--num-rollout",
    "--num-epoch",
    "--rollout-batch-size",
    "--global-batch-size",
    "--save-interval",
    "--max-tokens-per-gpu",
    "--tensor-model-parallel-size",
    "--pipeline-model-parallel-size",
    "--context-parallel-size",
    "--expert-model-parallel-size",
    "--expert-tensor-parallel-size",
}

DEPLOY_PARAM_NAMES = {
    "--model",
    "--model-name",
    "--base-url",
    "--api-base",
    "--serving-endpoint",
    "--service-name",
    "--replicas",
    "--replica",
    "--instance-count",
    "--nodes",
    "--node-count",
}

TAU_PARAM_NAMES = {
    "--benchmark",
    "--model",
    "--agent-llm",
    "--agent-model",
    "--user-llm",
    "--user-model",
    "--domain",
    "--domains",
    "--run-id",
    "--tag",
    "--max-concurrency",
    "--num-trials",
}

RUNTIME_PARAM_NAMES = QZ_TRAIN_PARAM_NAMES | DEPLOY_PARAM_NAMES | TAU_PARAM_NAMES

PARAMETER_PLACEHOLDER_NAMES = {
    "--arg",
    "--args",
    "--example",
    "--examples",
    "--flag",
    "--foo",
    "--bar",
    "--baz",
    "--param",
    "--params",
    "--placeholder",
    "--sample",
    "--test",
    "--value",
    "--xxx",
}

PARAMETER_PLACEHOLDER_VALUES = {
    "arg",
    "args",
    "example",
    "examples",
    "foo",
    "bar",
    "baz",
    "placeholder",
    "sample",
    "test",
    "todo",
    "tbd",
    "value",
    "values",
    "xxx",
}

RUNTIME_FACT_KEYWORDS = (
    "api_base",
    "average_reward",
    "base_url",
    "benchmark",
    "blocked_pool_note",
    "candidate_job_ids",
    "candidate_status",
    "command_target_output",
    "completed_instances",
    "completed_simulations",
    "accepted",
    "config_path",
    "dataset",
    "dataset_path",
    "deployment_id",
    "deployment_pool",
    "deployment_status_after_cleanup",
    "domain",
    "domains",
    "endpoint",
    "error_ids",
    "error_instances",
    "error_summary",
    "global_batch_size",
    "gpu_count",
    "judge_status",
    "job_id",
    "max_concurrency",
    "metric",
    "metrics",
    "model",
    "model_name",
    "node_count",
    "num_trials",
    "output_target_exists",
    "parquet_path",
    "pass_k",
    "pool",
    "preflight_ready",
    "problem_count",
    "project_id",
    "ready",
    "replica",
    "replicas",
    "resolved_instances",
    "resource_stopped",
    "rollout_batch_size",
    "run_id",
    "run_root",
    "run_tag",
    "service",
    "service_name",
    "simulation_json",
    "skipped_reason",
    "scheduler",
    "status",
    "stopped_due_to_timeouts",
    "submitted_instances",
    "summary_status",
    "tag",
    "task_count",
    "timeout_count",
    "timeout_limit",
    "total_instances",
    "total_simulations",
    "train_output_tag",
    "user_llm",
    "user_model",
    "worker_status",
)

RUNTIME_SECRET_KEYWORDS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "secret",
    "token",
)


@dataclass(frozen=True)
class ReviewInput:
    workspace: Path
    session_id: str
    review_id: str | None
    test_commands: list[str]
    log_paths: list[Path]
    changed_paths: list[str]
    status_context: str
    objective: str | None
    permission_boundary: str | None
    task_completion_summary: str | None = None


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    started_at: str
    ended_at: str


@dataclass(frozen=True)
class ContextFile:
    label: str
    path: str
    status: str
    excerpt: str

    def to_reliable_check_json(self) -> dict[str, str]:
        payload = self.__dict__.copy()
        payload["label_zh"] = CONTEXT_FILE_LABELS_ZH.get(self.label, self.label)
        payload["status_text"] = CONTEXT_FILE_STATUS_TEXT_ZH.get(self.status, self.status)
        return payload


@dataclass(frozen=True)
class RuntimeEvidence:
    label: str
    path: str
    status: str
    excerpt: str
    commands: list[str]
    parameters: dict[str, list[str]]
    facts: dict[str, Any]

    def to_reliable_check_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "label_zh": _runtime_evidence_label_zh(self.label),
            "path": self.path,
            "status": self.status,
            "status_text": CONTEXT_FILE_STATUS_TEXT_ZH.get(self.status, self.status),
            "excerpt": self.excerpt,
            "commands": self.commands,
            "parameters": self.parameters,
            "facts": self.facts,
        }


@dataclass(frozen=True)
class ReviewOutput:
    review_id: str
    session_dir: Path
    status: str
    report: dict[str, Any]
    unit_test_results: dict[str, Any]
    reliability_results: dict[str, Any]
    summary_path: Path
    report_json_path: Path


@dataclass
class ReviewBuildState:
    input_data: ReviewInput
    review_id: str
    session_dir: Path
    paths: dict[str, Path | str]
    command_trace: list[str] = field(default_factory=list)
    context_files: list[ContextFile] = field(default_factory=list)
    log_summaries: list[dict[str, Any]] = field(default_factory=list)
    runtime_evidence: list[RuntimeEvidence] = field(default_factory=list)
    diff_summary: dict[str, Any] = field(default_factory=dict)
    unit_test_results: dict[str, Any] = field(default_factory=dict)
    reliability_results: dict[str, Any] = field(default_factory=dict)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(input_data: ReviewInput) -> ReviewOutput:
    workspace = input_data.workspace.resolve()
    review_id = sanitize_review_id(
        input_data.review_id or _generate_review_id(input_data.session_id)
    )
    paths = resolve_session_paths(workspace, review_id=review_id)
    session_dir = Path(paths["session_dir"])
    session_dir.mkdir(parents=True, exist_ok=True)

    state = ReviewBuildState(
        input_data=input_data,
        review_id=review_id,
        session_dir=session_dir,
        paths=paths,
    )
    _write_session_metadata(state)
    _record_run_log_header(state)
    state.unit_test_results = _run_unit_tests(state)
    state.context_files = _read_session_context(state)
    state.log_summaries = _read_logs(state)
    state.runtime_evidence = _read_runtime_evidence(state)
    state.diff_summary = _collect_diff_summary(state)
    state.reliability_results = _build_reliability_results(state)
    report = _build_report(state)
    status = str(report["status"])

    summary_path = Path(paths["summary"])
    report_json_path = Path(paths["report_json"])
    unit_test_path = Path(paths["unit_test_results_json"])
    reliability_path = Path(paths["context_reliability_json"])

    markdown_report = _render_markdown_report(
        report,
        task_completion_summary=state.input_data.task_completion_summary,
    )
    summary_path.write_text(markdown_report, encoding="utf-8")
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    unit_test_path.write_text(
        json.dumps(state.unit_test_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    reliability_path.write_text(
        json.dumps(state.reliability_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _append_report_to_progress(state, markdown_report)
    write_latest_index(
        workspace,
        {
            "review_id": review_id,
            "session_dir": session_dir.relative_to(workspace).as_posix()
            if session_dir.is_relative_to(workspace)
            else session_dir.as_posix(),
            "status": status,
            "updated_at": utc_now(),
            "summary": summary_path.as_posix(),
            "report_json": report_json_path.as_posix(),
        },
    )
    _append_run_log(
        state,
        [
            f"[INFO] final_status={status}",
            f"[INFO] summary={summary_path}",
            f"[INFO] review_report={report_json_path}",
        ],
    )
    return ReviewOutput(
        review_id=review_id,
        session_dir=session_dir,
        status=status,
        report=report,
        unit_test_results=state.unit_test_results,
        reliability_results=state.reliability_results,
        summary_path=summary_path,
        report_json_path=report_json_path,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    review_input = ReviewInput(
        workspace=Path(args.workspace),
        session_id=args.session_id or os.environ.get("CODEX_THREAD_ID") or "main",
        review_id=args.review_id,
        test_commands=args.test_command or [],
        log_paths=[Path(path) for path in (args.log_path or [])],
        changed_paths=args.changed_path or [],
        status_context=args.status_context,
        objective=args.objective,
        permission_boundary=args.permission_boundary,
        task_completion_summary=_resolve_task_completion_summary(
            workspace=Path(args.workspace),
            inline=args.task_completion_summary,
            path=args.task_completion_summary_file,
        ),
    )
    output = run(review_input)
    print(output.report_json_path)
    return 0 if output.status == "PASS" else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run code-review-with-logs two-module closeout review."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root.")
    parser.add_argument(
        "--session-id", default=None, help="Session/thread id used for codex_record and codex_idea."
    )
    parser.add_argument("--review-id", default=None, help="Review id under .codex/reviews/.")
    parser.add_argument(
        "--test-command",
        action="append",
        default=[],
        help="Task-scoped unit-test command. Repeatable.",
    )
    parser.add_argument(
        "--log-path", action="append", default=[], help="Runtime log path to summarize. Repeatable."
    )
    parser.add_argument(
        "--changed-path", action="append", default=[], help="Task-owned changed path. Repeatable."
    )
    parser.add_argument(
        "--status-context",
        choices=["completed", "runtime_issue", "test_failure"],
        default="completed",
        help="Why this review is running.",
    )
    parser.add_argument("--objective", default=None, help="One-sentence task objective.")
    parser.add_argument(
        "--permission-boundary", default=None, help="Files/commands/tools allowed or blocked."
    )
    parser.add_argument(
        "--task-completion-summary",
        default=None,
        help="Final CLI-facing task completion summary to render in review_summary.md.",
    )
    parser.add_argument(
        "--task-completion-summary-file",
        default=None,
        help="Path to a file containing the final CLI-facing task completion summary.",
    )
    return parser.parse_args(argv)


def _resolve_task_completion_summary(
    *,
    workspace: Path,
    inline: str | None = None,
    path: str | None = None,
) -> str | None:
    candidates: list[str | None] = [
        inline,
        _read_summary_file(workspace, path),
        os.environ.get("CODEX_TASK_COMPLETION_SUMMARY"),
        _read_summary_file(workspace, os.environ.get("CODEX_TASK_COMPLETION_SUMMARY_PATH")),
    ]
    for candidate in candidates:
        cleaned = _clean_task_completion_summary(candidate)
        if cleaned:
            return cleaned
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


def _generate_review_id(session_id: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{sanitize_review_id(session_id)}"


def _write_session_metadata(state: ReviewBuildState) -> None:
    metadata_path = Path(state.paths["session_metadata"])
    metadata = {
        "review_id": state.review_id,
        "session_id": state.input_data.session_id,
        "status_context": state.input_data.status_context,
        "workspace": state.input_data.workspace.resolve().as_posix(),
        "created_at": utc_now(),
        "workflow": "unit_tests_then_context_report",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_run_log_header(state: ReviewBuildState) -> None:
    lines = [
        f"[INFO] started_at={utc_now()}",
        "[INFO] workflow=unit_tests_then_context_report",
        f"[INFO] workspace={state.input_data.workspace.resolve()}",
        f"[INFO] review_id={state.review_id}",
        f"[INFO] session_id={state.input_data.session_id}",
        f"[INFO] status_context={state.input_data.status_context}",
    ]
    _append_run_log(state, lines, mode="w")


def _append_run_log(state: ReviewBuildState, lines: list[str], *, mode: str = "a") -> None:
    run_log = Path(state.paths["run_log"])
    run_log.parent.mkdir(parents=True, exist_ok=True)
    with run_log.open(mode, encoding="utf-8") as handle:
        for line in lines:
            handle.write(f"{line}\n")


def _append_report_to_progress(state: ReviewBuildState, markdown_report: str) -> None:
    progress_path = (
        state.input_data.workspace.resolve()
        / ".codex_record"
        / state.input_data.session_id
        / "progress.md"
    )
    if not progress_path.is_file():
        _append_run_log(
            state,
            [
                "[WARN] progress_report_append=skipped",
                f"[WARN] missing_progress_path={progress_path}",
            ],
        )
        return

    start_marker = f"<!-- code-review-with-logs:{state.review_id}:start -->"
    end_marker = f"<!-- code-review-with-logs:{state.review_id}:end -->"
    block = "\n".join(["", "", start_marker, markdown_report.rstrip(), end_marker, ""])
    existing = progress_path.read_text(encoding="utf-8")
    if start_marker in existing and end_marker in existing:
        pattern = re.compile(
            re.escape(start_marker) + r".*?" + re.escape(end_marker),
            flags=re.DOTALL,
        )
        updated = pattern.sub(block.strip(), existing, count=1)
        progress_path.write_text(updated, encoding="utf-8")
        _append_run_log(
            state,
            [
                "[INFO] progress_report_append=replaced",
                f"[INFO] progress_report_path={progress_path}",
            ],
        )
        return
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write(block)
    _append_run_log(
        state,
        [
            "[INFO] progress_report_append=written",
            f"[INFO] progress_report_path={progress_path}",
        ],
    )


def _run_unit_tests(state: ReviewBuildState) -> dict[str, Any]:
    commands = list(state.input_data.test_commands)
    results: list[dict[str, Any]] = []
    if not commands:
        payload = {
            "status": "BLOCKED",
            "details": (
                "No unit-test commands were provided. Module 1 cannot prove task acceptance."
            ),
            "command_count": 0,
            "results": [],
        }
        _append_run_log(state, ["[UNIT_TEST] BLOCKED: no commands provided"])
        return payload

    for command in commands:
        state.command_trace.append(command)
        result = _run_shell_command(state.input_data.workspace, command)
        results.append(_command_result_to_json(result))
        _append_run_log(
            state,
            [
                f"[UNIT_TEST] COMMAND: {command}",
                f"[UNIT_TEST] EXIT_CODE: {result.exit_code}",
            ],
        )

    failed = [result for result in results if int(result["exit_code"]) != 0]
    return {
        "status": "FAIL" if failed else "PASS",
        "details": "One or more unit-test commands failed."
        if failed
        else "All unit-test commands passed.",
        "command_count": len(commands),
        "results": results,
    }


def _run_shell_command(workspace: Path, command: str) -> CommandResult:
    started_at = utc_now()
    proc = subprocess.run(
        command,
        cwd=workspace,
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    ended_at = utc_now()
    return CommandResult(
        command=command,
        exit_code=proc.returncode,
        stdout=_clip(proc.stdout),
        stderr=_clip(proc.stderr),
        started_at=started_at,
        ended_at=ended_at,
    )


def _command_result_to_json(result: CommandResult) -> dict[str, Any]:
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
    }


def _read_session_context(state: ReviewBuildState) -> list[ContextFile]:
    workspace = state.input_data.workspace.resolve()
    session_id = state.input_data.session_id
    candidates = [
        ("task_plan", workspace / ".codex_record" / session_id / "task_plan.md", "required"),
        ("progress", workspace / ".codex_record" / session_id / "progress.md", "required"),
        ("findings", workspace / ".codex_record" / session_id / "findings.md", "required"),
        ("idea_plan", workspace / ".codex_idea" / session_id / "idea_plan.md", "optional"),
        ("idea_progress", workspace / ".codex_idea" / session_id / "idea_progress.md", "optional"),
        ("idea_findings", workspace / ".codex_idea" / session_id / "idea_findings.md", "optional"),
    ]
    context_files: list[ContextFile] = []
    for label, path, requirement in candidates:
        if path.is_file():
            excerpt = _clip(path.read_text(encoding="utf-8", errors="replace"), limit=6000)
            status = "present"
        else:
            excerpt = ""
            status = "missing_required" if requirement == "required" else "missing_optional"
        context_files.append(
            ContextFile(
                label=label,
                path=_relativize(path, workspace),
                status=status,
                excerpt=excerpt,
            )
        )
    state.command_trace.extend(
        f"read:{item.path}" for item in context_files if item.status == "present"
    )
    return context_files


def _read_logs(state: ReviewBuildState) -> list[dict[str, Any]]:
    workspace = state.input_data.workspace.resolve()
    summaries: list[dict[str, Any]] = []
    for raw_path in state.input_data.log_paths:
        path = raw_path if raw_path.is_absolute() else workspace / raw_path
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            summary = {
                "path": _relativize(path, workspace),
                "status": "present",
                "line_count": len(text.splitlines()),
                "excerpt": _clip(text, limit=4000),
            }
            state.command_trace.append(f"read:{summary['path']}")
        else:
            summary = {
                "path": _relativize(path, workspace),
                "status": "missing",
                "line_count": 0,
                "excerpt": "",
            }
        summaries.append(summary)
    return summaries


def _read_runtime_evidence(state: ReviewBuildState) -> list[RuntimeEvidence]:
    workspace = state.input_data.workspace.resolve()
    candidates = _runtime_evidence_candidate_paths(state)
    evidence: list[RuntimeEvidence] = []
    seen: set[str] = set()
    for path in _explicit_runtime_log_paths(state, seen):
        if not path.is_file():
            continue
        item = _parse_runtime_evidence_file(path, workspace)
        evidence.append(item)
        seen.add(_relativize(path, workspace))
        state.command_trace.append(f"read:{item.path}")
    for path in candidates:
        resolved = _resolve_workspace_path(path, workspace)
        rel_path = _relativize(resolved, workspace)
        if rel_path in seen:
            continue
        seen.add(rel_path)
        if not _is_path_inside_workspace(resolved, workspace):
            evidence.append(
                RuntimeEvidence(
                    label=_runtime_evidence_label_from_path(path),
                    path=path.as_posix(),
                    status="missing_optional",
                    excerpt="外部路径未读取；仅作为任务记录中引用的运行产物路径。",
                    commands=[],
                    parameters={},
                    facts={},
                )
            )
            continue
        if not resolved.is_file():
            evidence.append(
                RuntimeEvidence(
                    label=_runtime_evidence_label_from_path(resolved),
                    path=rel_path,
                    status="missing_optional",
                    excerpt="任务记录引用了该运行产物，但当前 workspace 中未找到文件。",
                    commands=[],
                    parameters={},
                    facts={},
                )
            )
            continue
        item = _parse_runtime_evidence_file(resolved, workspace)
        evidence.append(item)
        state.command_trace.append(f"read:{item.path}")
    return evidence


def _explicit_runtime_log_paths(state: ReviewBuildState, seen: set[str]) -> list[Path]:
    workspace = state.input_data.workspace.resolve()
    paths: list[Path] = []
    for raw_path in state.input_data.log_paths:
        if raw_path.name not in RUNTIME_EVIDENCE_FILENAMES:
            continue
        path = raw_path if raw_path.is_absolute() else workspace / raw_path
        rel_path = _relativize(path, workspace)
        if rel_path in seen:
            continue
        paths.append(path)
    return paths


def _runtime_evidence_candidate_paths(state: ReviewBuildState) -> list[Path]:
    workspace = state.input_data.workspace.resolve()
    paths: list[Path] = []
    for text in _runtime_reference_texts(state):
        for match in RUNTIME_EVIDENCE_PATH_RE.finditer(text):
            path = Path(match.group("path").strip().strip("`"))
            if path.name in RUNTIME_EVIDENCE_FILENAMES:
                paths.append(path)

    resolved: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = _resolve_workspace_path(path, workspace)
        key = normalized.as_posix()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(path)
        if len(resolved) >= 20:
            break
    return resolved


def _runtime_reference_texts(state: ReviewBuildState) -> list[str]:
    texts = [item.excerpt for item in state.context_files if item.status == "present"]
    texts.extend(
        str(summary.get("excerpt", ""))
        for summary in state.log_summaries
        if summary.get("status") == "present"
    )
    texts.extend(state.input_data.test_commands)
    texts.extend(state.input_data.changed_paths)
    if state.input_data.objective:
        texts.append(state.input_data.objective)
    return texts


def _has_explicit_runtime_evidence_path(text: str) -> bool:
    for match in RUNTIME_EVIDENCE_PATH_RE.finditer(text):
        if Path(match.group("path").strip().strip("`")).name in RUNTIME_EVIDENCE_FILENAMES:
            return True
    return False


def _resolve_workspace_path(path: Path, workspace: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (workspace / path).resolve()


def _is_path_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _parse_runtime_evidence_file(path: Path, workspace: Path) -> RuntimeEvidence:
    label = _runtime_evidence_label_from_path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.name == "events.jsonl":
        commands, facts, excerpt = _parse_events_jsonl_runtime(text)
    elif path.suffix == ".json":
        payload = _loads_json_safely(text)
        commands, facts, excerpt = _parse_json_runtime_payload(payload, path.name)
    else:
        commands = _extract_runtime_commands_from_text(text)
        facts = _extract_runtime_facts_from_text(text)
        excerpt = _clip(_redact_secret_text(text), limit=1200)
    parameters = _extract_observed_command_parameters(commands)
    facts = _normalize_runtime_facts(facts)
    for name, values in _parameters_from_runtime_facts(facts).items():
        parameters.setdefault(name, [])
        parameters[name] = _dedupe_list([*parameters[name], *values])
    return RuntimeEvidence(
        label=label,
        path=_relativize(path, workspace),
        status="present",
        excerpt=excerpt,
        commands=commands,
        parameters=parameters,
        facts=facts,
    )


def _parse_events_jsonl_runtime(text: str) -> tuple[list[str], dict[str, Any], str]:
    commands: list[str] = []
    facts: dict[str, Any] = {}
    excerpts: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        payload = _loads_json_safely(line)
        if not isinstance(payload, dict):
            continue
        phase = str(payload.get("phase") or payload.get("event") or "")
        if phase:
            _append_fact_value(facts, "phase", phase)
        for key in ("qzcli_args", "argv", "args", "command"):
            commands.extend(_commands_from_value(payload.get(key)))
        for key in ("stdout_tail", "stderr_tail", "message", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                redacted = _redact_secret_text(value)
                excerpts.append(redacted)
                commands.extend(_extract_runtime_commands_from_text(redacted))
                _merge_fact_dict(facts, _extract_runtime_facts_from_text(redacted))
        _merge_fact_dict(facts, _extract_runtime_facts_from_mapping(payload))
    excerpt = _clip("\n".join(excerpts[-6:]), limit=1600)
    return _dedupe_list(commands), facts, excerpt


def _parse_json_runtime_payload(payload: Any, filename: str) -> tuple[list[str], dict[str, Any], str]:
    commands: list[str] = []
    facts: dict[str, Any] = {}
    if isinstance(payload, dict):
        commands.extend(_collect_runtime_commands_from_mapping(payload))
        _merge_fact_dict(facts, _extract_runtime_facts_from_mapping(payload))
        nested_text = _redact_secret_text(json.dumps(payload, ensure_ascii=False))
        _merge_fact_dict(facts, _extract_runtime_facts_from_text(nested_text))
        excerpt = _runtime_json_excerpt(payload, filename)
    else:
        excerpt = _clip(_redact_secret_text(json.dumps(payload, ensure_ascii=False)), limit=1200)
    return _dedupe_list(commands), facts, excerpt


def _runtime_json_excerpt(payload: dict[str, Any], filename: str) -> str:
    parts: list[str] = [f"file={filename}"]
    facts = _extract_runtime_facts_from_mapping(payload)
    for key in sorted(facts):
        parts.append(f"{key}={_jsonish_inline(facts[key])}")
    if len(parts) == 1:
        parts.append(_clip_inline(_redact_secret_text(json.dumps(payload, ensure_ascii=False)), limit=500))
    return _clip("\n".join(parts), limit=1200)


def _loads_json_safely(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _commands_from_value(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [_redact_secret_text(value)]
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            return [_redact_secret_text(shlex.join(value))]
        commands: list[str] = []
        for item in value:
            commands.extend(_commands_from_value(item))
        return commands
    if isinstance(value, dict):
        commands: list[str] = []
        for key in ("command", "cmd", "argv", "args", "qzcli_args"):
            commands.extend(_commands_from_value(value.get(key)))
        return commands
    return []


def _collect_runtime_commands_from_mapping(payload: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    for key, value in payload.items():
        normalized = _normalize_fact_key(str(key))
        if normalized in {"command", "cmd", "argv", "args", "qzcli_args"}:
            commands.extend(_commands_from_value(value))
        elif isinstance(value, dict):
            commands.extend(_collect_runtime_commands_from_mapping(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    commands.extend(_collect_runtime_commands_from_mapping(item))
    return _dedupe_list(commands)


def _extract_runtime_commands_from_text(text: str) -> list[str]:
    commands: list[str] = []
    redacted = _redact_secret_text(text)
    for line in redacted.splitlines():
        stripped = line.strip()
        if "--" not in stripped:
            continue
        if any(marker in stripped for marker in ("distributed-sft.sh", "tau2", "tau-bench", "tau_bench")):
            commands.append(stripped)
    if not commands and "--" in redacted:
        commands.append(_clip_inline(redacted, limit=1200))
    return _dedupe_list(commands)


def _extract_runtime_facts_from_text(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    patterns = {
        "model": r"(?:model(?:_name)?|model-name|agent_model|agent-model)\s*[=:]\s*['\"]?([A-Za-z0-9._/\-]+)",
        "user_llm": r"(?:user_llm|user-llm)\s*[=:]\s*['\"]?([A-Za-z0-9._/\-]+)",
        "user_model": r"(?:user_model|user-agent-model|user-model)\s*[=:]\s*['\"]?([A-Za-z0-9._/\-]+)",
        "dataset_path": r"(?:dataset(?:_path)?|dataset-path|parquet_path)\s*[=:]\s*['\"]?([^\s,'\"]+)",
        "domain": r"(?:domain|domains)\s*[=:]\s*['\"]?([A-Za-z0-9._/\-]+)",
        "benchmark": r"(?:benchmark)\s*[=:]\s*['\"]?([A-Za-z0-9._/\-]+)",
        "run_id": r"(?:run_id|run-id)\s*[=:]\s*['\"]?([A-Za-z0-9._/\-]+)",
        "run_tag": r"(?:run_tag|run-tag)\s*[=:]\s*['\"]?([A-Za-z0-9._/\-]+)",
        "config_path": r"(?:config_path|config-path|k8s-config)\s*[=:]\s*['\"]?([^\s,'\"]+)",
        "service_name": r"(?:service_name|service-name)\s*[=:]\s*['\"]?([A-Za-z0-9._/\-]+)",
        "base_url": r"(?:base_url|base-url|api_base|api-base)\s*[=:]\s*['\"]?([^\s,'\"]+)",
        "average_reward": r"(?:average_reward)\s*[=:]\s*([0-9.]+)",
        "completed_simulations": r"(?:completed_simulations)\s*[=:]\s*([0-9]+)",
        "total_simulations": r"(?:total_simulations)\s*[=:]\s*([0-9]+)",
        "timeout_count": r"(?:timeout_count|timeout-like)\s*[=:]\s*([0-9]+)",
        "timeout_limit": r"(?:timeout_limit)\s*[=:]\s*([0-9]+)",
        "job_id": r"(?:job_id|job)\s*[=:]\s*['\"]?(job-[A-Za-z0-9._/\-]+)",
        "node_count": r"(?:node_count|node-count)\s*[=:]\s*([0-9]+)",
    }
    for key, pattern in patterns.items():
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            _append_fact_value(facts, key, match)
    return facts


def _extract_runtime_facts_from_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    _collect_runtime_facts(payload, facts)
    return facts


def _collect_runtime_facts(value: Any, facts: dict[str, Any], prefix: str = "") -> None:
    if isinstance(value, dict):
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_secret_key(key):
                continue
            normalized = _normalize_fact_key(key)
            child_prefix = f"{prefix}.{normalized}" if prefix else normalized
            if normalized in RUNTIME_FACT_KEYWORDS or normalized in _runtime_fact_aliases():
                _append_fact_value(facts, _canonical_fact_key(normalized), _redact_secret_value(raw_value))
            if normalized == "metrics" and isinstance(raw_value, dict):
                for metric_key, metric_value in raw_value.items():
                    if not _is_secret_key(str(metric_key)):
                        _append_fact_value(facts, _canonical_fact_key(str(metric_key)), metric_value)
            _collect_runtime_facts(raw_value, facts, child_prefix)
    elif isinstance(value, list):
        for item in value:
            _collect_runtime_facts(item, facts, prefix)


def _runtime_fact_aliases() -> set[str]:
    return {
        "agent_model",
        "agent_llm",
        "user_model",
        "user_llm",
        "model-name",
        "dataset-path",
        "run-id",
        "run-tag",
        "service-name",
        "base-url",
        "api-base",
    }


def _canonical_fact_key(key: str) -> str:
    normalized = _normalize_fact_key(key)
    aliases = {
        "agent_llm": "model",
        "agent_model": "model",
        "user-model": "user_model",
        "user_llm": "user_llm",
        "model-name": "model_name",
        "dataset-path": "dataset_path",
        "run-id": "run_id",
        "run-tag": "run_tag",
        "service-name": "service_name",
        "base-url": "base_url",
        "api-base": "base_url",
        "api_base": "base_url",
    }
    return aliases.get(normalized, normalized)


def _normalize_fact_key(key: str) -> str:
    return key.strip().replace("-", "_").lower()


def _append_fact_value(facts: dict[str, Any], key: str, value: Any) -> None:
    if value is None or value == "":
        return
    key = _canonical_fact_key(key)
    value = _redact_secret_value(value)
    if key not in facts:
        facts[key] = value
        return
    existing = facts[key]
    if not isinstance(existing, list):
        existing_list = [existing]
    else:
        existing_list = existing
    if value not in existing_list:
        existing_list.append(value)
    facts[key] = existing_list


def _merge_fact_dict(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, list):
            for item in value:
                _append_fact_value(target, key, item)
        else:
            _append_fact_value(target, key, value)


def _normalize_runtime_facts(facts: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in facts.items():
        canonical = _canonical_fact_key(key)
        if isinstance(value, list):
            cleaned = [_redact_secret_value(item) for item in value if item not in (None, "")]
            if cleaned:
                normalized[canonical] = _dedupe_list([str(item) for item in cleaned])
        elif value not in (None, ""):
            normalized[canonical] = _redact_secret_value(value)
    return normalized


def _parameters_from_runtime_facts(facts: dict[str, Any]) -> dict[str, list[str]]:
    aliases = {
        "model": "--model",
        "model_name": "--model-name",
        "user_llm": "--user-llm",
        "user_model": "--user-model",
        "dataset_path": "--dataset-path",
        "benchmark": "--benchmark",
        "domain": "--domain",
        "domains": "--domain",
        "run_id": "--run-id",
        "run_tag": "--run-tag",
        "service_name": "--service-name",
        "base_url": "--base-url",
        "replicas": "--replicas",
        "replica": "--replicas",
        "global_batch_size": "--global-batch-size",
        "rollout_batch_size": "--rollout-batch-size",
    }
    parameters: dict[str, list[str]] = {}
    for fact_key, param_name in aliases.items():
        if fact_key not in facts:
            continue
        values = facts[fact_key] if isinstance(facts[fact_key], list) else [facts[fact_key]]
        parameters[param_name] = _dedupe_list(str(value) for value in values if value not in (None, ""))
    return parameters


def _runtime_evidence_label_from_path(path: Path) -> str:
    path_text = path.as_posix().lower()
    name = path.name.lower()
    if name in {"live_context_report.json", "live_preflight_report.json", "controller_state.json"}:
        return "contextswarm_live"
    if "tau2" in path_text or "tau-bench" in path_text or "tau_bench" in path_text:
        return "tau_bench"
    if name in {
        "deploy_submit_payload.json",
        "runtime_resolved_manifest.json",
        "launch_manifest.json",
    } or "/deploy" in path_text:
        return "qz_deployment"
    if name == "events.jsonl" or "train" in path_text or "qizhi-rollout-train-deploy-experiment" in path_text:
        return "qz_training"
    return "runtime_artifact"


def _runtime_evidence_label_zh(label: str) -> str:
    return {
        "contextswarm_live": "ContextSwarm live",
        "qz_training": "qz 训练",
        "qz_deployment": "qz 部署",
        "tau_bench": "tau bench",
        "runtime_artifact": "运行产物",
    }.get(label, label)


def _runtime_evidence_summary(item: RuntimeEvidence) -> str:
    parts = [
        f"{_runtime_evidence_label_zh(item.label)} `{item.path}`",
        CONTEXT_FILE_STATUS_TEXT_ZH.get(item.status, item.status),
    ]
    if item.parameters:
        rendered_params = []
        for name in sorted(item.parameters):
            if name in RUNTIME_PARAM_NAMES or item.label in {"contextswarm_live", "tau_bench"}:
                rendered_params.append(f"{name}={', '.join(item.parameters[name])}")
        if rendered_params:
            parts.append("参数：" + "；".join(rendered_params))
    fact_parts = _runtime_fact_summary_parts(item.facts)
    if fact_parts:
        parts.append("事实：" + "；".join(fact_parts))
    if not item.parameters and not fact_parts and item.excerpt:
        parts.append("摘要：" + _clip_inline(item.excerpt, limit=160))
    return "；".join(parts)


def _runtime_fact_summary_parts(facts: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    for key in (
        "model",
        "model_name",
        "user_llm",
        "user_model",
        "dataset_path",
        "project_id",
        "scheduler",
        "benchmark",
        "config_path",
        "domain",
        "domains",
        "run_id",
        "run_tag",
        "service_name",
        "base_url",
        "replicas",
        "job_id",
        "pool",
        "node_count",
        "gpu_count",
        "task_count",
        "ready",
        "preflight_ready",
        "accepted",
        "judge_status",
        "worker_status",
        "skipped_reason",
        "status",
        "summary_status",
        "average_reward",
        "pass_k",
        "resolved_instances",
        "completed_instances",
        "total_instances",
        "error_instances",
        "error_ids",
        "completed_simulations",
        "total_simulations",
        "timeout_count",
        "timeout_limit",
        "deployment_status_after_cleanup",
        "resource_stopped",
    ):
        if key in facts:
            parts.append(f"{key}={_jsonish_inline(facts[key])}")
    return parts


def _jsonish_inline(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return _clip_inline(json.dumps(value, ensure_ascii=False), limit=140)
    return _clip_inline(str(value), limit=140)


def _dedupe_list(values: Any) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in RUNTIME_SECRET_KEYWORDS)


def _redact_secret_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if _is_secret_key(str(key)) else _redact_secret_value(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_secret_value(item) for item in value]
    if isinstance(value, str):
        return _redact_secret_text(value)
    return value


def _redact_secret_text(text: str) -> str:
    redacted = re.sub(
        r"(?i)(--(?:api-key|token|secret)\s+)(\S+)",
        r"\1[REDACTED]",
        text,
    )
    redacted = re.sub(
        r"(?i)([\"']--(?:api-key|token|secret)[\"']\s*,\s*[\"'])([^\"']+)",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)([\"']?(?:api_key|token|secret|authorization)[\"']?\s*[:=]\s*[\"']?)([^'\"\s,}]+)",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)((?:[A-Z0-9_]*)(?:API_?KEY|TOKEN|SECRET)\s*=\s*[\"']?)([^'\"\s,;]+)",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", redacted)
    redacted = re.sub(
        (
            r"(?<![A-Za-z0-9_/\-])"
            r"(?=[A-Za-z0-9_=\-]{40,})"
            r"(?=[A-Za-z0-9_=\-]*[A-Z])"
            r"(?=[A-Za-z0-9_=\-]*[a-z])"
            r"(?=[A-Za-z0-9_=\-]*[0-9])"
            r"[A-Za-z0-9_=\-]{40,}"
            r"(?![A-Za-z0-9_/\-])"
        ),
        "[REDACTED]",
        redacted,
    )
    return redacted


def _collect_diff_summary(state: ReviewBuildState) -> dict[str, Any]:
    workspace = state.input_data.workspace.resolve()
    paths = list(dict.fromkeys(state.input_data.changed_paths))
    unstaged_stat_args = ["git", "diff", "--stat"]
    unstaged_name_args = ["git", "diff", "--name-status"]
    staged_stat_args = ["git", "diff", "--cached", "--stat"]
    staged_name_args = ["git", "diff", "--cached", "--name-status"]
    if paths:
        unstaged_stat_args.extend(["--", *paths])
        unstaged_name_args.extend(["--", *paths])
        staged_stat_args.extend(["--", *paths])
        staged_name_args.extend(["--", *paths])
    unstaged_stat = _run_git(workspace, unstaged_stat_args)
    unstaged_names = _run_git(workspace, unstaged_name_args)
    staged_stat = _run_git(workspace, staged_stat_args)
    staged_names = _run_git(workspace, staged_name_args)
    state.command_trace.extend(
        [
            "git diff --stat",
            "git diff --name-status",
            "git diff --cached --stat",
            "git diff --cached --name-status",
        ]
    )
    stat_text = "\n".join(
        part for part in [unstaged_stat.stdout.strip(), staged_stat.stdout.strip()] if part
    )
    name_status_text = "\n".join(
        part for part in [unstaged_names.stdout.strip(), staged_names.stdout.strip()] if part
    )
    return {
        "changed_paths_requested": paths,
        "git_diff_stat": stat_text,
        "git_diff_name_status": name_status_text,
        "git_diff_unstaged_stat": unstaged_stat.stdout.strip(),
        "git_diff_unstaged_name_status": unstaged_names.stdout.strip(),
        "git_diff_staged_stat": staged_stat.stdout.strip(),
        "git_diff_staged_name_status": staged_names.stdout.strip(),
        "status": "present" if (stat_text or name_status_text or paths) else "empty",
        "errors": [
            text
            for text in [
                unstaged_stat.stderr.strip(),
                unstaged_names.stderr.strip(),
                staged_stat.stderr.strip(),
                staged_names.stderr.strip(),
            ]
            if text
        ],
    }


def _run_git(workspace: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=workspace, text=True, capture_output=True, check=False)


def _build_reliability_results(state: ReviewBuildState) -> dict[str, Any]:
    required_missing = [item for item in state.context_files if item.status == "missing_required"]
    focused_context_files = _focus_context_files_for_current_task(
        state.context_files, state.input_data.objective or ""
    )
    optional_idea_present = any(
        item.label.startswith("idea_") and item.status == "present" for item in state.context_files
    )
    optional_idea_missing = all(
        item.status == "missing_optional"
        for item in state.context_files
        if item.label.startswith("idea_")
    )
    evidence_text = "\n".join(
        [item.excerpt for item in focused_context_files if item.status == "present"]
        + [
            summary.get("excerpt", "")
            for summary in state.log_summaries
            if summary.get("status") == "present"
        ]
    ).lower()
    runtime_text = _runtime_alignment_text(state.runtime_evidence)
    command_text = "\n".join(
        state.input_data.test_commands + state.input_data.changed_paths
    ).lower()
    objective = (state.input_data.objective or "").lower()
    classification_text = "\n".join(
        [
            command_text,
            objective,
            evidence_text,
            runtime_text.lower(),
        ]
    )
    implementation_like = _looks_like_reliable_check_implementation_task(
        "\n".join([objective, "\n".join(state.input_data.changed_paths).lower()])
    )
    research_like = _looks_like_research_task(command_text + "\n" + objective) and not implementation_like
    runtime_required = (
        _looks_like_runtime_task(classification_text)
        and not implementation_like
        and not _looks_like_readonly_data_audit_task(classification_text)
    )
    parameter_comparison = _compare_required_command_parameters(
        focused_context_files, state.input_data.test_commands, state.runtime_evidence
    )
    expected_paths = _extract_expected_changed_paths(focused_context_files)
    actual_paths = _actual_changed_paths(state)
    expected_methods = _extract_expected_change_methods(focused_context_files)
    actual_methods = _actual_change_methods(state)
    observed_alignment_text = command_text + "\n" + objective + "\n" + runtime_text.lower()
    overlap_matches = _overlap_matches(observed_alignment_text, evidence_text)
    idea_plan_text = _filtered_idea_relevance_text(
        "\n".join(
            item.excerpt
            for item in focused_context_files
            if item.status == "present" and item.label == "idea_plan"
        )
    )
    idea_matches = _overlap_matches(observed_alignment_text, idea_plan_text)
    runtime_idea_evidence = _runtime_idea_alignment_evidence(
        idea_plan_text, state.runtime_evidence, objective
    )

    checks: list[dict[str, Any]] = []
    if required_missing:
        checks.append(
            _reliable_check_item(
                "codex_record_presence",
                "BLOCKED",
                "缺少必需的会话记录文件："
                + "、".join(item.path for item in required_missing),
                evidence=[f"缺失文件：`{item.path}`" for item in required_missing],
            )
        )
    else:
        present_records = [
            item.path
            for item in state.context_files
            if item.status == "present" and not item.label.startswith("idea_")
        ]
        checks.append(
            _reliable_check_item(
                "codex_record_presence",
                "PASS",
                "必需的 .codex_record 文件均已读取。",
                evidence=[f"已读取 `{path}`" for path in present_records],
            )
        )

    if optional_idea_present and research_like and (idea_matches or runtime_idea_evidence):
        present_idea = [
            item.path
            for item in state.context_files
            if item.status == "present" and item.label.startswith("idea_")
        ]
        shown_idea_matches = "、".join(f"`{token}`" for token in idea_matches[:8])
        idea_evidence = [
            f"已读取科研记录 `{path}`" for path in present_idea
        ]
        if shown_idea_matches:
            idea_evidence.append(f"当前任务/命令与科研计划匹配 token：{shown_idea_matches}")
        idea_evidence.extend(runtime_idea_evidence)
        idea_evidence.append(f"科研计划摘要：{_first_content_line(idea_plan_text)}")
        checks.append(
            _reliable_check_item(
                "codex_idea_presence",
                "PASS",
                ".codex_idea 文件已读取，且科研计划与当前任务或命令存在可核对匹配。",
                evidence=idea_evidence,
            )
        )
    elif optional_idea_present:
        present_idea = [
            item.path
            for item in state.context_files
            if item.status == "present" and item.label.startswith("idea_")
        ]
        checks.append(
            _reliable_check_item(
                "codex_idea_presence",
                "FAIL" if research_like else "NOT_APPLICABLE",
                _idea_not_applicable_or_fail_details(research_like, bool(idea_matches)),
                evidence=[
                    *(f"已读取科研记录 `{path}`" for path in present_idea),
                    f"当前任务：{_clip_inline(state.input_data.objective or '未显式提供', limit=120)}",
                    f"科研计划摘要：{_first_content_line(idea_plan_text)}",
                    (
                        "当前任务是 reliable check / skill 实现任务；科研记录不作为本次实现任务的适用性依据。"
                        if implementation_like
                        else
                        "当前任务不是科研/实验任务；即使命中少量文本 token，也不足以证明科研记录适用。"
                        if idea_matches and not research_like
                        else "未匹配到能证明二者属于同一科研/实验目标的 token。"
                    ),
                ],
            )
        )
    elif optional_idea_missing:
        missing_idea = [
            item.path
            for item in state.context_files
            if item.status == "missing_optional" and item.label.startswith("idea_")
        ]
        checks.append(
            _reliable_check_item(
                "codex_idea_presence",
                "NOT_APPLICABLE",
                "此会话没有 .codex_idea 文件；对非科研或非实验任务这是可接受的。",
                evidence=[f"未发现可选科研记录 `{path}`" for path in missing_idea],
            )
        )

    command_matches_plan = bool(overlap_matches)
    if required_missing:
        command_status = "BLOCKED"
        command_details = "缺少任务计划记录，无法比较命令与任务意图。"
        command_evidence = ["缺少任务计划记录，无法抽取目标或命令证据。"]
    elif command_matches_plan:
        command_status = "PASS"
        shown_matches = "、".join(f"`{token}`" for token in overlap_matches[:8])
        command_details = f"命令或任务目标与会话记录匹配：{shown_matches}。"
        command_evidence = [
            f"任务目标：{_clip_inline(state.input_data.objective or '未显式提供', limit=120)}",
            f"实际命令/路径：{_clip_inline('; '.join(state.input_data.test_commands + state.input_data.changed_paths), limit=180)}",
            f"匹配证据 token：{shown_matches}",
        ]
        if state.runtime_evidence:
            command_evidence.append(
                "运行产物参与对齐："
                + _format_plain_list(
                    [f"{_runtime_evidence_label_zh(item.label)} `{item.path}`" for item in state.runtime_evidence]
                )
            )
    else:
        command_status = "FAIL"
        command_details = (
            "未能在任务计划、进度、发现或科研记录中找到命令或目标对应证据。"
        )
        command_evidence = [
            f"任务目标：{_clip_inline(state.input_data.objective or '未显式提供', limit=120)}",
            f"实际命令/路径：{_clip_inline('; '.join(state.input_data.test_commands + state.input_data.changed_paths), limit=180)}",
            "会话记录中未发现可用于核对的共同 token。",
        ]
    checks.append(
        _reliable_check_item(
            "command_and_plan_alignment",
            command_status,
            command_details,
            evidence=command_evidence,
        )
    )

    checks.append(_build_parameter_consistency_check(parameter_comparison, required_missing))

    checks.append(
        _build_runtime_evidence_check(
            state.runtime_evidence,
            runtime_required=runtime_required,
            implementation_like=implementation_like,
        )
    )

    if state.diff_summary.get("status") == "empty" and not state.input_data.changed_paths:
        diff_status = "BLOCKED"
        diff_details = "未提供变更路径，也没有可用的 git diff 证据。"
        diff_evidence = ["没有 `--changed-path`，也没有可读取的 git diff 路径证据。"]
    else:
        diff_status = "PASS"
        diff_details = "已从请求的变更路径或 git diff 中捕获差异证据。"
        diff_evidence = []
        if expected_paths:
            diff_evidence.append(f"预期修改路径：{_format_backtick_list(expected_paths)}")
        else:
            diff_evidence.append("未在任务记录中发现明确的预期修改路径。")
        if actual_paths:
            diff_evidence.append(f"实际修改路径：{_format_backtick_list(actual_paths)}")
        else:
            diff_evidence.append("未捕获到实际修改路径。")
        if expected_methods:
            diff_evidence.append(f"预期修改方式：{_format_plain_list(expected_methods)}")
        else:
            diff_evidence.append("未在任务记录中发现明确的预期修改方式。")
        if actual_methods:
            diff_evidence.append(f"实际修改方式：{_format_plain_list(actual_methods)}")
        else:
            diff_evidence.append("未能从 git diff 中概括实际修改方式。")
    checks.append(
        _reliable_check_item(
            "diff_evidence",
            diff_status,
            diff_details,
            evidence=diff_evidence,
            expected_changed_paths=expected_paths,
            actual_changed_paths=actual_paths,
            expected_change_methods=expected_methods,
            actual_change_methods=actual_methods,
        )
    )

    status = _combine_status([str(check["status"]) for check in checks])
    results = {
        "status": status,
        "checks": checks,
        "session_id": state.input_data.session_id,
        "context_files": [item.to_reliable_check_json() for item in state.context_files],
        "logs": state.log_summaries,
        "runtime_evidence": [item.to_reliable_check_json() for item in state.runtime_evidence],
        "required_command_parameters": parameter_comparison["required"],
        "observed_command_parameters": parameter_comparison["observed"],
        "observed_command_parameter_sources": parameter_comparison["observed_sources"],
        "missing_required_parameters": parameter_comparison["missing"],
        "unexpected_parameter_values": parameter_comparison["unexpected"],
        "expected_changed_paths": expected_paths,
        "actual_changed_paths": actual_paths,
        "expected_change_methods": expected_methods,
        "actual_change_methods": actual_methods,
    }
    results["reviewer_markdown"] = _render_reliable_check_reviewer_markdown(results)
    return results


def _build_parameter_consistency_check(
    comparison: dict[str, Any], required_missing: list[ContextFile]
) -> dict[str, Any]:
    if required_missing:
        return _reliable_check_item(
            "command_parameter_consistency",
            "BLOCKED",
            "缺少会话记录，无法核对命令参数是否符合最初要求。",
            evidence=["缺少会话记录，无法抽取最初要求的命令参数。"],
            required_command_parameters=comparison["required"],
            observed_command_parameters=comparison["observed"],
            observed_command_parameter_sources=comparison["observed_sources"],
            missing_required_parameters=comparison["missing"],
            unexpected_parameter_values=comparison["unexpected"],
        )
    if not comparison["required"]:
        return _reliable_check_item(
            "command_parameter_consistency",
            "NOT_APPLICABLE",
            "未在任务计划或科研记录中发现明确的命令参数要求。",
            evidence=["未找到带 `命令参数要求`、`实验命令` 或 `required parameters` 标记的参数记录。"],
            required_command_parameters=[],
            observed_command_parameters=comparison["observed"],
            observed_command_parameter_sources=comparison["observed_sources"],
            missing_required_parameters=[],
            unexpected_parameter_values=[],
        )
    if comparison["missing"] or comparison["unexpected"]:
        parts = []
        if comparison["missing"]:
            missing = "、".join(item["name"] for item in comparison["missing"])
            parts.append(f"缺少必需参数：{missing}")
        if comparison["unexpected"]:
            mismatched = "、".join(
                f"{item['name']} 期望 {item['expected']}，实际 {', '.join(item['observed'])}"
                for item in comparison["unexpected"]
            )
            parts.append(f"参数值不一致：{mismatched}")
        return _reliable_check_item(
            "command_parameter_consistency",
            "FAIL",
            "；".join(parts) + "。",
            evidence=_parameter_evidence(comparison),
            required_command_parameters=comparison["required"],
            observed_command_parameters=comparison["observed"],
            observed_command_parameter_sources=comparison["observed_sources"],
            missing_required_parameters=comparison["missing"],
            unexpected_parameter_values=comparison["unexpected"],
        )
    return _reliable_check_item(
        "command_parameter_consistency",
        "PASS",
        "实际执行命令包含最初记录要求的命令参数和值。",
        evidence=_parameter_evidence(comparison),
        required_command_parameters=comparison["required"],
        observed_command_parameters=comparison["observed"],
        observed_command_parameter_sources=comparison["observed_sources"],
        missing_required_parameters=[],
        unexpected_parameter_values=[],
    )


def _build_runtime_evidence_check(
    runtime_evidence: list[RuntimeEvidence], *, runtime_required: bool, implementation_like: bool
) -> dict[str, Any]:
    present = [item for item in runtime_evidence if item.status == "present"]
    missing = [item for item in runtime_evidence if item.status != "present"]
    blocking_missing = [item for item in missing if _runtime_missing_evidence_blocks(item, present)]
    nonblocking_missing = [item for item in missing if item not in blocking_missing]
    if present:
        status = "PASS" if not blocking_missing else "BLOCKED"
        details = (
            "已读取实际运行产物，并抽取命令、参数或实验指标。"
            if status == "PASS"
            else "部分运行产物已读取，但仍有任务记录引用的运行产物缺失。"
        )
        evidence = [_runtime_evidence_summary(item) for item in present]
        evidence.extend(f"缺失运行产物 `{item.path}`：{item.excerpt}" for item in blocking_missing)
        evidence.extend(_runtime_nonblocking_missing_summary(item, present) for item in nonblocking_missing)
        return _reliable_check_item(
            "experiment_runtime_evidence",
            status,
            details,
            evidence=evidence,
            runtime_evidence=[item.to_reliable_check_json() for item in runtime_evidence],
        )
    if runtime_required:
        return _reliable_check_item(
            "experiment_runtime_evidence",
            "BLOCKED",
            "当前任务看起来需要运行产物证据，但没有可读取的实际运行产物。",
            evidence=[
                "任务/idea/日志提到了 qz、训练、部署、tau、benchmark 或 ContextSwarm live 运行，但未发现可读取的运行产物。",
                "需要在任务记录或 log 中引用实际运行产物路径，才能核对运行参数、状态和指标是否符合计划。",
            ],
            runtime_evidence=[],
        )
    return _reliable_check_item(
        "experiment_runtime_evidence",
        "NOT_APPLICABLE",
        (
            "当前是 reliable check / skill 实现任务，不要求实际 qz/tau 运行产物。"
            if implementation_like
            else "当前任务未要求 qz 训练/部署、tau bench 或 ContextSwarm live 运行证据。"
        ),
        evidence=[
            (
                "检测到实现任务语义，运行产物读取逻辑只通过单测 fixture 验收。"
                if implementation_like
                else "任务记录和 review 输入中没有必须读取实验运行产物的要求。"
            )
        ],
        runtime_evidence=[],
    )


def _runtime_missing_evidence_blocks(item: RuntimeEvidence, present: list[RuntimeEvidence]) -> bool:
    if item.status != "missing_optional":
        return True
    item_path = Path(item.path)
    item_name = item_path.name
    return not any(Path(present_item.path).name == item_name and _is_data_swarm_path(present_item.path) for present_item in present)


def _runtime_nonblocking_missing_summary(item: RuntimeEvidence, present: list[RuntimeEvidence]) -> str:
    item_name = Path(item.path).name
    replacement = next(
        (
            present_item.path
            for present_item in present
            if Path(present_item.path).name == item_name and _is_data_swarm_path(present_item.path)
        ),
        None,
    )
    if replacement:
        return f"旧临时运行产物 `{item.path}` 已由持久产物 `{replacement}` 覆盖。"
    return f"缺失可选运行产物 `{item.path}`：{item.excerpt}"


def _is_data_swarm_path(path: str) -> bool:
    parts = Path(path).parts
    return len(parts) >= 2 and parts[0] == "data" and parts[1].startswith("swarm_")


def _reliable_check_item(name: str, status: str, details: str, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "display_name": CHECK_DISPLAY_NAMES.get(name, name),
        "status": status,
        "status_text": STATUS_TEXT_ZH.get(status, status),
        "details": details,
    }
    item.update(extra)
    item.setdefault("evidence", [details])
    return item


def _parameter_evidence(comparison: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    for item in comparison["required"]:
        evidence.append(
            f"要求参数 `{item['name']}={item['value']}`，来源：{item['source']}。"
        )
    observed = comparison["observed"]
    observed_sources = comparison.get("observed_sources", {})
    for name in sorted(observed):
        values = ", ".join(observed[name])
        source_text = _parameter_source_text(observed_sources.get(name, {}))
        evidence.append(f"实际参数 `{name}={values}`{source_text}。")
    for item in comparison["missing"]:
        evidence.append(
            f"缺少要求参数 `{item['name']}={item['value']}`，来源：{item['source']}。"
        )
    for item in comparison["unexpected"]:
        observed_values = ", ".join(item["observed"])
        evidence.append(
            f"参数值不一致：期望 `{item['name']}={item['expected']}`，实际 `{item['name']}={observed_values}`。"
        )
    return evidence or ["未发现需要核对的命令参数。"]


def _compare_required_command_parameters(
    context_files: list[ContextFile],
    test_commands: list[str],
    runtime_evidence: list[RuntimeEvidence] | None = None,
) -> dict[str, Any]:
    required = _extract_required_command_parameters(context_files)
    observed, observed_sources = _extract_observed_command_parameters_with_sources(
        test_commands, runtime_evidence or []
    )
    missing: list[dict[str, str]] = []
    unexpected: list[dict[str, Any]] = []
    for requirement in required:
        name = requirement["name"]
        expected = requirement["value"]
        observed_values = observed.get(name, [])
        if not observed_values:
            missing.append(requirement)
        elif expected and expected not in observed_values:
            unexpected.append(
                {
                    "name": name,
                    "expected": expected,
                    "observed": observed_values,
                    "source": requirement["source"],
                }
            )
    return {
        "required": required,
        "observed": observed,
        "observed_sources": observed_sources,
        "missing": missing,
        "unexpected": unexpected,
    }


def _extract_observed_command_parameters_with_sources(
    test_commands: list[str], runtime_evidence: list[RuntimeEvidence]
) -> tuple[dict[str, list[str]], dict[str, dict[str, list[str]]]]:
    observed: dict[str, list[str]] = {}
    sources: dict[str, dict[str, list[str]]] = {}
    for command in test_commands:
        params = _extract_parameters_from_command(command)
        _merge_observed_parameters(observed, sources, params, "review/test command")
    for item in runtime_evidence:
        if item.status != "present":
            continue
        _merge_observed_parameters(
            observed,
            sources,
            item.parameters,
            f"{_runtime_evidence_label_zh(item.label)} `{item.path}`",
        )
        if item.commands:
            for command in item.commands:
                _merge_observed_parameters(
                    observed,
                    sources,
                    _extract_parameters_from_command(command),
                    f"{_runtime_evidence_label_zh(item.label)} `{item.path}`",
                )
    return (
        {name: _dedupe_list(values) for name, values in observed.items()},
        {
            name: {value: _dedupe_list(value_sources) for value, value_sources in values.items()}
            for name, values in sources.items()
        },
    )


def _merge_observed_parameters(
    observed: dict[str, list[str]],
    sources: dict[str, dict[str, list[str]]],
    params: dict[str, list[str]],
    source: str,
) -> None:
    for name, values in params.items():
        for value in values:
            if not value:
                continue
            observed.setdefault(name, []).append(value)
            sources.setdefault(name, {}).setdefault(value, []).append(source)


def _parameter_source_text(value_sources: dict[str, list[str]]) -> str:
    if not value_sources:
        return ""
    parts = []
    for value in sorted(value_sources):
        parts.append(f"`{value}` 来源：{_format_plain_list(value_sources[value])}")
    return "，" + "；".join(parts)


def _focus_context_files_for_current_task(
    context_files: list[ContextFile], objective: str
) -> list[ContextFile]:
    focused: list[ContextFile] = []
    for context_file in context_files:
        if context_file.status != "present":
            focused.append(context_file)
            continue
        if context_file.label in {"task_plan", "idea_plan", "idea_progress", "idea_findings"}:
            excerpt = _current_task_excerpt(context_file.excerpt, objective)
            focused.append(
                ContextFile(
                    label=context_file.label,
                    path=context_file.path,
                    status=context_file.status,
                    excerpt=excerpt,
                )
            )
        else:
            focused.append(context_file)
    return focused


def _current_task_excerpt(text: str, objective: str) -> str:
    blocks = _split_markdown_blocks(text)
    if not blocks:
        return text
    objective_terms = _objective_focus_terms(objective)
    if objective_terms:
        matched_blocks = _expand_current_task_blocks(blocks, objective_terms)
        if matched_blocks:
            return "\n\n".join(matched_blocks)
    active_blocks = [
        block
        for block in blocks
        if any(
            marker in block.lower()
            for marker in (
                "active task",
                "active goal",
                "active acceptance",
                "active owned paths",
                "active cod",
                "当前任务",
            )
        )
    ]
    if active_blocks:
        return "\n\n".join(active_blocks)
    return blocks[0]


def _expand_current_task_blocks(blocks: list[str], objective_terms: set[str]) -> list[str]:
    selected: list[str] = []
    include_following = False
    for block in blocks:
        lowered = block.lower()
        heading = lowered.splitlines()[0] if lowered.splitlines() else ""
        if _looks_like_historical_task_heading(heading):
            include_following = False
            continue
        direct_match = any(term in lowered for term in objective_terms)
        if direct_match:
            selected.append(block)
            include_following = _looks_like_current_task_anchor(heading, lowered)
            continue
        if include_following and _looks_like_task_detail_heading(heading):
            selected.append(block)
            continue
        include_following = False
    return selected


def _looks_like_historical_task_heading(heading: str) -> bool:
    return any(
        marker in heading
        for marker in (
            "old task",
            "start-task",
            "previous",
            "completion",
            "follow-up",
            "旧任务",
            "历史",
            "完成",
        )
    )


def _looks_like_current_task_anchor(heading: str, block: str) -> bool:
    return (
        heading.startswith("# task plan")
        or "active task" in heading
        or "active goal" in heading
        or "当前任务" in heading
        or "goal:" in block
        or "objective:" in block
        or "目标:" in block
    )


def _looks_like_task_detail_heading(heading: str) -> bool:
    return any(
        marker in heading
        for marker in (
            "owned paths",
            "changed paths",
            "acceptance",
            "task gate",
            "unit-test",
            "active owned",
            "active acceptance",
            "active task gate",
            "修改路径",
            "验收",
            "任务 gate",
        )
    )


def _split_markdown_blocks(text: str) -> list[str]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("#") and current:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return ["\n".join(block).strip() for block in blocks if "\n".join(block).strip()]


def _objective_focus_terms(objective: str) -> set[str]:
    lowered = objective.lower()
    terms = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_.-]*", lowered)
        if len(token) >= 4
        and token not in ALIGNMENT_STOP_TOKENS
        and not token.endswith((".py", ".md"))
    }
    for term in ("审计", "数据", "质量", "训练", "报告", "坏模式", "0524", "cod-695", "cod695"):
        if term in lowered:
            terms.add(term)
    return terms


def _extract_expected_changed_paths(context_files: list[ContextFile]) -> list[str]:
    expected: list[str] = []
    for context_file in context_files:
        if context_file.status != "present":
            continue
        if context_file.label not in {"task_plan", "idea_plan"}:
            continue
        lines = context_file.excerpt.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index]
            if not any(marker in line.lower() for marker in PATH_REQUIREMENT_MARKERS):
                index += 1
                continue
            expected.extend(_extract_path_like_tokens(line))
            index += 1
            while index < len(lines):
                continuation = lines[index]
                stripped = continuation.strip()
                if not stripped:
                    index += 1
                    continue
                if stripped.startswith("#") or stripped.startswith("|"):
                    break
                if any(marker in stripped.lower() for marker in PATH_REQUIREMENT_MARKERS):
                    break
                if stripped.startswith(("-", "*")) or "`" in stripped:
                    expected.extend(_extract_path_like_tokens(stripped))
                    index += 1
                    continue
                break
    return list(dict.fromkeys(expected))


def _actual_changed_paths(state: ReviewBuildState) -> list[str]:
    paths = list(state.input_data.changed_paths)
    name_status = str(state.diff_summary.get("git_diff_name_status") or "")
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            paths.append(parts[-1])
    return list(dict.fromkeys(path for path in paths if path))


def _extract_expected_change_methods(context_files: list[ContextFile]) -> list[str]:
    methods: list[str] = []
    for context_file in context_files:
        if context_file.status != "present":
            continue
        if context_file.label not in {"task_plan", "idea_plan"}:
            continue
        methods.extend(_extract_marked_change_methods(context_file.excerpt))
        methods.extend(_extract_acceptance_change_methods(context_file.excerpt))
    if not methods:
        methods.extend(_fallback_expected_change_methods(context_files))
    return list(dict.fromkeys(methods))


def _extract_marked_change_methods(text: str) -> list[str]:
    methods: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "|")):
            continue
        if _is_plan_metadata_line(stripped):
            continue
        without_marker = _strip_list_marker(stripped)
        if not _starts_with_change_method_marker(without_marker):
            continue
        cleaned = re.sub(
            r"^[#*\-\s|]*(" + "|".join(re.escape(marker) for marker in CHANGE_METHOD_MARKERS) + r")\s*[:：-]?\s*",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
        cleaned = cleaned.strip(" |")
        if cleaned and not _looks_like_path_only(cleaned):
            methods.append(_clip_inline(cleaned, limit=180))
    return methods


def _strip_list_marker(text: str) -> str:
    return text.strip().lstrip("-* ").strip()


def _starts_with_change_method_marker(text: str) -> bool:
    lowered = text.lower()
    return any(lowered.startswith(marker) for marker in CHANGE_METHOD_MARKERS)


def _extract_acceptance_change_methods(text: str) -> list[str]:
    methods: list[str] = []
    in_relevant_section = False
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if stripped.startswith("#"):
            in_relevant_section = any(
                marker in lowered
                for marker in ("goal", "acceptance criteria", "验收", "目标")
            )
            continue
        if not in_relevant_section:
            continue
        if not stripped or stripped.startswith("|") or _is_plan_metadata_line(stripped):
            continue
        cleaned = _strip_plan_prefix(_strip_list_marker(stripped))
        if not cleaned:
            continue
        if "实际修改方式" in cleaned and "预期修改方式" not in cleaned:
            continue
        if any(
            term in cleaned.lower()
            for term in ("修改方式", "怎么改", "怎么修改", "change method", "how to modify")
        ):
            methods.append(_clip_inline(cleaned, limit=180))
    return methods


def _fallback_expected_change_methods(context_files: list[ContextFile]) -> list[str]:
    candidates: list[str] = []
    for context_file in context_files:
        if context_file.status != "present" or context_file.label != "task_plan":
            continue
        for line in context_file.excerpt.splitlines():
            stripped = line.strip().strip("-* ").strip()
            lowered = stripped.lower()
            if not stripped or stripped.startswith("#") or stripped.startswith("|"):
                continue
            if _is_plan_metadata_line(stripped):
                continue
            if lowered.startswith(("goal:", "- goal:", "目标:", "- 目标:")):
                candidates.append(_strip_plan_prefix(stripped))
            elif any(term in lowered for term in ("acceptance criteria", "验收标准")):
                continue
            elif any(term in lowered for term in ("修改方式", "怎么改", "怎么修改")):
                candidates.append(_strip_plan_prefix(stripped))
        if candidates:
            break
    return [_clip_inline(item, limit=180) for item in candidates if item]


def _is_plan_metadata_line(text: str) -> bool:
    lowered = text.strip().lstrip("-* ").lower()
    return lowered.startswith(
        (
            "task_date:",
            "session_id:",
            "linear_issue:",
            "issue_title_candidate:",
            "objective:",
            "failure_policy:",
            "tracking_note:",
            "chosen_action:",
            "review_required:",
        )
    )


def _strip_plan_prefix(text: str) -> str:
    text = _strip_list_marker(text)
    return re.sub(
        r"^[-* ]*(objective|goal|目标|验收标准|acceptance criteria)\s*[:：-]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def _looks_like_path_only(text: str) -> bool:
    cleaned = text.strip().strip("`")
    return bool(cleaned) and len(_extract_path_like_tokens(cleaned)) == 1 and " " not in cleaned


def _format_backtick_list(items: list[str], *, limit: int | None = None) -> str:
    return "、".join(f"`{item}`" for item in items)


def _format_plain_list(items: list[str], *, limit: int | None = None) -> str:
    return "；".join(" ".join(item.split()) for item in items)


def _actual_change_methods(state: ReviewBuildState) -> list[str]:
    methods = _summarize_path_categories(_actual_changed_paths(state))
    patch_text = _git_diff_patch_text(state)
    methods.extend(_summarize_patch_methods(patch_text))
    return list(dict.fromkeys(methods))


def _summarize_path_categories(paths: list[str]) -> list[str]:
    methods: list[str] = []
    if any(path.endswith(".py") and "/scripts/" in path for path in paths):
        methods.append("更新脚本逻辑。")
    if any(path.startswith("tests/") for path in paths):
        methods.append("更新测试断言。")
    if any(path.endswith((".md", ".yaml", ".yml")) and ".codex/skills/" in path for path in paths):
        methods.append("更新 skill 文档或参考说明。")
    if any(path.startswith(".codex/unit_test_specs/") for path in paths):
        methods.append("新增或更新任务验收 spec。")
    if any(path.startswith(".codex_record/") for path in paths):
        methods.append("更新线程计划、进度或发现记录。")
    if not methods and paths:
        methods.append(f"修改 {_format_backtick_list(paths, limit=3)}。")
    return methods


def _git_diff_patch_text(state: ReviewBuildState) -> str:
    workspace = state.input_data.workspace.resolve()
    paths = list(dict.fromkeys(state.input_data.changed_paths))
    commands = [
        ["git", "diff", "--", *paths] if paths else ["git", "diff"],
        ["git", "diff", "--cached", "--", *paths] if paths else ["git", "diff", "--cached"],
    ]
    chunks: list[str] = []
    for command in commands:
        result = _run_git(workspace, command)
        if result.stdout:
            chunks.append(result.stdout)
    return "\n".join(chunks)


def _summarize_patch_methods(patch_text: str) -> list[str]:
    methods: list[str] = []
    if not patch_text:
        return methods
    if re.search(r"^\+\s*def\s+\w+", patch_text, flags=re.MULTILINE):
        methods.append("新增函数或辅助逻辑。")
    if re.search(r"^-\s*def\s+\w+", patch_text, flags=re.MULTILINE):
        methods.append("删除函数或辅助逻辑。")
    if re.search(r"^\+\s*class\s+\w+", patch_text, flags=re.MULTILINE):
        methods.append("新增类或数据结构。")
    if re.search(r"^\+\s*assert\b", patch_text, flags=re.MULTILINE):
        methods.append("新增或加强测试断言。")
    if re.search(r"^\+\s*[-*]\s+", patch_text, flags=re.MULTILINE):
        methods.append("更新 Markdown 规则或文档说明。")
    if "evidence" in patch_text or "证据" in patch_text:
        methods.append("调整 reliable-check evidence 生成或展示。")
    return methods


def _extract_path_like_tokens(text: str) -> list[str]:
    candidates = re.findall(r"`([^`]+)`", text)
    if not candidates:
        candidates = text.replace(",", " ").split()
    paths: list[str] = []
    for candidate in candidates:
        stripped = candidate.strip().strip("，。；:：")
        if not stripped:
            continue
        if not re.search(r"[A-Za-z0-9_.]", stripped):
            continue
        if stripped.startswith((".codex/", ".codex_record/", "src/", "tests/", "scripts/")):
            paths.append(stripped)
        elif "/" in stripped and not stripped.startswith(("http://", "https://")):
            paths.append(stripped)
    return paths


def _extract_required_command_parameters(context_files: list[ContextFile]) -> list[dict[str, str]]:
    requirements: list[dict[str, str]] = []
    for context_file in context_files:
        if context_file.status != "present":
            continue
        if context_file.label not in {"task_plan", "idea_plan"}:
            continue
        source = CONTEXT_FILE_LABELS_ZH.get(context_file.label, context_file.label)
        for command in _extract_parameter_requirement_commands(context_file.excerpt):
            for name, value in _extract_parameters_from_command(command).items():
                if value and not _looks_like_placeholder_parameter(name, value[-1]):
                    requirements.append({"name": name, "value": value[-1], "source": source})
    deduped: dict[tuple[str, str, str], dict[str, str]] = {}
    for requirement in requirements:
        key = (requirement["name"], requirement["value"], requirement["source"])
        deduped[key] = requirement
    return list(deduped.values())


def _extract_parameter_requirement_commands(text: str) -> list[str]:
    commands: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if "--" not in line:
            index += 1
            continue
        lowered = line.lower()
        if not any(marker in lowered for marker in PARAMETER_REQUIREMENT_MARKERS):
            index += 1
            continue
        matches = [match.strip() for match in re.findall(r"`([^`]*--[^`]*)`", line)]
        if matches:
            commands.extend(matches)
        else:
            commands.append(line)
        index += 1
        while index < len(lines):
            continuation = lines[index].strip()
            if not continuation or continuation.startswith("#") or continuation.startswith("|"):
                break
            if "--" not in continuation:
                break
            if any(marker in continuation.lower() for marker in PARAMETER_REQUIREMENT_MARKERS):
                break
            if continuation.startswith(("-", "*")) or "`" in continuation:
                matches = [
                    match.strip() for match in re.findall(r"`([^`]*--[^`]*)`", continuation)
                ]
                commands.extend(matches or [continuation])
                index += 1
                continue
            break
    return commands


def _looks_like_placeholder_parameter(name: str, value: str) -> bool:
    normalized_name = name.lower().strip()
    normalized_value = value.strip().strip("`").strip("'\"").lower()
    if normalized_name in PARAMETER_PLACEHOLDER_NAMES:
        return True
    if normalized_value in PARAMETER_PLACEHOLDER_VALUES:
        return True
    if normalized_name.startswith("--") and normalized_name.lstrip("-") in {
        "flag",
        "param",
        "parameter",
        "placeholder",
        "value",
        "arg",
        "foo",
        "bar",
        "baz",
        "test",
        "example",
        "sample",
    }:
        return True
    return False


def _extract_observed_command_parameters(test_commands: list[str]) -> dict[str, list[str]]:
    observed: dict[str, list[str]] = {}
    for command in test_commands:
        for name, values in _extract_parameters_from_command(command).items():
            observed.setdefault(name, []).extend(value for value in values if value)
    return {name: list(dict.fromkeys(values)) for name, values in observed.items()}


def _extract_parameters_from_command(command: str) -> dict[str, list[str]]:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    params: dict[str, list[str]] = {}
    index = 0
    while index < len(parts):
        part = parts[index]
        if not part.startswith("--") or part == "--":
            index += 1
            continue
        if "=" in part:
            name, value = part.split("=", 1)
            params.setdefault(name, []).append(value)
            index += 1
            continue
        name = part
        value = "true"
        if index + 1 < len(parts) and not parts[index + 1].startswith("-"):
            value = parts[index + 1]
            index += 1
        params.setdefault(name, []).append(value)
        index += 1
    return params


def _overlap_matches(left: str, right: str) -> list[str]:
    normalized_left = left.replace("/", " ").replace("-", " ").replace("_", " ").lower()
    normalized_right = right.lower()
    ascii_tokens = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9.]*", normalized_left)
        if len(token) >= 4
        and not token.startswith(".")
        and token not in ALIGNMENT_STOP_TOKENS
        and not any(char.isdigit() for char in token)
        and not token.endswith((".py", ".md"))
    }
    cjk_tokens = {
        term for term in CJK_ALIGNMENT_TERMS if term in left and term in normalized_right
    }
    matches = [token for token in sorted(ascii_tokens) if token in normalized_right]
    return [*sorted(cjk_tokens), *matches]


def _runtime_alignment_text(runtime_evidence: list[RuntimeEvidence]) -> str:
    chunks: list[str] = []
    for item in runtime_evidence:
        chunks.append(item.label)
        chunks.append(item.path)
        chunks.extend(item.commands)
        chunks.append(json.dumps(item.parameters, ensure_ascii=False))
        chunks.append(json.dumps(item.facts, ensure_ascii=False))
        chunks.append(item.excerpt)
    return "\n".join(chunks)


def _runtime_idea_alignment_evidence(
    idea_plan_text: str, runtime_evidence: list[RuntimeEvidence], objective: str
) -> list[str]:
    if not idea_plan_text or not runtime_evidence:
        return []
    normalized_idea = idea_plan_text.lower()
    normalized_objective = objective.lower()
    evidence: list[str] = []
    for item in runtime_evidence:
        if item.status != "present":
            continue
        for fact_key, fact_value in item.facts.items():
            values = fact_value if isinstance(fact_value, list) else [fact_value]
            for value in values:
                value_text = str(value)
                if not value_text or value_text == "[REDACTED]":
                    continue
                value_lower = value_text.lower()
                if value_lower in normalized_idea or value_lower in normalized_objective:
                    evidence.append(
                        f"运行产物 `{item.path}` 的 `{fact_key}={_clip_inline(value_text, limit=120)}` 与科研计划或当前目标一致。"
                    )
        for name, values in item.parameters.items():
            for value in values:
                value_lower = value.lower()
                if value_lower in normalized_idea or value_lower in normalized_objective:
                    evidence.append(
                        f"运行产物 `{item.path}` 的实际参数 `{name}={value}` 与科研计划或当前目标一致。"
                    )
        if item.label == "tau_bench" and ("tau" in normalized_idea or "tau" in normalized_objective):
            evidence.append(f"运行产物 `{item.path}` 明确属于 tau bench / tau2 评测。")
        if item.label in {"qz_training", "qz_deployment"} and any(
            marker in normalized_idea or marker in normalized_objective
            for marker in ("qz", "qizhi", "启智", "训练", "部署", "train", "deploy")
        ):
            evidence.append(
                f"运行产物 `{item.path}` 明确属于 {_runtime_evidence_label_zh(item.label)}。"
            )
        if item.label == "contextswarm_live" and any(
            marker in normalized_idea or marker in normalized_objective
            for marker in ("contextswarm", "icpc", "live", "judge")
        ):
            evidence.append(f"运行产物 `{item.path}` 明确属于 ContextSwarm live 运行。")
    return list(dict.fromkeys(evidence))


def _filtered_idea_relevance_text(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(marker in lowered for marker in IDEA_METADATA_LINE_MARKERS):
            continue
        lines.append(stripped)
    return "\n".join(lines).lower()


def _looks_like_research_task(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "experiment",
            "hypothesis",
            "research",
            "benchmark",
            "audit",
            "eval",
            "data quality",
            "training data",
            "实验",
            "假设",
            "科研",
            "评测",
            "审计",
            "数据质量",
            "训练数据",
            "坏模式",
        )
    )


def _looks_like_runtime_task(text: str) -> bool:
    lowered = text.lower()
    runtime_markers = (
        "qz",
        "qizhi",
        "启智",
        "deploy",
        "deployment",
        "部署",
        "tau",
        "tau2",
        "contextswarm live",
        "live_context",
        "live_context_report",
        "live_preflight_report",
        "评测",
    )
    qwen3_training = "qwen3" in lowered and any(
        marker in lowered for marker in ("train", "training", "训练")
    )
    return any(marker in lowered for marker in runtime_markers) or qwen3_training


def _looks_like_readonly_data_audit_task(text: str) -> bool:
    lowered = text.lower()
    readonly_markers = ("read-only", "readonly", "只读", "no training", "no qz", "不启动", "不提交")
    return _looks_like_data_quality_audit_task(lowered) and any(
        marker in lowered for marker in readonly_markers
    )


def _looks_like_data_quality_audit_task(text: str) -> bool:
    lowered = text.lower()
    audit_markers = ("audit", "审计", "data quality", "数据质量", "坏模式")
    data_markers = ("parquet", "dataset", "训练数据", "schema", "数据")
    return any(marker in lowered for marker in audit_markers) and any(
        marker in lowered for marker in data_markers
    )


def _looks_like_runtime_experiment_task(text: str) -> bool:
    return _looks_like_runtime_task(text) and _looks_like_research_task(text)


def _looks_like_reliable_check_implementation_task(text: str) -> bool:
    lowered = text.lower()
    if _looks_like_data_quality_audit_task(lowered):
        return False
    reliable_markers = (
        "reliable check",
        "code-review-with-logs",
        "可靠检查",
    )
    action_markers = (
        "extend",
        "implement",
        "update",
        "fix",
        "skill",
        "扩展",
        "实现",
        "修改",
        "新增",
        "更新",
        "补充",
        "skill",
        "检查逻辑",
        "单测",
        "unit test",
    )
    scope_markers = (
        "qz",
        "tau",
        "swe",
        "训练",
        "部署",
        "benchmark",
        "summary",
        "completion",
        "delivery",
        "message",
        "feishu",
        "飞书",
        "汇报",
        "报告",
        "摘要",
    )
    return (
        any(marker in lowered for marker in reliable_markers)
        and any(marker in lowered for marker in action_markers)
        and any(marker in lowered for marker in scope_markers)
    )


def _idea_not_applicable_or_fail_details(research_like: bool, has_token_match: bool) -> str:
    if research_like:
        return "检测到 .codex_idea 文件，但科研计划与当前科研/实验任务没有可核对匹配。"
    if has_token_match:
        return (
            "检测到 .codex_idea 文件，但当前任务不是科研/实验任务；"
            "本次不因通用 token 重合而判定科研记录适用。"
        )
    return "检测到 .codex_idea 文件，但科研计划与当前非科研任务没有可核对匹配；本次不纳入一致性判定。"


def _first_content_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().strip("-").strip()
        if stripped and not stripped.startswith("#"):
            return _clip_inline(stripped, limit=160)
    return "未发现可摘要的科研计划内容"


def _render_reliable_check_reviewer_markdown(results: dict[str, Any]) -> str:
    lines = [
        f"状态：{STATUS_TEXT_ZH.get(str(results['status']), results['status'])}",
        "",
        "检查项：",
    ]
    for check in results["checks"]:
        lines.append(f"- {check['display_name']}：{check['status_text']}")
        lines.append(f"  说明：{_wrap_reviewer_text(str(check['details']))}")
        evidence = check.get("evidence") or []
        if evidence:
            lines.append("  证据：")
            for item in evidence:
                lines.append(f"  - {_wrap_reviewer_text(str(item))}")

    lines.extend(["", "命令参数核对："])
    required = results.get("required_command_parameters", [])
    missing = results.get("missing_required_parameters", [])
    unexpected = results.get("unexpected_parameter_values", [])
    observed = results.get("observed_command_parameters", {})
    observed_sources = results.get("observed_command_parameter_sources", {})
    if not required:
        lines.append("- 未发现明确的命令参数要求。")
    else:
        lines.append("- 要求参数：")
        for item in required:
            lines.append(f"  - `{item['name']}={item['value']}`（来源：{item['source']}）")
        lines.append("- 实际参数：")
        for name in sorted(observed):
            source_text = _parameter_source_text(observed_sources.get(name, {}))
            lines.append(f"  - `{name}={', '.join(observed[name])}`{source_text}")
        if missing:
            lines.append("- 缺少参数：")
            for item in missing:
                lines.append(f"  - `{item['name']}={item['value']}`（来源：{item['source']}）")
        if unexpected:
            lines.append("- 参数值不一致：")
            for item in unexpected:
                observed_values = ", ".join(item["observed"])
                lines.append(
                    f"  - `{item['name']}` 期望 `{item['expected']}`，实际 `{observed_values}`"
                )

    runtime_evidence = results.get("runtime_evidence", [])
    if runtime_evidence:
        lines.extend(["", "运行证据："])
        for item in runtime_evidence:
            summary_item = RuntimeEvidence(
                label=str(item.get("label", "runtime_artifact")),
                path=str(item.get("path", "")),
                status=str(item.get("status", "")),
                excerpt=str(item.get("excerpt", "")),
                commands=list(item.get("commands", [])),
                parameters=dict(item.get("parameters", {})),
                facts=dict(item.get("facts", {})),
            )
            lines.append(f"- {_wrap_reviewer_text(_runtime_evidence_summary(summary_item))}")

    context_files = results.get("context_files", [])
    if context_files:
        lines.extend(["", "读取的上下文："])
        for item in context_files:
            lines.append(
                f"- {item.get('label_zh', item['label'])}：{item.get('status_text', item['status'])}"
            )
    return "\n".join(lines)


def _wrap_reviewer_text(text: str, *, limit: int = 120) -> str:
    if len(text) <= limit:
        return text
    chunks = [
        text[index : index + limit].rstrip()
        for index in range(0, len(text), limit)
    ]
    return "\n  ".join(chunks)


def _has_overlap(left: str, right: str) -> bool:
    return bool(_overlap_matches(left, right))


def _combine_status(statuses: list[str]) -> str:
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if any(status == "BLOCKED" for status in statuses):
        return "BLOCKED"
    if statuses and all(status == "NOT_APPLICABLE" for status in statuses):
        return "NOT_APPLICABLE"
    return "PASS"


def _build_report(state: ReviewBuildState) -> dict[str, Any]:
    test_status = str(state.unit_test_results.get("status", "BLOCKED"))
    reliable_status = str(state.reliability_results.get("status", "BLOCKED"))
    status = _combine_status([test_status, reliable_status])
    report = {
        "schema_version": "2.0",
        "review_id": state.review_id,
        "session_id": state.input_data.session_id,
        "session_dir": _relativize(state.session_dir, state.input_data.workspace.resolve()),
        "generated_at": utc_now(),
        "status": status,
        "status_context": state.input_data.status_context,
        "fields": {
            "Field": _impacted_fields(state),
            "Why it matters": _why_it_matters(state),
            "Objective": state.input_data.objective
            or _extract_first_heading(
                state.context_files, fallback="Objective not explicitly provided."
            ),
            "Permission boundary": state.input_data.permission_boundary
            or (
                "Allowed: read session records/logs/diffs and run caller-provided "
                "unit-test commands. Blocked: benchmark runs, secret access, "
                "unrelated file edits."
            ),
            "Plan changes": _plan_changes(state),
            "command trace": state.command_trace,
            "Diff summary": state.diff_summary,
            "Tests and evals": state.unit_test_results,
            "Cost and retries": _cost_and_retries(state),
            "Rollback path": _rollback_path(state),
            "reliable check": state.reliability_results,
        },
    }
    missing_fields = [field for field in REPORT_FIELDS if field not in report["fields"]]
    if missing_fields:
        raise RuntimeError(f"missing report fields: {missing_fields}")
    return report


def _impacted_fields(state: ReviewBuildState) -> str:
    impacted_paths = _impacted_paths(state)
    if impacted_paths:
        lines = ["Impacted modules/paths/fields:"]
        lines.extend(f"- `{path}`" for path in impacted_paths)
        return "\n".join(lines)
    return (
        "Impact could not be localized from changed paths; inspect the diff summary "
        "before relying on this review."
    )


def _why_it_matters(state: ReviewBuildState) -> str:
    impacted_paths = _impacted_paths(state)
    objective = state.input_data.objective or _extract_first_heading(
        state.context_files, fallback="the requested task objective"
    )
    if impacted_paths:
        lines = ["Objective mapping by impacted module:"]
        lines.extend(
            f"- `{path}`: {_module_goal_mapping(path, objective)}" for path in impacted_paths
        )
        return "\n".join(lines)
    return (
        "No impacted module mapping could be derived from changed paths or git diff evidence; "
        "the user-objective alignment depends on the reliable check and diff summary."
    )


def _impacted_paths(state: ReviewBuildState) -> list[str]:
    if state.input_data.changed_paths:
        return list(dict.fromkeys(state.input_data.changed_paths))

    names = str(state.diff_summary.get("git_diff_name_status") or "").strip()
    paths: list[str] = []
    for line in names.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            paths.append(parts[-1])
    return list(dict.fromkeys(paths))


def _module_goal_mapping(path: str, objective: str) -> str:
    if path.endswith("scripts/code_review_with_logs.py"):
        return (
            "generates the Markdown and JSON report fields, so it directly determines "
            f"whether `Field` and `Why it matters` satisfy `{objective}`."
        )
    if path.endswith("scripts/report_review_result.py"):
        return (
            "validates generated report JSON, so it prevents the legacy misleading field "
            f"contract from being accepted for `{objective}`."
        )
    if path.endswith("SKILL.md") and "code-review-with-logs" in path:
        return (
            "documents the skill workflow and report contract, so future agents apply the "
            f"correct field semantics for `{objective}`."
        )
    if "review-report-contract.md" in path:
        return (
            "defines the durable report schema, so downstream report readers use the corrected "
            f"`Field` and `Why it matters` meanings for `{objective}`."
        )
    if "review_summary.template.md" in path:
        return (
            "templates the human-readable report, so new Markdown summaries present impacted "
            f"modules and objective mapping in the corrected sections for `{objective}`."
        )
    if path.startswith("tests/"):
        return (
            "contains regression coverage, so the corrected report semantics remain enforced "
            f"when `{objective}` changes are tested."
        )
    if ".codex/unit_test_specs/" in path:
        return (
            "captures the task acceptance gate, so the requested field semantics are checked "
            f"as a falsifiable contract for `{objective}`."
        )
    if ".codex_record/" in path:
        return (
            "records task traceability and review evidence, so the correction remains auditable "
            f"against `{objective}`."
        )
    return f"maps to the task surface that must be reviewed to satisfy `{objective}`."


def _extract_first_heading(context_files: list[ContextFile], *, fallback: str) -> str:
    for context_file in context_files:
        if context_file.label != "task_plan" or context_file.status != "present":
            continue
        for line in context_file.excerpt.splitlines():
            stripped = line.strip("# ").strip()
            if stripped and stripped.lower() not in {"task plan", "goal"}:
                return stripped
    return fallback


def _plan_changes(state: ReviewBuildState) -> str:
    progress = next((item.excerpt for item in state.context_files if item.label == "progress"), "")
    markers = [
        line.strip("- ")
        for line in progress.splitlines()
        if "plan" in line.lower() or "decision" in line.lower()
    ]
    if markers:
        return _clip("; ".join(markers), limit=1200)
    return "No explicit plan-change markers found in progress.md."


def _cost_and_retries(state: ReviewBuildState) -> dict[str, Any]:
    failed_count = sum(
        1
        for result in state.unit_test_results.get("results", [])
        if int(result.get("exit_code", 1)) != 0
    )
    return {
        "unit_test_command_count": state.unit_test_results.get("command_count", 0),
        "failed_unit_test_count": failed_count,
        "log_file_count": len(state.log_summaries),
        "retry_signal": "failed commands present"
        if failed_count
        else "no failed test retries detected",
    }


def _rollback_path(state: ReviewBuildState) -> str:
    changed = state.input_data.changed_paths
    if changed:
        return (
            "Rollback by reverting the task commit or restoring these task-owned paths: "
            + ", ".join(changed)
        )
    return (
        "Rollback by reverting the task commit; no explicit changed paths were supplied "
        "to narrow the rollback."
    )


def _render_markdown_report(
    report: dict[str, Any],
    *,
    task_completion_summary: str | None = None,
) -> str:
    fields = report["fields"]
    lines = [
        "# Code Review With Logs Report",
        "",
        f"- Final Status: {report['status']}",
        f"- Review ID: {report['review_id']}",
        f"- Session ID: {report['session_id']}",
        f"- Generated At: {report['generated_at']}",
        f"- Status Context: {report['status_context']}",
        "",
        "## Task completion summary",
        _task_completion_summary_for_report(
            report,
            task_completion_summary=task_completion_summary,
        ),
        "",
    ]
    for field_name in REPORT_FIELDS:
        value = fields[field_name]
        lines.append(f"## {field_name}")
        if field_name == "reliable check" and isinstance(value, dict):
            lines.append(str(value.get("reviewer_markdown") or "未生成可靠性检查摘要。"))
        elif isinstance(value, str):
            lines.append(value)
        else:
            lines.append("```json")
            lines.append(json.dumps(value, ensure_ascii=False, indent=2))
            lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _task_completion_summary_for_report(
    report: dict[str, Any],
    *,
    task_completion_summary: str | None = None,
) -> str:
    explicit = _clean_task_completion_summary(task_completion_summary)
    if explicit:
        return explicit
    return _detailed_task_completion_summary(report)


def _detailed_task_completion_summary(report: dict[str, Any]) -> str:
    fields = report["fields"]
    status = str(report.get("status") or "UNKNOWN").upper()
    evidence = _completion_evidence_bullets(report)
    lines = [_task_completion_headline(status), "", "完成证据如下：", ""]
    lines.extend(f"- {item}" for item in evidence)
    if status != "PASS":
        lines.append(f"- 需要关注：{_attention_summary_for_report(status, fields)}")
    else:
        lines.append("可以把本报告作为当前任务的收口证据。")
    return "\n".join(lines)


def _task_completion_headline(status: str) -> str:
    if status == "PASS":
        return "已完成当前任务，并已按当前状态逐项复核后标记为 complete。"
    if status == "FAIL":
        return "当前任务未完成。以下摘要列出已执行内容、失败证据和仍需修复的问题。"
    if status == "BLOCKED":
        return "当前任务收口被阻塞。以下摘要列出已完成内容和缺失的阻塞证据。"
    return "当前任务状态未完全适用。以下摘要列出可用证据。"


def _completion_evidence_bullets(report: dict[str, Any]) -> list[str]:
    fields = report["fields"]
    bullets: list[str] = []
    objective = _field_text_for_summary(fields, "Objective", fallback="未提供明确目标。")
    bullets.append(f"任务目标：{objective}")
    bullets.extend(_runtime_completion_evidence(fields.get("reliable check")))
    work_summary = _work_summary_for_report(fields)
    if work_summary:
        bullets.append(f"改动范围：{work_summary}")
    bullets.append(f"测试与评估：{_tests_summary_for_report(fields.get('Tests and evals'))}")
    bullets.append(f"可靠性检查：{_reliable_summary_for_report(fields.get('reliable check'))}")
    review_id = str(report.get("review_id") or "").strip()
    review_status = str(report.get("status") or "UNKNOWN").upper()
    if review_id:
        bullets.append(
            f"formal review：review id `{review_id}`，状态 {STATUS_TEXT_ZH.get(review_status, review_status)}。"
        )
    return _dedupe_list([item for item in bullets if item.strip()])


def _runtime_completion_evidence(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    items = value.get("runtime_evidence")
    if not isinstance(items, list):
        return []
    bullets: list[str] = []
    for raw_item in items:
        if not isinstance(raw_item, dict) or raw_item.get("status") != "present":
            continue
        path = str(raw_item.get("path") or "").strip()
        facts = raw_item.get("facts") if isinstance(raw_item.get("facts"), dict) else {}
        commands = raw_item.get("commands") if isinstance(raw_item.get("commands"), list) else []
        bullets.extend(_runtime_item_completion_bullets(path, facts, commands))
    return bullets


def _runtime_item_completion_bullets(
    path: str,
    facts: dict[str, Any],
    commands: list[Any],
) -> list[str]:
    bullets: list[str] = []
    command_text = " ".join(str(command) for command in commands)
    benchmark_values = _fact_values(facts, "benchmark")
    status_values = _fact_values(facts, "status")
    text = " ".join(
        [
            path,
            command_text,
            " ".join(benchmark_values),
            " ".join(status_values),
            _fact_text(facts, "config_path"),
            _fact_text(facts, "user_llm"),
            _fact_text(facts, "user_model"),
            _fact_text(facts, "job_id"),
        ]
    ).lower()

    if _looks_like_swe_runtime(text, facts):
        bullets.append(_swe_completion_bullet(path, facts))
    if _looks_like_tau_runtime(text, facts):
        bullets.append(_tau_completion_bullet(path, facts))
    if _looks_like_training_retry_runtime(text, facts):
        bullets.append(_training_retry_completion_bullet(path, facts))
    if _looks_like_training_triage_runtime(text, facts):
        bullets.append(_training_triage_completion_bullet(path, facts))
    if _looks_like_cleanup_runtime(facts) and not (
        _looks_like_swe_runtime(text, facts) or _looks_like_tau_runtime(text, facts)
    ):
        bullets.append(_cleanup_completion_bullet(path, facts))
    if _looks_like_contextswarm_live_runtime(text, facts):
        bullets.append(_contextswarm_live_completion_bullet(path, facts))
    if not bullets and facts:
        bullets.append(_generic_runtime_completion_bullet(path, facts))
    return bullets


def _looks_like_contextswarm_live_runtime(text: str, facts: dict[str, Any]) -> bool:
    return (
        "contextswarm" in text
        or "live_context" in text
        or bool(_fact_text(facts, "preflight_ready"))
        or bool(_fact_text(facts, "judge_status"))
        or bool(_fact_text(facts, "worker_status"))
    )


def _looks_like_swe_runtime(text: str, facts: dict[str, Any]) -> bool:
    return (
        "swe" in text
        or bool(_fact_text(facts, "config_path"))
        or bool(_fact_text(facts, "resolved_instances"))
    )


def _looks_like_tau_runtime(text: str, facts: dict[str, Any]) -> bool:
    return (
        "tau" in text
        or bool(_fact_text(facts, "user_llm"))
        or bool(_fact_text(facts, "user_model"))
        or bool(_fact_text(facts, "average_reward"))
    )


def _looks_like_training_retry_runtime(text: str, facts: dict[str, Any]) -> bool:
    return (
        "candidate_job_ids" in facts
        or "candidate_status" in facts
        or "job_queuing" in text
        or "scheduler_blocked" in text
    )


def _looks_like_training_triage_runtime(text: str, facts: dict[str, Any]) -> bool:
    return (
        bool(_fact_text(facts, "job_id"))
        and (
            "job_stopped" in text
            or "error_summary" in facts
            or "output_target_exists" in facts
        )
    )


def _looks_like_cleanup_runtime(facts: dict[str, Any]) -> bool:
    return bool(_fact_text(facts, "deployment_status_after_cleanup")) or bool(
        _fact_text(facts, "resource_stopped")
    )


def _swe_completion_bullet(path: str, facts: dict[str, Any]) -> str:
    parts = ["SWE-Bench 已完成或已有运行证据"]
    config = _fact_text(facts, "config_path")
    if config:
        parts.append(f"config_path={config}")
    metrics = _count_triplet(facts, "resolved_instances", "completed_instances", "total_instances")
    if metrics:
        parts.append(metrics)
    errors = _fact_text(facts, "error_ids") or _fact_text(facts, "error_instances")
    if errors:
        parts.append(f"error={errors}")
    cleanup = _cleanup_status_text(facts)
    if cleanup:
        parts.append(cleanup)
    return _artifact_prefix(path) + "，".join(parts) + "。"


def _tau_completion_bullet(path: str, facts: dict[str, Any]) -> str:
    parts = ["tau2/tau-bench 已完成或已有运行证据"]
    user = _fact_text(facts, "user_llm") or _fact_text(facts, "user_model")
    if user:
        parts.append(f"user_llm={user}")
    simulations = _count_pair(facts, "completed_simulations", "total_simulations")
    if simulations:
        parts.append(f"{simulations} simulations")
    reward = _fact_text(facts, "average_reward")
    if reward:
        parts.append(f"average reward {reward}")
    timeout = _count_pair(facts, "timeout_count", "timeout_limit")
    if timeout:
        parts.append(f"timeout-like {timeout}")
    stopped = _fact_text(facts, "stopped_due_to_timeouts")
    if stopped:
        parts.append(f"stopped_due_to_timeouts={stopped}")
    cleanup = _cleanup_status_text(facts)
    if cleanup:
        parts.append(cleanup)
    return _artifact_prefix(path) + "，".join(parts) + "。"


def _training_retry_completion_bullet(path: str, facts: dict[str, Any]) -> str:
    job_ids = _fact_values(facts, "candidate_job_ids") or _fact_values(facts, "job_id")
    status = _fact_text(facts, "candidate_status") or _fact_text(facts, "status")
    parts = ["训练已排队"]
    if job_ids:
        parts.append("job_ids=" + "、".join(job_ids))
    if status:
        parts.append(status)
    pool_note = _fact_text(facts, "blocked_pool_note")
    if pool_note:
        parts.append(pool_note)
    return _artifact_prefix(path) + "，".join(parts) + "。"


def _training_triage_completion_bullet(path: str, facts: dict[str, Any]) -> str:
    parts = ["失败训练 job 已检查"]
    for key, label in (
        ("job_id", "job_id"),
        ("status", "status"),
        ("pool", "pool"),
        ("gpu_count", "gpu_count"),
        ("output_target_exists", "output_target_exists"),
    ):
        value = _fact_text(facts, key)
        if value:
            parts.append(f"{label}={value}")
    error_summary = _fact_text(facts, "error_summary")
    if error_summary:
        parts.append(_clip_inline(error_summary, limit=320))
    return _artifact_prefix(path) + "，".join(parts) + "。"


def _cleanup_completion_bullet(path: str, facts: dict[str, Any]) -> str:
    cleanup = _cleanup_status_text(facts)
    return _artifact_prefix(path) + f"资源清理状态已记录：{cleanup or '见运行产物'}。"


def _contextswarm_live_completion_bullet(path: str, facts: dict[str, Any]) -> str:
    parts = ["ContextSwarm live 运行证据已读取"]
    for key, label in (
        ("project_id", "project_id"),
        ("scheduler", "scheduler"),
        ("task_count", "task_count"),
        ("ready", "ready"),
        ("preflight_ready", "preflight_ready"),
        ("status", "status"),
        ("skipped_reason", "skipped_reason"),
        ("worker_status", "worker_status"),
        ("judge_status", "judge_status"),
        ("accepted", "accepted"),
    ):
        value = _fact_text(facts, key)
        if value:
            parts.append(f"{label}={value}")
    return _artifact_prefix(path) + "，".join(parts) + "。"


def _generic_runtime_completion_bullet(path: str, facts: dict[str, Any]) -> str:
    rendered = []
    for key in (
        "status",
        "benchmark",
        "model",
        "run_id",
        "run_tag",
        "average_reward",
        "completed_simulations",
        "total_simulations",
    ):
        value = _fact_text(facts, key)
        if value:
            rendered.append(f"{key}={value}")
    if not rendered:
        rendered = [f"{key}={_jsonish_inline(value)}" for key, value in list(facts.items())[:8]]
    return _artifact_prefix(path) + "运行产物已读取：" + "，".join(rendered) + "。"


def _artifact_prefix(path: str) -> str:
    return f"产物 `{path}` 记录：" if path else ""


def _cleanup_status_text(facts: dict[str, Any]) -> str:
    status = _fact_text(facts, "deployment_status_after_cleanup")
    stopped = _fact_text(facts, "resource_stopped")
    if status and stopped:
        return f"deployment cleanup={status}, resource_stopped={stopped}"
    if status:
        return f"deployment cleanup={status}"
    if stopped:
        return f"resource_stopped={stopped}"
    return ""


def _count_triplet(facts: dict[str, Any], first: str, second: str, total: str) -> str:
    first_value = _fact_text(facts, first)
    second_value = _fact_text(facts, second)
    total_value = _fact_text(facts, total)
    parts = []
    if first_value and total_value:
        parts.append(f"{first.replace('_instances', '')}={first_value}/{total_value}")
    elif first_value:
        parts.append(f"{first}={first_value}")
    if second_value and total_value:
        parts.append(f"{second.replace('_instances', '')}={second_value}/{total_value}")
    elif second_value:
        parts.append(f"{second}={second_value}")
    return "，".join(parts)


def _count_pair(facts: dict[str, Any], first: str, second: str) -> str:
    first_value = _fact_text(facts, first)
    second_value = _fact_text(facts, second)
    if first_value and second_value:
        return f"{first_value}/{second_value}"
    if first_value:
        return first_value
    return ""


def _fact_text(facts: dict[str, Any], key: str) -> str:
    if key not in facts:
        return ""
    value = facts[key]
    if isinstance(value, list):
        return _jsonish_inline(value[0]) if value else ""
    return _jsonish_inline(value)


def _fact_values(facts: dict[str, Any], key: str) -> list[str]:
    if key not in facts:
        return []
    value = facts[key]
    if isinstance(value, list):
        return [_jsonish_inline(item) for item in value if item not in (None, "")]
    if isinstance(value, dict):
        return [_jsonish_inline(value)]
    if value in (None, ""):
        return []
    return [str(value)]


def _field_text_for_summary(
    fields: dict[str, Any],
    field_name: str,
    *,
    fallback: str,
) -> str:
    value = fields.get(field_name)
    if isinstance(value, str):
        return " ".join(value.split()) or fallback
    if value is None:
        return fallback
    return " ".join(json.dumps(value, ensure_ascii=False).split()) or fallback


def _work_summary_for_report(fields: dict[str, Any]) -> str:
    impacted = _summary_items_from_bullets(str(fields.get("Field") or ""))
    if impacted:
        return "涉及 " + "、".join(f"`{item}`" for item in impacted[:6]) + "。"
    diff_summary = fields.get("Diff summary")
    if isinstance(diff_summary, dict):
        requested = diff_summary.get("changed_paths_requested")
        if isinstance(requested, list) and requested:
            return "涉及 " + "、".join(f"`{str(item)}`" for item in requested[:6]) + "。"
        stat = str(diff_summary.get("git_diff_stat") or "").strip()
        if stat:
            return _clip_inline(stat, limit=280)
    return ""


def _summary_items_from_bullets(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        item = stripped[2:].strip().strip("`")
        if item:
            items.append(item)
    return items


def _tests_summary_for_report(value: Any) -> str:
    if not isinstance(value, dict):
        return "测试结果结构不可读，请查看完整 `Tests and evals` section。"
    status = str(value.get("status") or "UNKNOWN").upper()
    command_count = value.get("command_count", 0)
    details = str(value.get("details") or "").strip()
    commands = []
    for result in value.get("results", []):
        if not isinstance(result, dict):
            continue
        command = str(result.get("command") or "").strip()
        exit_code = result.get("exit_code")
        if command:
            output = _command_output_summary(result)
            suffix = f"，输出摘要：{output}" if output else ""
            commands.append(f"`{command}` -> exit {exit_code}{suffix}")
    status_text = STATUS_TEXT_ZH.get(status, status)
    prefix = f"{status_text}，共 {command_count} 条命令"
    if commands:
        return prefix + "；" + "；".join(commands[:5]) + ("。" if details == "" else f"。{details}")
    return prefix + ("。" if details == "" else f"。{details}")


def _reliable_summary_for_report(value: Any) -> str:
    if not isinstance(value, dict):
        return "可靠性检查结构不可读，请查看完整 `reliable check` section。"
    status = str(value.get("status") or "UNKNOWN").upper()
    status_text = STATUS_TEXT_ZH.get(status, status)
    checks = value.get("checks") if isinstance(value.get("checks"), list) else []
    check_parts: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = str(check.get("display_name") or check.get("name") or "").strip()
        check_status = str(check.get("status_text") or check.get("status") or "").strip()
        if name and check_status:
            check_parts.append(f"{name}{check_status}")
    if check_parts:
        return f"{status_text}；" + "；".join(check_parts[:6]) + "。"
    return f"{status_text}。"


def _command_output_summary(result: dict[str, Any]) -> str:
    for key in ("stdout", "stderr"):
        text = " ".join(str(result.get(key) or "").split())
        if text:
            return _clip_inline(text, limit=180)
    return ""


def _attention_summary_for_report(status: str, fields: dict[str, Any]) -> str:
    tests = fields.get("Tests and evals")
    reliable = fields.get("reliable check")
    parts: list[str] = []
    if isinstance(tests, dict) and str(tests.get("status") or "").upper() != "PASS":
        parts.append("测试/评估未通过或证据不足")
    if isinstance(reliable, dict) and str(reliable.get("status") or "").upper() != "PASS":
        parts.append("可靠性检查未通过或证据不足")
    if parts:
        return "；".join(parts) + "，需先处理完整报告中的对应证据。"
    return f"当前状态为 {status}，需查看完整报告确认剩余动作。"


def _relativize(path: Path, workspace: Path) -> str:
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _clip(value: str, *, limit: int = 3000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _clip_inline(value: str, *, limit: int = 160) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
