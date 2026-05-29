# Implementation Guidance (Anchor-Commit Review)

## Goal
Keep formal review auditable by binding one review session to one commit SHA.

## Core Rules
- Start every formal review with a `review_id` and one explicit `review_target_sha`.
- Treat the session as commit-anchored. Formal review for that session is about that one commit
  only; do not change the review target automatically or implicitly.
- If tracked deliverables drift after the anchored commit, mark the session `BLOCKED`.
- Deliverable validation passing is not final success. Final `PASS` requires:
  - deliverables `PASS`
  - tests `PASS`
  - both tied to the same anchored commit

## Artifact Consistency
- `run_review_flow.sh` and `validate_naming_and_outputs.py` must agree on the same `review_target_sha`.
- Do not reuse session artifacts that already point at a different target SHA.
- If session artifacts are stale, either clear them or create a fresh `review_id`.
- Track both the anchored commit and current `HEAD` in final artifacts so drift is auditable.

## Test and Benchmark Guidance
- Build the blocking acceptance section first with the `unit-test` skill whenever the task needs
  explicit proof that it failed before the fix and passes after the fix.
- Keep task-scoped `pytest`, `ruff`, and `mypy` commands in `Test Commands` and any matching
  shell-safe constraints.
- Keep repository-wide `ruff` / `mypy` / `pytest` status collection outside the blocking review
  section; it belongs in CI or a separate non-blocking report.
- Functional test results must record the anchored review target SHA they executed against.
- Benchmark results must do the same when benchmark validation is requested.
- If results target a different SHA than the session anchor, finalization must block.
- Benchmark validation only runs when `Final Deliverables` explicitly request benchmark output.

## Review Recovery
- If a blocking test fails, fix the code, create a new commit, and rerun the entire workflow for
  that new commit.
- If the workspace has uncommitted deliverable edits, stop and commit or discard them before
  retrying review.
- If deliverables change during or after test execution, the old anchored session is no longer
  trustworthy; report `BLOCKED` and rerun against a new explicit commit target.
