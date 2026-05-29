#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import NamedTuple


CORE_AGENTS_TOKENS = [
    "planning-with-files",
    "code-review-with-logs",
    "unit-test",
    "harness-bench",
    "experiment-handbook",
    "refinement",
    "linear-cli",
    "system-contract",
    "uv",
    ".codex_record",
    ".codex_idea",
    "Feishu",
    "Conventional Commits",
]

FORBIDDEN_AGENTSWARM_RECORD_TOKENS = [
    ".agent_record",
    "idea_record/",
    "idea_record<",
    "idea_record <",
]

CONTEXTSWARM_PROJECT_TOKENS = [
    "ContextSwarmJudge",
    "gateway/dashboard",
    "gateway_service.sh",
    "Controller Live RPM Data Plane",
    "Erdos formal",
    "PutnamBench",
    "Verina",
    "USACO",
    "/home/ubuntu/scratch/jingao/ContextSwarm",
]

UV_DISCIPLINE_FILES = [
    "AGENTS.md",
    ".codex/skills/code-review-with-logs/SKILL.md",
    ".codex/skills/unit-test/SKILL.md",
    ".codex/skills/unit-test/assets/templates/task_acceptance_spec.template.md",
    ".codex/skills/code-review-with-logs/scripts/run_code_review_with_logs.sh",
    ".codex/skills/code-review-with-logs/scripts/end_task_review_hook.sh",
    ".codex/skills/linear-cli/scripts/start_task_hook.sh",
]

FORBIDDEN_LOCAL_COMMAND_PATTERNS = [
    re.compile(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)*python3\b"),
    re.compile(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)*python\s+-m\s+(pytest|ruff|mypy|pip)\b"),
    re.compile(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)*pip(?:3)?\s+install\b"),
    re.compile(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)*pytest(?:\s|$)"),
    re.compile(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)*ruff\s+check\b"),
    re.compile(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)*mypy(?:\s|$)"),
    re.compile(r"--test-command\s+['\"](?:[A-Z_][A-Z0-9_]*=\S+\s+)*(python3|python\s+-m\s+(pytest|ruff|mypy|pip)|pytest|ruff\s+check|mypy)\b"),
]

ALLOWED_FORBIDDEN_COMMAND_CONTEXTS = [
    "Do not use",
    "do not use",
    "Do not invoke",
    "do not invoke",
    "禁止",
    "不要",
    "不得",
    "❌",
    "not use",
    "Forbidden",
    "forbidden",
    "bare `pytest`",
    "bare `python`",
    "uv run python",
    "uv run --with",
]

ALLOWED_FORBIDDEN_RECORD_CONTEXTS = [
    "Do not introduce",
    "do not introduce",
    "不要引入",
    "不引入",
    "不得引入",
    "forbidden",
    "禁止",
]

FORBIDDEN_PATH_PARTS = [
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
]

FORBIDDEN_FILE_SUFFIXES = [
    ".pyc",
    ".pyo",
]

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"(?i)\b(api[_-]?key|authorization|password|secret|token)\s*=\s*['\"][^'\"\s;,]{12,}['\"]"),
    re.compile(r"(?i)\bauthorization\s*:\s*['\"]bearer\s+[A-Za-z0-9._~+/=-]{12,}['\"]"),
]

SECRET_SCAN_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


class Failure(NamedTuple):
    check: str
    path: str
    detail: str


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    workspace = Path(args.workspace).resolve()
    failures: list[Failure] = []
    failures.extend(check_agents_contract(workspace))
    failures.extend(check_no_root_system_contract(workspace))
    failures.extend(check_uv_discipline(workspace))
    failures.extend(check_tests_bench_boundary(workspace))
    failures.extend(check_tracked_hygiene(workspace))
    failures.extend(check_secret_like_content(workspace))

    if failures:
        print("System contract: FAIL")
        for failure in failures:
            print(f"- [{failure.check}] {failure.path}: {failure.detail}")
        return 1

    print("System contract: PASS")
    return 0


def check_agents_contract(workspace: Path) -> list[Failure]:
    path = workspace / "AGENTS.md"
    text = _read_text(path)
    failures: list[Failure] = []
    if text is None:
        return [Failure("agents-contract", "AGENTS.md", "missing repository AGENTS.md")]

    for token in CORE_AGENTS_TOKENS:
        if token not in text:
            failures.append(Failure("agents-contract", "AGENTS.md", f"missing required token `{token}`"))

    for line_number, line in enumerate(text.splitlines(), start=1):
        for token in FORBIDDEN_AGENTSWARM_RECORD_TOKENS:
            if token in line and not _is_allowed_forbidden_record_context(line):
                failures.append(
                    Failure(
                        "agents-contract",
                        f"AGENTS.md:{line_number}",
                        f"forbidden record surface `{token}`",
                    )
                )

    for token in CONTEXTSWARM_PROJECT_TOKENS:
        if token in text and "不要迁移" not in text and "not migrate" not in text:
            failures.append(
                Failure(
                    "agents-contract",
                    "AGENTS.md",
                    f"ContextSwarm-specific token `{token}` appears as a possible hard rule",
                )
            )
    return failures


def check_no_root_system_contract(workspace: Path) -> list[Failure]:
    root_script = workspace / "scripts" / "check_system_contract.py"
    if root_script.exists():
        return [
            Failure(
                "system-contract-location",
                "scripts/check_system_contract.py",
                "system contract must live under .codex/skills/system-contract/",
            )
        ]
    skill_script = workspace / ".codex" / "skills" / "system-contract" / "scripts" / "check_system_contract.py"
    if not skill_script.is_file():
        return [
            Failure(
                "system-contract-location",
                ".codex/skills/system-contract/scripts/check_system_contract.py",
                "missing skill-local checker",
            )
        ]
    return []


def check_uv_discipline(workspace: Path) -> list[Failure]:
    failures: list[Failure] = []
    for rel_path in UV_DISCIPLINE_FILES:
        path = workspace / rel_path
        text = _read_text(path)
        if text is None:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or _is_allowed_forbidden_command_context(stripped):
                continue
            command_candidate = _command_candidate(stripped)
            if not command_candidate:
                continue
            for pattern in FORBIDDEN_LOCAL_COMMAND_PATTERNS:
                if pattern.search(command_candidate):
                    failures.append(
                        Failure(
                            "uv-discipline",
                            f"{rel_path}:{line_number}",
                            f"use uv-managed command instead of `{stripped}`",
                        )
                    )
                    break
    return failures


def check_tests_bench_boundary(workspace: Path) -> list[Failure]:
    bench = workspace / "tests" / "bench"
    if not bench.exists():
        return []
    failures: list[Failure] = []
    for path in bench.rglob("*.py"):
        rel = path.relative_to(workspace).as_posix()
        lowered = rel.lower()
        text = _read_text(path) or ""
        if not any(token in lowered or token in text.lower() for token in ["bench", "benchmark", "harness"]):
            failures.append(
                Failure(
                    "tests-bench-boundary",
                    rel,
                    "tests/bench files must clearly be benchmark or harness artifacts",
                )
            )
    return failures


def check_tracked_hygiene(workspace: Path) -> list[Failure]:
    failures: list[Failure] = []
    for rel in _git_tracked_files(workspace):
        parts = set(Path(rel).parts)
        if parts.intersection(FORBIDDEN_PATH_PARTS):
            failures.append(Failure("repo-hygiene", rel, "tracked cache/runtime path"))
        if any(rel.endswith(suffix) for suffix in FORBIDDEN_FILE_SUFFIXES):
            failures.append(Failure("repo-hygiene", rel, "tracked Python bytecode artifact"))
    return failures


def check_secret_like_content(workspace: Path) -> list[Failure]:
    failures: list[Failure] = []
    for rel in _git_tracked_files(workspace):
        path = workspace / rel
        if _is_secret_scan_excluded(path):
            continue
        text = _read_text(path, max_bytes=512_000)
        if text is None:
            continue
        for pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                failures.append(
                    Failure("secret-scan", rel, f"secret-like pattern `{pattern.pattern}`")
                )
                break
    return failures


def _read_text(path: Path, max_bytes: int | None = None) -> str | None:
    try:
        if max_bytes is not None and path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _git_tracked_files(workspace: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _is_allowed_forbidden_command_context(line: str) -> bool:
    return any(marker in line for marker in ALLOWED_FORBIDDEN_COMMAND_CONTEXTS)


def _is_allowed_forbidden_record_context(line: str) -> bool:
    return any(marker in line for marker in ALLOWED_FORBIDDEN_RECORD_CONTEXTS)


def _command_candidate(line: str) -> str:
    candidate = line.strip()
    while candidate.startswith("- "):
        candidate = candidate[2:].strip()
    if candidate.startswith("-"):
        return candidate
    if candidate.startswith(("`", '"', "'")) and candidate.endswith(("`", '"', "'")):
        candidate = candidate[1:-1].strip()
    command_starts = (
        "python",
        "python3",
        "pip",
        "pip3",
        "pytest",
        "ruff",
        "mypy",
        "PYTEST_",
    )
    if candidate.startswith(command_starts) or "--test-command" in candidate:
        return candidate
    return ""


def _is_secret_scan_excluded(path: Path) -> bool:
    return any(part in SECRET_SCAN_EXCLUDED_PARTS for part in path.parts)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AgentSwarm system contract checks.")
    parser.add_argument("--workspace", default=".")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
