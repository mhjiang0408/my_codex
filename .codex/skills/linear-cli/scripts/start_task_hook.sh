#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v uv >/dev/null 2>&1; then
  uv run python "$SCRIPT_DIR/start_task_hook.py" "$@"
else
  echo "[linear-cli] BLOCKED: uv is required to run start_task_hook.py" >&2
  exit 1
fi
