#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v uv >/dev/null 2>&1; then
  uv run python "$SCRIPT_DIR/code_review_with_logs.py" "$@"
else
  echo "[code-review-with-logs] BLOCKED: uv is required to run code_review_with_logs.py" >&2
  exit 1
fi
