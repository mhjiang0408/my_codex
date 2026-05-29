# Review Report Contract

## Output Files
Per review session, write:
- `.codex/reviews/<review_id>/review_summary.md`
- `.codex/reviews/<review_id>/review_report.json`
- `.codex/reviews/<review_id>/unit_test_results.json`
- `.codex/reviews/<review_id>/context_reliability_results.json`
- `.codex/reviews/<review_id>/review_run.log`
- `.codex/reviews/<review_id>/session.json`

`.codex/reviews/latest.json` may point at the newest run.

Also append the same standard Markdown report to:
- `.codex_record/<session_id>/progress.md`

The appended block must be bracketed with:
- `<!-- code-review-with-logs:<review_id>:start -->`
- `<!-- code-review-with-logs:<review_id>:end -->`

This progress append is part of the report contract. It must contain the standard report sections,
not a Feishu report or short closeout summary.

## JSON Contract
`review_report.json` must include:
- `schema_version`
- `review_id`
- `session_id`
- `session_dir`
- `generated_at`
- `status`
- `status_context`
- `fields`

`fields` must include:
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

The progress.md appended Markdown block must include the same section headings:
- `## Task completion summary`
- `## Field`
- `## Why it matters`
- `## Objective`
- `## Permission boundary`
- `## Plan changes`
- `## command trace`
- `## Diff summary`
- `## Tests and evals`
- `## Cost and retries`
- `## Rollback path`
- `## reliable check`

## Feishu Delivery Contract

Feishu delivery must not change the report contract above.

- `review_summary.md`, `review_report.json`, and the `progress.md` appended report block remain
  the authoritative complete report.
- `review_summary.md` must include `## Task completion summary` before the standard report
  sections. This section is the same natural-language closeout text Codex would finally present
  to the user in CLI. The explicit final CLI summary, when supplied through the hook, CLI flag,
  environment variable, or summary file, is authoritative. Preserve its wording and structure;
  do not force a fixed phrase such as `完成证据如下：` unless that phrase is present in the final
  CLI text. Synthesized runtime/diff/test evidence summaries are fallback behavior only for
  legacy callers that do not provide an explicit final CLI summary.
- The Feishu Markdown file attachment is a delivery copy of the complete `review_summary.md`; it
  must not drop or rename standard sections.
- The Feishu group message is a CLI-style task-summary message plus attachment pointer. It should
  include only:
  - final status,
  - review id,
  - objective summary,
  - task completion summary,
  - Tests and evals status,
  - reliable check status,
  - short conclusion,
  - and the Markdown attachment name.
- The group message should reuse the Markdown `Task completion summary` content so it contains
  exactly the same task-completion substance users expect from the CLI final response. Do not
  clip it down to a path-only or one-sentence pointer, and do not rebuild a different primary
  summary from review evidence.
- For runtime tasks, the explicit final CLI text should normally cite facts such as SWE
  `config_path` / resolved / completed counts, tau2 `user_llm` / completed simulations /
  average reward / timeout guard, qz training job ids / queue status, failed-job triage, and
  deployment cleanup when those facts are part of the real closeout. For implementation tasks,
  it should normally cite changed paths plus validation commands and outputs.
- The group message must not paste full sections such as `## command trace`, `## Tests and evals`,
  or `## reliable check`, and must not contradict the Markdown attachment.
- Do not use interactive card delivery unless the user explicitly asks for cards.
- `report_review_result.py --prepare-feishu-delivery` is the no-send contract test surface. It
  outputs `document_markdown`, `message_text`, `attachment_path`, and `attachment_name` without
  calling `lark-cli`.
- `report_review_result.py --send-feishu` sends the concise text message, sends the complete
  Markdown file attachment, and prints a JSON delivery receipt including `message_id`,
  `attachment_message_id`, and `delivery_status`.
- `report_review_result.py --send-feishu-doc` is the explicit legacy document mode. It must not be
  the default closeout path.

## Field Semantics
- `Field` is the affected surface list. It must identify the impacted modules, paths, or report
  fields.
- `Why it matters` is the user-objective mapping. It must explain why each impacted item in
  `Field` matters for the user's requested goal.
- New reports must not emit the legacy key or heading `Why it matters（影响了哪些模块）`.

## Blocking Conditions
Mark final status `BLOCKED` if:
- no unit-test command is supplied,
- required `.codex_record/<session_id>/` files are missing,
- diff evidence is absent and no changed paths are supplied,
- logs or plan records needed for comparison cannot be read.

Mark final status `FAIL` if:
- any unit-test command exits non-zero,
- reliable check finds evidence that command/code changes contradict the task plan or idea plan.

Missing `.codex_idea/<session_id>/` is `NOT_APPLICABLE` for non-research tasks.
