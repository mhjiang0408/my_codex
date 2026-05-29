# Deliverable Validation

## Goal
Make the review pipeline fail fast on the user-requested deliverables before any tests are attempted.

## Pipeline Order
1. Deliverable review
- Parse `Final Deliverables` from `.codex/review_spec.md`.
- Verify every listed path or glob resolves inside the workspace.
- Run naming, required-output, constraint, and uncertainty checks from the same review spec.
- If this step fails, stop immediately and write feedback to the session summary.

2. Test execution
- Run commands from `Test Commands`.
- Treat `Test Commands` as the blocking task-scoped acceptance gate. These commands should come
  from the `unit-test` skill when the task needs explicit acceptance coverage.
- Task-scoped lint/type commands belong here too when they are part of the acceptance contract.
- Benchmark commands are only part of this step when `Final Deliverables` explicitly requires benchmark output.

## Benchmark Gate
- `Benchmark Commands` is optional metadata until `Final Deliverables` requires benchmark output.
- A `tests/bench/**` deliverable or benchmark report artifact turns the gate on.
- If the task only needs proof that the implementation now satisfies the requirement, do not
  move that coverage into `Benchmark Commands`; route it to `unit-test` and keep it blocking in
  `Test Commands`.
- When the gate is off:
  - do not run benchmark commands,
  - do not require benchmark results,
  - record ignored benchmark-looking commands for traceability.

## Session Outputs
All review evidence should live under `.codex/reviews/<review_id>/`:
- `review_summary.md`
- `review_run.log`
- `validation_results.json`
- `test_results.json`
- `benchmark_results.json`

## Status Rules
- `PASS`: deliverables exist and planned tests pass.
- `FAIL`: any executed step fails.
- `BLOCKED`: a required review input is missing or a step cannot run to completion.
