#!/usr/bin/env python3
"""Retired legacy validator for code-review-with-logs."""

from __future__ import annotations

import sys


MESSAGE = """validate_naming_and_outputs.py has been retired.

code-review-with-logs now runs:
  1. unit-test commands;
  2. context/log/diff reporting with reliable check.

Use scripts/run_code_review_with_logs.sh or scripts/code_review_with_logs.py.
"""


def main(argv: list[str] | None = None) -> int:
    del argv
    sys.stderr.write(MESSAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
