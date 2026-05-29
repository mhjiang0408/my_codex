---
task_id: example-task-id
title: Short task title
test_kind: logic_regression
acceptance_criteria:
  - Describe the exact requirement in one falsifiable sentence.
failure_before_change:
  - State the signal that proves the old behavior does not satisfy the task.
success_after_change:
  - State the signal that proves the task is satisfied after the fix.
changed_paths:
  - src/path/to/code.py
test_paths:
  - tests/regression/path/to/test_case.py
task_pytest_commands:
  - PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/regression/path/to/test_case.py
task_ruff_commands:
  - python -m ruff check src/path/to/code.py tests/regression/path/to/test_case.py
task_mypy_commands:
  - python -m mypy src/path/to/code.py
repo_status_commands:
  - python -m ruff check src tests
  - python -m mypy src tests
requires_real_api: false
config_path: config/pipeline.yaml
notes:
  - Optional implementation note or fixture note.
---

# Task Acceptance Spec

Write only task-specific notes here. The YAML frontmatter above is the contract consumed by the
`unit-test` helper scripts.

Recommended note sections:
- Why this test kind was chosen
- Which user criterion it proves
- Why mock-only coverage would be insufficient, if applicable
- Any threshold rationale for performance tasks
