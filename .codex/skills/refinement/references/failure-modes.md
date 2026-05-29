# Failure Modes

Record reusable AGENTS.md and skill usability failures here. Keep task-local evidence in
`.codex_record/<session_id>/` and link or summarize only reusable lessons.

## Experiment Handbook Missing Run Command Schema
- Date: 2026-05-26
- Trigger: User invoked `$refinement` and said `experiment-handbook` should state how to run each experiment, including tau-bench examples and how to build scripts for training parquet data on a model.
- Expected: `experiment-handbook/SKILL.md` directly defines how to record experiment run commands and gives concrete reusable examples for tau-bench/tau2 and parquet training.
- Actual: The skill only required a vague "Command shape" field and pushed details into references without showing the required run-command entry shape.
- Root cause: The first version optimized for routing and storage location but did not include a falsifiable run-method schema or representative examples.
- Changed rule or skill: `.codex/skills/experiment-handbook/SKILL.md` now includes a run-method entry contract plus tau2 and parquet-training examples.
- Regression check: `uv run --with pytest python -m pytest -q tests/unit/skills/test_experiment_handbook.py`
- Verification result: Passed on 2026-05-26; the focused test confirms the command-recording schema and required examples are present.

## ContextSwarm Runtime Artifacts Missed By Review
- Date: 2026-05-27
- Trigger: `code-review-with-logs` reviewed a ContextSwarm live ICPC task with explicit `live_preflight_report.json` and `live_context_report.json` log paths.
- Expected: The review reads those ContextSwarm live artifacts as runtime evidence and checks their status facts instead of requiring qz/tau-only artifacts.
- Actual: The runtime-evidence detector only recognized filenames such as `events.jsonl`, `tau2-command.json`, `summary.json`, and `report.json`, so a ContextSwarm ICPC review was marked `BLOCKED` despite valid live artifacts being supplied.
- Root cause: The owning review skill coupled "runtime evidence required" to qz/tau filename heuristics and did not include the ContextSwarm live artifact contract used by AgentSwarm ICPC runs.
- Changed rule or skill: `.codex/skills/code-review-with-logs/scripts/code_review_with_logs.py` now recognizes `live_preflight_report.json`, `live_context_report.json`, and `controller_state.json` as `ContextSwarm live` runtime artifacts.
- Regression check: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --with pytest python -m pytest -q tests/unit/skills/test_code_review_with_logs.py`
- Verification result: The focused regression creates a ContextSwarm live report fixture and requires review status `PASS` with `contextswarm_live` runtime evidence.

## Linear Hook Reused A Completed Mismatched Issue
- Date: 2026-05-28
- Trigger: A continuation task for paper-faithful ContextSwarm live ICPC inherited or reused prior tracking state for a completed Feishu/reporting or replay-scoped issue.
- Expected: The start-task path must compare the current objective against the active issue, exact-title query result, and prior hook state before implementation; a completed or semantically mismatched issue must be repaired or replaced before work continues.
- Actual: The session initially pointed at completed or wrong-scope Linear issues, so the agent had to repair `hook_state.json`, create/reopen the correct issue, and preserve the mismatch in progress records.
- Root cause: The historical task chain mixed continuation state with prior closeout state, and the tracking workflow did not make stale issue reuse visible enough before substantive work.
- Changed rule or skill: `.codex/skills/linear-cli/SKILL.md` owns exact-title filtering, current issue reuse/reopen rules, hard-blocking hook failure, and session-record writes; this refinement entry records the reusable failure pattern.
- Regression check: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --with pytest python -m pytest -q tests/unit/skills/test_refinement_failure_modes.py`
- Verification result: The focused source assertion requires this failure mode entry and confirms `refinement/SKILL.md` now tells agents to curate historical traces by reproducible behavior.

## Blocked Or Fake Runtime Evidence Overclaimed As Completion
- Date: 2026-05-28
- Trigger: ContextSwarm ICPC work produced blocked preflight artifacts, deterministic fake-worker diagnostics, or replay artifacts while the user objective still required real AISW Codex workers and judge-backed ICPC evidence.
- Expected: The agent must report blocked/local-control-plane evidence as such and must not claim live ICPC completion until real worker, gateway, and judge artifacts satisfy the stated objective.
- Actual: Multiple closeouts needed corrections that distinguished implementation/pass-review evidence from the still-unmet live ICPC completion claim.
- Root cause: Review PASS, deterministic diagnostics, and fail-closed artifacts were easy to conflate with the user-visible completion condition when the claim boundary was not stated next to the evidence.
- Changed rule or skill: `.codex/skills/refinement/references/failure-modes.md` records this reusable claim-boundary failure; task-specific run methods should continue to encode concrete acceptance evidence in their owning skills.
- Regression check: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --with pytest python -m pytest -q tests/unit/skills/test_refinement_failure_modes.py`
- Verification result: The focused source assertion requires this failure mode entry and checks that trace curation avoids raw-log dumping while preserving reusable completion-boundary lessons.

## Review Bash Wrapper Invoked As Python
- Date: 2026-05-28
- Trigger: A manual closeout attempted to run `.codex/skills/code-review-with-logs/scripts/run_code_review_with_logs.sh` through `uv run python`.
- Expected: Shell wrappers must be executed with `bash`, while Python modules/scripts are executed through `uv run python`.
- Actual: The command failed because the target was a bash wrapper, not a Python file; the correction was to invoke `bash .codex/skills/code-review-with-logs/scripts/run_code_review_with_logs.sh ...`.
- Root cause: The review skill had many Python-runner examples, and the wrapper-vs-Python entrypoint distinction was not salient enough at the point of use.
- Changed rule or skill: `.codex/skills/code-review-with-logs/SKILL.md` documents the wrapper as a bash script and reserves direct Python execution for underlying Python scripts; this refinement entry records the failure pattern.
- Regression check: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --with pytest python -m pytest -q tests/unit/skills/test_refinement_failure_modes.py`
- Verification result: The focused source assertion requires this failure mode entry and validates the entry shape so the wrapper-type correction remains discoverable.

## Feishu Markdown Attachment Used An Absolute Temp Path
- Date: 2026-05-28
- Trigger: A closeout report send created a normalized Markdown attachment under `/tmp` and then called `lark-cli im +messages-send --file`.
- Expected: Feishu file upload paths used by the local CLI must be workspace-relative or otherwise accepted by `lark-cli`, while the group text remains a concise summary and the Markdown report is attached as a file.
- Actual: The text message sent, but the attachment failed because `lark-cli` rejected the absolute `/tmp` path; the closeout had to normalize the attachment into the workspace before sending.
- Root cause: The delivery workflow treated temporary-file convenience as equivalent to CLI upload compatibility and did not test the file path contract separately.
- Changed rule or skill: `.codex/skills/code-review-with-logs/SKILL.md` and its report delivery tooling own Feishu text-plus-file closeout behavior; this refinement entry captures the path-compatibility lesson.
- Regression check: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --with pytest python -m pytest -q tests/unit/skills/test_refinement_failure_modes.py`
- Verification result: The focused source assertion requires this failure mode entry and keeps the reusable Feishu upload constraint visible from `refinement`.

## Uv Tool Dependencies Missing Without Explicit Injection
- Date: 2026-05-28
- Trigger: Validation commands used `uv run python -m pytest ...` or a YAML-reading helper in an environment where `pytest` or `pyyaml` was not installed in the project environment.
- Expected: Task gates that need ad hoc tooling must stay under uv but inject missing tools with `uv run --with pytest --with pyyaml ...` instead of falling back to bare Python or silently weakening validation.
- Actual: Initial commands failed on missing tool imports, and the task gates had to be corrected to use `uv run --with ...`.
- Root cause: The workflow enforced uv-managed execution but did not always distinguish project dependencies from task-local validation tools.
- Changed rule or skill: `.codex/skills/unit-test/SKILL.md` owns task-scoped test gates and now documents `uv run --with ...` patterns; this refinement entry records the recurring dependency-injection failure.
- Regression check: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --with pytest python -m pytest -q tests/unit/skills/test_refinement_failure_modes.py`
- Verification result: The focused source assertion requires this failure mode entry and validates that the new trace-curation guidance remains present.

## Gateway Worker Inherited Main Codex Authorization
- Date: 2026-05-28
- Trigger: A gateway-routed AISW Codex worker inherited the main session `CODEX_HOME` while calling the ContextSwarm gateway `/responses` data plane.
- Expected: Child Codex workers routed through the gateway must use isolated per-worker `CODEX_HOME` so the gateway, not the client, owns upstream authorization.
- Actual: The child Codex sent client Authorization to the gateway data plane, which the legacy gateway intentionally rejects; the next run had to isolate `CODEX_HOME` and then exposed the real upstream gateway 401/502 class instead.
- Root cause: The worker environment inherited agent-session credentials by default, and the gateway data-plane auth boundary was not represented as a reusable failure mode.
- Changed rule or skill: `.codex/skills/refinement/references/failure-modes.md` records the auth-boundary failure; task-specific ContextSwarm run guidance should cite this when configuring gateway-routed workers.
- Regression check: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --with pytest python -m pytest -q tests/unit/skills/test_refinement_failure_modes.py`
- Verification result: The focused source assertion requires this failure mode entry and keeps credential-boundary lessons separate from raw worker logs.

## Desired Parallelism Collapsed To One Worker
- Date: 2026-05-28
- Trigger: A 12-task ContextSwarm controller/gateway diagnostic expected one worker per task, but runtime capacity was computed from the maximum per-task desired parallelism.
- Expected: Supervisor capacity for a multi-task tick must be based on total desired capacity, capped by configured limits, so 12 tasks at `desired_parallelism=1` can launch 12 worker episodes.
- Actual: `max(desired_parallelism)` collapsed the run to a single worker even though all 12 tasks requested capacity; the diagnostic had to be corrected to sum desired capacity.
- Root cause: Per-task desired parallelism and total launch capacity were conflated, hiding cross-task resource allocation failures in controller/gateway reproduction work.
- Changed rule or skill: `.codex/skills/refinement/references/failure-modes.md` records the resource-allocation failure pattern so future controller/gateway traces check both per-task and aggregate capacity.
- Regression check: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --with pytest python -m pytest -q tests/unit/skills/test_refinement_failure_modes.py`
- Verification result: The focused source assertion requires this failure mode entry and verifies all newly curated entries retain the required refinement fields.
