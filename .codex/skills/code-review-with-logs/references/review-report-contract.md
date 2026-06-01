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

When the user explicitly asks for a browsable HTML report, the optional HTML artifact defaults to:
- `.codex/html_report/<report-name>.html`

This HTML artifact is not part of the default stop-hook contract. If generation needs a script,
that script is review-local evidence under `.codex/reviews/<review_id>/`, not a reusable helper
inside this skill.

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
  - window label when available,
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
- Window labels in the group message must be complete tmux pane-address labels in
  `name:window.pane` form, such as `codex:1.0` or `codex:8.0`. Bare prefixes like `codex`,
  window-only labels like `codex:8`, and tmux internal pane ids like `%41` are treated as missing
  input and must not be shown as valid window labels.
- Window labels must be scoped to the reviewed session. A caller must not use the sender/current
  Codex window label for a report whose `review_report.json` `session_id` is different. If the
  reviewed session's window label is known, the send command must provide both `--codex-window`
  and `--codex-window-session <review_session_id>`; otherwise the group message must render
  `窗口号：未提供`.
- Feishu delivery must automatically detect current Codex context before sending. The script
  should infer the reviewed session id from report-local context or `CODEX_THREAD_ID`. The window
  label is inferred by matching the current Codex process TTY against `tmux list-panes -a` output
  rendered as `#{session_name}:#{window_index}.#{pane_index}`. `CODEX_WINDOW*` environment values
  are accepted only when they already use the same pane-address shape.
- New reports may include optional top-level `codex_context` containing `session_id`,
  `session_source`, `window_label`, `window_label_kind`, `window_source`, `pane_tty`, `pane_id`,
  and `window_name`. Delivery must prefer this report-local context when its `session_id` matches
  the report `session_id`, so later resends keep the original reviewed session's window context
  instead of the sender's current window. `pane_id` is auxiliary debug evidence and must not be
  rendered as the user-visible `窗口号`.

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

## Optional HTML Review Report Contract

Optional HTML reports are explicit, static report artifacts. They must:
- read existing artifacts only;
- write the HTML under `.codex/html_report/`;
- use Chinese visible report text while preserving code identifiers, field names, and paths;
- state the report object: module, workflow, benchmark, incident, experiment, or policy;
- include a structured overview, experiment score or result metrics when present, module
  composition (`module composition`), integration/data-flow links, representative cases, evidence paths, and claim
  boundaries;
- visualize module upstream/downstream relationships before detailed evidence, including the
  primary input object and primary output object for each non-trivial module in the chain;
- make single-input/single-output interface flow explicit when the report describes connected
  modules or agent/tool pipelines;
- render explicit module rules, agent rules, policies, rubrics, or config snippets as folded
  `<details>` code blocks; these are folded `<details>` code blocks paired with
  natural-language explanations;
- make full sample/task rows secondary or folded unless the user explicitly asks for a per-sample
  audit;
- redact secret-like keys such as token, bearer, authorization, secret, and api-key before
  rendering raw metadata.

## Optional HTML Script Contract

If an HTML report needs Python or shell generation logic, create it under the review directory,
for example `.codex/reviews/<review_id>/render_html_report.py`.

- Review-local scripts may be task-specific and may read that review's artifacts plus referenced
  runtime artifacts.
- The final HTML may still be written under `.codex/html_report/` for a stable browser entry.
- Do not add task-specific HTML renderers to `.codex/skills/code-review-with-logs/scripts/`.
- Keep the review-local script path and output path in the review command trace or task progress.
