#!/usr/bin/env python3
"""Extract failed unit-test command markers from a rebuilt review_run.log."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

COMMAND_RE = re.compile(r"^\[UNIT_TEST\] COMMAND: (?P<command>.+)$")
EXIT_RE = re.compile(r"^\[UNIT_TEST\] EXIT_CODE: (?P<exit_code>-?\d+)$")


def extract_failed_commands(log_text: str) -> list[dict[str, object]]:
    failed: list[dict[str, object]] = []
    pending_command: str | None = None
    for line in log_text.splitlines():
        command_match = COMMAND_RE.match(line.strip())
        if command_match:
            pending_command = command_match.group("command")
            continue
        exit_match = EXIT_RE.match(line.strip())
        if exit_match and pending_command is not None:
            exit_code = int(exit_match.group("exit_code"))
            if exit_code != 0:
                failed.append({"command": pending_command, "exit_code": exit_code})
            pending_command = None
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract failed UNIT_TEST markers from review_run.log."
    )
    parser.add_argument("run_log", help="Path to review_run.log")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)

    failed = extract_failed_commands(
        Path(args.run_log).read_text(encoding="utf-8", errors="replace")
    )
    if args.json:
        print(json.dumps({"failed_commands": failed}, ensure_ascii=False, indent=2))
    else:
        for item in failed:
            print(f"{item['exit_code']}: {item['command']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
