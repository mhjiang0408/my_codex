---
name: linear-cli
description: Delegating mirror of the canonical Linear CLI start-task hook workflow; use for Linear issue registration, reuse, sub-issue topology, and hard-blocking task traceability before substantive implementation.
allowed-tools: Bash(linear:*), Bash(curl:*)
hooks:
  PreToolUse:
    - matcher: "Write|Edit|Bash|Read|Glob|Grep"
      hooks:
        - type: command
          command: |
            WORKSPACE_ROOT="${CODEX_WORKSPACE_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
            SCRIPT="$WORKSPACE_ROOT/.codex/skills/linear-cli/scripts/start_task_hook.sh"
            if [ -x "$SCRIPT" ]; then
              "$SCRIPT" --workspace "$WORKSPACE_ROOT"
            elif [ -f "$SCRIPT" ]; then
              bash "$SCRIPT" --workspace "$WORKSPACE_ROOT"
            else
              echo "[linear-cli] BLOCKED: missing canonical start_task_hook.sh at $SCRIPT" >&2
              exit 1
            fi
---

# Linear CLI Mirror

This nested copy exists only for environments that discover skills through
`.codex/skills/uv-package-manager/**`. The canonical implementation and detailed rules live in:

```text
.codex/skills/linear-cli/SKILL.md
.codex/skills/linear-cli/scripts/start_task_hook.sh
```

Do not use the retired manual task-entry decision workflow from this mirror. Start-of-task Linear
registration is owned by the Codex start-task hook.

## Hook Contract

- Every non-casual task must be registered before substantive implementation.
- The hook initializes `.codex_record/<session_id>/task_plan.md`, `progress.md`, `findings.md`,
  and `hook_state.json`.
- The hook creates or reuses a Linear issue according to the canonical `linear-cli` rules.
- Hook failure is hard-blocking. If Linear query/create/update or session-record writes fail,
  repair the issue manually with `linear-cli`; do not silently continue.
- Existing active `hook_state.json` is reused until the end-task review hook marks the task as
  reviewed.

## Canonical Command

```bash
.codex/skills/linear-cli/scripts/start_task_hook.sh --workspace .
```

Useful test modes:
- `--dry-run`: classify and write records without mutating Linear.
- `--skip-linear`: verify hard-block behavior without mutating Linear.
- `--objective "<task>"`: pass an explicit task objective.
- `--force`: force tracking for ambiguous tasks.

## Companion Skills

- `planning-with-files`: supplies thread-scoped task/progress/findings records.
- `unit-test`: supplies task-scoped acceptance commands.
- `code-review-with-logs`: consumes `hook_state.json` at task end and appends the standard report.

## Validation

```bash
uv run --with pyyaml python .codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/uv-package-manager/linear-cli
uv run --with pytest --with pyyaml python -m pytest -q tests/unit/skills/test_task_hooks.py
```
