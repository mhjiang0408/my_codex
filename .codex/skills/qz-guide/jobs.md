# Jobs

## Commands

```
qz job create --name NAME --command CMD [--pool ALIAS] [--type TYPE] [--nodes N] [--image IMG]
qz job status JOB_NAME [--raw]
qz job list [--pool ALIAS] [--limit N] [--raw]
qz job logs JOB_NAME [--worker N | --instance POD] [--lines N] [--follow] [--text] [--raw]
qz job wait JOB_NAME [--start] [--interval S] [--timeout S]
qz job stop JOB_NAME
qz job events JOB_NAME
qz job metrics JOB_NAME [-m TYPES] [--series] [--text] [--raw]
```

## Canonical workflow

```bash
# 1. Create a job (typed auto-select defaults to [defaults].default_pool_type or h200)
qz job create --name grpo-train --command "bash scripts/train.sh" --type h200 --nodes 2

# 2. Wait for it to start running (or fail before startup)
qz job wait grpo-train --start

# 3. Tail logs
qz job logs grpo-train --worker 0 --lines 100 --text

# 4. Check GPU utilization
qz job metrics grpo-train --text

# 5. Stop when done
qz job stop grpo-train
```

Use `qz job wait` instead of polling `qz job status` in a shell loop. By default it waits for completion; add `--start` when you want to continue as soon as the job is running. The wait command exits non-zero if the terminal state is a failure.

## Project-id safety rule

- In this workspace, do not assume the current qz account context points at the right project.
- If `qz job create` fails with `您已离开所选项目，无法创建`, retry with an explicit `--project-id`.
- The currently known-good project id for `Q项目-科学认知基础模型` is:
  - `project-3cc580f0-7528-47d3-8456-ed6994854373`

## Image safety rule

- In this workspace, do not rely on short official image names like:
  - `slime:20250812-v2`
- Even with `--image-type SOURCE_OFFICIAL`, the platform can retain the short name and later pull it as:
  - `docker.io/library/slime:20250812-v2`
- The safe pattern for the standard Slime training image is to pass the full registry path explicitly:
  - `--image docker.sii.shaipower.online/inspire-studio/slime:20250812-v2`
  - `--image-type SOURCE_OFFICIAL`
- After create, check `qz job status <job> --raw`:
  - if `framework_config[].image` is still only `slime:20250812-v2`, treat the submit as invalid and expect `ErrImagePull` / `ImagePullBackOff`.

## Distributed startup scripts

For multi-node jobs, QZ runs the startup or entrypoint script on every allocated node.

- The startup script is interpreted by `sh`, not `bash`. Use POSIX shell syntax in examples and real scripts unless you explicitly re-exec into `bash`.
- Because the startup command is interpreted by `sh`, avoid `set -o pipefail` or `set -euo pipefail` in direct `qz job create --command` strings. Use POSIX `set -eu`, or explicitly run `bash -lc 'set -euo pipefail; ...'` when bash-specific behavior is required.
- QZ exposes these environment variables to every job container:
  - `PET_MASTER_ADDR` - master node hostname. Resolve it with `getent hosts` before use; DNS can lag briefly at startup.
  - `PET_NNODES` - total node count.
  - `PET_NODE_RANK` - current node rank. `0` is the master node.
- Common fallback pattern:

```sh
export MASTER_ADDR="${PET_MASTER_ADDR:-${MASTER_ADDR:-127.0.0.1}}"
export NUM_NODES="${PET_NNODES:-${NUM_NODES:-1}}"
export NODE_RANK="${PET_NODE_RANK:-${NODE_RANK:-0}}"
```

- Common master-IP resolution loop:

```sh
while :; do
  MASTER_IP=$(getent hosts "$MASTER_ADDR" | awk '{print $1}' || true)
  if [ -n "$MASTER_IP" ]; then
    MASTER_ADDR="$MASTER_IP"
    break
  fi
  sleep 1
done
```

- Job lifetime follows the per-node entrypoint scripts:
  - the overall job ends as soon as any worker entrypoint exits
  - the job is marked succeeded only if every node entrypoint returns `0`
  - do not let helper or worker scripts daemonize and exit immediately unless that is intentionally how you want the whole job to finish

## Name resolution

Job names and job IDs are interchangeable in all commands. If you pass a name, qz resolves it to the most recent job with that name.

## Auto pool selection

When `--pool` is omitted, qz auto-selects a pool from the requested type and current availability:

- Prefer `--type` over `--pool`; use `--pool` only when you need to pin an exact pool.
- `--type` filters to configured pool types such as `h200`, `h100`, `4090`, `cpu`, `cpu-xl`, or `hpc`.
- If `--type` is omitted, `qz job create` defaults to `[defaults].default_pool_type`, falling back to `h200`.
- `qz job create` uses whole-node availability for any `--nodes N` request, including `--nodes 1`, since job creation always requests full 8-GPU nodes.
- Partial-node GPU selection only applies to GPU-count workflows such as notebooks or single-node deployments with `--gpus < 8`.
- If the type does not exist in config, qz exits with an error listing the configured types.
- Retry policy note for this workspace:
  - once a single-node H200 run has already been used as a proof or blocker-finding run, do not assume the next retry should stay on `--nodes 1`
  - if the user says to start retries from `8 nodes / 64 GPUs`, freeze that as the next relaunch default and reflect it directly in `qz job create --nodes 8`

Availability is ranked by capacity first; config file order only matters as a tiebreaker between otherwise-equal pools.

## Wait flags

- Without `--start`, `qz job wait` blocks until the job reaches a terminal state: `job_succeeded`, `job_failed`, or `job_stopped`.
- `--start` exits once the job reaches `job_running`; if the job fails or stops before that, wait returns the terminal state instead.
- `--interval S` controls polling interval (default 30s).
- `--timeout S` sets a hard timeout; wait exits non-zero if exceeded.

## Current CLI compatibility notes

- On the qz CLI currently installed in this workspace, `qz job wait --start` may be unavailable even though older docs list it. If it errors, use `qz job status`, `qz job logs`, `qz job events`, and optionally `qz job metrics` instead of retrying the same wait command.
- When filtering qz JSON with Python, do not combine a pipeline with `python3 - <<'PY'`; the heredoc supplies the Python program on stdin, so `json.load(sys.stdin)` cannot read the qz output. Use `python3 -c '...'` for short filters or a real script file for longer filters.
- `qz job status --raw` is the strongest source for node and GPU shape (`node_count`, `gpu_count`, `framework_config[].instance_count`), while the curated status is the easiest source for human-readable `running`/`queued` state.
- `qz job logs ... --text` and some worker-specific log calls can occasionally emit a JSON parse error such as `Expecting value: line 1 column 1 (char 0)` even when the job is healthy. Cross-check with other workers, `qz job status --raw`, `qz job metrics`, and the training output directory before treating that as a training failure.
- For StepTron jobs that write shared GPFS logs, the output directory can be more authoritative than the qz log proxy once torchrun starts. Inspect `logs/<experiment>/log_*.txt`, `logs/torchrun/**/{stdout,stderr}.log`, and `checkpoints/` alongside qz status.
- For StepTron SFT jobs, a terminal `succeeded` qz status is not enough to prove a meaningful
  train run occurred. Check the output logs for `Will train for N iters`, at least one
  `training_log` line, and checkpoint directories such as `checkpoints/<experiment>/it*`; some
  successful jobs can report `Will train for 0 iters` or only save `it1`.

## Logs

- `qz job logs JOB_NAME` targets worker `0` by default instead of aggregating every pod.
- `--worker N` selects one worker by index; `--instance POD_NAME` selects an exact pod name.
- `--lines N` reads the most recent N lines for the selected worker.
- `--follow` / `--watch --text` polls for new lines from the selected worker.
- `--text` gives plain-text logs (one line per entry), suitable for piping to grep.
- `--raw` returns the backend log payload for the selected worker.

## W&B offline-run audit notes

- For follow-up questions about whether a repaired/fresh job synced W&B, do not reuse an older
  audit conclusion from pre-fix runs. Start from the fresh job id or job name, inspect the exact
  qz command and logs, and identify the qz-log-authoritative `wandb sync <offline-run-dir>` path.
- A W&B offline directory containing `run-<id>.wandb.synced` is local evidence that the specific
  offline run was synced/marked synced. Record the marker path and mtime.
- Distributed Ray jobs may create multiple same-run-id offline directories, including auxiliary
  `ray/_private/workers/default_worker.py` directories. Treat the offline path printed by the
  training/qz log as the authoritative training run path, and report unsynced auxiliary
  directories separately instead of collapsing them into "the run was not synced".

## Metrics

- `-m TYPES` selects metric types (comma-separated). Available types depend on the cluster.
- `--series` returns time-series data instead of latest-value summaries.
- `--text` gives a human-readable table to stderr, JSON to stdout.

## Events

`qz job events JOB_NAME` returns the job's event timeline (queued, scheduled, started, etc.) as a JSON array. Useful for debugging scheduling delays.

## Queue vs Unschedulable Interpretation

- Do not treat `qz job status ... -> job_queuing` plus `qz avail --type h200 --nodes <N>` showing
  `low_pri_nodes >= N` as proof that an H200 gang job is about to start.
- In this workspace, `low_pri_nodes` is only evidence of potential preemption candidates.
  It does not guarantee the scheduler can place the full gang immediately.
- When a long-queued job still has no logs and no resource-prepared transition, check
  `qz job events JOB_ID` before deciding whether the wait is "normal queueing."
- If events repeatedly show warnings such as:
  - `Unschedulable`
  - `Insufficient cpu`
  - `Insufficient memory`
  - `node(s) didn't match Pod's node affinity/selector`
  then report the state as:
  - queueing with active scheduler unschedulable warnings
  rather than as a clean queue-only wait.
- Practical reporting rule:
  - `qz avail` is candidate discovery
  - `qz job events` is the stronger source for whether the scheduler is actually close to starting the job
- Create-flag boundary rule:
  - `qz job create --help` in this workspace exposes pool/type/resource/priority/project/keep-alive knobs, but no explicit queue-expedite or "preempt-now" flag.
  - Once the currently strongest pool candidates are already submitted, do not churn the queue just because the CLI might have a hidden acceleration flag; first confirm such a capability really exists.
  - If the live candidate ranking still says the active pair already covers the strongest available pools, prefer keeping that pair and monitoring for a real phase change over speculative resubmits.
- Priority-field interpretation rule:
  - On job detail/list payloads in this workspace, prefer `priority_name` and `priority_level` as the user-facing priority signal.
  - `myqz` create paths send project priority levels such as `10`, but returned job payloads may still show `task_priority: 0` alongside:
    - `priority_name: "10"`
    - `priority_level: "HIGH"`
    - `priority: 35`
  - Do not interpret that returned `task_priority: 0` alone as evidence that the job was submitted at a low priority or that there is still a safe higher priority knob available through the normal CLI surface.
- Resource-request recovery rule:
  - `qz job create --help` in this workspace currently exposes per-node resource flags:
    - `--cpu` default `168`
    - `--mem` default `1800` GiB
    - `--shm-size` default `80%` of memory
    - `--cpu-burst` default `2`
  - If a queued gang job has no logs and `qz job events` repeatedly reports `Insufficient cpu`, the default `168` CPU request can be the placement blocker even when GPU capacity checks are inconclusive.
  - A recovery submit may lower `--cpu` and, if needed, `--mem`/`--shm-size` while preserving the model, data, node count, GPU count, command, image, and output isolation.
  - Treat such a recovery as a resource-request contract change for experiment tracking: document the rationale, use an independent output directory, and do not launch it as an unrecorded duplicate.
