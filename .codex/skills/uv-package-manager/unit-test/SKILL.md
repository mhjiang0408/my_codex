---
name: unit-test
description: Delegating mirror of the canonical unit-test acceptance workflow; use for task-level fail-before/pass-after tests, lint/type gates, and acceptance command planning.
metadata:
  short-description: Build strict task-level acceptance tests
---

# Unit Test Mirror

This nested copy exists only for environments that discover skills through
`.codex/skills/uv-package-manager/**`. The canonical implementation and detailed rules live in:

```text
.codex/skills/unit-test/SKILL.md
.codex/skills/unit-test/scripts/plan_task_tests.py
```

Load the canonical skill before designing acceptance tests. The canonical skill owns:

- task-scoped fail-before / pass-after acceptance contracts,
- `tests/bench/**` exclusion for ordinary unit/regression tests,
- uv-managed default commands,
- handoff to `code-review-with-logs`,
- and routing to `harness-bench` only for quantitative effect evaluation.

## Canonical Command

```bash
uv run --with pyyaml python .codex/skills/unit-test/scripts/plan_task_tests.py <spec> --format commands
```

## Validation

```bash
uv run --with pyyaml python .codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/uv-package-manager/unit-test
```
