#!/usr/bin/env python3
"""Validate review specs, execute task-scoped tests, and finalize a two-step review result."""

from __future__ import annotations

import argparse
import ast
import glob
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from review_session import resolve_session_paths, write_latest_index
except ModuleNotFoundError:
    _SESSION_PATH = Path(__file__).with_name("review_session.py")
    _SESSION_SPEC = importlib.util.spec_from_file_location("review_session", _SESSION_PATH)
    assert _SESSION_SPEC is not None
    assert _SESSION_SPEC.loader is not None
    _SESSION_MODULE = importlib.util.module_from_spec(_SESSION_SPEC)
    _SESSION_SPEC.loader.exec_module(_SESSION_MODULE)
    resolve_session_paths = _SESSION_MODULE.resolve_session_paths
    write_latest_index = _SESSION_MODULE.write_latest_index


SECTION_KEYS = {
    "final_deliverables": "Final Deliverables",
    "naming_rules": "Naming Rules",
    "required_output_files": "Required Output Files",
    "constraints": "Constraints",
    "uncertainty_handling": "Uncertainty Handling",
    "test_commands": "Test Commands",
    "benchmark_commands": "Benchmark Commands",
}

REQUIRED_SECTION_KEYS = {
    "final_deliverables",
    "naming_rules",
    "required_output_files",
    "constraints",
    "uncertainty_handling",
    "test_commands",
}

DEFAULTS = {
    "code_scopes": "src/**/*.py,tests/**/*.py",
    "code_file_regex": r"^[a-z0-9_]+\.py$",
    "python_function_regex": r"^[a-z_][a-z0-9_]*$",
    "python_class_regex": r"^[A-Z][A-Za-z0-9]*$",
    "python_variable_regex": r"^[a-z_][a-z0-9_]*$",
    "output_file_regex": r"^[a-z0-9_.-]+$",
}

TRANSIENT_PLANNING_PATHS = {
    ".codex/task_plan.md",
    ".codex/progress.md",
    ".codex/findings.md",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_heading(heading: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", heading.lower())).strip()


def canonical_section_key(heading: str) -> str | None:
    norm = normalize_heading(heading)
    if "final deliverables" in norm:
        return "final_deliverables"
    if "naming rules" in norm:
        return "naming_rules"
    if "required output files" in norm:
        return "required_output_files"
    if "constraints" in norm:
        return "constraints"
    if "uncertainty handling" in norm:
        return "uncertainty_handling"
    if "benchmark commands" in norm:
        return "benchmark_commands"
    if "test commands" in norm:
        return "test_commands"
    return None


def parse_sections(spec_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []

    for raw_line in spec_text.splitlines():
        line = raw_line.rstrip("\n")
        match = re.match(r"^##\s+(.+?)\s*$", line.strip())
        if match:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = canonical_section_key(match.group(1))
            buf = []
            continue
        if current is not None:
            buf.append(line)

    if current is not None:
        sections[current] = "\n".join(buf).strip()

    return sections


def bullet_items(section_text: str) -> list[str]:
    items: list[str] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        line = re.sub(r"^[-*]\s*\[[ xX]\]\s*", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        if line:
            items.append(line)
    return items


def parse_key_values(items: list[str]) -> tuple[dict[str, str], list[str]]:
    kv: dict[str, str] = {}
    plain: list[str] = []
    for item in items:
        if ":" in item:
            key, value = item.split(":", 1)
            kv[re.sub(r"\s+", "_", key.strip().lower())] = value.strip()
        else:
            plain.append(item.strip())
    return kv, plain


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def resolve_patterns(workspace: Path, raw_pattern: str) -> list[Path]:
    pattern = raw_pattern.strip().strip("`")
    if not pattern:
        return []
    if any(char in pattern for char in "*?["):
        if Path(pattern).is_absolute():
            return [Path(path).resolve() for path in glob.glob(pattern, recursive=True) if Path(path).resolve().is_relative_to(workspace)]
        return [path for path in workspace.glob(pattern)]

    candidate = Path(pattern)
    if not candidate.is_absolute():
        candidate = (workspace / candidate).resolve()
    if not candidate.is_relative_to(workspace):
        return []
    return [candidate] if candidate.exists() else []


def extract_codex_focus_paths(workspace: Path, deliverable_section: str) -> list[str]:
    focus_paths: list[str] = []
    for item in bullet_items(deliverable_section):
        candidate = item.split(":", 1)[1].strip() if item.lower().startswith("path:") else item
        if any(char in candidate for char in "*?["):
            if Path(candidate).is_absolute():
                matched_paths = [Path(path).resolve() for path in glob.glob(candidate, recursive=True) if Path(path).is_file()]
            else:
                matched_paths = [path.resolve() for path in workspace.glob(candidate) if path.is_file()]
        else:
            path = Path(candidate)
            if not path.is_absolute():
                path = (workspace / path).resolve()
            matched_paths = [path] if path.exists() and path.is_file() else []

        for path in matched_paths:
            if not path.is_relative_to(workspace):
                continue
            rel = path.relative_to(workspace).as_posix() if path.is_relative_to(workspace) else path.as_posix()
            if rel in TRANSIENT_PLANNING_PATHS:
                continue
            focus_paths.append(rel)

    return sorted(set(focus_paths))


def resolve_revision_sha(workspace: Path, revision: str | None) -> str | None:
    target = (revision or "HEAD").strip() or "HEAD"
    proc = subprocess.run(
        ["git", "rev-parse", target],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def resolve_head_sha(workspace: Path) -> str | None:
    return resolve_revision_sha(workspace, "HEAD")


def resolve_commit_subject(workspace: Path, revision: str | None) -> str | None:
    target = (revision or "").strip()
    if not target:
        return None
    proc = subprocess.run(
        ["git", "show", "-s", "--format=%s", target],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def list_dirty_focus_paths(workspace: Path, focus_paths: list[str]) -> list[str]:
    if not focus_paths:
        return []
    proc = subprocess.run(
        ["git", "status", "--short", "--", *focus_paths],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []

    dirty_paths: list[str] = []
    for raw_line in proc.stdout.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        path_text = line[3:] if len(line) > 3 else line
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        path_text = path_text.strip()
        if path_text:
            dirty_paths.append(path_text)
    return dirty_paths


def list_committed_focus_path_differences(
    workspace: Path,
    *,
    base_revision: str | None,
    current_revision: str | None,
    focus_paths: list[str],
) -> list[str]:
    if not focus_paths or not base_revision or not current_revision or base_revision == current_revision:
        return []
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--find-renames", base_revision, current_revision, "--", *focus_paths],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def extract_target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for elt in target.elts:
            names.extend(extract_target_names(elt))
        return names
    return []


def collect_python_symbols(file_path: Path) -> tuple[list[str], list[str], list[str], list[str]]:
    parse_errors: list[str] = []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        parse_errors.append(f"{file_path}: {exc}")
        return [], [], [], parse_errors

    functions: list[str] = []
    classes: list[str] = []
    variables: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

    def collect_assignments(stmt: ast.stmt) -> list[str]:
        names: list[str] = []
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                names.extend(extract_target_names(target))
        elif isinstance(stmt, ast.AnnAssign):
            names.extend(extract_target_names(stmt.target))
        elif isinstance(stmt, ast.AugAssign):
            names.extend(extract_target_names(stmt.target))
        return names

    for stmt in tree.body:
        variables.extend(collect_assignments(stmt))
        if isinstance(stmt, ast.ClassDef):
            for class_stmt in stmt.body:
                variables.extend(collect_assignments(class_stmt))

    return functions, classes, variables, parse_errors


def append_run_log(run_log: Path, message: str) -> None:
    run_log.parent.mkdir(parents=True, exist_ok=True)
    with run_log.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip("\n") + "\n")


def extract_commands(section_text: str) -> list[str]:
    commands: list[str] = []

    for item in bullet_items(section_text):
        if item.lower().startswith("command:"):
            commands.append(item.split(":", 1)[1].strip())
        elif item.startswith(">"):
            continue
        else:
            commands.append(item)

    in_block = False
    block_lang = ""
    block_lines: list[str] = []
    for raw_line in section_text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            if not in_block:
                block_lang = stripped[3:].strip().lower()
                in_block = True
                block_lines = []
            else:
                if block_lang in {"", "bash", "sh", "shell", "zsh"}:
                    for line in block_lines:
                        candidate = line.strip()
                        if candidate and not candidate.startswith("#") and not candidate.startswith(">"):
                            commands.append(candidate)
                in_block = False
                block_lang = ""
                block_lines = []
            continue

        if in_block:
            block_lines.append(raw_line)

    deduped: list[str] = []
    seen: set[str] = set()
    for command in commands:
        cleaned = command.strip().strip("`")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def looks_like_benchmark_command(command: str) -> bool:
    normalized = command.replace("\\", "/")
    return "tests/bench/" in normalized


def deliverables_require_benchmark(deliverable_section: str) -> bool:
    for item in bullet_items(deliverable_section):
        candidate = item.split(":", 1)[1].strip() if item.lower().startswith("path:") else item
        normalized = candidate.replace("\\", "/").lower()
        if "tests/bench/" in normalized:
            return True
        basename = Path(normalized).name
        if "benchmark" in basename or normalized.endswith("benchmark_results.json"):
            return True
    return False


def classify_commands(test_section: str, benchmark_section: str, *, benchmark_gate_enabled: bool) -> dict[str, Any]:
    test_commands = extract_commands(test_section)
    benchmark_commands = extract_commands(benchmark_section)

    explicit_bench = list(benchmark_commands)
    explicit_set = set(explicit_bench)
    inferred_bench: list[str] = []
    functional: list[str] = []
    ignored_bench: list[str] = []

    for command in test_commands:
        if command in explicit_set:
            if not benchmark_gate_enabled:
                ignored_bench.append(command)
            continue
        if looks_like_benchmark_command(command):
            if benchmark_gate_enabled:
                inferred_bench.append(command)
            else:
                ignored_bench.append(command)
        else:
            functional.append(command)

    combined_bench: list[str] = []
    seen: set[str] = set()
    for command in (explicit_bench if benchmark_gate_enabled else []) + inferred_bench:
        if command not in seen:
            seen.add(command)
            combined_bench.append(command)

    return {
        "benchmark_gate_enabled": benchmark_gate_enabled,
        "functional_commands": functional,
        "benchmark_commands": combined_bench,
        "inferred_benchmark_commands": inferred_bench,
        "explicit_benchmark_commands": explicit_bench,
        "ignored_benchmark_commands": ignored_bench + ([] if benchmark_gate_enabled else explicit_bench),
        "all_test_commands": test_commands,
    }


def load_json_if_exists(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def validate_deliverables(workspace: Path, section: str) -> dict[str, Any]:
    items = bullet_items(section)
    failed: list[str] = []
    checked: list[dict[str, Any]] = []
    for item in items:
        pattern = item.split(":", 1)[1].strip() if item.lower().startswith("path:") else item
        matches = resolve_patterns(workspace, pattern)
        exists = bool(matches)
        checked.append({"pattern": pattern, "exists": exists, "matches": [str(m) for m in matches[:5]]})
        if not exists:
            failed.append(pattern)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checked": checked,
        "failed_items": failed,
        "details": f"Checked {len(items)} deliverable requirement(s).",
    }


def validate_required_output_files(workspace: Path, section: str) -> dict[str, Any]:
    items = bullet_items(section)
    failed: list[str] = []
    checked: list[dict[str, Any]] = []

    for item in items:
        output_path = item.split(":", 1)[1].strip() if item.lower().startswith("path:") else item
        candidate = Path(output_path)
        if not candidate.is_absolute():
            candidate = (workspace / candidate).resolve()
        exists = candidate.exists()
        checked.append({"path": str(candidate), "exists": exists})
        if not exists:
            failed.append(str(candidate))

    return {
        "status": "PASS" if not failed else "FAIL",
        "checked": checked,
        "failed_items": failed,
        "details": f"Checked {len(items)} required output file(s).",
    }


def validate_naming(workspace: Path, naming_section: str, output_section: str) -> dict[str, Any]:
    items = bullet_items(naming_section)
    kv, _ = parse_key_values(items)

    code_scopes = split_csv(kv.get("code_scopes", DEFAULTS["code_scopes"]))
    code_file_regex = re.compile(kv.get("code_file_regex", DEFAULTS["code_file_regex"]))
    function_regex = re.compile(kv.get("python_function_regex", DEFAULTS["python_function_regex"]))
    class_regex = re.compile(kv.get("python_class_regex", DEFAULTS["python_class_regex"]))
    variable_regex = re.compile(kv.get("python_variable_regex", DEFAULTS["python_variable_regex"]))
    output_file_regex = re.compile(kv.get("output_file_regex", DEFAULTS["output_file_regex"]))

    files: dict[str, Path] = {}
    for scope in code_scopes:
        for path in workspace.glob(scope):
            if path.is_file() and path.suffix == ".py":
                files[str(path.resolve())] = path.resolve()

    code_file_failures: list[str] = []
    function_failures: list[str] = []
    class_failures: list[str] = []
    variable_failures: list[str] = []
    parse_errors: list[str] = []

    for file_path in sorted(files.values()):
        if not code_file_regex.match(file_path.name):
            code_file_failures.append(str(file_path))

        functions, classes, variables, errors = collect_python_symbols(file_path)
        parse_errors.extend(errors)
        for name in functions:
            if not function_regex.match(name):
                function_failures.append(f"{file_path}:{name}")
        for name in classes:
            if not class_regex.match(name):
                class_failures.append(f"{file_path}:{name}")
        for name in variables:
            if not variable_regex.match(name):
                variable_failures.append(f"{file_path}:{name}")

    output_name_failures: list[str] = []
    for item in bullet_items(output_section):
        output_path = item.split(":", 1)[1].strip() if item.lower().startswith("path:") else item
        if any(char in output_path for char in "*?["):
            continue
        if not output_file_regex.match(Path(output_path).name):
            output_name_failures.append(output_path)

    failed = code_file_failures + function_failures + class_failures + variable_failures + output_name_failures
    return {
        "status": "PASS" if not failed and not parse_errors else "FAIL",
        "details": f"Validated {len(files)} python file(s) across {len(code_scopes)} scope pattern(s).",
        "failed_items": failed,
        "parse_errors": parse_errors,
        "breakdown": {
            "code_file_failures": code_file_failures,
            "function_failures": function_failures,
            "class_failures": class_failures,
            "variable_failures": variable_failures,
            "output_name_failures": output_name_failures,
        },
    }


def validate_constraints(workspace: Path, section: str) -> dict[str, Any]:
    commands = extract_commands(section)
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for command in commands:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "command": command,
                "exit_code": proc.returncode,
                "stdout": "\n".join(proc.stdout.splitlines()[:20]),
                "stderr": "\n".join(proc.stderr.splitlines()[:20]),
            }
        )
        if proc.returncode != 0:
            failures.append(command)

    return {
        "status": "PASS" if not failures else "FAIL",
        "details": f"Executed {len(commands)} constraint command(s).",
        "failed_items": failures,
        "results": results,
    }


def validate_uncertainty(section: str, run_log: Path) -> dict[str, Any]:
    items = bullet_items(section)
    kv, _ = parse_key_values(items)

    levels = split_csv(kv.get("required_levels", "High,Medium,Low"))
    require_mitigation = kv.get("require_mitigation", "true").strip().lower() not in {"false", "0", "no"}
    default_action = kv.get("default_mitigation_action", "").strip() or kv.get("fallback_action", "").strip()
    log_text = run_log.read_text(encoding="utf-8") if run_log.exists() else ""

    present_levels: list[str] = []
    missing_levels: list[str] = []
    for level in levels:
        found = bool(re.search(rf"RiskLevel\s*[:=]\s*{re.escape(level)}", log_text, flags=re.IGNORECASE))
        if found:
            present_levels.append(level)
        else:
            missing_levels.append(level)

    mitigation_present = bool(re.search(r"Mitigation\s*[:=]", log_text, flags=re.IGNORECASE))
    failures: list[str] = []
    warnings: list[str] = []

    if missing_levels:
        if default_action:
            warnings.append(
                "Missing explicit risk levels in logs: "
                + ", ".join(missing_levels)
                + f". Applied default mitigation action: {default_action}"
            )
        else:
            failures.append("Missing risk level markers in logs: " + ", ".join(missing_levels))

    if require_mitigation and not mitigation_present and not default_action:
        failures.append("Mitigation marker missing in logs and no default mitigation action provided.")

    return {
        "status": "PASS" if not failures else "FAIL",
        "details": "Validated uncertainty handling markers in run logs.",
        "failed_items": failures,
        "warnings": warnings,
        "present_levels": present_levels,
        "missing_levels": missing_levels,
        "mitigation_present": mitigation_present,
        "default_mitigation_action": default_action,
    }


def extract_metrics(stdout_text: str) -> Any:
    candidates: list[str] = []
    stripped = stdout_text.strip()
    if stripped:
        candidates.append(stripped)
        lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
        if lines:
            candidates.append(lines[-1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed
    return None


def summarize_metrics(metrics: Any) -> str | None:
    if isinstance(metrics, dict):
        parts: list[str] = []
        for key, value in list(metrics.items())[:8]:
            if isinstance(value, (str, int, float, bool)) or value is None:
                parts.append(f"{key}={value}")
            else:
                parts.append(f"{key}=<{type(value).__name__}>")
        return ", ".join(parts) if parts else None
    if isinstance(metrics, list):
        return f"list(len={len(metrics)})"
    return None


def extract_reported_status(metrics: Any) -> str | None:
    if not isinstance(metrics, dict):
        return None
    value = metrics.get("status")
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized or None


def run_command_group(
    commands: list[str],
    *,
    workspace: Path,
    run_log: Path,
    label: str,
    heading: str,
) -> dict[str, Any]:
    if not commands:
        return {
            "status": "PASS",
            "details": f"No {heading.lower()} configured.",
            "failed_items": [],
            "results": [],
            "command_count": 0,
        }

    results: list[dict[str, Any]] = []
    blocked_commands: list[str] = []
    failures: list[str] = []

    for command in commands:
        append_run_log(run_log, f"[{label}] COMMAND: {command}")
        proc = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout_text = "\n".join(proc.stdout.splitlines()[:80])
        stderr_text = "\n".join(proc.stderr.splitlines()[:80])
        append_run_log(run_log, f"[{label}] EXIT_CODE: {proc.returncode}")
        if stdout_text:
            append_run_log(run_log, f"[{label}] STDOUT:")
            append_run_log(run_log, stdout_text)
        if stderr_text:
            append_run_log(run_log, f"[{label}] STDERR:")
            append_run_log(run_log, stderr_text)

        metrics = extract_metrics(stdout_text)
        metric_summary = summarize_metrics(metrics)
        reported_status = extract_reported_status(metrics)
        row = {
            "kind": label.lower(),
            "command": command,
            "exit_code": proc.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "metrics": metrics,
            "metric_summary": metric_summary,
            "reported_status": reported_status,
        }
        results.append(row)
        if proc.returncode != 0:
            failures.append(command)
        elif reported_status == "BLOCKED":
            blocked_commands.append(command)
        elif reported_status == "FAIL":
            failures.append(command)

    status = "PASS"
    details = f"Executed {len(commands)} {heading.lower()}."
    if blocked_commands:
        status = "BLOCKED"
        details = (
            f"Executed {len(commands)} {heading.lower()}; "
            f"{len(blocked_commands)} command(s) reported blocked status."
        )
    elif failures:
        status = "FAIL"
    return {
        "status": status,
        "details": details,
        "blocked_items": blocked_commands,
        "failed_items": failures,
        "results": results,
        "command_count": len(commands),
    }


def summarize_step_status(*statuses: str) -> str:
    normalized = [status for status in statuses if status]
    if any(status == "BLOCKED" for status in normalized):
        return "BLOCKED"
    if any(status == "FAIL" for status in normalized):
        return "FAIL"
    return "PASS"


def not_requested_benchmark_result() -> dict[str, Any]:
    return {
        "required": False,
        "status": "NOT_REQUESTED",
        "details": "Benchmark validation was not requested by Final Deliverables.",
        "failed_items": [],
        "results": [],
        "command_count": 0,
    }


def blocked_result(details: str) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "details": details,
        "failed_items": [],
        "results": [],
        "command_count": 0,
    }


def pending_phase_feedback(phase: str) -> str:
    if phase == "deliverables":
        return "Deliverable review passed; test execution is still pending."
    if phase == "tests":
        return "Deliverables and tests passed; finalization is still pending."
    return "Review is still in progress."


def format_bullets(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def format_command_results(section: dict[str, Any], *, include_metrics: bool) -> str:
    lines = [f"- Status: {section.get('status', 'UNKNOWN')}"]
    details = section.get("details")
    if details:
        lines.append(f"- Details: {details}")
    results = section.get("results", [])
    if not results:
        return "\n".join(lines)

    for row in results:
        suffix = ""
        if include_metrics and row.get("metric_summary"):
            suffix = f" | metrics: {row['metric_summary']}"
        lines.append(f"- `{row['command']}` => exit {row['exit_code']}{suffix}")
    return "\n".join(lines)


def build_deliverable_reviews(
    *,
    workspace: Path,
    sections: dict[str, str],
    run_log_path: Path,
) -> dict[str, dict[str, Any]]:
    return {
        "deliverables": validate_deliverables(workspace, sections.get("final_deliverables", "")),
        "naming": validate_naming(
            workspace,
            sections.get("naming_rules", ""),
            sections.get("required_output_files", ""),
        ),
        "required_outputs": validate_required_output_files(workspace, sections.get("required_output_files", "")),
        "constraints": validate_constraints(workspace, sections.get("constraints", "")),
        "uncertainty": validate_uncertainty(sections.get("uncertainty_handling", ""), run_log_path),
    }


def summarize_requirement_status(domain_results: dict[str, dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    blocked: list[str] = []
    failed: list[str] = []
    for name, result in domain_results.items():
        status = str(result.get("status", "")).upper()
        if status == "BLOCKED":
            blocked.append(f"{name} blocked")
        elif status == "FAIL":
            failed.append(f"{name} failed")
    if blocked:
        return "BLOCKED", blocked, failed
    if failed:
        return "FAIL", blocked, failed
    return "PASS", blocked, failed


def write_summary(
    summary_path: Path,
    *,
    final_status: str,
    spec_path: Path,
    review_id: str,
    session_dir: Path,
    review_target_sha: str | None,
    requirement_status: str,
    domain_results: dict[str, dict[str, Any]],
    functional_tests: dict[str, Any],
    benchmarks: dict[str, Any],
    blocked_reasons: list[str],
    fail_reasons: list[str],
    stop_reason: str,
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    target_commit_message = resolve_commit_subject(session_dir.parent.parent.parent, review_target_sha) if review_target_sha else None
    requirement_findings: list[str] = []
    requirement_findings.extend(blocked_reasons)
    requirement_findings.extend(fail_reasons)
    for domain, result in domain_results.items():
        for item in result.get("failed_items", []):
            requirement_findings.append(f"{domain}: {item}")
        for warning in result.get("warnings", []):
            requirement_findings.append(f"{domain} warning: {warning}")
    for item in functional_tests.get("failed_items", []):
        requirement_findings.append(f"functional test: {item}")

    benchmark_findings: list[str] = []
    for item in benchmarks.get("failed_items", []):
        benchmark_findings.append(f"benchmark: {item}")
    for row in benchmarks.get("results", []):
        if row.get("exit_code") != 0:
            summary = row.get("metric_summary")
            benchmark_findings.append(
                f"`{row['command']}` failed with exit {row['exit_code']}"
                + (f" ({summary})" if summary else "")
            )

    header_lines = [
        "# Code Review Summary",
        "",
        f"- Final Status: {final_status}",
        f"- Generated At: {utc_now()}",
        f"- Review ID: {review_id}",
        f"- Session Dir: {session_dir}",
        f"- Spec Path: {spec_path}",
        f"- Stop Reason: {stop_reason}",
    ]
    if review_target_sha:
        header_lines.append(f"- Review Target SHA: {review_target_sha}")
    if target_commit_message:
        header_lines.append(f"- Review Target Commit Message: {target_commit_message}")
    content = "\n".join(header_lines) + f"""

## Step 1: Deliverable Review
### Deliverable Validation
- Status: {domain_results['deliverables']['status']}
- Details: {domain_results['deliverables']['details']}
{format_bullets(domain_results['deliverables'].get('failed_items', []))}

### Naming Validation
- Status: {domain_results['naming']['status']}
- Details: {domain_results['naming']['details']}
{format_bullets(domain_results['naming'].get('failed_items', []))}

### Required Output Files Validation
- Status: {domain_results['required_outputs']['status']}
- Details: {domain_results['required_outputs']['details']}
{format_bullets(domain_results['required_outputs'].get('failed_items', []))}

### Constraint Validation
- Status: {domain_results['constraints']['status']}
- Details: {domain_results['constraints']['details']}
{format_bullets(domain_results['constraints'].get('failed_items', []))}

### Uncertainty Handling Validation
- Status: {domain_results['uncertainty']['status']}
- Details: {domain_results['uncertainty']['details']}
{format_bullets(domain_results['uncertainty'].get('failed_items', []))}

## Step 2: Test Execution
### Requirement Review Status
- Status: {requirement_status}

### Functional Tests
{format_command_results(functional_tests, include_metrics=False)}

## Benchmark Validation
{format_command_results(benchmarks, include_metrics=True)}

## Final Findings
### Requirement Fulfillment Gaps
{format_bullets(requirement_findings)}

### Benchmark Effect Regressions
{format_bullets(benchmark_findings)}

## Final Feedback
- {stop_reason}
"""
    summary_path.write_text(content, encoding="utf-8")


def build_fail_fast_summary(
    *,
    summary_path: Path,
    final_status: str,
    stop_reason: str,
    spec_path: Path,
    review_id: str,
    session_dir: Path,
    command_classification: dict[str, Any],
    domain_results: dict[str, dict[str, Any]],
    functional_tests: dict[str, Any],
    benchmark_validation: dict[str, Any],
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_lines = [
        f"- Required: {'Yes' if benchmark_validation.get('required') else 'No'}",
        f"- Status: {benchmark_validation.get('status', 'UNKNOWN')}",
        f"- Details: {benchmark_validation.get('details', '')}",
        f"- Ignored Commands: {', '.join(command_classification.get('ignored_benchmark_commands', [])) or 'None'}",
    ]
    benchmark_render = format_command_results(benchmark_validation, include_metrics=True)
    if benchmark_render:
        benchmark_lines.append(benchmark_render)

    content = "\n".join(
        [
            "# Code Review Summary",
            "",
            f"- Final Status: {final_status}",
            f"- Generated At: {utc_now()}",
            f"- Review ID: {review_id}",
            f"- Session Dir: {session_dir}",
            f"- Spec Path: {spec_path}",
            f"- Stop Reason: {stop_reason}",
            "",
            "## Step 1: Deliverable Review",
            f"- Requirement Status: {summarize_requirement_status(domain_results)[0]}",
            f"- Deliverables: {domain_results['deliverables'].get('status', 'UNKNOWN')}",
            f"- Naming: {domain_results['naming'].get('status', 'UNKNOWN')}",
            f"- Required Outputs: {domain_results['required_outputs'].get('status', 'UNKNOWN')}",
            f"- Constraints: {domain_results['constraints'].get('status', 'UNKNOWN')}",
            f"- Uncertainty: {domain_results['uncertainty'].get('status', 'UNKNOWN')}",
            "",
            "## Step 2: Test Execution",
            "### Functional Tests",
            format_command_results(functional_tests, include_metrics=False),
            "",
            "### Benchmark Validation",
            "\n".join(benchmark_lines),
            "",
            "## Final Feedback",
            f"- {stop_reason}",
        ]
    )
    summary_path.write_text(content + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate deliverables and aggregate fail-fast review results.")
    parser.add_argument("--spec", default=".codex/review_spec.md", help="Path to review spec markdown file")
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--review-id", default=None, help="Session-scoped review identifier.")
    parser.add_argument(
        "--phase",
        choices=("full", "deliverables", "tests", "finalize"),
        default="full",
        help="Which review phase to run.",
    )
    parser.add_argument("--summary", default=None, help="Summary output markdown path")
    parser.add_argument("--run-log", default=None, help="Run log path")
    parser.add_argument("--validation-json", default=None, help="Validation JSON output path")
    parser.add_argument("--test-results-json", default=None, help="Functional test results JSON path")
    parser.add_argument("--benchmark-results-json", default=None, help="Benchmark results JSON path")
    parser.add_argument("--repro-results-json", default=None, help="Reproduction results JSON path")
    parser.add_argument("--codex-review-json", default=None, help="Deprecated codex review result path; ignored in two-step flow")
    parser.add_argument(
        "--review-target-sha",
        default=None,
        help="Explicit commit SHA/ref the deliverable and test results should target. Defaults to HEAD when omitted.",
    )
    parser.add_argument("--emit-test-commands", action="store_true", help="Only print functional test commands")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = (workspace / spec_path).resolve()

    artifact_arg = None
    for candidate in (args.summary, args.validation_json, args.test_results_json, args.codex_review_json):
        if candidate:
            artifact_arg = Path(candidate)
            break
    if artifact_arg is not None and not artifact_arg.is_absolute():
        artifact_arg = (workspace / artifact_arg).resolve()
    elif artifact_arg is not None:
        artifact_arg = artifact_arg.resolve()

    session_paths = resolve_session_paths(
        workspace,
        review_id=args.review_id,
        artifact_path=artifact_arg,
        fallback_review_target_sha=args.review_target_sha,
    )
    review_id = str(session_paths["review_id"])
    session_dir = Path(session_paths["session_dir"])

    def _resolve_output(value: str | None, key: str) -> Path:
        if value:
            path = Path(value)
            if not path.is_absolute():
                return (workspace / path).resolve()
            return path.resolve()
        return Path(session_paths[key])

    summary_path = _resolve_output(args.summary, "summary")
    run_log_path = _resolve_output(args.run_log, "run_log")
    validation_json_path = _resolve_output(args.validation_json, "validation_json")
    test_results_json_path = _resolve_output(args.test_results_json, "test_results_json")
    benchmark_results_json_path = _resolve_output(args.benchmark_results_json, "benchmark_results_json")
    repro_results_json_path = _resolve_output(args.repro_results_json, "repro_results_json")

    spec_missing = not spec_path.exists()
    sections = parse_sections(spec_path.read_text(encoding="utf-8")) if not spec_missing else {}
    missing_sections = sorted(REQUIRED_SECTION_KEYS - set(sections)) if not spec_missing else sorted(REQUIRED_SECTION_KEYS)
    deliverable_section = sections.get("final_deliverables", "")
    benchmark_required = deliverables_require_benchmark(deliverable_section)
    command_classification = classify_commands(
        sections.get("test_commands", ""),
        sections.get("benchmark_commands", ""),
        benchmark_gate_enabled=benchmark_required,
    )

    if args.emit_test_commands:
        for command in command_classification["functional_commands"]:
            print(command)
        return 0

    if run_log_path.exists():
        run_log_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        run_log_path.parent.mkdir(parents=True, exist_ok=True)
        run_log_path.touch()

    domain_results = build_deliverable_reviews(workspace=workspace, sections=sections, run_log_path=run_log_path) if not spec_missing else {
        "deliverables": blocked_result(f"Spec not found: {spec_path}"),
        "naming": blocked_result("Spec not found."),
        "required_outputs": blocked_result("Spec not found."),
        "constraints": blocked_result("Spec not found."),
        "uncertainty": blocked_result("Spec not found."),
    }
    requirement_status, requirement_blocked, requirement_failed = summarize_requirement_status(domain_results)
    functional_tests: dict[str, Any] = blocked_result("Functional tests were not executed.")
    benchmark_validation: dict[str, Any] = not_requested_benchmark_result()

    final_status = "PASS"
    stop_reason = ""
    review_target_sha = resolve_revision_sha(workspace, args.review_target_sha or "HEAD")

    if args.phase in {"full", "deliverables"}:
        if spec_missing:
            final_status = "BLOCKED"
            stop_reason = f"Review spec missing: {spec_path}"
        elif missing_sections:
            final_status = "BLOCKED"
            stop_reason = "Missing required sections in spec: " + ", ".join(missing_sections)
        elif requirement_status != "PASS":
            final_status = requirement_status
            stop_reason = (
                "Deliverable review failed." if requirement_status == "FAIL" else "Deliverable review is blocked."
            )

        payload = {
            "status": final_status,
            "generated_at": utc_now(),
            "phase": "deliverables",
            "formal_review_complete": False,
            "pending_steps": ["functional_tests"],
            "review_id": review_id,
            "session_dir": str(session_dir),
            "spec": str(spec_path),
            "workspace": str(workspace),
            "review_target_sha": review_target_sha,
            "steps": {"deliverable_review": domain_results},
            "requirement_fulfillment": {
                "status": requirement_status,
                "deliverables": domain_results,
            },
            "command_classification": command_classification,
            "benchmark_validation": benchmark_validation,
            "feedback": stop_reason or pending_phase_feedback("deliverables"),
        }
        if final_status != "PASS" or args.phase == "deliverables":
            build_fail_fast_summary(
                summary_path=summary_path,
                final_status=final_status,
                stop_reason=stop_reason or pending_phase_feedback("deliverables"),
                spec_path=spec_path,
                review_id=review_id,
                session_dir=session_dir,
                command_classification=command_classification,
                domain_results=domain_results,
                functional_tests=functional_tests,
                benchmark_validation=benchmark_validation,
            )
            validation_json_path.parent.mkdir(parents=True, exist_ok=True)
            validation_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            write_latest_index(
                workspace,
                {
                    "review_id": review_id,
                    "session_dir": str(session_dir),
                    "status": final_status,
                    "kind": "deliverables",
                    "validation_json": str(validation_json_path),
                    "generated_at": payload["generated_at"],
                },
            )
            return 0 if final_status == "PASS" else 1

    if args.phase in {"full", "tests"}:
        if spec_missing:
            final_status = "BLOCKED"
            stop_reason = f"Review spec missing: {spec_path}"
        elif missing_sections:
            final_status = "BLOCKED"
            stop_reason = "Missing required sections in spec: " + ", ".join(missing_sections)
        elif requirement_status != "PASS":
            final_status = requirement_status
            stop_reason = "Deliverable review failed." if requirement_status == "FAIL" else "Deliverable review is blocked."
        elif not sections.get("test_commands", "").strip():
            functional_tests = blocked_result("Test Commands section is missing or empty.")
            final_status = "BLOCKED"
            stop_reason = functional_tests["details"]
        else:
            functional_tests = run_command_group(
                command_classification["functional_commands"],
                workspace=workspace,
                run_log=run_log_path,
                label="FUNC_TEST",
                heading="Functional Test Command(s)",
            )
            if benchmark_required and not command_classification["benchmark_commands"]:
                benchmark_validation = blocked_result(
                    "Benchmark is required by Final Deliverables but no benchmark command was configured."
                )
                benchmark_validation["required"] = True
            elif benchmark_required:
                benchmark_validation = run_command_group(
                    command_classification["benchmark_commands"],
                    workspace=workspace,
                    run_log=run_log_path,
                    label="BENCH",
                    heading="Benchmark Command(s)",
                )
                benchmark_validation["required"] = True
            else:
                benchmark_validation = not_requested_benchmark_result()

            functional_tests["review_target_sha"] = review_target_sha
            benchmark_validation["review_target_sha"] = review_target_sha
            test_results_json_path.parent.mkdir(parents=True, exist_ok=True)
            test_results_json_path.write_text(json.dumps(functional_tests, ensure_ascii=False, indent=2), encoding="utf-8")
            benchmark_results_json_path.parent.mkdir(parents=True, exist_ok=True)
            benchmark_results_json_path.write_text(json.dumps(benchmark_validation, ensure_ascii=False, indent=2), encoding="utf-8")
            tests_status = summarize_step_status(
                functional_tests.get("status", ""),
                benchmark_validation.get("status", "PASS") if benchmark_required else "PASS",
            )
            if tests_status != "PASS":
                final_status = tests_status
                stop_reason = "Test execution failed." if tests_status == "FAIL" else "Test execution is blocked."

        payload = {
            "status": final_status,
            "generated_at": utc_now(),
            "phase": "tests",
            "formal_review_complete": False,
            "pending_steps": [],
            "review_id": review_id,
            "session_dir": str(session_dir),
            "spec": str(spec_path),
            "workspace": str(workspace),
            "review_target_sha": review_target_sha,
            "steps": {
                "deliverable_review": domain_results,
                "functional_tests": functional_tests,
            },
            "requirement_fulfillment": {
                "status": summarize_step_status(requirement_status, functional_tests.get("status", "")),
                "deliverables": domain_results,
                "functional_tests": functional_tests,
            },
            "benchmark_validation": benchmark_validation,
            "command_classification": command_classification,
            "feedback": stop_reason or pending_phase_feedback("tests"),
        }
        if final_status != "PASS" or args.phase == "tests":
            build_fail_fast_summary(
                summary_path=summary_path,
                final_status=final_status,
                stop_reason=stop_reason or pending_phase_feedback("tests"),
                spec_path=spec_path,
                review_id=review_id,
                session_dir=session_dir,
                command_classification=command_classification,
                domain_results=domain_results,
                functional_tests=functional_tests,
                benchmark_validation=benchmark_validation,
            )
            validation_json_path.parent.mkdir(parents=True, exist_ok=True)
            validation_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            write_latest_index(
                workspace,
                {
                    "review_id": review_id,
                    "session_dir": str(session_dir),
                    "status": final_status,
                    "kind": "tests",
                    "validation_json": str(validation_json_path),
                    "generated_at": payload["generated_at"],
                },
            )
            return 0 if final_status == "PASS" else 1

    loaded_tests = load_json_if_exists(test_results_json_path)
    functional_tests = loaded_tests if isinstance(loaded_tests, dict) else blocked_result("Functional test results not found.")
    expected_test_review_target_sha = review_target_sha
    actual_test_review_target_sha = str(functional_tests.get("review_target_sha", "")).strip() or None
    if (
        functional_tests.get("status") != "BLOCKED"
        and expected_test_review_target_sha is not None
        and actual_test_review_target_sha != expected_test_review_target_sha
    ):
        functional_tests = blocked_result(
            "Functional test results target a different review SHA than the current anchored session. Rerun tests for the updated target."
        )
        functional_tests["expected_review_target_sha"] = expected_test_review_target_sha
        functional_tests["actual_review_target_sha"] = actual_test_review_target_sha

    loaded_benchmarks = load_json_if_exists(benchmark_results_json_path)
    if benchmark_required:
        benchmark_validation = loaded_benchmarks if isinstance(loaded_benchmarks, dict) else blocked_result("Benchmark results not found.")
        benchmark_validation["required"] = True
        actual_benchmark_review_target_sha = str(benchmark_validation.get("review_target_sha", "")).strip() or None
        if (
            benchmark_validation.get("status") != "BLOCKED"
            and expected_test_review_target_sha is not None
            and actual_benchmark_review_target_sha != expected_test_review_target_sha
        ):
            benchmark_validation = blocked_result(
                "Benchmark results target a different review SHA than the current anchored session. Rerun benchmark commands for the updated target."
            )
            benchmark_validation["required"] = True
            benchmark_validation["expected_review_target_sha"] = expected_test_review_target_sha
            benchmark_validation["actual_review_target_sha"] = actual_benchmark_review_target_sha
    else:
        benchmark_validation = not_requested_benchmark_result()

    tests_status = summarize_step_status(
        functional_tests.get("status", "BLOCKED"),
        benchmark_validation.get("status", "PASS") if benchmark_required else "PASS",
    )
    blocked_reasons = list(requirement_blocked)
    failed_reasons = list(requirement_failed)
    if tests_status == "BLOCKED":
        blocked_reasons.append("functional tests blocked")
    elif tests_status == "FAIL":
        failed_reasons.append("functional tests failed")

    if missing_sections:
        final_status = "BLOCKED"
        blocked_reasons.insert(0, "Missing required sections in spec: " + ", ".join(missing_sections))
    elif requirement_status != "PASS":
        final_status = requirement_status
    elif tests_status != "PASS":
        final_status = tests_status
    else:
        final_status = "PASS"

    if final_status == "PASS":
        stop_reason = "Deliverables and tests all passed."
    elif final_status == "FAIL":
        stop_reason = "Review failed because at least one deliverable gate or test command failed."
    else:
        stop_reason = "Review is blocked because required inputs or results are missing or inconsistent."

    write_summary(
        summary_path=summary_path,
        final_status=final_status,
        spec_path=spec_path,
        review_id=review_id,
        session_dir=session_dir,
        review_target_sha=review_target_sha,
        requirement_status=requirement_status,
        domain_results=domain_results,
        functional_tests=functional_tests,
        benchmarks=benchmark_validation,
        blocked_reasons=blocked_reasons,
        fail_reasons=failed_reasons,
        stop_reason=stop_reason,
    )

    payload = {
        "status": final_status,
        "generated_at": utc_now(),
        "phase": "finalize",
        "formal_review_complete": True,
        "pending_steps": [],
        "review_id": review_id,
        "session_dir": str(session_dir),
        "spec": str(spec_path),
        "workspace": str(workspace),
        "review_target_sha": review_target_sha,
        "steps": {
            "deliverable_review": domain_results,
            "functional_tests": functional_tests,
        },
        "command_classification": command_classification,
        "requirement_fulfillment": {
            "status": summarize_step_status(requirement_status, tests_status),
            "deliverables": domain_results,
            "functional_tests": functional_tests,
        },
        "benchmark_validation": benchmark_validation,
        "feedback": stop_reason,
        "repro_results": load_json_if_exists(repro_results_json_path),
    }

    validation_json_path.parent.mkdir(parents=True, exist_ok=True)
    validation_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_latest_index(
        workspace,
        {
            "review_id": review_id,
            "session_dir": str(session_dir),
            "status": final_status,
            "kind": "finalize",
            "validation_json": str(validation_json_path),
            "summary": str(summary_path),
            "generated_at": payload["generated_at"],
        },
    )
    return 0 if final_status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
