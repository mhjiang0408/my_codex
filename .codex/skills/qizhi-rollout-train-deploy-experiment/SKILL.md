---
name: qizhi-rollout-train-deploy-experiment
description: Automate qizhi workflow after rollout compose. Convert rollouts to parquet, submit and monitor training, submit and monitor deployment, then run a post-deploy experiment command with fail-fast + Feishu notification.
---

# Qizhi Rollout Train Deploy Experiment

Use this skill when the user wants an end-to-end automation flow:
1. rollout compose directory -> training parquet,
2. submit qizhi training job and monitor,
3. wait for HF conversion output (`iter_*_hf`) before deploy submit,
4. submit qizhi inference serving and monitor,
5. run a custom experiment command after serving is ready.

For recovery/debug runs where the benchmark callback must be launched manually later, the
orchestrator supports `--stop-after deploy_monitor`. This resumes through HF wait, deploy submit,
and deploy readiness, then exits before `callback` while preserving serving artifacts.

## Files
- Orchestrator entry:
  - `scripts/orchestrate.py`
- Manual HF export recovery helper for Qwen dense checkpoints:
  - repository root `scripts/convert_qwen_torch_dist_to_hf.py`
- Legacy config parser and mapping:
  - `scripts/legacy_config_loader.py`
- QZ CLI transport:
  - `qz login`
  - `qz avail`
  - `qz job create/status/wait/logs`
  - `qz deploy create/status/wait/logs`
- Run-state persistence:
  - `scripts/state_store.py`
- Config template:
  - `assets/automation.template.yaml`
- Transport and platform references:
  - `QZ_SKILL.md`
  - `references/qizhi_api_notes.md`
  - `references/frontend_api_patterns.md`

## Companion Skills
- This skill is the workflow entrypoint and stays the orchestrator for rollout -> parquet -> train -> deploy -> callback.
- Load companion skills on demand. Do not preload all QZ-related skills when one focused companion can answer the current subproblem.

| Companion skill | Invoke when | Pass this input | Expect this output |
|---|---|---|---|
| `qz-guide` | You need exact `qz` CLI syntax, config semantics, pool/type rules, or command mapping from old `qzcli` behavior | Current orchestration step, known workspace/pool/type constraints, and the command family that is unclear | Exact `qz` commands/flags, config assumptions, and constraints the orchestrator must preserve |
| `qz-browser` | `qz` lacks a needed capability, browser/API replay is required, or workspace/pool/spec IDs must be recovered from WebUI/API traffic | The target page/API/action, known IDs, and why the CLI path was insufficient | IDs, endpoints, payloads, replay steps, and platform gotchas that the orchestrator can consume |
| `qz-customize` | A repeated multi-step QZ sequence should be promoted into project-specific `qzx` commands, templates, or wrappers | The repeated workflow, stable defaults, project paths, and desired output contract | A `qzx` scaffold/design/implementation plan or code path that turns the repeated flow into reusable project tooling |
| `cpt-experiment-workflow` | The task moves beyond train/deploy and needs checkpoint-level experiment matrix orchestration, aliyun benchmark dispatch, or local wandb offline sync | ckpt list, qizhi run artifacts or serving metadata, benchmark selection, and wandb offline root | remote benchmark commands, tmux assignment plan, resumable experiment run state, and wandb sync plan |
| `deployment-benchmark-workflow` | The deployment is ready and a post-deploy API benchmark should run from callback without evaluating checkpoints directly | serving endpoint/base URL, automation config path, deployment benchmark config, and desired mode (`smoke`, `full`, `smoke_then_launch_full`) | deployment benchmark artifacts plus smoke/full launch state for API-facing benchmarks such as APTBench |

- Routing rule:
  - Use `qz-guide` instead of re-documenting generic `qz` command semantics in this skill.
  - Use `qz-browser` instead of reviving direct frontend replay logic inside this skill.
  - Use `qz-customize` when the task stops being one-off orchestration and should become reusable project automation.
  - Use `deployment-benchmark-workflow` when the deploy callback should start a benchmark against a ready OpenAI-compatible endpoint.
  - For APTBench callback recovery or manual post-deploy launches, follow
    `deployment-benchmark-workflow`'s execution contract: launch through `uv` inside tmux session `experiment`,
    and do not run APTBench directly in the current terminal.
  - Use `cpt-experiment-workflow` when the user asks to run benchmark experiments on trained checkpoints or to connect deployed endpoints to SWE/FeatureBench workflows.
  - Do not keep extending this skill with benchmark-specific execution logic; route checkpoint experiments to `cpt-experiment-workflow` and deployment API benchmarks to `deployment-benchmark-workflow`.

## Transport Policy
- Primary automation boundary is the `qz` CLI from `myqz`.
- Orchestrator should shell out to `qz`; do not reimplement `myqz` HTTP flows in `orchestrate.py` unless the CLI lacks a required capability.
- This skill no longer depends on `qzcli`, `~/.qzcli/*`, or `qzcli`-specific CAS fallback logic.
- Legacy operator notes may still mention `qzcli train/deploy/avail`; treat those as read-only aliases for `qz job/deploy/avail` and do not restore a runtime `qzcli` dependency.
- `qz` may internally use Bearer-token OpenAPI calls and internal cookie-backed APIs. That is acceptable because the transport boundary is the CLI itself.
- If the question is really about `qz` command syntax or config semantics, switch to `qz-guide`.
- If `qz` truly lacks a capability and browser replay is required, switch to `qz-browser` instead of reviving the old `qzcli` path.
- If the same QZ sequence keeps recurring across tasks, switch to `qz-customize` and extract it into project-specific `qzx`.
- `deploy_api_prefix`-derived `https://{prefix}.openapi-qb*.sii.edu.cn` remains the serving endpoint domain, not the orchestration transport.
- Ambiguous create gotcha:
  - `qz job create` may return a validation-like error such as `unknown field "cpu_elastic_ratio"` while the platform still ends up retaining a queued job with the exact run name.
  - Treat that class of failure as an ambiguous submit outcome, not an automatic proof that no job exists.
  - During manual recovery or fallback submit, inspect platform-side jobs for the exact run name when possible; once a later winner really enters `running`, explicitly stop stale queued duplicates to preserve `max_parallel_jobs` and `first-running-wins`.
- Transient queued-job query gotcha:
  - During long queue monitoring, `qz job status <job> --raw` or `qz job logs <job> --raw` can occasionally emit empty/non-JSON upstream output that the CLI surfaces as null fields or a parse error such as `Expecting value: line 1 column 1 (char 0)`.
  - Do not classify a queued job as missing, failed, or terminal from a single parse/null response.
  - Retry the same job with `qz job status <job> --raw` and, if possible, `qz job logs <job> --worker 0 --lines 20 --raw`; only change the experiment state after a successful structured status response or repeated corroborating failures.
- Explicit project-id gotcha:
  - In this workspace, `qz job create` cannot safely rely on the current global project context.
  - A create call without an explicit `--project-id` may fail with:
    - `您已离开所选项目，无法创建`
  - For train-job submission, prefer carrying the frozen project id directly in the create command or direct-openapi payload.
  - For the current `Q项目-科学认知基础模型` tasks, the known-good id is:
    - `project-3cc580f0-7528-47d3-8456-ed6994854373`
- Failed-retention submit gotcha:
  - In this workspace, when submitting `qz` jobs/deployments/auxiliary export tasks, do not set a task-failure retention duration or failed-job keepalive duration unless the user explicitly requests that override.
  - Treat the absence of failed-retention settings as the default-safe contract.
  - If an existing wrapper or payload template exposes a failed-retention field, remove or leave it unset for ordinary submits instead of freezing failed pods by default.
- Large HF export placement rule:
  - For 30B-class Qwen torch-dist -> HF conversion, do not run the heavy conversion directly on the shared agent host unless the user explicitly requests a local run.
  - Prefer a one-node QZ export job and run the repository exporter from the repo root with the Megatron path on `PYTHONPATH`, for example:
    `PYTHONPATH=/inspire/hdd/global_public/yanmin/Megatron-main-org:$PWD:${PYTHONPATH:-} /usr/bin/python3 scripts/convert_qwen_torch_dist_to_hf.py --input-dir <iter_dir> --output-dir <iter_dir>_hf --origin-hf-dir <origin_hf_dir> --model-name qwen3 --chunk-size 5368709120`
  - After conversion, the job should check `config.json`, `generation_config.json`, `model.safetensors.index.json`, and at least one `*.safetensors` shard, then print `HF_EXPORT_READY <hf_dir>` as the unambiguous ready marker.
  - Keep this as an auxiliary export job; do not change train batch, sample count, epochs, model, tokenizer, or chunk-data contracts while recovering export/deploy handoff.
  - Auxiliary export jobs can end with platform `job_failed` even after the HF directory has been fully materialized.
    Before relaunching or classifying export as failed, inspect the target `_hf` directory directly.
    If `config.json`, `generation_config.json`, `model.safetensors.index.json`, and the expected safetensors shards are present, treat the HF export as effectively ready and proceed to deploy readiness checks while recording the platform-exit noise.
    If those files are absent or partial, do not deploy the directory; inspect logs and rerun/repair export instead.
- Deploy sizing default gotcha:
  - Do not treat `4 replicas x 1 node` as a universal deployment default in generated qizhi configs.
  - Deployment sizing is task-specific and must follow the active matrix or user-confirmed contract.
  - A smaller default such as `2 replicas x 1 node` is valid and should be encoded directly in the generated config when that is the requested deploy baseline.
- User-corrected room3-128 preference:
  - In this workspace, `special-h200-room3-128` / `128节点3号机房` should no longer be treated as the default preferred pool for either training or deployment.
  - Deployment remains a hard no-go for that room unless the user explicitly overrides.
  - Training is softer but still constrained:
    - avoid `special-h200-room3-128` when a comparable candidate exists in `special-h200-room3`, `special-h200`, or another acceptable pool
    - only fall back to `room3-128` when the user explicitly approves it or when no practical alternative can satisfy the required capacity/latency target
  - Reporting rule:
    - if a submit had to use `room3-128`, call it out explicitly as an exception to the default preference
    - do not silently route there just because it appears earlier in an old allowlist
- Train image short-name gotcha:
  - In this workspace, do not assume `qz job create --image slime:20250812-v2 --image-type SOURCE_OFFICIAL` will be normalized to the internal official registry image.
  - A create using the short image name can persist platform-side as:
    - `framework_config[].image = "slime:20250812-v2"`
  - The resulting pod may then try to pull:
    - `docker.io/library/slime:20250812-v2`
    and fail with repeated:
    - `ErrImagePull`
    - `ImagePullBackOff`
  - For qizhi train fallback submits that need the standard Slime image, pin the full registry path explicitly:
    - `--image docker.sii.shaipower.online/inspire-studio/slime:20250812-v2`
    - `--image-type SOURCE_OFFICIAL`
  - After submit, confirm the persisted image via `qz job status <job> --raw`; if the job-side `framework_config[].image` is not the full registry path, do not treat that submit as valid.
- Train command rendering gotcha:
  - `orchestrate.py` renders only `train.create_payload.command` for the train submit path.
  - Keys under root-level `train_env` are not injected into that command automatically.
  - If a workflow needs train-time env overrides, either encode them directly into `create_payload.command`, or move the special logic into the invoked train wrapper's defaults.
  - Data-artifact precedence gotcha:
    - `legacy_run_config` files may carry stale or relative `parquet_path` values.
    - When the operator passes `--parquet-path` or resumes from a validated data-stage artifact, that path is authoritative and must override any later legacy run YAML merge.
    - A broken precedence order can submit a qizhi job whose train command contains a relative path such as `data/train/...parquet`; the container then starts outside the repo and fails immediately with `FileNotFoundError`.
    - Before accepting a `train_submit` run, inspect `logs/runs/<run_id>/train_submit_payload.json` and confirm the rendered command uses the intended absolute parquet path.
  - Rollout parquet boundary-quality gotcha:
    - A parquet row having at least one non-empty `user` message and at least one non-empty
      `assistant` message is not sufficient evidence that it is a clean SFT sample.
    - COD-695 baseline/data-quality follow-up found that
      `data/train/dataset/20260501/composed_rollouts_user_anchor.parquet` removed the known
      no-user rows but still retained `176/1159` rows whose first non-system role was `tool`
      or `assistant`, plus `93` duplicate extra rows.
    - The root cause was the long-trajectory chunking path in
      `messages_json2parquet_128k.py`: `append_sample()` only checked user-anchor/assistant
      presence somewhere in the chunk, so later chunks that began with orphaned tool output or
      assistant continuation still passed.
    - Before using a rollout parquet for train-submit, audit at least:
      - first non-system role counts, requiring `user` for clean-boundary SFT unless explicit
        carryover memory is injected;
      - no-user/no-assistant rows;
      - duplicate message-hash groups and duplicate extra rows;
      - source-family contribution when retry/native/raw sources were concatenated.
    - If a task intentionally uses mid-trajectory chunks, record the chunk metadata or injected
      carryover summary and report why the first visible state is coherent. Do not present
      "user anchor exists somewhere" as a clean-boundary guarantee.
    - User-corrected chunking contract for composed rollout SFT/CPT base:
      - pack chunks by full user turns, not by final-assistant segments;
      - target `120_000` tokens for CPT base chunks while keeping the outer tokenizer
        `max_tokens` margin;
      - every emitted chunk must begin with a `user` turn after any leading system prefix;
      - the next chunk should overlap the previous complete user turn when that overlap fits;
      - if previous-turn overlap plus the current user turn exceeds budget, drop the overlap
        and start from the current user turn instead of truncating the current turn;
      - truncate only when a single user turn itself exceeds the chunk budget.
  - For manual `qz job create --command ...` calls, distinguish local submit-time variables from
    runtime in-container variables:
    - expand local paths, timestamps, and output roots before submit, e.g. dataset/output paths
      and run names;
    - escape only variables intentionally resolved by the qizhi container, e.g.
      `${PET_MASTER_ADDR}`, `${MASTER_ADDR}`, `${PET_NNODES}`, `${PET_NODE_RANK}`.
  - GLM/Slime multi-node startup gotcha:
    - QZ exposes `PET_MASTER_ADDR` / `PET_MASTER_PORT`, but training wrappers may only read
      `MASTER_ADDR` / `MASTER_PORT`. Resolve the PET master address in the wrapper before Ray
      startup, preferably with a bounded `getent hosts` loop, then export `MASTER_ADDR`.
    - Under `set -euo pipefail`, probes like `nvidia-smi | grep -o "NVLink" | wc -l` fail when
      the GPU topology has no matching `NVLink` text. Add `|| true` to the pipeline or otherwise
      handle the zero-match case, because this can kill the qizhi job immediately after dependency
      installation and before any `train/loss` appears.
    - If qz logs end right after `pip install -e .` and events show one worker exit code `1`,
      inspect wrapper shell probes before concluding the model/training recipe failed.
    - For Slime SFT jobs that use `--num-epoch`, do not infer "no checkpoint will be saved" only
      from a large `--save-interval`. In `train_async.py`, Slime also saves at each
      `num_rollout_per_epoch` boundary when `num_rollout_per_epoch` is computed from the global
      rollout dataset. Estimate the first materialization point as
      `len(dataset) // rollout_batch_size` rollouts, and look for `latest_checkpointed_iteration.txt`
      / `iter_*` after that boundary before classifying the export path as blocked.
    - GLM/Slime small-dataset zero-rollout gotcha:
      - In the Slime async train path, when the wrapper passes `--num-epoch` but does not pass an
        explicit positive `--num-rollout`, `train_async.py` computes:
        - `num_rollout_per_epoch = len(dataset) // rollout_batch_size`
        - `num_rollout = num_rollout_per_epoch * num_epoch`
      - If the parquet row count is smaller than `rollout_batch_size`, then
        `num_rollout_per_epoch == 0`, `num_rollout == 0`, and training aborts immediately at:
        - `assert args.num_rollout > 0`
      - COD-645 (`glm47/openclaw`, `2026-05-04`) concrete evidence:
        - parquet rows: `63`
        - wrapper default: `ROLLOUT_BATCH_SIZE=64`, `GLOBAL_BATCH_SIZE=64`
        - runtime log showed:
          - `Generating train split: 63 examples`
          - `AssertionError`
          - `assert args.num_rollout > 0`
      - Recovery rule:
        - before accepting a GLM/Slime submit, compare parquet row count with the effective
          `rollout_batch_size`
        - if `rows < rollout_batch_size`, reduce `ROLLOUT_BATCH_SIZE` (and usually
          `GLOBAL_BATCH_SIZE`) to `<= rows`, or pass an explicit positive `--num-rollout`
        - do not keep rerunning the same wrapper defaults against a too-small dataset
  - Do not build the whole train command as a single-quoted shell string if it contains local
    variables such as `${TS}`, `${DATASET}`, or `${OUT1}`. The platform will preserve them
    literally, the job can still queue, and the failure will only appear after scheduling.
  - Stop-after deploy monitor gotcha:
    - When a deployment benchmark callback is known to block on local APTBench/shared-storage
      execution, use `orchestrate.py --stop-after deploy_monitor` for the next train/deploy arm.
    - This still validates HF wait, deploy submit, and deploy readiness, but does not launch
      another potentially stuck APTBench process.
    - Do not report this as benchmark completion. It only proves deployment readiness and leaves
      callback/benchmark execution as a separate follow-up.
  - For `scripts/train/qwen3-8b.sh`, a true `8 nodes / 64 GPUs` run also needs explicit
    `ACTOR_NUM_GPUS_PER_NODE=8` and `NUM_GPUS_THIS_NODE=8`; the wrapper defaults are `4` and
    would otherwise create a platform/runtime topology mismatch.
- Callback endpoint authority gotcha:
  - In the qizhi callback path, `orchestrate.py` injects runtime endpoint env vars:
    - `SERVING_ENDPOINT`
    - `DEPLOY_API_BASE`
    - `EXPERIMENT_API_BASE`
  - The companion `deployment-benchmark-workflow` resolves deployment base URL from env before
    falling back to YAML config.
  - Practical consequence:
    - for callback-launched deployment benchmarks, the runtime-derived env endpoint is the
      authoritative serving target
    - a static benchmark-config `deployment.base_url` is fallback-only and should not be treated
      as proof that the callback will hit the wrong room/domain unless the env override is missing
- Custom-domain validation fallback gotcha:
  - `qz deploy create --url-prefix ...` can fail with the localized platform error:
    - `自定义域名不满足格式要求`
  - Treat this the same as an English `custom_domain` validation failure.
  - Explicit prefixes must satisfy the platform naming rule in practice; in particular, a prefix
    that ends with digits such as `cod431-30ba3b-20260424` can be rejected even though it looks
    DNS-like. Prefer a short lowercase prefix that starts and ends with a letter, or skip the
    prefix entirely.
  - The safe recovery path is to retry the deploy create payload without `custom_domain` /
    `--url-prefix`, letting the platform auto-generate a valid subdomain.
  - After such a retry, do not keep using the configured `api_domain_prefix` as the benchmark
    endpoint. Read the deployment detail response and prefer `extra_info.service` as the runtime
    `SERVING_ENDPOINT` / `DEPLOY_API_BASE` / `EXPERIMENT_API_BASE`.
- Deploy-create response id gotcha:
  - `qz deploy create` can return the created serving id under `deployment_id` instead of
    `inference_serving_id`.
  - Automation must treat `deployment_id` as an equivalent serving id candidate; otherwise a
    successful create can be misclassified as `deploy_submit` failure even though the QZ
    deployment exists and can be monitored by that id.
  - When generating task-specific automation YAMLs, do not override the default serving-id
    candidates with only `inference_serving_id`; include both `data.deployment_id` and
    `deployment_id` in the generated `deploy.id_field_candidates`, or the template-level default
    fix will be bypassed.
- QZ native status gotcha:
  - In this workspace, qizhi job polling can return native status strings such as:
    - `job_queuing`
    - `job_running`
    - `job_stopped`
  - Do not rely only on generic aliases like `queued`, `running`, or `stopped` in automation YAML.
  - For train/deploy polling contracts, explicitly include:
    - running-side: `job_queuing`, `job_running`
    - failed-side: `job_stopped`
  - Otherwise a platform-terminal stopped job can be recorded as `unknown_status`, leaving stale local orchestrators alive and polluting long-running monitoring.
- QZ log rendering fallback gotcha:
  - `qz job logs <job_id> --worker N --lines M --text` can intermittently fail with a wrapper
    JSON parse error like:
    - `{"error": "Expecting value: line 1 column 1 (char 0)"}`
  - Do not treat this as evidence that the job has no logs or that training failed.
  - Retry with `--raw`, then inspect the returned `logs[*].message` fields for markers such as
    `train/loss`, `step`, `Traceback`, `OutOfMemory`, `NCCL`, or checkpoint save lines.
  - For deterministic report/export tasks, if both the primary log fetch and a retry fail but a
    previously frozen raw log JSON snapshot for the same job already exists, reuse that snapshot
    for validation and record a `log_fetch_fallback` note rather than failing the artifact refresh.
    This keeps review stable when QZ log rendering is flaky, while preserving traceability to the
    last successful raw snapshot.
- For reports, summarize the extracted message evidence rather than pasting raw platform JSON.
- `qz job status --raw` error-summary gotcha:
  - On misses, qz can return a JSON error string whose message appends a huge
    `Known names:` suffix with the entire local jobs cache.
  - When persisting read-only evidence snapshots or summary reports, do not
    save the full `qz job status --raw` payload for those miss cases.
  - Preferred handling:
    - parse the JSON error when present
    - truncate the summary before that suffix
    - persist only a short `error_summary` / `stdout_summary`
  - Otherwise a tiny negative probe can bloat JSON and Markdown artifacts by
    hundreds of KB and make later formal review noisy.
- Exact-name recovery probe rule:
  - When checking whether a qizhi recovery run was already submitted, do not start with
    `qz job list --raw` if the platform cache is large and noisy.
  - Prefer an exact probe using the deterministic orchestrator train-job name:
    - `train-{service_name}-{run_id}`
  - For deploy existence checks, prefer the exact `service_name`.
  - Workflow:
    - first run `qz job status <predicted-train-name> --raw`
    - then run `qz deploy status <service_name> --raw` if relevant
    - only fall back to list scans when the exact name cannot be derived
  - On a miss, summarize the `Known names:` error instead of storing the full cache dump.
- Distributed W&B offline sibling-dir gotcha:
  - In Slime / Ray qizhi training runs, one logical W&B run id can correspond to multiple
    sibling `offline-run-*` directories written by different roles such as driver and workers.
  - The `wandb sync /.../offline-run-*` hint printed in qz logs is not authoritative for
    `train/loss` history location; it may point to the driver directory while the actual
    persisted `train/loss` records live in a sibling worker directory.
  - When reconstructing local `train/loss` history:
    - inspect every sibling offline directory that shares the same W&B run id
    - prefer the directory whose `.wandb` history actually contains `train/loss`
    - keep qz worker logs as the authoritative fallback for tail steps or short failed runs
  - COD-549 evidence on `2026-05-03`:
    - run ids `pu1fg2hg` and `hlhwyk71` stored usable `train/loss` history in the third sibling
      offline directory rather than the driver directory named by the sync hint
    - run id `shj4tox0` did not retain complete local W&B `train/loss` history, but qz worker
      logs still preserved one recoverable `step 0` point
- User-corrected train-success classification rule:
  - For train monitoring in this workspace, platform terminal status alone is not authoritative.
  - A train job ending in:
    - `job_failed`
    - `job_stopped`
    may still count as an effective training success when the job logs already show real training progress.
  - The minimum accepted positive evidence is:
    - at least one `train/loss` log line
  - Stronger corroborating evidence often also appears:
    - `step N`
    - checkpoint save lines such as `saving checkpoint` / `successfully saved checkpoint`
    - Ray submit success lines such as `Job '...' succeeded`
  - Practical rule for automation:
    - keep the existing runtime-minutes fallback when needed
    - but before classifying `train_monitor` as failed on `job_failed` / `job_stopped`, probe recent train logs
    - if configured log markers such as `train/loss` are present, accept the run and continue to HF export / deploy instead of relaunching training
  - Materialization guardrail from COD-549 `combined` on `2026-05-01`:
    - `train/loss` alone is not enough to justify entering `deploy_hf_wait`.
    - Before continuing past a terminal `job_failed` / `job_stopped`, verify that the expected train output root actually exists and that there is at least one real materialized training artifact, such as:
      - an `iter_*` checkpoint directory under the output root,
      - `common.pt` or equivalent shard files,
      - or another explicit checkpoint-save artifact the downstream HF/export step can consume.
    - If logs show `train/loss` but the output root itself is missing, or HF wait polls stay at `candidate_count=0` because no checkpoint tree was ever materialized, classify the run as a real failed training run that still needs recovery. Do not treat it as an effective-success case and do not loop forever in `deploy_hf_wait`.
  - Reporting rule:
    - describe this as “effective training success with platform-exit noise”, not as a clean platform success
- GLM slime HF handoff rule:
  - In this workspace, `scripts/train/glm4.7.sh` trains to `iter_*` torch_dist checkpoints but does not auto-materialize a standard `iter_*_hf` directory.
  - If downstream deploy logic expects `^iter_(\d+)_hf$`, the automation must add an explicit post-train HF export stage instead of waiting forever in `deploy_hf_wait`.
  - Preferred export contract:
    - select the latest checkpoint from `latest_checkpointed_iteration.txt` when available
    - run slime `tools/convert_torch_dist_to_hf.py`
    - output to a standard sibling directory named `<iter_dir>_hf`
    - copy assets from the original HF checkpoint directory, for example GLM-4.7 HF root
  - Record the selected export input and output directories in run artifacts so a resumed run can skip redundant conversion and proceed directly to `deploy_hf_wait`.
- User-corrected controlled-experiment recovery rule:
  - For fixed-stage or other controlled comparison experiments, do not recover only failed arms by
    changing `GLOBAL_BATCH_SIZE`, `ROLLOUT_BATCH_SIZE`, sample count, epoch count, or another
    controlled training variable.
  - If the failed arms need a train-shape change to run, either:
    - apply the same train-shape change to every comparison arm and rerun the full matrix, or
    - ask the user to explicitly approve a changed experimental contract.
  - Infra-only recovery is acceptable without changing the experiment contract when it preserves
    train semantics, for example:
    - a fresh run id after a failed local state,
    - a different capacity-qualified H200 pool,
    - qz auth/login refresh,
    - or scheduler/resource placement changes that keep the rendered training command equivalent.
  - Reporting rule:
    - call out batch-size preservation explicitly when recovering a controlled experiment after an
      OOM/CUDA allocation failure.
  - COD-556 fixed-stage lower-batch variant rule:
    - keep the existing default `cod556-stage` matrix unchanged when the user says batch size is a
      controlled variable
    - if a lower-batch recovery is needed, add a separate full-matrix variant such as
      `cod556-stage-gbs16` instead of mutating old stage configs
    - the lower-batch variant must cover stage1..stage5 and set the same explicit env for every arm:
      `GLOBAL_BATCH_SIZE=16` and `ROLLOUT_BATCH_SIZE=16`
    - generated run/model/output suffixes must be distinct, for example `stage1-gbs16`, so the new
      variant cannot overwrite the old default-batch `stage1` artifacts
    - if `cod556-stage-gbs16` still fails before `train/loss`, the next valid recovery remains a
      separate full-matrix variant, for example `cod556-stage-gbs16-tok6144`, with every stage using
      the same `GLOBAL_BATCH_SIZE=16`, `ROLLOUT_BATCH_SIZE=16`, and `MAX_TOKENS_PER_GPU=6144`
    - user correction from COD-579: do not mix default-batch stage1 with lower-batch stage2+
      after canary failures; if the next candidate preserves batch size, create a separate
      full-matrix variant such as `cod556-stage-gbs32-cp4`
    - `cod556-stage-gbs32-cp4` must cover stage1..stage5 and every train command must explicitly
      set the same `GLOBAL_BATCH_SIZE=32`, `ROLLOUT_BATCH_SIZE=32`, `CONTEXT_PARALLEL_SIZE=4`, and
      `MAX_TOKENS_PER_GPU=12288`
    - the base SFT wrapper must keep `CONTEXT_PARALLEL_SIZE` defaulting to `1` so the default
      `cod556-stage` matrix is not changed by adding the cp4 candidate
    - do not submit training jobs from this bounded config patch; submit only after a separate
      user-approved runtime step
  - COD-556 fixed-stage chunking correction:
    - do not describe chunking as a train-time automatic fallback for Thinking SFT long-tail
      failures
    - in this repo, `chunk_long_conversations`, `chunk_tokens`, `overlap_tokens`,
      `emit_chunk_metadata`, and `long_horizon_mode` are data-pipeline preprocessing options under
      `src/cli/data_pipeline_cli.py` and the `messages_json2parquet_*` converters
    - the current COD-556 `composed_stage1..5.parquet` artifacts were generated without those
      chunk flags, so a fixed-stage train OOM is not expected to be solved automatically by the
      training wrapper
    - if chunking is chosen as the next recovery, treat it as a new full-matrix data-preprocessing
      experiment: regenerate stage1..stage5 under one uniform chunking contract, revalidate the
      resulting sample/row contract, and do not compare chunked arms with unchunked arms
    - if the active experiment contract requires exactly 722 training rows per stage, record how
      chunking affects row count before submitting QZ jobs; ordinary chunking can increase emitted
      rows and therefore may change the scientific comparison unless the user explicitly approves
      the new contract
- Manual HF export helper path gotcha:
  - The operational Qwen torch-dist to HF helper for this repo lives at repository root:
    - `scripts/convert_qwen_torch_dist_to_hf.py`
  - Do not look for it under `.codex/skills/qizhi-rollout-train-deploy-experiment/scripts/`; that path was observed to be absent during COD-488/COD-489 recovery.
  - For Qwen3-30B-A3B checkpoints, a successful one-node export command should:
    - run from the AgencyDataFlywheel repo root;
    - call `python3 scripts/convert_qwen_torch_dist_to_hf.py --input-dir <iter_dir> --output-dir <iter_dir>_hf --origin-hf-dir <origin_hf_dir>`;
    - verify `config.json`, `generation_config.json`, and `model.safetensors.index.json`;
    - print a clear marker such as `HF_EXPORT_READY <output_dir>`.
  - Use a high-memory qz job for this helper rather than local execution when the checkpoint is a 30B-class torch-dist directory.
- User-corrected rerun submit rule for failed-mask recovery loops:
  - When a future rerun is requested after fixing a training blocker such as the `COD-429` zero-supervision crash,
    do not add a task-failure retention / failed-job keepalive duration just to preserve the failed pod.
  - Preserve the normal submit surface unless the user explicitly requests a retention override.
  - The monitoring-side success classification remains unchanged:
    - still decide effective success from log evidence such as `train/loss`, not from failed-job retention settings.
- Single-node H200 tracing fallback rule:
  - For the current `Qwen3-8B` token-tracing fallback, a single-node H200 submission on `special-h200-room3` is a valid escalation target once local `4x4090` shrink policy is exhausted.
  - The stable qizhi-side train contract reused from the final local shrink attempt is:
    - `ENABLE_OPTIMIZER_CPU_OFFLOAD=0`
    - `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
    - `BOOTSTRAP_FROM_HF=1`
    - `LOCAL_SKIP_LOAD=1`
    - `ROLLOUT_BATCH_SIZE=4`
    - `GLOBAL_BATCH_SIZE=4`
    - `MAX_TOKENS_PER_GPU=14336`
  - Preserve the same tracing/custom-loss path when escalating to qizhi; do not fork a second training implementation just for the fallback.
  - User-corrected retry rule:
    - if that single-node tracing baseline has already been proven and a later fresh relaunch is still required, do not silently keep retrying on `1 node / 8 GPUs`
    - for the next relaunch starting point, prefer `8 nodes / 64 GPUs` unless the user explicitly freezes a smaller topology again
    - practical reading: single-node H200 is acceptable as the first qizhi fallback proof run; repeated post-proof retries should start by scaling out rather than by looping on the same 8-GPU shape
- Deploy ready gotcha:
  - For qizhi serving monitor in this workspace, deploy-ready is not the bare status string alone.
  - Native in-progress statuses can include:
    - `PRE_DEPLOYING`
    - `DEPLOYING`
    They must be treated as running-side statuses, not unknown terminal states.
  - Historical ready evidence here uses:
    - `status=RUNNING`
    - and `available_replicas > 0`
  - Platform detail can also report `status=DEPLOYING` while nodes are allocated but
    `available_replicas=0`; treat `DEPLOYING` / `deploying` as a running-side polling state,
    not an unknown terminal state.
  - Therefore:
    - deploy polling config should allow `running` to enter the success branch
    - but `deploy_monitor` must still wait until `available_replicas > 0` before treating that `running` state as terminal success
  - Auth-gated readiness nuance from COD-549 `no_openclaw` on `2026-05-01`:
    - an unauthenticated `/v1/models` probe can return `401` even when qizhi serving is already
      healthy and `ready_replicas > 0`;
    - do not classify that bare `401` as deploy-not-ready by itself;
    - instead, repeat the smoke with the runtime deployment credential and require the
      authenticated `/v1/models` result to succeed alongside `qz deploy status`.
  - Otherwise the callback can fail in either direction:
    - wait forever because `RUNNING` is never accepted
    - or fire too early while the serving is still `RUNNING` with `available_replicas=0`
- Nested parquet chat-template gotcha:
  - For nested-object parquet loaded through `pandas.read_parquet(..., dtype_backend="pyarrow")`, fields such as `messages` or assistant `tool_calls` may surface at runtime as `numpy.ndarray`, even when a local `pyarrow.to_pydict()` probe looks like plain Python lists.
  - In this repo, raw summary parquet with tool-calling assistant turns has been observed to fail runtime `tokenizer.apply_chat_template(...)` inside `slime.utils.data.Dataset`.
  - For this class of dataset, prefer an offline conversion step such as `scripts/convert_chat_parquet_to_cpt.py` that emits a text-only CPT parquet before training, instead of depending on train-time chat templating.
- Agentic SFT raw-messages gotcha:
  - The previous rule does **not** apply unchanged to agentic stage-2 SFT data that is intentionally consumed by `slime.rollout.sft_rollout.generate_rollout`.
  - When the rollout path expects raw multi-turn `messages` plus `tools` and computes assistant loss masks via `MultiTurnLossMaskGenerator`, keep:
    - `INPUT_KEY=messages`
    - `TOOL_KEY=tools`
    - `APPLY_CHAT_TEMPLATE=0`
  - Do **not** pre-render the dataset with `Dataset(..., apply_chat_template=True)`, because that converts `messages` from `list[dict]` into a flat string and breaks `sft_rollout`'s `messages = sample.prompt` contract.
  - Do **not** pass `rollout_max_prompt_len` for that raw-messages path unless you also own a compatible length-filter implementation.
    `Dataset(max_length=...)` tokenizes `prompt` directly; with raw `messages` lists, that check is incompatible with the SFT path.
  - The correct mitigation is:
    - either leave `ROLLOUT_MAX_PROMPT_LEN` empty for the raw-messages SFT path,
    - or add a dedicated offline/loader-side length filter that understands `messages` before enabling max-length pruning.
- Agentic CPT raw-messages safety rule:
  - For the `COD-319`-style triplet parquet outputs (`cpt_base`, `cpt_long_horizon`, `cpt_utility`), do not force a `messages/tools -> apply_chat_template -> text` conversion just to satisfy the 32B wrapper.
  - A tokenize-level probe in this repo confirmed:
    - raw-content concat + `add_special_tokens=False` produced no `<|im_start|>` hit on the sampled row
    - `apply_chat_template(..., tokenize=True)` on the same row injected `<|im_start|>` and many role tokens such as `user`
  - Do not treat raw parquet string search as sufficient evidence for or against the special-token risk:
    - tokens such as `<|im_start|>` or role ids may be absent from the raw `messages/tools` payload
    - they can still be introduced only after tokenizer/chat-template materialization
    - therefore the check must be done on the post-tokenize sequence or an equivalent tokenizer-level probe, not by grepping the raw parquet content
  - Therefore, when the goal is CPT-style full-sequence supervision without chat-template special-token leakage:
    - prefer `INPUT_KEY=messages`
    - keep `ROLLOUT_FUNCTION_PATH=src.training.qwen3_cpt_rollout.generate_rollout` or an equivalent raw-concat rollout
    - do not insert `scripts/convert_chat_parquet_to_cpt.py` into that path
  - Because `slime.utils.data.Dataset(max_length=...)` tokenizes `prompt` directly, raw `messages` CPT paths should also avoid `rollout_max_prompt_len` unless a message-aware length filter is owned explicitly.
- Stage-1 summary checkpoint load-contract gotcha:
  - For stage-2 policy/SFT continuation that starts from a stage-1 `summary` checkpoint directory,
    do not set both:
    - `REF_LOAD=<stage1 summary dir>`
    - `INIT_LOAD=<stage1 summary dir>`
  - In this workspace, the stage-1 summary checkpoint may lack optimizer state.
  - The safe contract is:
    - keep `REF_LOAD=<stage1 summary dir>`
    - omit wrapper-level `INIT_LOAD`
    - let slime enter its finetune path with `no_load_optim` / `no_load_rng`
  - If runtime init fails with `KeyError: optimizer`, classify it as a checkpoint-load contract bug first, not as a scheduler issue.
- Selected-pool migration gotcha:
  - An explicit `selected_pool` should not be treated as an absolute lock when it cannot prove the required H200 gang capacity.
  - If the requested pool is effectively wait-only or otherwise cannot prove `required_nodes` using current `qz avail` data, prefer migrating to a better H200 candidate in the same type family.
  - In this workspace, candidate ranking should consider:
    - `tier` priority: `immediate < preemption < wait`
    - `effective_nodes = free_nodes + low_pri_nodes`
    - workspace/pool preference only after capacity and tier checks
  - Otherwise a fallback train can remain indefinitely queued on a weaker wait pool even though a preemption candidate is available.
- Queue-vs-unschedulable interpretation gotcha:
  - For H200 gang jobs in this workspace, a monitor must not infer "startup is imminent" only because:
    - `qz job status` is still `job_queuing`
    - and `qz avail --type h200 --nodes <required_nodes>` shows `low_pri_nodes >= required_nodes`
  - `low_pri_nodes` is only candidate/preemption evidence; it is not a guarantee that the full gang is schedulable now.
  - When a job remains queued with no worker logs and no output directory, inspect `qz job events <job>`:
    - repeated warnings such as `Unschedulable`, `Insufficient cpu`, `Insufficient memory`, or `node(s) didn't match Pod's node affinity/selector`
      should be classified as active scheduler unschedulable signals, not as a clean queue-only wait
  - Practical monitoring rule:
    - use `qz avail` for candidate discovery
    - use `qz job events` as the stronger signal for whether the scheduler is actually close to starting the job
  - Reporting rule:
    - tell the user "still waiting on scheduler with unschedulable warnings" when those events exist
    - do not overstate the readiness implied by `low_pri_nodes`
- Same-workspace room preference gotcha:
  - When multiple pools inside the same preferred workspace are all already capacity-qualified for the current request, selection must still respect the explicit `pool_allowlist` order before comparing larger `free_nodes`.
  - Otherwise a `deploy` request that only needs `required_nodes=1` can drift from the intended `special-h200-room3(-128)` pool back to generic `special-h200` just because the generic pool reports more spare nodes.
  - Practical rule:
    - use capacity/tier checks to filter viable pools first,
    - then honor `pool_allowlist` order among same-workspace same-type viable pools,
    - only use larger `free_nodes` as a later tiebreaker.
- Workspace preference vs hard pinning gotcha:
  - In this repo, `workspace_preferences=["专项","分布式"]` is only a soft ordered preference.
  - The orchestrator will keep walking later workspaces when the earlier workspace cannot prove a capacity-qualified candidate.
  - Practical consequence:
    - this default does **not** guarantee that the submit actually lands in `专项`
    - it only biases the selection order
  - If the user explicitly wants the next submit attempt to stay inside `专项`, the safe contract is:
    - set `workspace_preferences=["专项"]`
    - keep `workspace_keyword="专项"`
    - restrict `pool_allowlist` to special H200 pools only
  - Candidate-selection nuance:
    - when no pool is `immediate`/`preemption` with enough nodes, `_select_qz_capacity_candidate(...)` still returns the first non-`error`/non-`reject` usable candidate
    - so a special-only config can still force a real submit onto a `tier=wait` special pool instead of silently falling back to distributed
- 30B CPT wrapper runtime-contract gotcha:
  - In this workspace, `scripts/train/qwen3-30b-a3b-base-cpt.sh` must not keep the older implicit runtime contract:
    - `PYTHONPATH` pointing at `/root/Megatron-LM/`
    - no explicit `runtime_env.py_executable`
    - implicit `python3` entrypoint inside `ray job submit`
  - A failed `COD-367` room3 candidate (`job-8eb5c3dd-63bb-4fbe-938a-910d721d34ab`) proved that this can surface as a misleading import-time tokenizer crash:
    - `AttributeError: ... tokenizer ... has no attribute 'MegatronLegacyTokenizer'`
  - Local verification showed the known-good Megatron checkout at:
    - `/inspire/hdd/global_public/yanmin/Megatron-main-org`
    still exports `MegatronLegacyTokenizer`
  - Therefore the durable fix is to align the 30B wrapper with the already-proven 8B contract:
    - explicit `MEGATRON_ROOT`
    - explicit `RUNTIME_PYTHON`
    - explicit `runtime_env.py_executable`
    - runtime `PYTHONPATH=${repo_root}:${slime_root}:${megatron_root}`
    - explicit `TORCH_CUDA_ARCH_LIST`
  - Practical rule:
    - when a new qizhi train wrapper is derived from older scripts in this repo, copy the validated runtime-env contract from the latest working wrapper first
    - do not assume `/root/Megatron-LM/` or implicit Ray interpreter inheritance are still safe defaults
- Text-only CPT length gotcha:
  - A text-only parquet is not automatically safe just because it no longer uses nested chat objects.
  - In this repo, `pr_chain_data_20260410_cpt.parquet` was measured under the real Qwen3-30B tokenizer at roughly:
    - `p50≈44k tokens`
    - `p90≈105k`
    - `p95≈160k`
    - `max≈214k`
  - That shape can still OOM or exceed model context limits even after lowering `MAX_TOKENS_PER_GPU`.
  - When a text-only CPT parquet shows long-tail rows at this scale, the safe contract is:
    - rechunk the text parquet offline into bounded token windows first,
    - then train on the rechunked parquet,
    - rather than continuing to tune only runtime batch/token-budget flags.
- Training OOM scaling rule for this workspace:
  - when a real training run OOMs, do not treat smaller runtime tweaks as the default first answer
  - prefer increasing node count first when the topology allows it
  - for substantial H200 training in this workspace, `8 nodes` should be treated as the preferred default shape unless the user explicitly freezes a smaller topology
  - if a temporary smaller-node run exists for queue/capacity reasons, classify it as a fallback rather than the preferred steady-state training shape
  - when reporting next actions after OOM, propose the node increase explicitly instead of only suggesting token/batch reductions
- Agentic CPT composed-rollout normalization rule:
  - when the training source is `data/train/dataset/<date>/composed_rollouts`, do not assume the raw rollout JSON already matches the final training contract
  - normalize it first into compact agentic conversations with only two top-level keys:
    - `messages`
    - `tools`
  - real composed-rollout dumps may include empty `messages` lists
  - filter those records out during the normalization/load step itself
  - do not pass empty conversations into the legacy token-count or `apply_chat_template(...)` path, or the run can fail before chunking with an index error on `conversation[0]`
  - for each message, keep only:
    - `role`
    - string `content`
  - explicitly drop message-level transport fields such as:
    - `timestamp`
    - `tool_call_id`
    - `tool_calls`
  - assistant `tool_calls` must be serialized back into `content` in user-frozen order:
    - original assistant content
    - any `description` extracted from `function.arguments`
    - tagged tool-call blocks such as `<function=...>` and `<parameter=...>`
  - after long-horizon / utility chunking, sanitize again before parquet write so the final training parquet still contains only `messages/tools`
- `cpt_base` near-100K rechunk rule:
  - if the user explicitly says one sample should target a `128K` context window and asks to split around `100K`, do not reuse historical small-window chunk settings such as `--chunk-tokens 24000`
  - for `data_pipeline_cli --emit-cpt-triplet`, prefer a base-only export path that leaves existing triplet outputs untouched:
    - select only `cpt_base`
    - write a new parquet path such as `cpt_base_100k.parquet`
    - do not overwrite the old `cpt_base.parquet`
  - in this repo, the internal chunk budget and the final serialized row token count are not 1:1
  - a literal internal budget of `100000` was observed to produce final rows up to `108049` tokens
  - the safe contract for this dataset family was to keep an internal slack budget around `92000`, which yielded:
    - `714` rows from the `20260410` composed rollouts
    - final `max_tokens=99831`
  - therefore, when the user asks for “final rows around 100K”, validate against a tokenizer recount on the emitted parquet instead of assuming the internal budget number is already the final row budget
- Loss-mask interpretation rule for CPT/tokenized rollouts:
  - `loss_mask=None` in the relevant CPT-style slime rollout paths means full-sequence supervision after controller materialization
  - do not describe that state as "masking out user tokens" or as the direct cause of role-token injection
  - if the trained model emits tokens like `<|im_start|>` or `assistant`, the first diagnosis questions are:
    - did raw message content already contain those strings?
    - or did `apply_chat_template(...)` inject those role/special tokens before training?

## Input Requirements
- `--automation-config`: YAML object config (copy from template and fill values)
- `--legacy-run-config`: AutoQZ legacy `run.yaml` (list format `- key: value`)
  - Not required when using `--stop-after data_pipeline`
- Training input is one of:
  - `--parquet-path`: skip compose/data_pipeline
  - `--rollouts-path`: already composed rollout directory
  - `--registry-path`: rollout SQLite registry; orchestrate composes rollouts first
- `--dataset-date`:
  - controls parquet output date directory (`YYYYMMDD`)
  - orchestrate writes parquet to `data_pipeline.dataset_path/<dataset_date>`
- Parquet volume rule:
  - default `parquet sample_count >= 64` (`data_pipeline.min_parquet_samples`)
  - orchestrate may increase `duplicate_times` automatically based on rollout count
  - if final sample count is still below threshold, `data_pipeline` fails fast
- Default training resource policy, overridable by legacy `run.yaml`:
  - `train_instance_count`: default `8`
  - `train_shm_gi`: default `800`
  - `train_image_name`: default `docker.sii.shaipower.online/inspire-studio/slime:20250812-v2`
  - `train_image_type`: default `SOURCE_OFFICIAL`
  - output dir default: `<output_root>/<model>-pr-<MMDD>`
- Recommended minimal inputs:
  - `dataset_path`
  - `train_instance_count`
  - `deploy_api_prefix`
- Shared train entrypoint contract:
  - if a shared train script needs to support both fresh runs and checkpoint resume, keep the script fresh-by-default
  - express resume only in the automation command/payload, for example by adding an explicit third CLI arg such as `1`
  - do not hardcode `--load <output_dir>` unconditionally in the shared script, or later fresh submits that reuse a stable output dir will be silently polluted into resume mode
  - for `slime` SFT/CPT wrappers that run with `--debug-train-only` and default `n_samples_per_prompt=1`,
    keep the default batch contract self-consistent:
    - `rollout_batch_size * n_samples_per_prompt` must be divisible by `global_batch_size`
    - for the current `qwen3-32b-cpt.sh` path, the safe default is to keep `GLOBAL_BATCH_SIZE` aligned with `ROLLOUT_BATCH_SIZE`
    - a default like `rollout_batch_size=64` plus `global_batch_size=128` will fail only after the job really starts, with
      `AssertionError: rollout_batch_size 64 * n_samples_per_prompt 1 is not a multiple of global_batch_size 128`
  - for local `slime + Megatron` `--debug-train-only` tracing in this workspace, the runtime-safe contract is stricter than just “lazy-load sglang arguments”:
    - `debug_train_only` must not start router state or depend on `args.sglang_router_ip`
    - the debug path may still instantiate `RolloutController` and its data-source path, so modules imported by `rollout_function_path` remain part of the training critical path even when no SGLang engine is launched
    - if the host Python has broken `scipy/sklearn`, broad `AutoTokenizer` imports can still kill a debug-train-only job before the first train step
    - for Qwen3 checkpoints whose tokenizer config resolves to `Qwen2Tokenizer`, prefer a narrow loader (`Qwen2TokenizerFast -> Qwen2Tokenizer`) over `AutoTokenizer` on those critical import paths
- `automation_config.qz` must supply enough pool metadata to honor the frozen selection rule:
  - `workspace_keyword`
  - ordered `workspace_preferences` when the workflow may fall back from `专项` to `分布式`
  - optional `pool_allowlist`
  - optional stage-specific overrides such as:
    - `qz.train.pool_allowlist`
    - `qz.deploy.pool_allowlist`
  - ordered `type_preference`
  - optional `scan_before_submit`
  - optional `existing_parallel_train_job_ids`
  - optional `max_parallel_jobs`
  - optional `cancel_other_jobs_on_first_running`
- Stage-specific pool override rule:
  - when the user freezes different train-vs-deploy pool contracts, do not mutate the train policy just to satisfy deploy placement
  - prefer:
    - global `qz.pool_allowlist` for train/default behavior
    - `qz.deploy.pool_allowlist` for deploy-only narrowing
  - for the current `COD-431` style contract:
    - train may still keep `special-h200-room3-128` in the special-room priority chain
    - deploy must explicitly exclude `special-h200-room3-128`
    - deploy should prefer:
      - `special-h200-room3`
      - `special-h200`
- Failed-retention submit rule:
  - when the user explicitly freezes “不要设置任务失败保留时长”, keep the qizhi submit path free of failed-job/deploy retention duration flags
  - current `qz job create` / `qz deploy create` transport in this skill does not emit such fields; preserve that absence unless the user explicitly asks for retention behavior

## QZ Requirements
- `qz` must be installed from `/inspire/hdd/project/qproject-fundationmodel/public/mhjiang/myqz`.
- Any step that runs `qz` should `source` this skill's `env.sh` first.
- `env.sh` should export or forward:
  - `QZ_API_USERNAME`
  - `QZ_API_PASSWORD`
  - `QZ_COOKIE_USERNAME`
  - `QZ_COOKIE_PASSWORD`
- Recommended manual health checks:
  - `source .codex/skills/qizhi-rollout-train-deploy-experiment/env.sh && qz login`
  - `python scripts/setup_qz_special_config.py`
  - `qz pools`
  - `qz avail --type h200 --nodes 8`
- Train nodes in these H200 workspaces may have no outbound network during runtime:
  - do not rely on `pip install`, `uv sync`, or build-isolation downloads inside the submitted train command
  - the image and shared filesystem must already contain the required runtime dependencies
  - training scripts should prefer prebuilt images plus `PYTHONPATH` wiring over startup-time package installation
  - when the user still needs wandb loss, do not switch the train job to `WANDB_MODE=online`
  - preferred contract is:
    - train zone writes wandb offline runs to a shared root such as `/inspire/hdd/project/qproject-fundationmodel/public/mhjiang/DataFlyWheel/wandb`
    - later, from a network-enabled zone, execute `wandb sync` against the discovered `offline-run-*` directories
  - avoid blocking `train_async.py` on online `wandb.init()` in no-network H200 workspaces
- `qz` config must define pool aliases for the target workspaces in `~/.config/qz/config.toml` or the configured `QZ_CONFIG_DIR`.
- For the current Qwen3-32B CPT fallback workflow, `scripts/setup_qz_special_config.py` is the canonical way to populate:
  - `"专项"` and `"分布式"` workspace aliases
  - extra `专项` H200 pools
  - `分布式` H200 pools
- `qz pools` is the preferred manual inspection command before orchestration because it exposes `pool/type/workspace_id/lcg_id`, which is the metadata used to lock workspace before type ranking.
- Deploy image argument rule:
  - `qz deploy create --image` expects `name:version` or an `image-...` id.
  - Do not prepend `docker.sii.shaipower.online/` inside deploy payload templates for the qz CLI path.
  - If a previous API-oriented config used a fully qualified registry URL, strip it before calling `qz deploy create`.
- Deploy URL-prefix gotcha:
  - The public deployment subdomain prefix must satisfy the platform validator and end with a lowercase letter.
  - Step-stamped names like `...-s50` are safe as deployment names, but they are not stable as explicit `--url-prefix` values because the prefix would end with a digit.
  - For deterministic benchmark wiring, prefer an explicit prefix like `...-step50` instead of reusing the raw service name as `url-prefix`.

## Pool / Type Selection Policy
- User correction is now part of the skill contract:
  - do not add or emulate `usage`
  - use `qz avail` for all capacity and monitoring snapshots
  - use `pool` to lock the target workspace first, then use `type` to filter or rank candidate pools
- H200-first is not just a preference, it is the default hard policy in this repo:
  - unless the user explicitly asks for H100, default candidate types are H200 only
  - do not silently append H100 as an automatic fallback type
  - when H200 has no usable workspace / room yet, report the H200 blocker instead of auto-submitting H100
- Candidate discovery should use configured qz pools, not `qzcli` resource caches.
- Expected selection flow:
  - inspect configured pools from `qz pools` / qz config
  - resolve candidate workspaces in `workspace_preferences` order, typically `专项 -> 分布式`
  - apply optional `pool_allowlist`
  - apply `type_preference` in order; repo default is `["h200"]`
  - call `qz avail` for the selected type
  - filter the returned entries back to the candidate pool alias
  - only keep the current workspace when it can prove `tier in {immediate, preemption}` and `free_nodes >= required_nodes`
  - within the same `workspace/type/tier` bucket, sort by higher effective capacity first
    (`effective_nodes = raw_free_nodes + low_priority_nodes`), and use room preference only as a tie-break
  - when `qz_capacity_candidates_report` appears to show an unexpected winner, do not stop at the summarized `free_nodes` field
    - that report currently records only the already-merged effective-capacity number
    - inspect the preceding `qz_command_result phase=qz_capacity_scan` payload to recover:
      - `raw_free_nodes`
      - `low_priority_nodes`
      - `effective_nodes`
    - in `COD-326` rerun3, `distributed-h200-room3` (`1 + 10`) and `distributed-h200-room3-2` (`0 + 11`) both resolved to `effective_nodes=11`
    - the winner returning to `room3` in that case was a legitimate room-level tie-break, not a ranking regression
  - if the earlier workspace cannot prove enough H200 nodes, continue to the next workspace in `workspace_preferences` instead of snapping back to the first pool
  - if all H200 candidates only return permission-style `tier=error/free_nodes=0`, prefer a later workspace candidate over the first `专项` pool so the real submit path can continue probing `分布式`
- `workspace_keyword` is still valid as the legacy single-workspace default, but new fallback automation should prefer explicit `workspace_preferences`.
- If a task wants cross-workspace H200 search, prefer:
  - `workspace_preferences: ["专项", "分布式"]`
  - `type_preference: ["h200"]`
  - and keep `pool_allowlist` either empty or limited to H200 pools only.
- `qz avail` does not currently accept `--pool`; filtering by pool alias is the orchestrator's responsibility.
- `qz avail` may return a workspace-scoped permission error such as
  `"You are not the admin of the <workspace> workspace."` with `tier=error`.
  Treat that as a capacity-snapshot warning, not automatic proof that bearer-token
  `train_job/create` will also fail. Keep the warning in run artifacts, but continue to
  verify the real submit path before declaring the workspace unusable.
- `scan_before_submit=false` is allowed for legacy direct-submit cases. When disabled, skip the capacity scan and submit using the already frozen `workspace_id` / `logic_compute_group_id` / `spec_id`.
- Some distributed train candidates may expose a valid `logic_compute_group_id=lcg-...` but no
  stable `logic_compute_group` alias.
  - In that case, the orchestrator must still treat the candidate as usable.
  - The selected `logic_compute_group_id` should be promoted into the legacy
    `logic_compute_group` slot before legacy mapping runs, so `passthrough_if_id_like=true`
    can carry it through to the final train payload.
  - Do not fail early just because the alias field is empty when the id field is present.

## Duplicate-Job Winner Policy
- For same-goal fallback retries, keep the live duplicate count explicit in config:
  - `existing_parallel_train_job_ids`
  - `max_parallel_jobs`
  - `cancel_other_jobs_on_first_running`
- When the original job and the fallback job may coexist for some time, do not point both at the same train output directory.
  - give the fallback a distinct `output_tag` / `train_output_dir` until the winner is known
  - otherwise concurrent checkpoint/HF export writes can collide before the loser is stopped
- If a stage-2 SFT job initializes from a stage-1 checkpoint that only contains model/reference weights
  and no optimizer state, do not force that checkpoint through a wrapper-level `INIT_LOAD=<stage1_dir>`.
  - keep `REF_LOAD=<stage1_dir>`
  - let slime fall back to `no_load_optim + no_load_rng + finetune + load=ref_load`
  - otherwise the job can fail immediately with `KeyError: 'optimizer'` during checkpoint load
- Preferred execution contract for this repo:
  - keep the original queued job
  - submit at most one additional fallback job
  - monitor both job ids during `train_monitor`
  - the first job that enters real `running` becomes the winner
  - immediately request stop for the loser job
  - continue monitoring only the winner until train terminal state
- Winner resolution must also refresh runtime context from the winning job detail:
  - `workspace_id`
  - `logic_compute_group_id`
  - `spec_id`
  - `train_output_dir`
  - selected qz `pool/type` when resolvable from configured pools

## Monitoring Policy
- Precheck before `train_submit` / `deploy_submit`:
  - use `qz avail --type <selected_type> --nodes <required_nodes>`
  - capacity decision is based on the selected pool entry only
- Monitor during `train_monitor` / `deploy_monitor`:
  - periodically run `qz avail` again for the selected `type`
  - while a train job is still queued / unschedulable, re-check every candidate H200 workspace / room in `workspace_preferences` order instead of only staring at the originally selected pool
  - if another H200 workspace / room can newly prove `tier in {immediate, preemption}` and `free_nodes >= required_nodes`, treat it as a valid migration candidate for the next submit / duplicate-winner decision
  - record only capacity-related snapshots and warnings
  - do not claim workspace-wide task count or GPU-in-use metrics
  - do not introduce a separate `usage` collector or `usage_snapshot` event family
  - when a queued training job has pod-level scheduler warnings in `qz job events`, treat those event reasons as the authoritative blocker classification
  - specifically, if events repeatedly report `Unschedulable` with messages such as:
    - `Insufficient cpu`
    - `Insufficient memory`
    - `Insufficient nvidia.com/gpu`
    - `node(s) didn't match Pod's node affinity/selector`
    the monitor should classify the job as scheduler-blocked rather than as a generic script/runtime failure
  - once that blocker family is established, do not emit repeated progress comments for the same `Unschedulable` classification unless one of these changes occurs:
    - `qz job status` changes to a different real state such as `job_running`, `job_failed`, `job_success`
    - the event stream materially changes to indicate the job has become schedulable or started binding resources
    - output artifacts such as the train `output_dir` or `iter_*_hf` actually appear
  - if `qz job status` transiently fails to return structured JSON and the polling code falls back to `unknown`, do not treat that alone as a meaningful state transition when the last authoritative scheduler diagnosis is still the same queued `Unschedulable` condition
  - `SuccessfulCreatePod` / `SuccessfulCreateService` on a queued PyTorchJob is not winner evidence by itself
  - if `qz job status` still reports `job_queuing`, `qz job events` keeps emitting `Unschedulable`, and the configured train `output_dir` does not exist yet, classify the job as still scheduler-blocked pre-run even if pod/service creation events have already appeared
  - for duplicate-winner runs that enable `cancel_other_jobs_on_first_running`, do not manually stop the other queued candidate before one job reaches a real winner signal such as `job_running`; otherwise you can throw away queue age without any confirmed runnable path
  - duplicate-winner output-dir routing is winner-driven:
    - after a winner is selected, `orchestrate.py` refreshes `train_output_dir` from the winner job response rather than blindly keeping the newly submitted shadow output root
    - therefore mixed old/new competing candidates are safe as long as the winner response still exposes the real train command/output dir
  - resume preflight state-transition rule:
    - a resumed orchestrator run does need to clear stale top-level failure state eventually, but **not** during `RunStateStore(..., resume=True)` construction
    - if persisted state is rewritten to `status=running` / `last_error=null` before resume preflight validates saved artifacts, a later preflight failure leaves `state.json` falsely advertising a healthy resumed run
    - the safe contract is:
      - load prior state/artifacts without mutating them during resume initialization
      - run resume preflight first
      - only after preflight succeeds and the main execution path is about to start, explicitly mark the run resumed/running
    - preserving only the prior `failed` state is not sufficient
    - if `--resume-run-id` points at an already completed `success` run and preflight fails before any phase re-entry, do **not** downgrade that historical success to `failed`
    - safe rollback contract before first phase activation is:
      - preserve prior `failed`
      - preserve prior `success` only when the run really completed through the final callback boundary
      - do not treat partial `--stop-after data_pipeline` / `--stop-after train_submit` checkpoints as fully completed success
      - explicitly downgrade prior interrupted/`running` state to `failed`
      - explicitly downgrade partial stop-after `success` checkpoints to `failed` when a later resume preflight aborts before phase re-entry
  - local run-root override rule:
    - `orchestrate.py` should keep an env seam such as `CODEX_QIZHI_RUNS_ROOT` for task-scoped tests
    - this lets focused verifiers stage temporary `state.json` / `artifacts.json` fixtures without touching authoritative long-running runtime state under `logs/runs`
- Polling status compatibility remains:
  - handle `job_failed` / deploy failure states
  - allow the existing `accept_failed_if_runtime_minutes` training compatibility rule
  - when a task explicitly freezes a threshold such as `accept_failed_if_runtime_minutes: 20`, treat a training job that exceeds that runtime and then lands in `job_failed` as accepted completion for closeout
  - workspace correction for training closeout:
    - do not use control-plane `job_failed` as the sole success criterion for train-stage closeout
    - if a training run has already executed for more than `10` minutes and there is authoritative evidence that real training happened, classify it as an accepted train success even if the final control-plane status is `job_failed`
    - acceptable authoritative evidence includes any of:
      - visible loss / step progress in shared logs or terminal output
      - saved train artifacts such as real `iter_*` checkpoints
      - framework-level success markers for the core train loop before later cleanup / teardown failure
    - in that state, treat the post-10-minute failure as a tail failure / cleanup failure unless logs prove the core training itself never started
    - for this workspace, checkpointed progress or visible loss always outranks the final `job_failed` label when judging whether the training stage itself succeeded
  - once such an authoritative accepted-runtime run exists, prefer closing out on that run and stop/deprecate later redundant resubmits instead of keeping the issue open on an outdated "must continue rerun" assumption
- If the training entrypoint spends extra time on `wandb sync`, HF export, or upload cleanup, `qz job status` may remain in a running-like state after the core training compute is done. In that case prefer shared logs such as `train.log` / `orchestrator.log`.
- Expected `events.jsonl` families after migration:
  - `qz_command_result`
  - `qz_login_refresh_*`
  - `qz_avail_snapshot`
  - `qz_capacity_warning`
  - `qz_monitor_error`
- When an interactive orchestrate PTY appears silent for long stretches, use `logs/runs/<run_id>/state.json`, `artifacts.json`, and `events.jsonl` as the authoritative live state source before assuming the run is stuck.
- Deploy runtime failure triage:
  - if `qz deploy status --raw` shows `available_replicas=0` and later `status=FAILED`,
  - and `qz deploy instances` shows the leader restarted multiple times,
  - do not assume the root cause is image/model/quota just because `qz deploy logs` is sparse.
  - First inspect the exact redirect target embedded in the deploy `command` payload, because this repo's deploy commands commonly send stdout/stderr to a workspace-local log file.
  - In the April 11, 2026 Qwen3-32B CPT recovery, the decisive root cause came from that redirected log:
    - `exec: CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7: not found`
  - Practical rule:
    - prefer `qz deploy instances` + redirected command log + local warmup evidence over empty platform stderr
    - for shell entrypoints, set/export env vars before `exec`; do not write `exec ENV=... python ...`

## HF Wait Before Deploy
- 30B Base deploy/bench helper gap:
  - a task-scoped helper that only hardcodes `iter_<step>_hf` paths is not yet a complete closeout flow when training actually leaves only `iter_<step>` `torch_dist` directories behind.
  - in this repo, COD-200 30B Base training on 2026-04-16 produced authoritative step checkpoints plus Ray-success evidence while still leaving deploy blocked on missing `_hf` directories.
  - practical rule:
    - if step checkpoints exist in `torch_dist` format and deploy needs `iter_*_hf`,
    - the helper must either export `torch_dist -> _hf` explicitly or emit that export command as part of the blocking plan,
    - instead of treating missing `_hf` as if training itself had not reached deploy readiness.
- `deploy.hf_wait` is enabled by default
- before `deploy_submit`, poll for `_hf` output readiness
- default directory regex: `^iter_(\d+)_hf$`
- default readiness files:
  - `config.json`
  - `generation_config.json`
- default selection policy: `latest_ready`
- default behavior rewrites `_hf` path in `bash_command`
- default timeout is infinite (`timeout_seconds: 0`)
- StepTronOss Step-3.5-Flash output pattern:
  - The SteptronOss PR-chain wrapper
    `/inspire/hdd/project/qproject-fundationmodel/public/mhjiang/SteptronOss/scripts/train/steptron_step3p5_pr_chain.sh`
    exports the deployable HF directory under:
    `checkpoints/step3_flash_sft_pr_chain_muon/it1/hf`.
  - The PR-chain wrapper runs parquet -> StepChat conversion before training. The converter imports
    `pyarrow`; in the current qizhi Slime image the SteptronOss `.venv/bin/python` may not have
    `pyarrow` even when `/usr/bin/python3` does. Set `STEPTRON_CONVERT_PYTHON_BIN` to a Python
    with `pyarrow` and keep `STEPTRON_PYTHON_BIN` on the StepTronOss training environment.
  - Do not reuse the default `^iter_(\d+)_hf$` scanner for this family.
  - In the qizhi run config, point `bash_command` at
    `{train_output_dir}/checkpoints/step3_flash_sft_pr_chain_muon/it1/hf`, and set:
    `deploy.hf_wait.dir_name_regex: "^hf$"`.
  - Step train output in this workspace can finish with only:
    - `model-*.safetensors`
    - `model.safetensors.index.json`
    and without prelinked `config.json` / tokenizer metadata.
  - Practical rule:
    - for Step `hf_wait`, do not require `generation_config.json`;
    - do not require prelinked Step metadata before deploy submit;
    - key readiness off the produced HF weight index, then let the deploy wrapper backfill metadata.
  - `scripts/deploy/step35_flash_vllm.sh` should backfill missing metadata from:
    `/inspire/qb-ilm/project/qproject-fundationmodel/public/model/Step-3.5-Flash`
    before `vllm serve`.
  - Historical Step success in this repo did not require `generation_config.json`.
    If an older live wait loop is already blocked on that filename, treat a minimal JSON shim as
    a compatibility workaround for that stale run rather than as a required training output.
  - Train-output-dir extraction gotcha for Step train responses:
    - qizhi can report the train command as `bash -lc 'set -eo pipefail; ... bash <wrapper> <parquet> <output_dir>'`
    - do not treat the whole inner shell fragment as `train_output_dir`
    - the extractor must recover the final output-dir argument from the wrapped Step train invocation, or later `deploy_submit` will rewrite the Step HF hint into a malformed serving command
    - failure signature:
      - `artifacts.json["train_output_dir"]` contains shell text instead of a path
      - the generated deploy command passes training-shell text after `step35_flash_vllm.sh`
      - deploy logs then fail with Step training env errors such as `PET_NNODES: missing PET_NNODES`
  - With the current orchestrator, a hint whose basename is `hf` and regex `^hf$` makes
    `deploy_hf_wait` scan the parent `it1` directory for the `hf` child, which matches the
    StepTronOss output shape.
  - `_extract_hf_path_token_from_bash_command` must treat a path whose basename is exactly `hf`
    as a valid HF hint, in addition to the older `iter_*_hf` tokens.
  - GLM deploy-root handoff gotcha:
    - some GLM run YAMLs intentionally pass the family train root such as `{train_output_dir}`
      into `scripts/deploy/deploy_glm47.sh`, relying on `deploy_hf_wait` to pick the latest
      ready `iter_*_hf` sibling and rewrite the command before deploy submit
    - if the parsed `bash_command` contains the GLM train root but no explicit `iter_*_hf`
      token yet, `deploy_hf_wait` must fall back to that `train_output_dir` path as the scan
      base instead of failing early with `Unable to parse HF checkpoint path from bash_command`
    - after selection, rewrite that root-dir argument to the resolved standard HF directory
      before `deploy_submit`
- Manual recovery note:
  - if the shared training output already has `iter_xxxxxxx/` checkpoints but no `_hf`,
    first verify whether the export tooling is blocked by environment problems rather than by
    checkpoint corruption.
  - For GLM-4.7 / slime runs in this workspace, positive training evidence can stop at
    `torch_dist` materialization such as `latest_checkpointed_iteration.txt` plus
    `iter_0000018/common.pt` and `.distcp` shards, with no automatic `_hf` directory appearing
    during active training.
  - When that happens, the standard export path is the slime converter itself:
    ```bash
    cd /inspire/hdd/project/qproject-fundationmodel/public/sunjie/slime
    PYTHONPATH=/inspire/hdd/project/qproject-fundationmodel/public/sunjie/Megatron-LM \
      python tools/convert_torch_dist_to_hf.py \
      --input-dir <iter_dir> \
      --output-dir <iter_dir>_hf \
      --origin-hf-dir /inspire/hdd/project/qproject-fundationmodel/public/sunjie/workspace/LLMs/GLM-4.7
    ```
  - Do not wait forever for `_hf` if train has already produced a valid GLM `torch_dist`
    checkpoint set and the family wrapper does not include an explicit HF export stage.
  - In this workspace, slime's `tools/convert_torch_dist_to_hf.py` can be blocked by package
    initialization side effects:
    - `slime.backends.megatron_utils.__init__ -> actor.py -> AutoTokenizer -> sklearn/scipy`
    - a broken system `scipy` then fails before export begins.
  - Separate GLM-4.7 export gotcha observed on `cod601_glm47_openclaw_relaunch1_20260504`:
    - running `/usr/bin/python3 /inspire/hdd/project/qproject-fundationmodel/public/sunjie/slime/tools/convert_torch_dist_to_hf.py`
      directly from the repo workspace can fail immediately with:
      `ModuleNotFoundError: No module named 'slime'`
    - this means the converter was launched without a package-visible slime root, even though the
      training checkpoint itself is already valid.
    - recovery rule:
      - set `PYTHONPATH=<repo_root_parent>` or otherwise include
        `/inspire/hdd/project/qproject-fundationmodel/public/sunjie`
        before invoking the converter module, so `import slime` resolves
      - treat the import failure as an environment handoff bug, not as checkpoint corruption
  - For Qwen dense checkpoints in this repo, prefer the repo-local recovery wrapper:
    ```bash
    source .venv/bin/activate
    /usr/bin/python3 scripts/convert_qwen_torch_dist_to_hf.py \
      --checkpoint-root /path/to/train_output \
      --iterations 67 50 33 16 \
      --origin-hf-dir /inspire/qb-ilm/project/qproject-fundationmodel/public/model/Qwen3-32B
    ```
  - Prioritize exporting the latest checkpoint first to unblock `deploy_hf_wait`, then backfill
    older checkpoints requested for comparison.

## Run
Prepare auth and qz config first:

```bash
source .codex/skills/qizhi-rollout-train-deploy-experiment/env.sh
qz login
qz pools
```

Full workflow from composed rollouts:

```bash
python .codex/skills/qizhi-rollout-train-deploy-experiment/scripts/orchestrate.py \
  --automation-config .codex/skills/qizhi-rollout-train-deploy-experiment/assets/automation.template.yaml \
  --legacy-run-config /path/to/run.yaml \
  --rollouts-path /path/to/composed_rollouts_dir
```

Submit from an existing parquet:

```bash
python .codex/skills/qizhi-rollout-train-deploy-experiment/scripts/orchestrate.py \
  --automation-config .codex/skills/qizhi-rollout-train-deploy-experiment/assets/automation.template.yaml \
  --legacy-run-config /path/to/run.yaml \
  --parquet-path /path/to/train.parquet \
  --dataset-date 20260305
```

Compose from registry then run end to end:

```bash
python .codex/skills/qizhi-rollout-train-deploy-experiment/scripts/orchestrate.py \
  --automation-config .codex/skills/qizhi-rollout-train-deploy-experiment/assets/automation.template.yaml \
  --legacy-run-config /path/to/run.yaml \
  --registry-path data/synthetic/rollouts/rollouts.db \
  --compose-output-dir .codex/skills/qizhi-rollout-train-deploy-experiment/runs/manual_run/composed_rollouts
```

Only build parquet:

```bash
python .codex/skills/qizhi-rollout-train-deploy-experiment/scripts/orchestrate.py \
  --automation-config .codex/skills/qizhi-rollout-train-deploy-experiment/assets/automation.template.yaml \
  --rollouts-path /path/to/composed_rollouts_dir \
  --dataset-date 20260305 \
  --stop-after data_pipeline
```

Only submit train job:

```bash
python .codex/skills/qizhi-rollout-train-deploy-experiment/scripts/orchestrate.py \
  --automation-config .codex/skills/qizhi-rollout-train-deploy-experiment/assets/automation.template.yaml \
  --legacy-run-config /path/to/run.yaml \
  --rollouts-path /path/to/composed_rollouts_dir \
  --dataset-date 20260305 \
  --stop-after train_submit
```

Resume an interrupted run:

```bash
python .codex/skills/qizhi-rollout-train-deploy-experiment/scripts/orchestrate.py \
  --automation-config <config.yaml> \
  --legacy-run-config <run.yaml> \
  --registry-path <rollouts.db> \
  --resume-run-id <run_id>
```

## Runtime Outputs
- `runs/<run_id>/state.json`
- `runs/<run_id>/events.jsonl`
- `runs/<run_id>/artifacts.json`
- deploy HF wait artifacts:
  - `hf_selected_dir`
  - `hf_base_dir`
  - `hf_selection_policy`
  - `hf_wait_seconds`

## Failure Behavior
- Any stage failure (`data_pipeline`, `train_submit`, `train_monitor`, `deploy_submit`, `deploy_monitor`, `callback`) marks the run as failed and triggers Feishu notification when enabled.
- HF wait failure stops the workflow in `deploy_hf_wait`; deploy is not submitted.

## Operational Notes
- When `--rollouts-path` / `--composed-rollouts-path` points at a composed rollout directory,
  the current loader in `src.pipelines.data_process.composed_rollouts` intentionally skips
  `summary.json`.
  - It is safe for composed directories to keep `summary.json` colocated with rollout JSON
    payloads.
  - The loader also skips zero-byte `*.json` files during directory iteration. This preserves
    dirty source artifacts for audit while allowing parquet conversion to proceed on valid
    trajectories.
  - The single-file reader uses `json.JSONDecoder(strict=False)` to tolerate unescaped control
    characters inside otherwise valid JSON strings.
  - For directory conversion, malformed non-empty JSON files are skipped with a stderr warning
    such as `[composed-rollouts] Skipping invalid JSON file ...`; record the skipped filenames in
    the run report because they reduce the number of source trajectories contributing to the
    parquet.
  - Do not silently delete or rewrite bad composed JSON files just to make conversion pass unless
    the user explicitly asks for data repair; prefer keeping the raw artifacts and documenting the
    skipped set.
- Workspace and train-spec discovery facts to preserve in repo context:
  - `GET /api/v1/user/routes/{ws_id}` can be used to enumerate accessible workspaces from `data.routes[name=userWorkspaceList].routes[]`
  - `POST /api/v1/resource_prices/logic_compute_groups/` with `schedule_config_type="SCHEDULE_CONFIG_TYPE_TRAIN"` returns train quota / `spec_id` candidates for a logic compute group
- If the user explicitly forbids editing a legacy script such as `scripts/run_train_data_process.sh`, prefer environment-only repairs first:
  - shell activation via `source .venv/bin/activate`
  - host-level `uv` compatibility overrides when needed:
    - `UV_NO_BUILD_ISOLATION=1`
    - `SETUPTOOLS_ENABLE_FEATURES=legacy-editable`
    - `UV_LINK_MODE=copy`
- If a hardcoded tokenizer path is missing, an environment-side path mapping or symlink can unblock data processing without changing the script.
  - Record the mapped tokenizer family explicitly in the run log/report.
  - Do not silently treat that as proof that the original model checkpoint path is healthy for downstream training.
- `~/.config/qz/config.toml` must serialize non-bare keys safely.
  - Workspace aliases such as `专项` cannot be emitted as unquoted TOML bare keys.
  - If you generate config programmatically, quote non-ASCII or otherwise non-bare keys, e.g.
    `"专项" = "ws-..."`; otherwise `qz pools` / `qz avail` can fail early with
    `Invalid statement (at line ..., column ...)`.
- Legacy mapping passthrough has an id-shape edge case:
  - `passthrough_if_id_like` handles IDs with prefixes like `ws-...`, `lcg-...`, `project-...`,
    but a pure UUID `spec_id` may still miss the id-like heuristic.
  - For one-off automation configs, the lowest-risk fix is an explicit self-mapping under
    `legacy.mapping_overrides.spec_id`.
- Current `myqz` compatibility gap:
  - `qz job create` may still inject `cpu_elastic_ratio`, which some Qizhi training
    create endpoints now reject with `unknown field "cpu_elastic_ratio"`.
  - The orchestrator now falls back to direct bearer-token
    `POST /openapi/v1/train_job/create` when that exact error appears.
  - For that fallback payload, keep `framework_config[0].spec_id` intact and avoid
    auto-injecting optional defaults such as `enable_slow_detect`, `enable_vccl`,
    `enable_troubleshoot`, `enable_notification`, or `dataset_info` unless the caller
    explicitly requested them.
- 30B A3B torch-dist to HF export resource gotcha:
  - `scripts/convert_qwen_torch_dist_to_hf.py` currently loads the full torch-dist checkpoint
    into a CPU `state_dict` before writing HuggingFace safetensor shards.
  - For Qwen3-30B-A3B checkpoints this can exceed the memory available on the local Codex host;
    an observed `iter_0000271` export was killed with exit code `137` before producing an HF dir.
  - Treat this as an execution-medium/resource blocker first, not immediate checkpoint
    corruption.
  - Prefer a dedicated high-memory `qz job` or `qz notebook` on shared storage for HF export,
    with at least about `120GiB` usable system memory and preferably `150GiB+`.
  - Lowering `--chunk-size` only affects output shard size; it does not reduce the initial
    full-checkpoint load peak.
- Long-context deploy gotcha for SGLang-based CPT services:
  - SGLang defaults to the context length derived from the HF `config.json`.
  - If the serving contract needs a longer window than the HF default, the deploy command must
    pass `--context-length` explicitly.
  - Otherwise online evaluation can fail with API-side `400` errors like
    `The input (...) is longer than the model's context length (32768 tokens)`.
- 30B A3B SFT Megatron runtime gotcha:
  - The standard qizhi Slime image may contain more than one Megatron checkout or Python
    runtime on `PYTHONPATH`.
  - A 30B Thinking SFT run using the old base-SFT wrapper defaulted to `python3` plus
    `/root/Megatron-LM/` and failed during `slime/train_async.py -> parse_args()` with:
    `AttributeError: module 'megatron.training.tokenizer.tokenizer' has no attribute
    'MegatronLegacyTokenizer'`.
  - The working 30B CPT wrapper contract is the safer default for 30B SFT too:
    - `MEGATRON_ROOT=/inspire/hdd/global_public/yanmin/Megatron-main-org`
    - `RUNTIME_PYTHON=/usr/bin/python3`
    - include `${megatron_root}` in both local and Ray runtime `PYTHONPATH`
    - set Ray runtime-env `py_executable` to `${runtime_python}`
  - Before relaunching a failed 30B A3B SFT job, verify the train-submit payload still uses the
    absolute parquet path and the wrapper contains the pinned Megatron/Python runtime contract;
    do not classify this import failure as a data-quality issue or an effective training success.
  - 30B Thinking SFT also needs Thinking-specific RoPE args. The shared
    `qwen3-30B-A3B.sh` model args default to Base `--rotary-base 1000000`, while
    `Qwen3-30B-A3B-Thinking-2507/config.json` has `rope_theta=10000000`.
    If this is not overridden, the job can pass the runtime import phase and then fail in
    `hf_validate_args` with:
    `AssertionError: rope_theta in hf config 10000000 is not equal to rotary_base 1000000`.
    For Thinking SFT wrappers, set `ROTARY_BASE=10000000` or otherwise append
    `--rotary-base 10000000` after sourcing the shared model args.
  - Qizhi outer job status can disagree with the inner Ray training result after checkpoint
    save. In one COD-695 30B Thinking SFT run, worker-0 logged
    `Job 'raysubmit_...' succeeded` and saved `iter_0000035`, while another worker later logged
    a Ray subprocess exit and the platform reported `job_failed`.
    Closeouts must report both surfaces separately:
    - platform status from `qz job status`;
    - worker logs around final `train/loss`, checkpoint save, and `Ray job succeeded`;
    - checkpoint marker and shard count from the output directory.
    Do not call such a run "cleanly completed" unless the platform status and artifact audit both
    support that wording.

## References
- For qz/myqz command mapping and constraints, read `QZ_SKILL.md`
- For `qz` CLI usage/config questions that should be delegated out of this orchestrator, use `qz-guide`
- For WebUI/API capture and browser fallback, use `qz-browser`
- For project-specific `qzx` extraction when workflows repeat, use `qz-customize`
- For QZ browser fallback or internal API RE notes, read `references/frontend_api_patterns.md`
- For QZ platform guardrails and endpoint notes, read `references/qizhi_api_notes.md`
