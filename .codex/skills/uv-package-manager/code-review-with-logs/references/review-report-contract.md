# Review Report Contract

## Output Files
Per review session, write:
- `.codex/reviews/<review_id>/review_run.log`
- `.codex/reviews/<review_id>/review_summary.md`
- `.codex/reviews/<review_id>/validation_results.json`
- `.codex/reviews/<review_id>/review_result_report.json`
- `.codex/reviews/<review_id>/test_results.json`
- `.codex/reviews/<review_id>/benchmark_results.json`

`.codex/reviews/latest.json` may point at the newest session, but it is not the canonical
evidence file.

## Summary Structure
`review_summary.md` must contain:
1. header metadata
- final status
- generated time
- review id
- session dir
- spec path
- stop reason

2. ordered sections
- Step 1: Deliverable Review
- Step 2: Test Execution
- Final Feedback

3. status vocabulary
- `PASS`
- `FAIL`
- `BLOCKED`
- `NOT_REQUESTED` for benchmark validation only

Deliverable review passing only means step 1 passed. Final `PASS` requires both deliverables and
tests to pass for the same anchored commit.

## Blocking Conditions
Mark the review `BLOCKED` if:
- `review_spec.md` is missing,
- `Final Deliverables` is missing or empty,
- `Test Commands` is missing or empty,
- benchmark output is required by `Final Deliverables` but no benchmark command or result exists,
- tracked deliverables contain uncommitted edits on top of the anchored commit,
- tracked deliverables changed in later commits after the anchored commit,
- any attempt continues the same review session against a different commit,
- functional or benchmark results target a different anchored commit than the session target.

## Findings Quality Bar
- Deliverable failures must include explicit missing path patterns.
- Test failures must include the failed command and exit code.
- Benchmark failures must include the failed command and exit code when benchmark validation is active.

## Feishu Reporting Contract
- `review_result_report.json` is the session-scoped handoff artifact for final result delivery
  and must record whether the outer workflow sent, skipped, or failed the final Feishu result
  message.
- `review_result_report.json.review_target_sha` must always describe the anchored commit that the
  session attempted to review.
