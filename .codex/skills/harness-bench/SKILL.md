---
name: harness-bench
description: Design and implement small, task-specific harness benchmarks that measure the exact user scenario, compare against explicit baselines, support expensive online runs behind environment gates, and emit auditable JSON/Markdown artifacts. Use when a task needs a benchmark plan, a `tests/bench` implementation, or benchmark methodology for code review.
---

# Harness Bench

## Goal
Use this skill when the user needs a benchmark that answers a concrete product or engineering question, not a generic benchmark score.
If the user explicitly requests to add a benchmark to tests/bench, the system should default to designing a 'miniature harness benchmark' tailored to the current task. Do not introduce or copy existing large-scale benchmarks from the internet.

Do not use this skill for task acceptance coverage whose main question is "did the code change
meet the requirement?". That belongs to the `unit-test` skill, even when the acceptance check is
a performance threshold test or a real API regression reproducer.

Typical cases:
- compare a new mechanism against baselines,
- verify routing or storage behavior in a long-running workflow,
- build a real online benchmark with archived samples,
- define benchmark commands for `.codex/review_spec.md`.

Route to `unit-test` instead when:
- the user wants strict CI or linter gates for a code change,
- the user wants proof that a bug reproduces before the fix and does not reproduce after,
- the user wants a task-scoped latency threshold for implementation acceptance,
- the user wants a real API regression test that answers "fixed or not" rather than
  "better or worse in production".

## Companion Skills
- `unit-test`
  - Trigger: the task is about implementation acceptance, task-scoped blocking tests,
    task-scoped lint/type gates, regression reproducers, threshold checks, or real API fix
    verification.
  - Input context: task goal, acceptance criteria, chosen test directory, relevant code paths,
    whether the task reads runtime config from `config/pipeline.yaml`.
  - Expected output: blocking task acceptance commands and any non-benchmark test artifacts.
- `code-review-with-logs`
  - Trigger: benchmark methodology or `tests/bench/**` deliverables must be checked in formal
    review.
  - Input context: benchmark commands, benchmark deliverables, artifact contract.
  - Expected output: copied `Benchmark Commands` in the review spec and review evidence.

## Workflow
1. Write down the benchmark question in one sentence.
2. Fix the comparison groups before coding:
   - candidate
   - baseline A
   - baseline B
3. Decide what is actually being measured:
   - correctness / success rate
   - latency / throughput
   - routing integrity
   - storage integrity
4. Apply control-variable design before coding any expensive run:
   - If you are comparing the effect of one intervention, keep every upstream state identical across groups.
   - For retry/comment benchmarks, first produce one shared attempt-1 result, then branch only on the comment injected into attempt 2.
   - Do not let groups generate different first attempts and then compare raw deltas; that mixes intervention quality with sampling variance.
   - If a shared upstream state cannot be enforced, explicitly document the remaining confounder in the artifact and review spec.
5. Choose the smallest real sample set that still matches the user scenario.
6. Put the executable harness in `tests/bench/`.
7. Put structured outputs in `logs/*.json` or a benchmark-specific artifact path.
8. If the real run is expensive, gate it behind an env var and still make the harness write a skipped report when disabled.
9. If real-sample discovery returns zero candidates, write a skipped report with the exact discovery reason instead of failing the harness.
10. If the task also uses `code-review-with-logs`, translate the harness into `Benchmark Commands` in `.codex/review_spec.md`.

If, during this workflow, you realize the ask is really a task-scoped acceptance test, stop and
hand the problem to `unit-test` instead of forcing it into `tests/bench/**`.

## What To Load
- Read `references/benchmark-design.md` for the core design checklist.
- Read `references/online-benchmark-patterns.md` when the benchmark must hit real services or real archived data.
- Read `references/rollout-memory-example.md` when the task looks like staged rollout / continuation / long-trajectory evaluation.
- Reuse `assets/templates/benchmark_spec.template.md` when you need a file-based benchmark design note.

## Memory / Rollout-Memory Hard Rules
Treat the following as required, not optional, whenever the benchmark evaluates memory quality, fact preservation, or fact hit rate:
- `expected facts` must be selected by an independent worker/subagent from the sample materials. The main agent may orchestrate integration, but it must not directly assemble facts from ground-truth answers, labels, or metadata fields and then score against that same derived list.
- The benchmark must emit an auditable fact manifest. Prefer a structured artifact that records, for each fact, the sample id, the selected fact text, who selected it, and provenance back to the source material such as file path, field name, excerpt, or span.
- Avoid feeding the evaluation target back into memory construction verbatim. Do not copy the exact scored fact strings unchanged into the same benchmark inputs that the memory writer or summarizer consumes unless the benchmark explicitly documents why that leakage is unavoidable.
- If these independence requirements cannot be met, narrow the benchmark claim. Report the run as a weaker retrieval/regurgitation probe, not as strong evidence of memory-based fact preservation.

## Output Expectations
- Benchmark question is explicit.
- Baselines are explicit.
- Metrics are explicit.
- Controlled variables are explicit.
- Skip gate is explicit.
- Artifact schema is explicit.
- The benchmark command can be copied into `.codex/review_spec.md` without rewriting the methodology.

## Notes
- Prefer one focused benchmark over a wide benchmark suite.
- Prefer real archived samples over synthetic toy data when the user asks for scenario realism.
- If the benchmark measures effect, keep correctness evaluation logic aligned with the production evaluator whenever possible.
- If the benchmark claims to isolate the effect of comments, prompts, rerankers, or judges, enforce a shared upstream state and compare only the downstream branch.
- If a remote runner reports a temporary workspace path for the shared upstream attempt, branch follow-up runs from the persistent local workspace mirror or replayed patch state, not that ephemeral path.
- If the harness uses `multiprocessing spawn` for evaluator or judge deadlines, do not debug it from `python - <<'PY'` or other stdin-only entrypoints; use a real script path so child processes can re-import the main module.
- Treat the main benchmark artifact path as single-writer state. Do not let concurrent benchmark owners share `logs/*.json` or the same artifact directory unless you first namespace the outputs.
- For remote online benchmarks, add a local deadline around each expensive attempt and each evaluator/judge call, then write a structured blocked/failed artifact when the remote call hangs; do not let the harness stall indefinitely.
- For archived SWE-bench evaluator benchmarks, do not trust ad-hoc archive sidecar `.patch` files as authoritative gold patches. Load the official dataset `patch` field by `instance_id`, and treat any archive-local `.patch` only as a diagnostic mismatch surface.
- If the user explicitly requires a `full` archived benchmark run, treat any `smoke` or subset replay only as intermediate diagnostics. Do not present the smoke result as the final benchmark conclusion; the final report, acceptance decision, and Feishu summary must all cite the completed full-run artifact instead.
- During a long archived benchmark run, it is valid to compute an optimistic upper bound from the current progress and observed failure classes to decide whether a candidate can still beat the target. However, if the user explicitly requires `full`, keep that upper-bound reasoning as an intermediate diagnostic only and still finish or cite the completed full artifact before final reporting.
- For evaluator-prompt benchmark tuning on real archived large-patch samples, avoid large rubric rewrites that substantially lengthen the judge prompt unless you explicitly want to measure timeout sensitivity too. Longer prompt copies can degrade apparent "accuracy" by triggering more timeout / non-JSON failures on the same samples, confounding prompt-quality comparisons.
- When benchmark-mode evaluator recovery repairs a malformed judge response, keep the repair prompt aligned with the benchmark output contract itself: short neutral JSON with `score` plus brief `comment`. Do not reuse production-style `Fix path` / structured remediation contracts there, or the benchmark will confound prompt quality with comment-shape drift and unusable-verdict collapse.
- For evaluator-comment optimization benchmarks, do not compare prompt revisions alone when the scorer fallback can still leak substantive non-JSON/plaintext verdicts directly to the agent. Canonicalize those fallback comments first, or explicitly treat comment-shape drift as a confounder; otherwise a "more detailed" prompt can look worse simply because downstream retries receive less stable comment structure.
- When a benchmark compares multiple evaluator prompts through `scorer.evaluate_rollout(...)` under benchmark mode, keep prompt fallback group-local. Do not let context-length or JSON-repair fallback silently switch from an explicit prompt group to a shared benchmark prompt, or the comparison becomes confounded.
- For evaluator-prompt tuning, do not compare an old archived baseline reported at a fixed threshold (for example `threshold=0.8`) against a new harness winner selected by a different rule such as an unresolved-FP cap. Expose the winner-selection policy explicitly in the artifact and also emit fixed-threshold comparability metrics so "prompt got worse" is not inferred from mixed decision surfaces.
- If the user's real objective is "maximize accuracy while still allowing more successes," prefer an accuracy-first winner policy with an explicit precision floor over a pure unresolved-FP-cap gate. When you do this, record both the precision floor and whether the chosen winner actually met it; if no threshold meets the floor, mark the fallback explicitly instead of silently reusing the old gate.
- If a prompt-tuning round already required a manually completed archived `full` artifact, review-time `Benchmark Commands` should validate that captured artifact deterministically with a local assertion command rather than rerunning the same `full` benchmark inside `run_review_flow`. Otherwise the formal review ceases to be a bounded validation step and can silently dominate turnaround time.
- When you wrap an evaluator/judge call in a Python thread with a timeout, do not put that work under a `with ThreadPoolExecutor(...)` that will immediately `shutdown(wait=True)` on timeout. That pattern can re-block the caller during executor teardown and nullify the fail-fast deadline; prefer a daemon thread + queue or an explicit non-waiting shutdown path.
- For archived-rollout benchmarks, "no eligible archived continuation sample" is a legitimate skipped state that should be captured in the artifact contract.
- Default local benchmarks should stay small and fast enough to run during normal development and review. Do not make a real long-running rollout or remote dependency the default pass path; put heavy or long-duration validation behind an explicit environment gate and still emit a structured local report by default.
- For predict/rollout shell benchmarks, cover the production command shape directly. If rollout traffic commonly uses `grep/rg ... | head -N`, include that exact pipeline form in the harness; otherwise shell no-match semantics can be flattened into `exit 0 + empty` and the benchmark will miss the real regression.
- If a benchmark is split across multiple rounds/modules, each round must have its own artifact contract tests: default env-gated execution should write a structured skipped report when no completed artifact exists, and enabled execution should write a non-empty completed report. Do not leave secondary rounds as empty placeholder files.
- If the archived-rollout workflow itself hangs on shared storage during workspace copy or `git checkout`, first move the rollout execution to a minimal repo mirror on local disk such as `/tmp`; then run the benchmark from that same local mirror so `REPO_ROOT`, archived samples, and workspace paths stay co-located. If the benchmark still blocks before writing its report, record that as an environment-level benchmark blocker distinct from "no eligible archived continuation sample".
- For long-running real rollout success-rate reruns, do not treat a flat `query_dir_count` or quiet `stdout.log` as sufficient evidence of a stall. Before declaring the benchmark hung, also check whether the group runner processes are still alive and whether artifact mtimes under the group artifact root are still advancing.
- For long-running rollout success-rate group launchers, do not use `run_status.json` mtime as the sole liveness signal. Some runs may leave the status file at its initial timestamp for hours while the launcher is still making forward progress. Judge liveness from the combination of terminal `status`, runner process health, and advancing mtimes/counts under `artifacts/queries/**`.
- During a live rollout-success bench, avoid repeated full-tree recursive glob scans over `artifacts/queries/**` just to count comments or status files. On large shared-storage artifact trees that can become its own bottleneck and distort monitoring. Prefer lightweight `run_status.json` / `report.json` existence checks plus tmux-pane execution evidence, and reserve deep recursive scans for one-off diagnostics.
- For sample-scoped rollout success probes, do not infer a stall solely from missing `workspace/records/*.json` or `comments/*.txt`. `workspace/metrics/stage_executions/**.json`, `workspace/metrics/status/rollout/default.json`, and revision-attempt metrics may advance earlier and show that stage execution already succeeded with a captured patch even before records/comments are flushed.
- For rollout success-rate group launchers, export the full scorer benchmark env explicitly, including judge-specific knobs such as `EVALUATOR_BENCHMARK_JUDGE_MAX_TOKENS`, `EVALUATOR_BENCHMARK_JUDGE_PROMPT_PATCH_CHAR_LIMIT`, and `EVALUATOR_BENCHMARK_JUDGE_PROMPT_PATCH_CHAR_LIMIT_FALLBACK`. Do not rely on scorer defaults if the benchmark needs auditable, self-contained reruns.
- If rollout memory artifacts live outside the workspace root (for example under `session_logs/agent_memory`), do not inject those external absolute paths directly into agent-visible prompt/progress surfaces during a probe. Mirror them into workspace-local files first, or the probe may fail with `tool.invalid_path_outside_root` before the agent reaches the real task.
- If rollout delta capture includes untracked files, never blanket-stage the whole workspace with `git add .` during probe diagnostics. Exclude runtime artifact roots such as `.sii` and `.rollout_revision_switch_conflicts`, or a large baseline-conflict sidecar can be re-ingested into the candidate patch and overwhelm the judge.
- When a rerun uses a local `/tmp` repo mirror, verify at least one representative code signature inside that mirror before accepting the result as evidence for the latest fix. Checking only the eval-root name or launch time is insufficient; compare concrete runtime signatures such as the updated `scorer.py` fallback text or the launcher's exported env keys.
- If a benchmark module name collides with an existing unit-test module name, prefer making the review command explicit with `pytest --import-mode=importlib` instead of relying on default import semantics.
- For rollout CLI micro-benchmarks that call `_run_stage_session_with_timeout()` directly, either return a real `StageRolloutSession` or temporarily monkeypatch the module-local `StageRolloutSession` symbol. The helper ends with an `isinstance(..., StageRolloutSession)` assertion, so plain dummy objects will look like candidate regressions even when the timeout logic is correct.
- If a benchmark launcher lives under `.codex/scripts/**` and imports a `tests/bench/**` module via `importlib.util.spec_from_file_location`, do two things before `exec_module(...)`: inject the repo root into `sys.path`, and register the module object under `sys.modules[spec.name]`. Otherwise the benchmark module can fail immediately on `from src...` imports or on decorators such as `@dataclass` that expect the module to be registered during execution.
- For benchmark group launchers that write `run_status.json`, keep benchmark-module loading inside the same `try/except` path as benchmark invocation. If `_load_benchmark_module()` fails before the real run starts, the launcher must still flip `run_status.json` to `failed` and emit a failed artifact instead of leaving stale `status=running`.
- For real rollout success-rate benchmarks that reuse production rollout helpers, never point the benchmark at the default production `session_logs_dir` / `session_registry_path`. Load the normal pipeline config, then clone `rollout_execution` with redirected `session_logs_dir`, `session_registry_path`, `workspace_root`, `workspace_delta_dir`, `transcripts_dir`, `records_dir`, `metrics_dir`, and `baselines_dir` for each sample so the harness cannot mutate the real `rollouts.db`.
- If a task-scoped probe needs a subset manifest but the shared benchmark hardcodes a full-sample invariant such as `expected 30 samples`, do not weaken the shared benchmark for all callers. Patch the probe wrapper to monkeypatch or replace the manifest loader only inside the probe process, keeping the authoritative full benchmark strict while allowing one-off acceptance probes.
- When analyzing real rollout success-rate artifacts, treat `report.json` and its `samples[*].plan_results[*].stage_results[*].status` as the authoritative benchmark verdict surface. Do not infer benchmark success from sample-local `workspace/metrics/status/rollout/default.json` alone; that file may show `last_verdict=pass` for a stage-local status cache even when the benchmark report records the sample/query as failed or not executed.
- For rollout failure-cause analysis, explicitly separate at least three classes before proposing fixes: pipeline provenance failures such as empty workspace delta, agent no-op / no-tool attempts, and pre-stage silent drops with missing records/logs. Mixed categories are common, and collapsing them into a single "timeout" bucket hides the real repair order.
- When a benchmark round is optimizing evaluator retry comments, treat `Fix path` detail as part of the benchmark contract: require both actions to repeat the target file path, require each action to state the concrete next edit, and enforce the same rule in both the prompt contract and scorer-side canonicalization. Otherwise comment usefulness can regress even while headings still look structurally correct.
- For evaluator-comment optimization where the user explicitly wants a better next-try plan, require the production comment surface itself to preserve both roles: `Overall review summary` must stay as the issue analysis, and `Fix path` must stay as the next-step repair plan derived from `candidate patch + ground-truth patch`, naming the file plus the function, method, branch, or logic block to edit and the concrete change to make whenever those targets are inferable.
- For DS-1000 runs in Agentic-Evaluation-infra, the wrapper's pre-evaluator `report.json` that only contains generation counts such as `generated`, `new_generated`, and `existing_records` is not a valid final score even when `total_tests=1000`. Treat the final DS-1000 artifact as evaluator-backed only after `DS-1000/scripts/test_ds1000.py` has produced metrics and `report.json` includes `metrics.evaluated`, `metrics.accuracy`, and a per-library or equivalent breakdown.
