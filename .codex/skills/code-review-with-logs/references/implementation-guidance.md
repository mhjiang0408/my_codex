# Implementation Guidance

## New Workflow
The active review unit is a task closeout session, not a review spec or commit target.

The runner must:
1. execute unit-test commands;
2. read session context and logs;
3. collect git diff metadata;
4. render Markdown and JSON reports;
5. write artifacts under `.codex/reviews/<review_id>/`.

## Boundaries
- Do not run benchmark commands unless another skill explicitly owns that benchmark task.
- Do not require `.codex/review_spec.md`.
- Do not mutate source files while reviewing.
- Do not infer correctness bugs from missing transcript or plan evidence.

## Artifact Consistency
- `review_summary.md`, `review_report.json`, `unit_test_results.json`, and `context_reliability_results.json` must describe the same `review_id`, `session_id`, and final status.
- `review_run.log` records runner actions and unit-test command exits.
