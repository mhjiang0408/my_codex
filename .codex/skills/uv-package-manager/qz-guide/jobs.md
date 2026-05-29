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

## Distributed startup scripts

For multi-node jobs, QZ runs the startup or entrypoint script on every allocated node.

- The startup script is interpreted by `sh`, not `bash`. Use POSIX shell syntax in examples and real scripts unless you explicitly re-exec into `bash`.
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

Availability is ranked by capacity first; config file order only matters as a tiebreaker between otherwise-equal pools.

## Wait flags

- Without `--start`, `qz job wait` blocks until the job reaches a terminal state: `job_succeeded`, `job_failed`, or `job_stopped`.
- `--start` exits once the job reaches `job_running`; if the job fails or stops before that, wait returns the terminal state instead.
- `--interval S` controls polling interval (default 30s).
- `--timeout S` sets a hard timeout; wait exits non-zero if exceeded.

## Current CLI compatibility notes

- On the qz CLI currently installed in this workspace, `qz job wait --start` may be unavailable even though older docs list it. If it errors, use `qz job status`, `qz job logs`, `qz job events`, and optionally `qz job metrics` instead of retrying the same wait command.
- `qz job status --raw` is the strongest source for node and GPU shape (`node_count`, `gpu_count`, `framework_config[].instance_count`), while the curated status is the easiest source for human-readable `running`/`queued` state.
- `qz job logs ... --text` and some worker-specific log calls can occasionally emit a JSON parse error such as `Expecting value: line 1 column 1 (char 0)` even when the job is healthy. Cross-check with other workers, `qz job status --raw`, `qz job metrics`, and the training output directory before treating that as a training failure.
- For StepTron jobs that write shared GPFS logs, the output directory can be more authoritative than the qz log proxy once torchrun starts. Inspect `logs/<experiment>/log_*.txt`, `logs/torchrun/**/{stdout,stderr}.log`, and `checkpoints/` alongside qz status.

## Queue vs Unschedulable Interpretation

- Do not treat `qz job status ... -> job_queuing` plus `qz avail --type h200 --nodes <N>` as proof that a gang job is close to starting.
- When a long-queued job has no logs and no resource-prepared transition, check `qz job events JOB_ID`.
- If events repeatedly show warnings such as `Unschedulable`, `Insufficient cpu`, `Insufficient memory`, or `node(s) didn't match Pod's node affinity/selector`, report the state as queueing with active scheduler unschedulable warnings rather than as clean queueing.
- `qz job create --help` in this workspace currently exposes per-node resource flags:
  - `--cpu` default `168`
  - `--mem` default `1800` GiB
  - `--shm-size` default `80%` of memory
  - `--cpu-burst` default `2`
- If `qz job events` repeatedly reports `Insufficient cpu`, the default `168` CPU request can be the placement blocker even when GPU capacity checks are inconclusive.
- A recovery submit may lower `--cpu` and, if needed, `--mem`/`--shm-size` while preserving the model, data, node count, GPU count, command, image, and output isolation.
- Treat such a recovery as a resource-request contract change for experiment tracking: document the rationale, use an independent output directory, and do not launch it as an unrecorded duplicate.

## Logs

- `qz job logs JOB_NAME` targets worker `0` by default instead of aggregating every pod.
- `--worker N` selects one worker by index; `--instance POD_NAME` selects an exact pod name.
- `--lines N` reads the most recent N lines for the selected worker.
- `--follow` / `--watch --text` polls for new lines from the selected worker.
- `--text` gives plain-text logs (one line per entry), suitable for piping to grep.
- `--raw` returns the backend log payload for the selected worker.

## Metrics

- `-m TYPES` selects metric types (comma-separated). Available types depend on the cluster.
- `--series` returns time-series data instead of latest-value summaries.
- `--text` gives a human-readable table to stderr, JSON to stdout.

## Events

`qz job events JOB_NAME` returns the job's event timeline (queued, scheduled, started, etc.) as a JSON array. Useful for debugging scheduling delays.
