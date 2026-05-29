#!/usr/bin/env python3
"""Reproduce failed functional test and benchmark commands from review logs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENTRY_PATTERNS = {
    "func_test": {
        "command": re.compile(r"^\[FUNC_TEST\]\s+COMMAND:\s*(.+)$"),
        "exit": re.compile(r"^\[FUNC_TEST\]\s+EXIT_CODE:\s*(-?\d+)\s*$"),
    },
    "bench": {
        "command": re.compile(r"^\[BENCH\]\s+COMMAND:\s*(.+)$"),
        "exit": re.compile(r"^\[BENCH\]\s+EXIT_CODE:\s*(-?\d+)\s*$"),
    },
    "test": {
        "command": re.compile(r"^\[TEST\]\s+COMMAND:\s*(.+)$"),
        "exit": re.compile(r"^\[TEST\]\s+EXIT_CODE:\s*(-?\d+)\s*$"),
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_test_entries(run_log_text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current_kind: str | None = None
    current_command: str | None = None

    for raw_line in run_log_text.splitlines():
        line = raw_line.strip()

        matched_command = False
        for kind, patterns in ENTRY_PATTERNS.items():
            command_match = patterns["command"].match(line)
            if command_match:
                current_kind = "func_test" if kind == "test" else kind
                current_command = command_match.group(1).strip()
                matched_command = True
                break
        if matched_command:
            continue

        if current_kind is None or current_command is None:
            continue

        exit_pattern = ENTRY_PATTERNS["test"]["exit"] if current_kind == "func_test" and "[TEST]" in line else ENTRY_PATTERNS[current_kind]["exit"]
        exit_match = exit_pattern.match(line)
        if exit_match:
            entries.append(
                {
                    "kind": current_kind,
                    "command": current_command,
                    "exit_code": int(exit_match.group(1)),
                }
            )
            current_kind = None
            current_command = None

    latest_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        latest_by_key[(entry["kind"], entry["command"])] = entry

    return list(latest_by_key.values())


def rerun_failures(workspace: Path, failed_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for entry in failed_entries:
        proc = subprocess.run(
            entry["command"],
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "kind": entry["kind"],
                "command": entry["command"],
                "previous_exit_code": entry["exit_code"],
                "rerun_exit_code": proc.returncode,
                "stdout": "\n".join(proc.stdout.splitlines()[:40]),
                "stderr": "\n".join(proc.stderr.splitlines()[:40]),
                "classification": "verified-fix" if proc.returncode == 0 else "reproduced",
            }
        )
    return results


def summarize_status(total_entries: int, failed_entries: list[dict[str, Any]], rerun_results: list[dict[str, Any]]) -> tuple[str, str]:
    if total_entries == 0:
        return "blocked", "No functional test or benchmark command markers found in run log."
    if not failed_entries:
        return "not-needed", "No failing functional test or benchmark command found in latest run log entries."

    reproduced = [row for row in rerun_results if row["classification"] == "reproduced"]
    fixed = [row for row in rerun_results if row["classification"] == "verified-fix"]

    if reproduced and fixed:
        return "mixed", "Some failures were reproduced while others are now fixed."
    if fixed and not reproduced:
        return "verified-fix", "All previous failures now pass on rerun."
    return "reproduced", "All previous failures are reproducible."


def write_repro_steps(path: Path, status: str, details: str, rerun_results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Reproduction and Fix Verification Steps",
        "",
        f"- Generated At: {utc_now()}",
        f"- Status: {status}",
        f"- Details: {details}",
        "",
    ]

    if not rerun_results:
        lines.extend(
            [
                "## Reproduced Failures",
                "- None",
                "",
                "## Behavior Analysis",
                "- No failing functional test or benchmark command required reproduction.",
            ]
        )
    else:
        lines.append("## Reproduced Failures")
        for row in rerun_results:
            lines.append(
                f"- [{row['kind']}] `{row['command']}` previous={row['previous_exit_code']} rerun={row['rerun_exit_code']} ({row['classification']})"
            )
        lines.append("")
        lines.append("## Behavior Analysis")
        for row in rerun_results:
            lines.append(f"- Kind: {row['kind']}")
            lines.append(f"- Command: `{row['command']}`")
            lines.append("- Expected: exit 0")
            lines.append(f"- Actual: exit {row['rerun_exit_code']}")
            lines.append(
                "- Delta from previous run: "
                + ("fixed" if row["classification"] == "verified-fix" else "still failing")
            )
            lines.append(
                "- Suggested action: "
                + (
                    "keep regression coverage and proceed to final review."
                    if row["classification"] == "verified-fix"
                    else "inspect logs/review_run.log and patch root cause before rerun."
                )
            )
            lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reproduce failed functional test or benchmark commands from review logs.")
    parser.add_argument("--run-log", default="logs/review_run.log", help="Path to review run log")
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--output-md", default="logs/repro_steps.md", help="Output markdown path")
    parser.add_argument("--output-json", default="logs/repro_results.json", help="Output json path")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    run_log = Path(args.run_log)
    if not run_log.is_absolute():
        run_log = (workspace / run_log).resolve()

    output_md = Path(args.output_md)
    if not output_md.is_absolute():
        output_md = (workspace / output_md).resolve()

    output_json = Path(args.output_json)
    if not output_json.is_absolute():
        output_json = (workspace / output_json).resolve()

    if not run_log.exists():
        payload = {
            "status": "blocked",
            "details": f"Run log not found: {run_log}",
            "generated_at": utc_now(),
            "results": [],
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        write_repro_steps(output_md, payload["status"], payload["details"], [])
        return 0

    entries = parse_test_entries(run_log.read_text(encoding="utf-8"))
    failed_entries = [entry for entry in entries if entry["exit_code"] != 0]
    rerun_results = rerun_failures(workspace, failed_entries)
    status, details = summarize_status(len(entries), failed_entries, rerun_results)

    payload = {
        "status": status,
        "details": details,
        "generated_at": utc_now(),
        "total_entries": len(entries),
        "total_failures": len(failed_entries),
        "results": rerun_results,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_repro_steps(output_md, status, details, rerun_results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
