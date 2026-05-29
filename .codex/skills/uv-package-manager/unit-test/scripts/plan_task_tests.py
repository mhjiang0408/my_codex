#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = "config/pipeline.yaml"
DEFAULT_REPO_RUFF_COMMAND = "python -m ruff check src tests"
DEFAULT_REPO_MYPY_COMMAND = "python -m mypy src tests .codex/skills"
DEFAULT_REPO_PYTEST_COMMAND = "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q"
ALLOWED_TEST_KINDS = {"logic_regression", "performance_threshold", "real_api_regression"}


def _read_frontmatter(spec_path: Path) -> tuple[dict[str, Any], str]:
    raw = spec_path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{spec_path} is missing YAML frontmatter")
    end = raw.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"{spec_path} has an unterminated YAML frontmatter block")
    payload = yaml.safe_load(raw[4:end]) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{spec_path} frontmatter must decode to a mapping")
    body = raw[end + 5 :]
    return payload, body


def _read_json_mapping(spec_path: Path) -> dict[str, Any]:
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{spec_path} must decode to a JSON object")
    return payload


def _list_of_strings(value: Any, *, field: str, required: bool = False) -> list[str]:
    if value is None:
        if required:
            raise ValueError(f"missing required field: {field}")
        return []
    if not isinstance(value, list):
        raise ValueError(f"field {field} must be a list of strings")
    cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if required and not cleaned:
        raise ValueError(f"field {field} must be a non-empty list of strings")
    return cleaned


def _validate_test_kind(value: str) -> str:
    if value not in ALLOWED_TEST_KINDS:
        allowed_text = ", ".join(sorted(ALLOWED_TEST_KINDS))
        raise ValueError(f"test_kind must be one of: {allowed_text}")
    return value


def _join_command(parts: list[str], prefix: str) -> list[str]:
    cleaned = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
    if not cleaned:
        return []
    return [f"{prefix} {' '.join(cleaned)}"]


def _normalize_real_api_flag(payload: dict[str, Any], test_kind: str) -> bool:
    real_api = payload.get("real_api")
    if isinstance(real_api, dict):
        return bool(real_api.get("enabled", False))
    if isinstance(real_api, bool):
        return real_api
    if "requires_real_api" in payload:
        return bool(payload.get("requires_real_api"))
    return test_kind == "real_api_regression"


def _default_repo_status_commands(repository_status: dict[str, Any]) -> list[str]:
    repo_ruff_paths = _list_of_strings(
        repository_status.get("ruff_paths"), field="repository_status.ruff_paths"
    )
    repo_mypy_paths = _list_of_strings(
        repository_status.get("mypy_paths"), field="repository_status.mypy_paths"
    )
    repo_pytest_targets = _list_of_strings(
        repository_status.get("pytest_targets"),
        field="repository_status.pytest_targets",
    )
    commands: list[str] = []
    commands.extend(
        _join_command(repo_ruff_paths, "python -m ruff check") or [DEFAULT_REPO_RUFF_COMMAND]
    )
    commands.extend(_join_command(repo_mypy_paths, "python -m mypy") or [DEFAULT_REPO_MYPY_COMMAND])
    commands.extend(
        _join_command(repo_pytest_targets, "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q")
        or [DEFAULT_REPO_PYTEST_COMMAND]
    )
    return commands


def _load_markdown_spec(spec_path: Path) -> dict[str, Any]:
    payload, body = _read_frontmatter(spec_path)
    task_id = payload.get("task_id")
    title = payload.get("title")
    raw_kind = payload.get("test_kind")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    if not isinstance(raw_kind, str) or not raw_kind.strip():
        raise ValueError("test_kind must be a non-empty string")

    test_kind = _validate_test_kind(raw_kind.strip())
    requires_real_api = _normalize_real_api_flag(payload, test_kind)
    config_path = payload.get("config_path") or DEFAULT_CONFIG_PATH
    if not isinstance(config_path, str) or not config_path.strip():
        raise ValueError("config_path must be a non-empty string when present")

    return {
        "task_id": task_id.strip(),
        "title": title.strip(),
        "test_kind": test_kind,
        "acceptance_criteria": _list_of_strings(
            payload.get("acceptance_criteria"), field="acceptance_criteria", required=True
        ),
        "failure_before_change": _list_of_strings(
            payload.get("failure_before_change"), field="failure_before_change", required=True
        ),
        "success_after_change": _list_of_strings(
            payload.get("success_after_change"), field="success_after_change", required=True
        ),
        "changed_paths": _list_of_strings(
            payload.get("changed_paths"), field="changed_paths", required=True
        ),
        "test_paths": _list_of_strings(
            payload.get("test_paths"), field="test_paths", required=True
        ),
        "task_pytest_commands": _list_of_strings(
            payload.get("task_pytest_commands"), field="task_pytest_commands", required=True
        ),
        "task_ruff_commands": _list_of_strings(
            payload.get("task_ruff_commands"), field="task_ruff_commands"
        ),
        "task_mypy_commands": _list_of_strings(
            payload.get("task_mypy_commands"), field="task_mypy_commands"
        ),
        "repo_status_commands": _list_of_strings(
            payload.get("repo_status_commands"), field="repo_status_commands"
        ),
        "requires_real_api": requires_real_api,
        "config_path": config_path.strip() or DEFAULT_CONFIG_PATH,
        "notes": _list_of_strings(payload.get("notes"), field="notes"),
        "body": body.strip(),
    }


def _load_json_spec(spec_path: Path) -> dict[str, Any]:
    payload = _read_json_mapping(spec_path)
    task_scope = payload.get("task_scope") or {}
    repository_status = payload.get("repository_status") or {}
    acceptance_tests = payload.get("acceptance_tests") or []
    if not isinstance(task_scope, dict):
        raise ValueError("task_scope must be an object when present")
    if not isinstance(repository_status, dict):
        raise ValueError("repository_status must be an object when present")
    if acceptance_tests and not isinstance(acceptance_tests, list):
        raise ValueError("acceptance_tests must be a list when present")

    task_id = payload.get("task_id")
    title = payload.get("title") or payload.get("summary")
    raw_kind = payload.get("test_kind") or payload.get("category") or "logic_regression"
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title or summary must be a non-empty string")
    if not isinstance(raw_kind, str) or not raw_kind.strip():
        raise ValueError("test_kind or category must be a non-empty string")

    test_kind = _validate_test_kind(raw_kind.strip())
    requires_real_api = _normalize_real_api_flag(payload, test_kind)

    acceptance_criteria = _list_of_strings(
        payload.get("acceptance_criteria"), field="acceptance_criteria"
    )
    if not acceptance_criteria:
        acceptance_criteria = [
            test_case["name"].strip()
            for test_case in acceptance_tests
            if isinstance(test_case, dict)
            and isinstance(test_case.get("name"), str)
            and test_case["name"].strip()
        ]
    if not acceptance_criteria:
        acceptance_criteria = [title.strip()]

    failure_before_change = _list_of_strings(
        payload.get("failure_before_change"), field="failure_before_change"
    )
    if not failure_before_change:
        failure_before_change = [
            "Run the task-scoped acceptance command before the fix and capture the failing signal."
        ]

    success_after_change = _list_of_strings(
        payload.get("success_after_change"), field="success_after_change"
    )
    if not success_after_change:
        success_after_change = [
            "Run the same task-scoped acceptance command after the fix and require it to pass."
        ]

    changed_paths = _list_of_strings(
        task_scope.get("code_paths") or payload.get("changed_paths"),
        field="changed_paths",
        required=True,
    )
    test_paths = _list_of_strings(
        task_scope.get("test_paths") or payload.get("test_paths"), field="test_paths", required=True
    )
    pytest_targets = _list_of_strings(
        task_scope.get("pytest_targets"), field="task_scope.pytest_targets"
    )
    lint_paths = _list_of_strings(task_scope.get("lint_paths"), field="task_scope.lint_paths")
    typecheck_paths = _list_of_strings(
        task_scope.get("typecheck_paths"), field="task_scope.typecheck_paths"
    )

    task_pytest_commands = _list_of_strings(
        payload.get("task_pytest_commands"), field="task_pytest_commands"
    )
    if not task_pytest_commands:
        task_pytest_commands = _join_command(
            pytest_targets, "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q"
        )
    if not task_pytest_commands:
        raise ValueError("task_pytest_commands or task_scope.pytest_targets must be provided")

    task_ruff_commands = _list_of_strings(
        payload.get("task_ruff_commands"), field="task_ruff_commands"
    )
    if not task_ruff_commands:
        task_ruff_commands = _join_command(lint_paths, "python -m ruff check")

    task_mypy_commands = _list_of_strings(
        payload.get("task_mypy_commands"), field="task_mypy_commands"
    )
    if not task_mypy_commands:
        task_mypy_commands = _join_command(typecheck_paths, "python -m mypy")

    repo_status_commands = _list_of_strings(
        payload.get("repo_status_commands"), field="repo_status_commands"
    )
    if not repo_status_commands:
        repo_status_commands = _default_repo_status_commands(repository_status)

    real_api_cfg = payload.get("real_api") or {}
    config_path = payload.get("config_path")
    if not config_path and isinstance(real_api_cfg, dict):
        config_path = real_api_cfg.get("config_path")
    if not config_path:
        config_path = DEFAULT_CONFIG_PATH

    return {
        "task_id": task_id.strip(),
        "title": title.strip(),
        "test_kind": test_kind,
        "acceptance_criteria": acceptance_criteria,
        "failure_before_change": failure_before_change,
        "success_after_change": success_after_change,
        "changed_paths": changed_paths,
        "test_paths": test_paths,
        "task_pytest_commands": task_pytest_commands,
        "task_ruff_commands": task_ruff_commands,
        "task_mypy_commands": task_mypy_commands,
        "repo_status_commands": repo_status_commands,
        "requires_real_api": requires_real_api,
        "config_path": str(config_path).strip() or DEFAULT_CONFIG_PATH,
        "notes": _list_of_strings(payload.get("notes"), field="notes"),
        "body": "",
    }


def load_acceptance_spec(spec_path: Path) -> dict[str, Any]:
    raw = spec_path.read_text(encoding="utf-8").lstrip()
    if raw.startswith("{"):
        return _load_json_spec(spec_path)
    return _load_markdown_spec(spec_path)


def build_command_plan(spec: dict[str, Any]) -> dict[str, Any]:
    task_gate_commands = (
        spec["task_pytest_commands"] + spec["task_ruff_commands"] + spec["task_mypy_commands"]
    )
    return {
        **spec,
        "task_gate_commands": task_gate_commands,
        "real_api": {
            "enabled": spec["requires_real_api"],
            "config_path": spec["config_path"],
        },
    }


def _markdown_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# Task Test Plan: {plan['title']}",
        "",
        f"- Task ID: `{plan['task_id']}`",
        f"- Test Kind: `{plan['test_kind']}`",
        f"- Real API Required: `{str(plan['requires_real_api']).lower()}`",
        f"- Config Path: `{plan['config_path']}`",
        "",
        "## Acceptance Criteria",
        _markdown_bullets(plan["acceptance_criteria"]),
        "",
        "## Failure Before Change",
        _markdown_bullets(plan["failure_before_change"]),
        "",
        "## Success After Change",
        _markdown_bullets(plan["success_after_change"]),
        "",
        "## Task-Scoped Gate Commands",
        "```bash",
        *plan["task_gate_commands"],
        "```",
        "",
        "## Full-Repo Status Commands",
        "```bash",
        *(plan["repo_status_commands"] or ["# no full-repo status commands declared"]),
        "```",
    ]
    return "\n".join(lines) + "\n"


def render_commands(plan: dict[str, Any]) -> str:
    sections: list[str] = []
    for title, commands in (
        ("TASK_PYTEST_COMMANDS", plan["task_pytest_commands"]),
        ("TASK_RUFF_COMMANDS", plan["task_ruff_commands"]),
        ("TASK_MYPY_COMMANDS", plan["task_mypy_commands"]),
        ("TASK_GATE_COMMANDS", plan["task_gate_commands"]),
        ("REPO_STATUS_COMMANDS", plan["repo_status_commands"]),
    ):
        sections.append(f"[{title}]")
        sections.extend(commands or ["# none"])
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


def _resolve_spec_path(spec_arg: Path | None, spec_option: Path | None) -> Path:
    spec_path = spec_option or spec_arg
    if spec_path is None:
        raise ValueError("a task acceptance spec path is required")
    return spec_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize a unit-test task acceptance spec.")
    parser.add_argument("spec_arg", nargs="?", type=Path, help="Path to the task acceptance spec")
    parser.add_argument(
        "--spec", dest="spec_option", type=Path, help="Path to the task acceptance spec"
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown", "commands"),
        default="markdown",
        help="Output format",
    )
    args = parser.parse_args()

    plan = build_command_plan(
        load_acceptance_spec(_resolve_spec_path(args.spec_arg, args.spec_option))
    )
    if args.format == "json":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    elif args.format == "commands":
        print(render_commands(plan), end="")
    else:
        print(render_markdown(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
