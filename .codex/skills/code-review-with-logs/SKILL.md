---
name: code-review-with-logs
description: Run a task-closeout or runtime-issue review after implementation, failed execution, or task completion. Use when Codex must first run task-scoped unit-test commands and then produce Markdown and JSON reports from repository context, command logs, git diff, session-scoped codex_record files, and optional codex_idea files, including reliable check against the task plan and idea plan.
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
              echo "[code-review-with-logs] BLOCKED: missing end_task_review_hook.sh at $SCRIPT" >&2
              exit 1
            fi
---

# Code Review With Logs

Use this skill only at the end of a task or when a run/test has a problem that needs a structured closeout. The workflow is no longer a deliverable validator and no longer uses `.codex/review_spec.md`, naming rules, benchmark gates, `codex review`, or commit-target review.

In this workspace, this closeout is owned by the Codex end-task review hook. The old manual
code-review checkpoint is removed: agents should not pause at task end and ask whether to run
review.
The Stop hook runs the review/report workflow for any active tracked task created by the
start-task Linear hook.

## Workflow
Run two modules in this exact order:

1. **Unit-test module**
   - Use the `unit-test` skill before this skill whenever the task needs acceptance coverage.
   - Pass the task-scoped pytest, lint, type, runtime assertion, or source assertion commands through `--test-command`.
   - If no test command is available, the review must be `BLOCKED`; do not invent broad repository-wide tests during review.

2. **Context/report module**
   - Read repository context, provided logs, git diff metadata, `.codex_record/<session_id>/`, and optional `.codex_idea/<session_id>/`.
   - Emit both human-readable Markdown and machine-readable JSON.
   - Perform `reliable check`: compare the running command and code/template changes with the task plan and, for research sessions, the idea plan.
   - Apply high-signal review discipline: flag only consequential, evidence-backed issues and
     avoid noisy style feedback.

## High-Signal Review Discipline

Use this stance for final closeout findings and review-only requests:

- Review changed files first, expanding to nearby context only when needed to prove an issue.
- Report an issue only when it is likely real and consequential: compile/import/type failures,
  definite logic errors, broken invariants, plausible security/privacy leaks, undocumented public
  API/schema/behavior changes, tests that miss the changed behavior, or clear repository-rule
  violations.
- Do not report subjective style preferences, formatter nits, speculative edge cases, broad
  "add more tests" comments without concrete risk, or pre-existing unrelated issues.
- For each finding include severity (`blocker`, `major`, or `minor`), location, problem, impact,
  minimal fix direction, and confidence (`high` or `medium`).
- If no high-signal issues are found, say that clearly and list what was checked.

## End-Task Hook
Canonical local entrypoint:

```bash
.codex/skills/code-review-with-logs/scripts/end_task_review_hook.sh --workspace .
```

The wrapper is a bash script (`set -euo pipefail`), so hook frontmatter fallbacks must invoke it
with `bash "$SCRIPT"` when the executable bit is missing; do not use plain `sh`.

The hook reads `.codex_record/<session_id>/hook_state.json`. If no active tracked task exists, it
skips. If an active task exists, it runs `run_code_review_with_logs.sh` through the Python hook
adapter and hard-blocks on `FAIL` or `BLOCKED`.

Do not manually invoke `end_task_review_hook.sh` from an ordinary shell inside an active Codex
session to perform a closeout with custom evidence. That wrapper is the Stop-hook entrypoint; a
manual call can be observed as another shell command by the same Stop hook and recursively launch
more end hooks. For manual or scripted closeout evidence, call `run_code_review_with_logs.sh`
directly with explicit `--test-command` and `--changed-path` arguments.

Trigger contexts:
- `completed`: normal task closeout.
- `runtime_issue`: command/tool/runtime failure closeout.
- `test_failure`: unit-test or acceptance command failure closeout.

Evidence inputs:
- `CODEX_REVIEW_TEST_COMMANDS`, semicolon/newline separated or JSON list.
- `CODEX_CHANGED_PATHS`, semicolon/newline separated or JSON list.
- `CODEX_REVIEW_LOG_PATHS`, semicolon/newline separated or JSON list.
- explicit CLI flags `--test-command`, `--changed-path`, and `--log-path`.

If no task-scoped test command can be found, the report status is `BLOCKED`; this is intentional
and hard-blocking for tracked tasks. Pure planning tasks may skip the end hook only when no active
tracked implementation task exists.

## Command
```bash
.codex/skills/code-review-with-logs/scripts/run_code_review_with_logs.sh \
  --workspace . \
  --session-id <session_id> \
  --review-id <review_id> \
  --status-context completed \
  --objective "<task objective>" \
  --permission-boundary "<allowed/blocked files, commands, tools, network, secrets>" \
  --task-completion-summary-file .codex_record/<session_id>/final_cli_summary.md \
  --test-command "uv run python -m pytest -q tests/unit/path/test_file.py" \
  --changed-path .codex/skills/code-review-with-logs/SKILL.md \
  --log-path logs/runtime.log
```

Arguments:
- `--workspace`: repository root; default `.`.
- `--session-id`: session/thread id for `.codex_record/<session_id>/` and `.codex_idea/<session_id>/`; default `CODEX_THREAD_ID`, then `main`.
- `--review-id`: optional artifact id; default timestamp plus sanitized session id.
- `--status-context`: one of `completed`, `runtime_issue`, or `test_failure`.
- `--test-command`: repeatable; every command is blocking unit-test evidence.
- `--changed-path`: repeatable; task-owned paths used for diff and rollback reporting.
- `--log-path`: repeatable; runtime/test logs to summarize.
- `--objective` and `--permission-boundary`: optional explicit report fields; provide them when available.
- `--task-completion-summary` / `--task-completion-summary-file`: optional final CLI-facing
  closeout text. When supplied, this is the authoritative source for `## Task completion summary`
  and the Feishu text message. The file path is resolved relative to `--workspace` when it is not
  absolute.

`scripts/run_review_flow.sh` is retired and intentionally exits with instructions for the new command.

## Outputs
Every run writes to:

```text
.codex/reviews/<review_id>/
```

Required artifacts:
- `review_summary.md`
- `review_report.json`
- `unit_test_results.json`
- `context_reliability_results.json`
- `review_run.log`
- `session.json`

`.codex/reviews/latest.json` may point at the newest run. The canonical evidence remains the session directory.

The same standard Markdown report must also be appended to
`.codex_record/<session_id>/progress.md`, bracketed by:

```text
<!-- code-review-with-logs:<review_id>:start -->
...
<!-- code-review-with-logs:<review_id>:end -->
```

Do not substitute a Feishu summary, final closeout note, or short status update for this append.
The appended block must contain the standard report fields listed below.

## Feishu Delivery Note

- Workspace user correction from 2026-05-24: do not use Feishu documents as the default closeout
  report carrier. Full closeout reports are too hard to scan when pasted directly into the fixed
  Feishu group message, so keep the local report structure unchanged, send one ordinary
  text message to the group, and send the complete `review_summary.md` as a Markdown file
  attachment. The text message is still a real task-completion summary: it must say what was
  completed or blocked, cite the key test/experiment/bench result when present, and then point to
  the Markdown attachment.
- Workspace user correction from 2026-05-26: the group text message and the Markdown
  `Task completion summary` must use the same final CLI closeout text Codex would present to the
  user. Do not make the review script invent a different primary summary from diff, runtime, or
  test evidence. If the final CLI reply says `完成证据如下：`, preserve it; if it does not, do not
  force that phrase. For manual closeout, pass this text through
  `--task-completion-summary-file` or `--task-completion-summary`. The auto-generated evidence
  summary is only a fallback for legacy callers that provide no final CLI summary.
- Do not use interactive card messages unless the user explicitly asks for cards. The group
  notification should use `lark-cli im +messages-send --text` semantics.
- Keep `review_summary.md`, `review_report.json`, and the required `progress.md` append as the
  durable source of truth. The Feishu Markdown file attachment is the readable copy of the full
  report; the group text message is a CLI-style task-summary message and must not replace local
  review artifacts or the progress append.
- Before sending, dry-run the delivery payload without any Feishu API calls:

```bash
uv run python .codex/skills/code-review-with-logs/scripts/report_review_result.py \
  .codex/reviews/<review_id>/review_report.json \
  --summary-md .codex/reviews/<review_id>/review_summary.md \
  --prepare-feishu-delivery
```

- To send the final review report, send the concise text message and Markdown attachment with:

```bash
HOME=/inspire/hdd/project/qproject-fundationmodel/public/mhjiang/DataFlyWheel/.lark \
  uv run python .codex/skills/code-review-with-logs/scripts/report_review_result.py \
  .codex/reviews/<review_id>/review_report.json \
  --summary-md .codex/reviews/<review_id>/review_summary.md \
  --send-feishu \
  --chat-id oc_28abbb3d6e900a7084967e947da391fe
```

- Default `--send-feishu` must call only `lark-cli im +messages-send --text` and
  `lark-cli im +messages-send --file`. It must not create a Feishu document or call document
  permission APIs.
- The legacy Feishu-document path is available only through explicit `--send-feishu-doc`. Do not
  use it for normal closeout unless the user explicitly asks for a Feishu document again.

## Report Fields
The Markdown report, JSON report, and progress.md appended report block must include these
fields exactly:
- `Task completion summary` in Markdown/progress only; do not add it to
  `review_report.json.fields`
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
- `Task completion summary` is the final user-facing CLI closeout text rendered before the
  standard fields in `review_summary.md` and the appended `progress.md` block. Its primary source
  is the explicit final CLI summary passed by the hook or manual command. Preserve that text's
  structure and wording; do not force fixed phrases. It is intentionally not a required
  `review_report.json.fields` key so existing machine consumers remain compatible. If no explicit
  final CLI summary is supplied, the runner falls back to a synthesized evidence summary for
  backward compatibility; that fallback should remain truthful but is not the normal closeout
  path.
- `Field` lists the impacted modules, paths, or report fields. It answers "what areas did this
  task touch?"
- `Why it matters` explains how each item in `Field` maps to the user's stated objective. It must
  not be used as the impacted-module list itself.
- Do not use the legacy heading/key `Why it matters（影响了哪些模块）`; that phrasing attaches the
  impacted-module meaning to the wrong field.

Status vocabulary:
- `PASS`: unit-test module and reliable check both passed.
- `FAIL`: tests failed or the command/code changes contradict the plan or idea records.
- `BLOCKED`: required evidence is missing or cannot be compared.
- `NOT_APPLICABLE`: only for optional subchecks such as missing `.codex_idea/<session_id>/` on a non-research task.

If formal review is `BLOCKED`, distinguish evidence/tooling gaps from correctness findings. Do not describe a missing transcript, missing test command, or missing session record as a confirmed P0/P1 bug.

## Reliable Check
Read these records for the supplied `session_id`:
- `.codex_record/<session_id>/task_plan.md`
- `.codex_record/<session_id>/progress.md`
- `.codex_record/<session_id>/findings.md`

If present, also read:
- `.codex_idea/<session_id>/idea_plan.md`
- `.codex_idea/<session_id>/idea_progress.md`
- `.codex_idea/<session_id>/idea_findings.md`

Rules:
- Missing required `.codex_record` files make reliable check `BLOCKED`.
- Missing `.codex_idea` files are `NOT_APPLICABLE` unless the task is explicitly research/experiment work.
- Compare command names, changed paths, and objective text against the task plan/progress/findings and any idea plan.
- For qz training/deployment, tau bench / tau2, or ContextSwarm live experiment tasks, also read
  referenced runtime artifacts from the workspace when present. Supported evidence includes qizhi run
  `events.jsonl`, `artifacts.json`, `state.json`, `train_submit_payload.json`,
  `deploy_submit_payload.json`, deployment `launch_manifest.json` /
  `runtime_resolved_manifest.json`, and tau2 `tau2-command.json`, `summary.json`, `report.json`,
  or `results.txt`; ContextSwarm live evidence includes `live_preflight_report.json`,
  `live_context_report.json`, and `controller_state.json`.
- If the real task artifacts use custom names such as `swe_bench_0521.json`,
  `tau_bench_0521.json`, or `train_retry_candidates.json`, add a small canonical manifest with a
  supported name such as `report.json` or `summary.json` and reference the detailed custom
  artifacts from it. The reliable check discovers runtime evidence by filename from task
  records, log paths, changed paths, objective text, and test commands; custom filenames alone
  are not enough for automatic qz/tau runtime-evidence detection.
- If the command or code/template changes cannot be mapped to the task plan or idea plan, mark reliable check `FAIL` and cite the mismatch evidence.
- If evidence is insufficient to decide, mark `BLOCKED` and state exactly which artifact is missing.
- Reliable-check reviewer-facing output must be Simplified Chinese and multi-line in Markdown and
  appended progress reports. Do not render the `reliable check` report section as a full JSON code
  block for humans; render the Chinese `reviewer_markdown` summary instead so Feishu/group chat
  readers can scan it line by line.
- Reliable-check JSON artifacts may keep machine-stable English keys, but must include Chinese
  review fields such as `reviewer_markdown`, `checks[*].display_name`, `checks[*].status_text`,
  `checks[*].details`, `context_files[*].label_zh`, and `context_files[*].status_text`.
- Command consistency must check more than token overlap. When task/idea records specify command
  or experiment parameters such as `--model qwen`, `--dataset agentbench`, or `--seed 7`, compare
  the actual review/test commands against those required parameter values. Missing or mismatched
  required parameters make reliable check `FAIL`.
- Training/deployment/benchmark parameters must be compared against actual runtime artifacts, not
  only review/test commands. For example:
  - qz training: compare `--model-name`, `--dataset-path`, `--global-batch-size`,
    `--rollout-batch-size`, `--run-tag`, and parallelism flags when the task/idea requires them.
  - qz deployment: compare model/service identifiers, `--base-url` / API base, replica or node
    count, and endpoint/service-name fields when the task/idea requires them.
  - tau bench / tau2: compare benchmark name, model, domain, run id/tag, concurrency/trial count,
    status, and metrics such as `average_reward` / `pass_k` when they are part of the idea.
- If a task is explicitly a qz/tau/ContextSwarm live experiment but no readable runtime artifact
  is available, mark the runtime evidence subcheck `BLOCKED` and name the missing artifact class.
  Ordinary implementation tasks, including reliable-check skill changes tested with fixtures,
  must remain `NOT_APPLICABLE` for this runtime-evidence subcheck.
- Runtime evidence summaries must redact secrets. Do not copy `api_key`, bearer tokens,
  authorization headers, or raw endpoint credentials into Markdown, JSON evidence, progress
  reports, or Feishu messages.
- Runtime evidence discovery must be reference-driven. For qz/tau/ContextSwarm live tasks, read only runtime
  artifacts explicitly referenced by task records, logs, test commands, or changed paths. Do not
  glob shared history directories such as `.codex/skills/qizhi-rollout-train-deploy-experiment/runs/*`
  just because the task mentions training or qz; unrelated historical runs can pollute the
  reliable check and may contain stale secrets. If a qz/tau task has no explicit readable
  runtime artifact, mark the runtime-evidence subcheck `BLOCKED` and name the missing artifact
  class.
- When the same `review_id` is rerun, replace the existing marked block in
  `.codex_record/<session_id>/progress.md` instead of appending a duplicate block. This is the
  recovery path for regenerated reports after redaction or evidence-scope fixes.
- Current ruff versions may reject removed rule ids such as `E999`; use `py_compile` for a
  syntax gate and narrow ruff selectors such as `F401,F841` when validating this skill's helper
  scripts without reformatting legacy long lines.
- Every reliable-check subcheck must include a concise Chinese `evidence` list explaining why the
  status was assigned. Passing checks must cite concrete evidence, such as which task/idea files
  were read, which objective/command tokens matched, which parameters were expected and observed,
  and which expected/actual changed paths were compared. Do not use generic phrases like
  "存在可匹配证据" without naming the evidence.
- Reliable-check evidence must not use counted omission wording to hide undisplayed paths,
  methods, or bullets. If a list is long, render every evidence item in separate Markdown lines
  or complete inline lists; do not replace the tail with an omitted-count summary or an equivalent
  "other items" phrase.
- Diff evidence must explain both scope and method. In addition to expected/actual changed paths
  or modules, cite concise Chinese evidence for the expected modification method from the plan
  and the actual modification method from git diff, for example "预期修改方式：增加参数一致性检查"
  and "实际修改方式：新增辅助函数并更新测试断言".
- `.codex_idea` presence alone does not prove research applicability. When idea files exist,
  mark the idea subcheck `PASS` only if the current objective/commands match the idea plan with
  concrete tokens, snippets, or runtime evidence facts such as model, dataset, benchmark, domain,
  run id, metric, training run tag, or deployment service. If they exist but do not match a non-research task, mark
  `NOT_APPLICABLE` and cite the current task plus idea-plan summary; if they do not match an
  explicitly research/experiment task, mark `FAIL`.
- In long-lived sessions, reliable-check evidence extraction must focus on the current active
  task block that matches the review objective. Do not let old task-plan sections or previous
  closeout blocks supply expected changed paths or expected modification methods for the current
  review.
- Read-only data-quality audits for training datasets are research-relevant when they explicitly
  map to an idea/hypothesis, but they are not qz/tau runtime tasks by themselves. Do not require
  qz training/deployment/tau artifacts for a parquet-only audit when the plan says no training or
  benchmark was launched.
- Keep machine-stable protocol fields unchanged: status enums remain `PASS` / `FAIL` /
  `BLOCKED` / `NOT_APPLICABLE`, the report field/key remains `reliable check`, check ids stay in
  `checks[*].name`, and context file ids/statuses stay in `context_files[*].label` /
  `context_files[*].status`.

## Companion Skills
- `unit-test`
  - Trigger before this skill for task-level acceptance commands.
  - Expected handoff: exact blocking commands, changed paths, and acceptance criteria.
- `harness-bench`
  - Use only when the user explicitly asks for quantitative benchmark methodology or `tests/bench/**`.
  - Do not run benchmark commands from this skill by default.
- `planning-with-files`
  - Use for tasks that need durable `.codex_record/<session_id>/` planning/progress/findings records.
- `system-contract`
  - Use before closing agent-rule, skill, workflow, or repository-hygiene changes.
  - Expected handoff: include the system-contract command as one blocking review test command.

## Validation
```bash
uv run --with pyyaml python .codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/code-review-with-logs
uv run --with pytest --with pyyaml python -m pytest -q tests/unit/skills/test_code_review_with_logs.py
```
