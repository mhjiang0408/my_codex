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

## Files
- Orchestrator entry:
  - `scripts/orchestrate.py`
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

- Routing rule:
  - Use `qz-guide` instead of re-documenting generic `qz` command semantics in this skill.
  - Use `qz-browser` instead of reviving direct frontend replay logic inside this skill.
  - Use `qz-customize` when the task stops being one-off orchestration and should become reusable project automation.

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

- Agentic CPT composed-rollout normalization rule:
  - when the training source is `data/train/dataset/<date>/composed_rollouts`, normalize raw rollout JSON into compact agentic conversations before any downstream token counting
  - keep only two top-level keys: `messages` and `tools`
  - for each message, keep only `role` and string `content`
  - assistant `tool_calls` must be serialized back into `content`; drop transport-only message fields such as `timestamp`, `tool_call_id`, and message-level `tool_calls`
  - real composed-rollout dumps may include empty `messages` lists
  - filter those records out during the normalization/load step itself
  - do not pass empty conversations into legacy token-count or `apply_chat_template(...)` paths, or the run can fail before chunking with an index error on `conversation[0]`
- COD-556 fixed-stage chunking correction:
  - do not describe chunking as a train-time automatic fallback for Thinking SFT long-tail failures
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
- `automation_config.qz` must supply enough pool metadata to honor the frozen selection rule:
  - `workspace_keyword`
  - optional `pool_allowlist`
  - ordered `type_preference`

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
  - `qz pools`
  - `qz avail --type h200 --nodes 1`
- `qz` config must define pool aliases for the target `专项` workspace in `~/.config/qz/config.toml` or the configured `QZ_CONFIG_DIR`.
- `qz pools` is the preferred manual inspection command before orchestration because it exposes `pool/type/workspace_id/lcg_id`, which is the metadata used to lock workspace before type ranking.

## Pool / Type Selection Policy
- User correction is now part of the skill contract:
  - do not add or emulate `usage`
  - use `qz avail` for all capacity and monitoring snapshots
  - use `pool` to lock the target workspace first, then use `type` to filter or rank candidate pools
- Candidate discovery should use configured qz pools, not `qzcli` resource caches.
- Expected selection flow:
  - inspect configured pools from `qz pools` / qz config and resolve pools whose workspace matches `workspace_keyword=专项`
  - apply optional `pool_allowlist`
  - apply `type_preference` in order
  - call `qz avail` for the selected type
  - filter the returned entries back to the candidate pool alias
  - choose the best pool using `tier` first, then room preference, then free-node capacity
- `qz avail` does not currently accept `--pool`; filtering by pool alias is the orchestrator's responsibility.

## Monitoring Policy
- Precheck before `train_submit` / `deploy_submit`:
  - use `qz avail --type <selected_type> --nodes <required_nodes>`
  - capacity decision is based on the selected pool entry only
- Monitor during `train_monitor` / `deploy_monitor`:
  - periodically run `qz avail` again for the selected `type`
  - record only capacity-related snapshots and warnings
  - do not claim workspace-wide task count or GPU-in-use metrics
  - do not introduce a separate `usage` collector or `usage_snapshot` event family
- Polling status compatibility remains:
  - handle `job_failed` / deploy failure states
  - allow the existing `accept_failed_if_runtime_minutes` training compatibility rule
- If the training entrypoint spends extra time on `wandb sync`, HF export, or upload cleanup, `qz job status` may remain in a running-like state after the core training compute is done. In that case prefer shared logs such as `train.log` / `orchestrator.log`.
- Expected `events.jsonl` families after migration:
  - `qz_command_result`
  - `qz_login_refresh_*`
  - `qz_avail_snapshot`
  - `qz_capacity_warning`
  - `qz_monitor_error`

## HF Wait Before Deploy
- `deploy.hf_wait` is enabled by default
- before `deploy_submit`, poll for `_hf` output readiness
- default directory regex: `^iter_(\d+)_hf$`
- default readiness files:
  - `config.json`
  - `generation_config.json`
- default selection policy: `latest_ready`
- default behavior rewrites `_hf` path in `bash_command`
- default timeout is infinite (`timeout_seconds: 0`)

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

## References
- For qz/myqz command mapping and constraints, read `QZ_SKILL.md`
- For `qz` CLI usage/config questions that should be delegated out of this orchestrator, use `qz-guide`
- For WebUI/API capture and browser fallback, use `qz-browser`
- For project-specific `qzx` extraction when workflows repeat, use `qz-customize`
- For QZ browser fallback or internal API RE notes, read `references/frontend_api_patterns.md`
- For QZ platform guardrails and endpoint notes, read `references/qizhi_api_notes.md`
