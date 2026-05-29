---
name: rollout-monitoring-review
description: Monitor active rollout panes and logs on shared hosts, classify anomaly families, inspect traceback context before concluding root cause, and send structured Feishu alerts/summaries during long-running rollout health checks.
---

# Rollout Monitoring Review

Use this skill when the user asks to:
- monitor rollout panes or run directories for a period of time,
- classify current rollout failures instead of mixing them into one timeout bucket,
- inspect traceback / timeout / evaluator errors from terminal logs,
- or send structured Feishu alerts while a rollout batch is running.

## Companion Skills

- `planning-with-files`
  - Use to freeze the monitoring window, anomaly rules, and update `.codex/task_plan.md` / `.codex/progress.md` / `.codex/findings.md`.
- `lark-doc` / Feishu MCP
  - Use to send start receipts, anomaly alerts, and end-of-window summaries.

## Core Workflow

1. Freeze the monitoring window with absolute UTC timestamps.
   - Example: `start=2026-04-09T11:44:23Z`, `end=2026-04-09T12:44:23Z`.
2. Freeze anomaly rules before polling.
   - Process disappearance / pane dead
   - `timeout_budget_exhausted before git/workspace prepare`
   - `exhausted the staged plan timeout budget before attempt`
   - `git ls-files -m -z timed out`
   - `Evaluator infrastructure deadline exceeded`
   - `Traceback` / `IndentationError`
   - long log stall / empty log
3. Enumerate active rollout chains from `ps`, not only from `tmux`.
   - Prefer `rollout_executor_cli` as the primary active-run key.
   - Recover `run_dir` from the Python command line.
   - Recover wrapper/bash and pane by PPID walking.
   - Do not rely on `tmux pane_start_command`; after respawn it may be empty or stale.
   - Do not assume wrapper/bash contains `--run-dir`; in this repo it may only exist on the Python child command line.
4. Read only new log content each cycle and emit deduplicated alerts.
5. When `Traceback` appears, inspect surrounding lines before classifying.
   - Never classify from the keyword alone.
   - Read at least 20-40 lines around the traceback.
6. Separate failure families explicitly.
   - Do not collapse SDK launch failures, evaluator deadlines, cleanup noise, and stalled logs into one “timeout” bucket.
7. Send Feishu alerts only for new anomalies, not every repeated line.
8. At the end of the window, send a summary with:
   - monitoring window,
   - anomaly families,
   - affected panes / run_dirs,
   - whether the runner stayed globally alive.

## FeatureBench Connection-Error Lesson From 2026-05-05

- When a user reports `litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`
  on FeatureBench / mini-swe-agent runs, do not conclude from the top-level run status or
  `featurebench_redacted.log` alone.
- The decisive root-cause evidence may live only in per-instance logs under:
  - `run_outputs/<instance>/attempt-*/infer.log`
  - and sometimes `run_outputs/<instance>/attempt-*/mini_swe_agent_output.log`
- Required triage order:
  1. Confirm whether the family is present in a sampled per-instance `infer.log`.
  2. Read the traceback context around the first `Connection error`.
  3. Distinguish wrapper/provider text from the upstream transport cause.
- In the confirmed 2026-05-05 direct-native FeatureBench case, the real upstream cause was:
  - `ConnectError: [Errno -2] Name or service not known`
  which then surfaced as:
  - `APIConnectionError: Connection error.`
  - `OpenAIError: Connection error.`
  - `litellm.InternalServerError: InternalServerError: OpenAIException - Connection error.`
- Interpretation:
  - the OpenAI-compatible endpoint hostname was not resolvable from inside the mini-swe-agent
    task/container runtime.
  - This is a runtime DNS/hostname reachability issue, not enough evidence by itself to blame the
    model, prompt, or FeatureBench scoring logic.

## FeatureBench Docker Network-Pool Lesson From 2026-05-05

- When a long-running FeatureBench/mini-swe-agent run is still producing new instance logs but one
  or a few instances stall near the tail, inspect sampled per-instance `infer.log` files before
  concluding that the whole run is simply “slow”.
- A concrete 2026-05-05 tail blocker for `cod661_qwen_stage4_featurebench_fast_20260505_r2`
  appeared only at instance level:
  - `no available IPv4 addresses on this network's address pools: bridge`
- Interpretation:
  - this is a Docker bridge IPv4 address-pool exhaustion problem during container networking
    setup for a subset of instances.
  - It is different from:
    - deployment endpoint health issues,
    - direct API DNS failures,
    - or stale top-level wrapper `status.json`.
- Monitoring consequence:
  - if `output.jsonl` row count is already high and some instance logs still advance, classify the
    run as a partial-instance tail blocker instead of a globally dead run.
  - prioritize sampling a few failed instance logs and reporting the exact infra string above.

## Traceback Triage Rules

### Family A: SDK Launch Failure

Treat as a substantive startup failure when the traceback is accompanied by:
- `Run via sdk failed`
- `SiiSDKError`
- `WRAPPER_ERROR`
- `EEXIST: file already exists, symlink .../.sii/SII.md`

Interpretation:
- The SII bridge / wrapper home initialization collided with an already-existing symlink.
- This is usually a workspace-local or run-local bootstrap idempotency problem, not a generic evaluator timeout.

Likely causes:
- repeated SDK launches racing on the same bridge-wrapper home,
- stale `.bridge_wrapper_home/.sii/SII.md` left from an earlier attempt,
- symlink creation path not handling existing targets idempotently.

Concrete repo-local location to inspect first:
- `third_party/sii_agent_bridge_fork/lib/rollout-bridge-wrapper.mjs`
  - `buildRuntimeContext()` prepares `memoryDir/.bridge_wrapper_home/.sii/SII.md`
  - `ensureSymlink()` is the first place to confirm whether `EEXIST` is handled idempotently
- `src/services/sii_agent_client.py`
  - confirms whether the rollout is using the vendored bridge path and whether bridge startup progressed to first-event logging

Do not jump straight to blaming the global `@gair/sii-cli` bundle unless repo-local vendored wrapper evidence is absent.

### Family B: Cleanup Noise After Completion

Treat as cleanup noise, not the original failure, when the traceback is accompanied by:
- `Suppressed bridge cleanup timeout after completion`
- `Loop <_UnixSelectorEventLoop ... closed=True>`
- `RuntimeError: Event loop is closed`
- `Exception ignored in: <function BaseSubprocessTransport.__del__ ...>`

Interpretation:
- The bridge cleanup path is tearing down subprocess transports after the event loop has already closed.
- This is a post-completion cleanup race. It may pollute logs but is often secondary to the real failure or even happen after successful AI/tool activity.

### Family C: False-Positive Traceback Token

Downgrade when `Traceback` appears only inside:
- agent-generated text,
- tool output previews,
- diff hunks / patch payloads,
- JSON fields such as `originalContent` / `newContent`.

Interpretation:
- The monitor matched a traceback string in model content or tool output, not in the runtime stack.
- You must verify there is a real Python stack frame around it before alerting as a runtime traceback.

### Family D: Evaluator Deadline

Treat separately from traceback:
- `Evaluator infrastructure deadline exceeded after 120.0s`

Interpretation:
- The evaluator/judge path timed out.
- This may coexist with SDK launch failures in the same run, but it is a distinct downstream failure family.

## Shared-Host Lessons From 2026-04-09

- `cloudquery/cloudquery`, `microsoft/autogen`, and `sympy/sympy` all showed the same substantive startup failure:
  - `SiiSDKError: WRAPPER_ERROR: EEXIST: file already exists, symlink '../../bridge_memory.md' -> .../.bridge_wrapper_home/.sii/SII.md`
- The same runs later also showed cleanup-noise tracebacks:
  - `Suppressed bridge cleanup timeout after completion`
  - `RuntimeError: Event loop is closed`
- Therefore one run can contain at least two traceback families:
  - primary launch failure,
  - secondary cleanup race.
- During monitoring, some logs also contained the literal word `Traceback` inside tool-returned diff payloads.
  - Always inspect context before filing a runtime-root-cause conclusion.

## Registry Path Correction Lesson From 2026-04-27

- When a user corrects the concrete registry DB filename, treat the new filename as the
  authoritative literal command value even if earlier logs or prior runs used a similar path.
- Do not infer provider words such as `claude` from a previous run name when the current rollout is
  OpenClaw-specific. For OpenClaw 3, the user-corrected path was
  `data/synthetic/rollouts/rollouts_openclaw3.db`, replacing the earlier mistaken
  `data/synthetic/rollouts/rollouts_claude_openclaw3.db`.
- For command-only follow-ups, verify the wrapper with a fake-python launch check and assert that
  the exact corrected `--registry-path` appears as the inner `--rollouts-path`.

## OpenClaw Workspace Copy Monitoring Lesson From 2026-04-27

- For OpenClaw staged rollouts on shared storage, a missing DB row after scheduling may be caused
  by per-stage workspace copy/prep rather than by registry-path failure. Confirm the live Python
  argv first, then inspect `py-spy` and the direct child process under the rollout executor.
- `cp -a --reflink=auto` children can disappear and be replaced by another stage workspace copy
  while the terminal log and DB row counts stay flat. Treat the active child target as a moving
  pointer, not as a single permanent blocker.
- Avoid repeated full-tree `du` / `find` scans over the shared source image such as
  `workspace/images/openclaw__openclaw`; those checks can be slow enough to distort monitoring.
  Prefer lightweight evidence:
  - rollout wrapper/Python/tee process state,
  - current `cp` child state and target path,
  - target directory shallow file count or recent mtime,
  - registry DB size/counts,
  - terminal log size/mtime and stage-summary keywords.
- Do not conclude "failed" solely from a flat terminal log while a workspace-copy child is still
  alive in `D` state and the target directory mtime/file count is moving.
- If the direct child under the rollout executor changes from `cp -a --reflink=auto` to
  `git status --porcelain --untracked-files=all`, treat that as the next workspace-prep subphase
  rather than a new DB-path failure. Confirm cwd via `/proc/<pid>/cwd` and, if needed, confirm the
  Python worker stack in `git_workspace.py:_has_preservable_local_changes -> _run_git`. This
  means the copied stage workspace is now blocked on git local-change detection before agent/tool
  execution, so DB rows and stage summaries can still remain absent.
- Terminal log growth to `stage stage-1 attempt ... starting` / `Starting rollout...stage-1`
  means one workspace has crossed into stage execution startup, but it is not equivalent to a
  completed stage summary. Continue to watch DB counts, `Stage stage-1 status=...` lines, and
  session jsonl growth before declaring that rows should exist.
- A log line such as `stage stage-1 attempt 1 finished status=succeeded` means the agent/run phase
  ended successfully enough to proceed to patch capture/evaluation. It is not the same as an
  evaluator success and does not imply a registry row should exist. Continue to wait for
  `evaluation finished decision=...`, session jsonl `attempt` / `stage_summary` records, and DB
  row counts.
- If session jsonl files contain failed `stage_summary` / `attempt` records but registry counts
  remain zero, inspect the DB schema before calling it a registry write failure. In this repo's
  rollout registry, `stage_rollouts.status` may be constrained to `success` and `rollouts.status`
  to `completed`, with no `stage_rollout_failures` table. In that case failed stages are expected
  to remain in per-session jsonl/comments and not increment registry rows.
- A ready `workspace/images/<repo>` image does not mean a stage can execute in-place. The staged
  OpenClaw flow still creates a fresh isolated workspace for each stage via
  `cp -a --reflink=auto <image> <workspace/openclaw__...stage...>`, then runs post-copy git
  checks such as `git status --porcelain --untracked-files=all`. On GPFS/shared storage,
  `--reflink=auto` may not become an O(1) copy and can degrade into a slow recursive copy over
  the full repository and `.git` metadata. Therefore "image exists but still stuck" usually means
  "template exists but per-stage workspace derivation or post-copy git status is slow", not that
  the image is missing.
- Treat `staged.missing_ground_truth_prefilter` as an asset-completeness skip family rather than a
  runtime rollout failure. When many OpenClaw staged plans log this marker, distinguish "query
  lacks evaluator ground truth and was skipped before prewarm" from "agent/evaluator failed after
  execution." These skipped plans should not be counted as failed rollout attempts or used to claim
  the model/runtime directly failed.
- A host-pressure log with many unrelated D-state git processes can be a shared-host throttle
  signal, not necessarily a reason to abort the current OpenClaw run. Prefer diagnosing whether the
  executor continues with workspace prepare concurrency `1`; only call it a hard refusal when the
  log explicitly says `Refusing to start rollout fanout` and the process exits before fanout.
  `ROLLOUT_HARD_BLOCK_HOST_GIT_STORM=1` is the explicit opt-in mode for hard refusal.
- When a directory-mode OpenClaw restart logs discovery and then stalls before prewarm/fanout,
  inspect the Python stack before assuming workspace copy or registry failure. A stack like
  `load_stage_queries -> pathlib.read_bytes/read` means the main process is synchronously reading
  query JSON artifacts from shared storage. With large directories this can be slow because the
  default directory discovery cap is high. Prefer bounding the restart with
  `--directory-file-limit <N>` after confirming the wrapper forwards that flag, then verify the
  run reaches prewarm/fanout. This is a directory JSON-loading bottleneck, not a DB path mismatch.
- When a rollout command prints the inner `[rollout] ...` invocation but the terminal log remains
  zero bytes, sample the Python process before assuming directory discovery has started. In the
  OpenClaw3 case, a bounded restart blocked during import-time I/O:
  `src/services/reporting/rollout_dataset_stats.py -> transformers.__init__`, pulled in by eager
  `src.services` package exports. That is neither a DB write issue nor a query JSON discovery
  issue. The reusable fix is to make optional reporting/statistics modules lazy so runtime rollout
  imports do not load `transformers` unless a reporting command explicitly needs it.
- If the user explicitly rejects `git worktree` for a GPFS workspace-copy blocker, do not keep
  proposing worktree fast paths from earlier incidents. A non-worktree mitigation is a stage
  workspace prewarm pool: pre-create real isolated workspace directories under
  `workspace/prewarmed/<repo>/<revision>/slot-*`, mark complete slots with `.ready`, claim a ready
  slot by atomic rename during `create_workspace()`, and fall back to direct template copy on a
  pool miss. On GPFS, also skip external `cp -a --reflink=auto`; otherwise the prewarm pool can
  reproduce the same `D+ / cxiWaitEventWait` subprocess path before fanout instead of fixing the
  operational blocker.
- If a `--scaffold sii` OpenClaw restart prints the inner rollout command, then emits a
  `mini-swe-agent` banner while the terminal log remains zero bytes, treat that as an eager import
  regression rather than as mini scaffold execution. The default OpenClaw SII path must not import
  `src.services.mini_swe_runner`, `minisweagent`, `src.pipelines.evaluator.scorer`, `openai`, or
  `httpx` before directory discovery/prewarm. Prefer lazy imports or a small no-side-effect
  verifier that imports `src.cli.rollout_executor_cli` and asserts those modules are absent from
  `sys.modules`.
- If the OpenClaw run progresses past template prewarm and then stalls immediately after
  `Prewarming stage workspace pool ...`, sample the Python stack before assuming mini/import or a
  direct `cp` child. A stack like
  `prewarm_stage_workspace_slots -> _assert_template_symlinks_resolved -> Path.rglob -> os_scandir`
  means the pool is blocked in a full-template GPFS metadata scan. The reusable fix is for normal
  git templates to validate symlinks from `git ls-files -s -z` tracked `120000` entries and to
  claim an existing ready slot before scanning the template tree; otherwise prewarm can recreate a
  startup metadata bottleneck even when no `cp -a --reflink=auto` child exists.
- After removing the `Path.rglob` scan, the next GPFS pool-prewarm blocker can become Python
  `shutil.copytree/copy2 -> open64`, still before fanout. If the user forbids `git worktree`, a
  bounded non-worktree mitigation for normal git templates is `git clone --shared --no-checkout`
  from the local template followed by `git checkout --force <template_head>`. This still
  materializes a working tree, but avoids copying the template `.git` object store through GPFS
  and keeps each stage in a real isolated directory. Keep submodule-heavy templates on the older
  copy path unless tests cover their shared-clone semantics.

## Recommended Outputs

- A short user-facing anomaly summary in Chinese.
- A Feishu alert card with:
  - affected pane / run_dir,
  - anomaly family,
  - concrete snippet,
  - current runner liveness context.
- `.codex/progress.md` append-only monitoring receipts.

## FeatureBench Nested-Run Monitoring Lesson From 2026-05-05

- For FeatureBench proxy reruns that wrap `fb infer`, do not treat top-level `status.json` or the
  root run directory alone as the ground truth for live progress.
- A wrapper can remain at `status=infer_start` and have no root-level `output.jsonl` yet, while
  the real full run is already writing rows under a nested timestamp directory like:
  - `runs/featurebench/<run_id>/2026-05-05__09-55-56/output.jsonl`
  - `runs/featurebench/<run_id>/2026-05-05__09-55-56/run_outputs/**/infer.log`
- For context-window investigations, smoke success is not sufficient evidence by itself:
  - smoke can eliminate the old immediate provider rejection but still end as an ordinary agent
    failure
  - the required next check is whether the nested full run has started materializing rows and
    whether current `infer.log` files still hit `ContextWindowExceeded`
- Preferred live checks for this family:
  - locate the latest nested `2026-*` directory,
  - count nested `output.jsonl` rows,
  - count nested `run_outputs` directories,
  - grep nested `run_outputs/**/infer.log` for `ContextWindowExceeded`,
  - and only then classify the blocker shape.
