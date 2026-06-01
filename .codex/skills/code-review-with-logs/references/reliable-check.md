# Reliable Check

Use reliable check to decide whether the executed command and code/template changes match the recorded task intent.

## Inputs
- `.codex_record/<session_id>/task_plan.md`
- `.codex_record/<session_id>/progress.md`
- `.codex_record/<session_id>/findings.md`
- optional `.codex_idea/<session_id>/idea_plan.md`
- optional `.codex_idea/<session_id>/idea_progress.md`
- optional `.codex_idea/<session_id>/idea_findings.md`
- caller-provided test commands
- caller-provided changed paths
- caller-provided logs
- git diff metadata
- matched `experiment-handbook` run methods from `.codex/skills/experiment-handbook/references/`
- workspace-local runtime artifacts explicitly referenced by the records/logs/test commands or
  by the matched handbook method.

## Status
- `PASS`: required records exist and command/change evidence maps to the plan.
- `FAIL`: evidence exists and contradicts the task or idea plan.
- `BLOCKED`: required records or logs are missing, or evidence is insufficient to compare.
- `NOT_APPLICABLE`: only for optional idea records on non-research tasks.

## Reporting Rule
When evidence is missing, report it as a tooling/transcript blocker. Do not turn missing evidence into a correctness finding.

Human-readable reliable-check output must be Simplified Chinese and multi-line. In Markdown and
progress reports, render the Chinese `reviewer_markdown` summary instead of dumping the full JSON
object as a code block. Use Chinese for check display names, status descriptions, details,
context-file display labels, and context-file status descriptions.

Reliable check must compare actual commands against the original task/experiment requirements and
the matched `experiment-handbook` method. If the task plan, idea records, objective, or handbook
method explicitly require command parameters or runtime facts such as `--model qwen`,
`--dataset agentbench`, `--seed 7`, `task_count=12`, or `run_tag=...`, extract those
requirements and compare them with executed review/test commands plus runtime artifact facts.
Missing or mismatched required parameter values are `FAIL`, not a mere warning, even if broad
command/objective tokens overlap.

The review skill must not own a hard-coded list of experiment families. Concrete experiment
contracts belong in `experiment-handbook` run methods. The reviewer-facing report must show:
- which handbook method matched the task;
- which runtime artifacts were read;
- which commands, parameters, and facts were extracted;
- which required values were missing or mismatched.

Runtime artifact discovery is reference-driven. Only read workspace-local artifacts whose paths
are explicitly mentioned in task records, logs, test commands, changed paths, objective text, or
matched handbook methods. Do not scan shared historical run roots such as
`.codex/skills/.../runs/*` just because the task mentions a type of experiment. Historical runs
may belong to another Linear issue/session and may contain stale secret fragments; including them
makes the reliable check both misleading and unsafe.

If the task clearly claims an experiment/evaluation/benchmark/training/deployment run but no
matching handbook method is available, mark the runtime-evidence subcheck `BLOCKED`. If a matching
method exists but no readable runtime artifact is available, also mark it `BLOCKED`. If the task
is ordinary code or skill implementation work and experiment terms appear only as fixture tests or
documentation, mark the subcheck `NOT_APPLICABLE`.

Do not leak secrets from runtime artifacts. Redact `api_key`, bearer tokens, authorization
headers, raw tokens, and secret fields in JSON and Markdown. It is acceptable to cite a path and
redacted parameter summary instead of copying the raw artifact.

When regenerating a review with the same `review_id`, replace the existing marked
`code-review-with-logs:<review_id>` block in `progress.md` rather than appending a duplicate. This
keeps progress logs auditable after redaction or evidence-scope fixes without preserving the stale
report body.

Each subcheck must include concise Chinese evidence. Evidence should answer "why did this pass or
fail?" with concrete observations:
- session record presence: list the files read or missing;
- idea applicability: list the idea files read or state that optional idea files were absent;
- command/objective alignment: show the task objective, observed commands/paths, and matched
  tokens/snippets;
- command parameters: show required parameters, observed parameters, and missing/mismatched items;
- diff evidence: show expected changed paths/modules from the plan when present, actual changed
  paths from review inputs or git diff, expected modification method, and actual modification
  method. Keep method evidence short: one-line summaries such as "预期修改方式：增加参数一致性检查"
  or "实际修改方式：新增辅助函数并更新测试断言" are enough.

Do not use counted omission wording in reliable-check evidence or reviewer-facing Markdown. If
there are many paths, methods, parameters, or evidence bullets, render all of them, preferably as
separate Markdown lines. Do not hide undisplayed evidence behind an omitted-count summary or an
equivalent "other items" phrase.

For idea applicability, do not treat `.codex_idea` file presence as sufficient. A passing idea
subcheck must cite a concrete match between the current objective/commands and the idea plan, such
as the experiment target, hypothesis, metric, parameter, or module named in both places. Runtime
facts can prove the match when they name the same model, dataset/parquet path, benchmark, domain,
run id/tag, qz training run, deployment service, or metric as the idea plan. If idea files are
present only because the session previously handled another research task, mark the subcheck
`NOT_APPLICABLE` for a non-research closeout and include evidence for both sides: the current task
plus the unrelated idea-plan summary. If the current task is explicitly research or experiment work
and the idea plan does not match, mark it `FAIL`.

Do not rely on generic statements such as "matched evidence exists" without naming the evidence.

Preserve the machine-readable contract: `checks[*].name`, `checks[*].status`,
`context_files[*].label`, `context_files[*].status`, and the `reliable check` report key/heading
remain unchanged.
