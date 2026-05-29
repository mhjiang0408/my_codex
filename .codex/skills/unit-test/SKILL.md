---
name: unit-test
description: Build strict task-level acceptance tests and lint gates that prove a user-requested code change fails before the fix and passes after the fix, including logic regressions, threshold-based performance checks, and real-API regression tests.
metadata:
  short-description: Build strict task-level acceptance tests
---

# Unit Test

Use this skill when the user asks for strict tests, unit tests, regression tests, CI tests,
linter gates, "fail before / pass after" proof, or task-specific acceptance tests.

This skill is about **did the code change satisfy the task**.
It is not about measuring production impact or comparing experimental groups.

## Boundary

- `unit-test`: code-implementation acceptance. It answers "did we do the requested thing?"
- `harness-bench`: production or product-effect evaluation. It answers "how good is the outcome?"

Route to `harness-bench` only when the user asks for benchmark methodology, online evaluation,
or production-effect comparison in `tests/bench/**`.

Do not put `unit-test` deliverables in `tests/bench/**` unless the user explicitly asked for a
benchmark and the task really is an effect evaluation rather than a correctness gate.

## Companion Skills

### `planning-with-files`
- Trigger: any non-trivial task that needs more than a couple of commands.
- Context to pass:
  - frozen task goal,
  - acceptance criteria,
  - changed paths,
  - the intended test kind,
  - the failure-before-change proof plan.
- Expected output:
  - `.codex/task_plan.md`,
  - `.codex/progress.md`,
  - `.codex/findings.md`,
  - explicit task dependencies and worker ownership.

### `code-review-with-logs`
- Trigger: after the implementation and task tests are ready for formal review.
- Context to pass:
  - the task acceptance spec path,
  - the task-scoped pytest / ruff / mypy commands,
  - any full-repo status commands,
  - the deliverable paths,
  - the intended review scope / review id; pass a commit SHA only when the caller explicitly
    needs legacy commit-target metadata.
- Expected output:
  - a review spec block or full review spec,
  - a formal review session under `.codex/reviews/<review_id>/`,
  - session-scoped proof that the task-scoped deliverable and test gates passed.

### `harness-bench`
- Trigger: the task has moved from "prove the code satisfies the requirement" to
  "measure production effect, success rate, latency, or quality."
- Context to pass:
  - benchmark question,
  - fixed comparison groups,
  - metrics,
  - any archived or live sample requirements.
- Expected output:
  - a benchmark spec,
  - a `tests/bench/**` harness,
  - benchmark artifacts and optional review-spec benchmark commands.

If another skill calls `unit-test`, it should pass only the task contract and code scope.
`unit-test` should not absorb benchmark design or formal review behavior that belongs to the
companion skill.

## Workflow

1. Freeze the task contract.
   - Rewrite the request into a short, falsifiable acceptance statement.
   - Pick one test kind:
     - `logic_regression`
     - `performance_threshold`
     - `real_api_regression`
2. Create or update a task acceptance spec.
   - Use `assets/templates/task_acceptance_spec.template.md`.
   - Keep the spec in `.codex/`, not under the skill directory.
3. Prove failure before the fix.
   - Add or select a task-scoped test that fails against the old behavior.
   - Record the exact failing command and the expected failure signal.
4. Implement the change.
5. Prove success after the fix.
   - Run the same task-scoped test and require it to pass.
   - Run task-scoped `ruff` and `mypy` through `uv run python -m ...`.
6. Emit review-spec content.
   - Use `scripts/plan_task_tests.py` to normalize commands.
   - Use `scripts/render_review_block.py` to generate the markdown block that can be inserted
     into `.codex/review_spec.md` or a task-specific review spec.
7. Hand off to `code-review-with-logs`.

## Hard Rules

- Every explicit user task gets its own acceptance test contract.
- The same task must show:
  - **before**: failing or blocked evidence that matches the requirement,
  - **after**: passing evidence from the same contract.
- Task-scoped gates are blocking:
  - `uv run python -m pytest`
  - `uv run python -m ruff`
  - `uv run python -m mypy`
- Full-repo health is reported separately. It is useful, but it is not the default blocker for
  a single task unless the user explicitly asks for whole-repo cleanup.
- If the task is about a real API failure mode, prefer a real regression test under
  `tests/regression/` or `tests/integration/`, not a mock-only test.
- Real-API regression tests default to `config/pipeline.yaml` unless the user explicitly says
  to use a different config path.

## Test Kinds

### `logic_regression`
- Use for pure code-path or state-machine correctness.
- Preferred locations:
  - `tests/unit/**`
  - `tests/regression/**`

### `performance_threshold`
- Use when the requirement is still code-level correctness, but the contract is a threshold.
- Example:
  - "workspace clear must complete below 2.0 seconds for this fixture"
- Preferred locations:
  - `tests/performance/**`
- The test must assert a threshold, not just print timing.

### `real_api_regression`
- Use when the acceptance criteria depend on the behavior of a real backend, evaluator, or
  external API.
- Preferred locations:
  - `tests/regression/**`
  - `tests/integration/**`
- Default config source: `config/pipeline.yaml`
- The test must assert the real failure mode directly, for example:
  - timeout present before the fix,
  - timeout absent after the fix.

Read `references/test-taxonomy.md` for placement guidance and
`references/task-to-test-mapping.md` for concrete examples.

## Acceptance Spec Contract

The acceptance spec uses YAML frontmatter plus optional markdown notes. The frontmatter fields
are the contract consumed by the helper scripts.
For automation-heavy callers, the helper scripts also accept a JSON task spec and normalize it
to the same command plan.

Required frontmatter fields:
- `task_id`
- `title`
- `test_kind`
- `acceptance_criteria`
- `failure_before_change`
- `success_after_change`
- `changed_paths`
- `test_paths`
- `task_pytest_commands`

Optional frontmatter fields:
- `task_ruff_commands`
- `task_mypy_commands`
- `repo_status_commands`
- `requires_real_api`
- `config_path`
- `notes`

Validation details:
- `acceptance_criteria`, `failure_before_change`, `success_after_change`, `changed_paths`,
  `test_paths`, and `task_pytest_commands` must each be a YAML list of strings. Do not write
  `failure_before_change` or `success_after_change` as a scalar string; `plan_task_tests.py`
  rejects that shape.
- `task_pytest_commands` must be a non-empty list of strings even for runtime-only or
  read-only acceptance tasks; use deterministic artifact/source assertions when no pytest
  module is appropriate.
- Optional `notes`, when present, must be a list of strings, not a scalar string.

When `requires_real_api: true`, `config_path` defaults to `config/pipeline.yaml`.

## Scripts

### `scripts/plan_task_tests.py`
- Input: task acceptance spec path.
- Output:
  - normalized metadata,
  - blocking task-scoped commands,
  - non-blocking full-repo status commands.
- Formats:
  - `json`
  - `markdown`
  - `commands`

### `scripts/render_review_block.py`
- Input: task acceptance spec path.
- Output: markdown block for review specs, including:
  - task summary,
  - failure-before-change contract,
  - success-after-change contract,
  - task-scoped test / lint / type commands,
  - full-repo status commands.

## Validation

Run:

```bash
uv run --with pyyaml python .codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .codex/skills/unit-test
```

## Notes

- Keep task acceptance specs in `.codex/`, for example
  `.codex/unit_test_specs/<task_id>.md`.
- Prefer deterministic helper scripts and small templates over free-form prose.
- In YAML frontmatter specs, quote any entire shell command that contains `: ` inside the command
  text, for example `grep -F "Slug: codingwithai"` or `print("ruff not applicable: ...")`.
  Otherwise YAML can parse that list item as a mapping instead of a string, and
  `plan_task_tests.py` will silently drop it from the normalized command list.
- Task command lists such as `task_pytest_commands`, `task_ruff_commands`,
  `task_mypy_commands`, and `repo_status_commands` are still executed through a
  shell. Do not place literal Markdown backticks inside `python -c "..."` or
  similar shell-parsed commands, because the shell can treat them as command
  substitution before Python receives the source. Prefer plain-substring checks
  or build the backtick character inside Python when the exact character must be
  asserted.
- In YAML frontmatter specs, quote list items that begin with a markdown backtick/code span, such
  as `` `create_workspace()` claims...``. PyYAML can reject a leading backtick in a block sequence
  with `found character '`' that cannot start any token`; quoting the whole item preserves the
  markdown text and keeps `plan_task_tests.py` parseable.
- Markdown acceptance specs must terminate the YAML frontmatter with a closing `---` line before
  any prose notes. If the closing delimiter is missing, both `plan_task_tests.py` and
  `render_review_block.py` fail immediately with an `unterminated YAML frontmatter block` error,
  which blocks review-spec generation even when the task commands themselves are correct.
- In Markdown acceptance specs, `failure_before_change`, `success_after_change`, and `notes`
  must be YAML lists of strings, not scalar strings. `plan_task_tests.py` rejects scalar values
  for these fields with `field ... must be a list of strings`.
- For rolling-window or time-based acceptance tests, do not hard-code timestamps that will age out
  against the real wall clock during later formal review runs. Prefer one of:
  - inject `now=` into the tested function/CLI seam, or
  - generate fixture timestamps relative to `datetime.now(timezone.utc)` inside the test itself.
- On this workspace, prefer task-scoped gates like `uv run python -m pytest`,
  `uv run python -m ruff`, and `uv run python -m mypy` so the fail-before / pass-after
  contract runs against the uv-managed environment.
- If the repo-local `.venv` intentionally omits tooling such as `pytest` or `mypy`, it is
  acceptable to express task-scoped gates as `uv run --with pytest python -m pytest ...` and
  `uv run --with mypy python -m mypy ...` so formal review can provision the exact tool on demand
  without mutating the locked environment. Record that choice in
  `.codex_record/<session_id>/progress.md` and keep the command pinned to the task paths only.
- If a task proves its fail-before condition by diffing or grepping an old file revision, pin the
  command to a concrete pre-change commit SHA, fixture, or immutable baseline rather than moving
  `HEAD`. Formal review is workspace/session-scoped by default, so `HEAD` can drift with the
  current workspace and is not a reliable historical pre-fix state.
- If default task-scoped `mypy` repeatedly times out on a shared host without surfacing any
  type errors, it is acceptable to switch the task gate to
  `uv run python -m mypy --follow-imports=skip <changed-paths...>` as long as:
  - the timeout behavior is recorded in `.codex/progress.md`,
  - the narrowed command is written explicitly in the task acceptance spec and review spec,
  - and the gate still covers the changed Python modules directly.
- If the `pytest` runner itself is blocked by shared-host startup or repo-level test bootstrap
  before the task contract code even runs, it is acceptable to add a task-scoped direct contract
  script (for example a small AST/source-contract verifier under `tests/unit/**`) and use
  `uv run python <script>.py` as the blocking execution command, as long as:
  - the blocked `pytest` command and timeout/host evidence are recorded in `.codex/progress.md`,
  - the direct script executes the same task assertions that the blocked pytest target would cover,
  - and the acceptance spec / review spec explicitly explain why `pytest` was not the runnable
    gate on that host.
- If a task-scoped direct contract script still blocks on shared-storage imports before it reaches
  the real task logic, it is acceptable to make that script stage a minimal `/tmp` local mirror of
  the changed module plus only the stub dependencies it actually imports, and then run the contract
  against that local mirror, as long as:
  - the mirrored file is copied from the current worktree at execution time,
  - the stubbed dependencies are limited to import-only surface needed for the contract,
  - the mirror command is written explicitly in the acceptance spec / review spec when used as a
    blocking gate,
  - and the shared-host import blocker is recorded in `.codex/progress.md`.
- If task-scoped `ruff` on the changed paths is blocked by pre-existing repository-wide long-line
  noise in already-large touched files, it is acceptable to run
  `uv run python -m ruff check --ignore E501 <changed-paths...>` as long as:
  - the reason is recorded in `.codex/progress.md`,
  - the exact narrowed command is written explicitly in the task acceptance spec and review spec,
  - import/order issues and all other lint rules still run on the changed paths,
  - and the user did not ask for whole-file or whole-repo style cleanup.
- If `uv run python -m ruff` itself stalls on a shared host before even returning `--version`,
  record that blocker in `.codex_record/<session_id>/progress.md` and use a narrower
  uv-managed syntax gate such as `uv run python -m py_compile <changed-python-files>` rather
  than silently falling back to a system `ruff`.
- For shell launcher fixes that change how a script selects its Python interpreter, add a
  deterministic test seam such as an env override for the Python binary or a force-fallback
  switch. Otherwise focused tests may silently hit the repo's real `.venv` and stop being
  hermetic.
- If the user asks for both correctness proof and production-effect evaluation, use this skill
  first for the correctness gate and then route to `harness-bench` for the benchmark layer.
- For read-only explanation or analysis tasks that intentionally do not change product code,
  it is acceptable to treat a missing report file under `.codex/reports/` as the
  fail-before condition and a single-line deterministic `uv run python -c` content assertion as the
  pass-after gate.
- For prompt-contract tasks that are supposed to improve retry guidance or evaluator comments,
  write acceptance criteria against the rendered prompt text itself. Do not stop at generic
  "actionable" wording; assert that the prompt tells the model to name the next file(s) to edit
  and the concrete modifications to make whenever those targets can be inferred reliably.
- When the user explicitly asks for more detailed retry plans, tighten the contract beyond file
  naming alone: assert that the rendered prompt tells the model to tie the unresolved query issue
  to a specific file plus a specific function, method, branch, or logic block whenever those
  targets can be inferred reliably, and only fall back to `[unknown]` when both file and
  function/block location are not inferable.
- User correction recorded 2026-05-01: for staged rollout dataset acceptance, "最长到 stageN"
  should be tested as a cumulative threshold by default, not an exact bucket. A correct gate checks
  `stage1 <= stage2 <= stage3 <= stage4 <= stage5` as file-set subsets, verifies `stage5` equals
  the full source set, and rejects exact-only counts unless the user explicitly requested exact
  disjoint buckets.
