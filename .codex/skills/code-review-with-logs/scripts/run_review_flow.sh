#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
run_review_flow.sh has been retired.

code-review-with-logs no longer uses review_spec.md, deliverable validation,
naming validation, benchmark gates, or commit-target review flow.

Use:
  .codex/skills/code-review-with-logs/scripts/run_code_review_with_logs.sh \
    --workspace . \
    --session-id <session_id> \
    --test-command '<unit-test command>' \
    --changed-path <path> \
    --log-path <path>
EOF

exit 2
