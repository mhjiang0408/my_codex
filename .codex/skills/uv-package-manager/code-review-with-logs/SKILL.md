---
name: code-review-with-logs
description: Delegating mirror of the canonical code-review-with-logs closeout hook workflow; use for task completion, runtime issues, or test failures when unit-test evidence and standard Markdown/JSON reports must be produced from session records, logs, diffs, and reliable check.
hooks:
  Stop:
    - hooks:
        - type: command
          command: |
            WORKSPACE_ROOT="${CODEX_WORKSPACE_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
            SCRIPT="$WORKSPACE_ROOT/.codex/skills/code-review-with-logs/scripts/end_task_review_hook.sh"
            if [ -x "$SCRIPT" ]; then
              "$SCRIPT" --workspace "$WORKSPACE_ROOT"
            elif [ -f "$SCRIPT" ]; then
              bash "$SCRIPT" --workspace "$WORKSPACE_ROOT"
            else
              echo "[code-review-with-logs] BLOCKED: missing canonical end_task_review_hook.sh at $SCRIPT" >&2
              exit 1
            fi
---

# Code Review With Logs Mirror

This nested copy exists only for environments that discover skills through
`.codex/skills/uv-package-manager/**`. The canonical implementation and contract live in:

```text
.codex/skills/code-review-with-logs/SKILL.md
.codex/skills/code-review-with-logs/scripts/end_task_review_hook.sh
```

Do not use the retired `.codex/review_spec.md`, deliverable-first, commit-anchored, or
`run_review_flow.sh` workflow from this mirror. The old manual code-review checkpoint has been
replaced by the Codex end-task review hook.

High-signal review criteria, Feishu delivery rules, reliable-check behavior, and validation
commands are owned by the canonical skill. Load the canonical `SKILL.md` before making review
policy decisions.

## Workflow

Run the canonical two-module workflow in this order:

1. **Unit-test module**
   - Use `unit-test` to provide exact task-scoped pytest/lint/type/runtime commands.
   - Missing task-scoped test commands make the review `BLOCKED`.

2. **Context/report module**
   - Read repository context, logs, git diff metadata, `.codex_record/<session_id>/`, and optional
     `.codex_idea/<session_id>/`.
   - Emit Markdown and JSON under `.codex/reviews/<review_id>/`.
   - Append the same standard report to `.codex_record/<session_id>/progress.md`.
   - Perform reliable check against task plan and, for research sessions, idea plan.

## Canonical Command

```bash
.codex/skills/code-review-with-logs/scripts/end_task_review_hook.sh --workspace .
```

The hook hard-blocks tracked tasks on `FAIL` or `BLOCKED` and skips only when no active tracked
task exists in `.codex_record/<session_id>/hook_state.json`.

## Required Report Sections

- `Field`
- `Why it matters`
- `Objective`
- `Permission boundary`
- `Plan changes`
- `command trace`
- `Diff summary`
- `Tests and evals`
- `Cost and retries`
- `Rollback path`
- `reliable check`

Field semantics:
- `Field` lists impacted modules, paths, or report fields.
- `Why it matters` explains how each impacted item corresponds to the user's objective.
- Do not use the legacy heading/key `Why it matters（影响了哪些模块）`.

## Validation

```bash
uv run --with pyyaml python .codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/uv-package-manager/code-review-with-logs
uv run --with pytest --with pyyaml python -m pytest -q tests/unit/skills/test_code_review_with_logs.py tests/unit/skills/test_task_hooks.py
```
