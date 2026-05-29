# Deployments

## Commands

```
qz deploy create --name NAME [--pool ALIAS] [--type TYPE] [--image IMG] [--image-type T] [--gpus N] [--cpu N] [--mem N] --command CMD [--port N] [--url-prefix PREFIX] [--replicas N] [--nodes-per-replica N]
qz deploy list [--workspace ALIAS] [--type TYPE] [--mine] [--raw]
qz deploy status DEPLOYMENT_NAME [--verbose] [--raw]
qz deploy metrics DEPLOYMENT_NAME [-m TYPES] [--series] [--text] [--raw] [--run-index N] [--version N]
qz deploy start DEPLOYMENT_NAME
qz deploy stop DEPLOYMENT_NAME [--no-wait] [--interval S] [--timeout S]
qz deploy wait DEPLOYMENT_NAME [--until STATUS|terminal] [--interval S] [--timeout S]
qz deploy delete DEPLOYMENT_NAME [--force] [--interval S] [--timeout S]
qz deploy scale DEPLOYMENT_NAME REPLICAS
qz deploy logs DEPLOYMENT_NAME [--replica N] [--worker N] [--instance POD] [--lines N] [--follow] [--text] [--raw]
qz deploy url DEPLOYMENT_NAME
qz deploy update DEPLOYMENT_NAME [--command CMD] [--image IMG] [--gpus N] [--cpu N] [--mem N] [--url-prefix PREFIX] [--replicas N]
qz deploy api-key list
qz deploy api-key show KEY_ID
```

## Workflow: deploy a model

```bash
# Find an image with vLLM pre-installed
qz image search vllm --workspace gpu

# Create the deployment (typed auto-select defaults to [defaults].default_pool_type or h200)
qz deploy create \
  --name llm-serve \
  --image vllm-cu128:v1 \
  --gpus 8 \
  --url-prefix llm-serve \
  --command "python -m vllm.entrypoints.openai.api_server --model /models/my-model --port \${PORT}"

# Wait until running
qz deploy wait llm-serve

# Get the serving URL
qz deploy url llm-serve

# Check logs for startup errors
qz deploy logs llm-serve --replica 0 --worker 0 --lines 50 --text

# Inspect resource usage history
qz deploy metrics llm-serve --text

# Get API key for authenticated access
qz deploy api-key list
```

## Image Spec Gotcha

- `qz deploy create --image` resolves the platform image picker spec, not necessarily the
  registry-style mirror address returned inside an existing deployment's raw `mirror.address`.
- Prefer either:
  - the exact `image` value from `qz image search ...`, such as
    `torch2.7.1-vllm0.10.0-sglang0.4.9.post6-lmdeploy-0.9.2-cuda128-py312:0.1.4`
  - or the image id, such as `image-3dc64148-300a-4f0d-8a11-f0b0dd68cc54`.
- Do not blindly pass an existing raw mirror address like
  `inspire-studio/torch2.7.1-vllm0.10.0-sglang0.4.9.post6-lmdeploy-0.9.2-cuda128-py312:0.1.4`;
  it can fail with `Image ... not found` even when the same image exists in the picker.

## Name resolution

Deployment names and deployment IDs are interchangeable in all commands. If you pass a name, qz resolves it to the most recent deployment with that name.

List and status output still keep `deployment_id` because deployment names can collide.

Create, list, and status paths refresh the deployment name cache when the backend returns both the name and ID, so looking up a deployment by raw `sv-...` ID also repairs the cache for later name-based commands.

## Name retention gotcha

- Stopping a deployment does **not** free its deployment name on this platform.
- If you stop a deployment and then try to `create` a new deployment with the same name, the platform can still reject the create with:
  - `QZError('模型部署的名字已经存在')`
- Practical implication:
  - for same-name pool migrations or same-name full recreates, use:
    - `qz deploy stop <deployment-id-or-name>`
    - `qz deploy delete <deployment-id-or-name>`
    - then a fresh `qz deploy create ...`
- Using the raw deployment id for the delete step is safer than name-based resolution when multiple historical deployments share the same name.

## Status

- Default `qz deploy status` keeps the common health fields: status, replicas, ready replicas, workspace, pool, and URL.
- Add `--verbose` to include command, port, image/model info, timestamps, version, nodes-per-replica, priority, and resource summary.
- Add `--raw` to keep the full platform detail payload instead of the translated qz summary.
- During placement waits, prefer direct `qz deploy status <id> --verbose`, `qz deploy instances <id>`, and `qz deploy events <id>` over an exited external orchestrator state. A monitor process can fail on one transient `qz deploy status --raw`/detail call while the platform deployment remains `pending`.
- If direct deployment status remains `pending`, instances are `INSTANCE_PENDING` with no node, and events only show LeaderWorkerSet pending, classify the blocker as placement/capacity unless logs/events show a runtime, image, startup, or health-check error.
- Do not treat stale backend fields such as `extra_info.available_replicas` from a broad `qz deploy list --raw` result as readiness evidence. A stopped deployment can still show old availability counts there. For live benchmark launches, require `qz deploy status <id> --verbose` with normalized `status=running` and `ready_replicas > 0`, then probe the serving endpoint such as `/v1/models`.

Default status values are normalized qz terms such as `running`, `stopped`, `failed`, and `deploying`, even though the backend may use different strings in some endpoints. `--raw` keeps the original platform payload.

## Runtime behavior

- QZ injects these environment variables into deployment containers:
  - `${PORT}` - the serving port from the deployment command. The port used in your actual model server must match this value.
  - `${LWS_GROUP_SIZE}` - number of instances in the multi-instance group.
  - `${LWS_WORKER_INDEX}` - instance index within the group, starting from `0`.
  - `${LWS_LEADER_ADDRESS}` - address of instance `0` in a multi-instance group.
- Always pass `${PORT}` through to the server you start inside `--command`:

```bash
qz deploy create \
  --name api \
  --image vllm:v1 \
  --command 'python serve.py --port ${PORT}'
```

- For multi-instance deployments, use `${LWS_WORKER_INDEX}` to branch leader/worker behavior and `${LWS_LEADER_ADDRESS}` for worker-to-leader discovery.
- Container fault tolerance includes up to 5 automatic restarts on failure.
- Deployment readiness is determined by `GET /health`:
  - while `/health` is not healthy yet, the deployment stays in `deploying`
  - once `/health` responds healthy, the deployment transitions to `running`
  - make sure your server exposes `/health`, or the deployment may never become ready

## URL prefix

- `--url-prefix PREFIX` sets the deployment URL subdomain prefix.
- If omitted, QZ auto-generates a random prefix for the public URL.
- `qz deploy update DEPLOYMENT_NAME --url-prefix PREFIX` changes the prefix later.
- The platform rule for the custom subdomain prefix is `^[a-z]([a-z0-9-]*[a-z])?$`:
  - it must start with a lowercase letter
  - it may contain lowercase letters, digits, and hyphens in the middle
  - it must end with a lowercase letter
- Practical implication: explicit prefixes that end in digits, such as `...step50`, are rejected by the platform with `{"error":"自定义域名不满足格式要求"}`.
- If you want a stable explicit prefix for a step-tagged deployment, rewrite it to end with a letter, or omit `--url-prefix` and let QZ auto-generate one.

## Project ID Gotcha

- The deployment create API requires a non-empty `project_id` in the payload.
- In the current qz CLI implementation, `deploy create` does not expose a `--project-id` flag.
- The CLI therefore relies on `[deploy].project_id` or `[account].project_id` in `config.toml`; if both are missing, it silently builds `project_id=""`.
- On this platform, that empty `project_id` can surface as a generic create-time failure like `{"error":"数据库错误, 请联系管理员"}` instead of a clean validation message.
- Practical implication:
  - for scripted deploy flows, either set `[deploy].project_id` / `[account].project_id` explicitly in qz config
  - or bypass the CLI create path and call the serving create API with an explicit `project_id`
- Known-good example from the current workspace:
  - `project_id=project-3cc580f0-7528-47d3-8456-ed6994854373`
- If a create still fails with the same generic database error after image resolution succeeds,
  retry with an explicit `--model-id` and `--model-version` from a known-good existing deployment
  instead of relying on workspace auto-detection.

## Pool selection

- `--pool` is optional. If omitted, deployment creation auto-selects a pool from the requested type.
- Prefer `--type` over `--pool`; use `--pool` only when you need to pin an exact pool.
- If you pass both `--pool` and `--type`, qz rejects mismatches instead of silently ignoring `--type`.
- `--type` defaults to `[deploy].default_pool_type`, then `[defaults].default_pool_type`, then `h200`.
- `--gpus N` is optional. Defaults: `[deploy].default_gpus` (8) on GPU pools, `0` on cpu pools.
- **`--gpus 0` is valid on every pool, including GPU pools.** Pods get whatever cpu/mem you ask for via `--cpu`/`--mem`. The platform doesn't validate the rsp shape against any per-lcg whitelist.
- Full-node deployment requests (`--gpus 8` or multi-node deploys) use full-node availability; partial-node deploys (`--gpus < 8`) use aggregate GPU availability; `--gpus 0` skips GPU availability entirely.
- If `--type` is unknown, qz exits with an error listing configured types.

## Resource sizing (`--cpu` / `--mem` / `--gpus`)

- `--cpu N` and `--mem N` set per-replica CPU cores and memory GiB. Defaults branch on the requested gpu shape:
  - When `effective_gpus > 0`: GPU defaults from `[deploy].default_cpu` (168) / `default_mem` (1800).
  - When `effective_gpus == 0` (any pool): cpu defaults from `[deploy].cpu_default_cpu` (16) / `cpu_default_mem` (64).
- The platform honors arbitrary cpu/mem values — they aren't validated against any quota whitelist. Whatever you pass shows up in the container's cgroup.
- The `quota_id` in the stored deployment is synthesized as `c{cpu}m{mem}g{gpus}t` so the WebUI label stays meaningful.

## Listing

- Without `--type`, `qz deploy list` stays workspace-scoped and defaults to `[deploy].default_workspace`.
- `--type TYPE` filters deployments to pools of that type.
- If `--workspace` is omitted and `--type` is provided, qz queries every configured workspace that has a pool of that type and merges the results client-side.

## Wait and Stop

- `qz deploy wait` accepts `--until STATUS|terminal`. Valid normalized statuses are `pending`, `deploying`, `running`, `stopping`, `stopped`, and `failed`.
- The default wait target is `running`.
- `qz deploy stop` waits for `stopped` by default. Pass `--no-wait` to only request the stop.
- `--interval S` and `--timeout S` work the same on both commands.

## Delete

- Deleting a non-terminal deployment now fails fast with a guided error.
- Use `qz deploy stop NAME` for the explicit two-step flow.
- Use `qz deploy delete NAME --force` to stop and delete in one command.

## Replica topology

- `--replicas` is horizontal scale: how many serving copies sit behind one deployment URL.
- `--nodes-per-replica` is vertical/distributed scale: how many nodes each replica spans.
- Total nodes reserved = `replicas * nodes-per-replica`.
- For `nodes-per-replica > 1`, the platform creates one `LEADER` plus worker nodes for each replica.
- The public proxy/load balancer targets replica leaders; worker nodes stay internal to the replica group.
- Load balancing happens across leaders, not across worker nodes.

## Logs

- `qz deploy logs DEPLOYMENT_NAME` targets replica `0`, worker `0` by default.
- `--replica N` chooses the replica group; `--worker N` chooses a worker inside that replica.
- Worker `0` is the replica `LEADER`; worker `1+` maps to `WORKER` instances from `instances/list`.
- `--instance POD_NAME` selects an exact pod name when you already know it.
- `--lines N` reads the most recent N lines for the selected instance.
- `--follow` / `--watch --text` polls for new lines from the selected instance.
- `--text` prints only the raw log message text for each entry, with no timestamp or pod/worker prefix.
- The current CLI supports `--raw` on `qz deploy status`, but not on `qz deploy instances` or
  `qz deploy events`.
  - `qz deploy instances --help` only accepts one positional `serving_id`.
  - `qz deploy events --help` only accepts one positional `serving_id`.
  - Passing `--raw` to either subcommand currently fails with
    `qz: error: unrecognized arguments: --raw`.
  - Practical implication: for deployment triage, use default JSON output from
    `qz deploy instances <id>` / `qz deploy events <id>`, and reserve `--raw` for
    `qz deploy status`.

## Metrics

`qz deploy metrics` uses the same normalized output and flags as `qz job metrics`, but keyed by `deployment_id`.

- Default metric types are `gpu_usage_rate,gpu_memory_usage_rate`.
- Deployments may resolve to backend task type `inference_serving` or `inference_serving_customize`; qz hides that mismatch unless you ask for `--raw`.
- `--run-index N` selects a specific deployment run with zero-based indexing; `--run-index -1` (default) means the latest run.
- qz derives deployment run history from `/api/v1/inference_servings/events/list`, then translates the selected run to the metric `start`/`end` window while still querying metrics by stable `inference_serving_id`.
- `--version N` is an optional zero-based deployment version index filter/selector. When runs exist for that version index, qz picks the latest matching run by default; if that version has never been started, qz falls back to the version window from `/api/v1/inference_servings/{id}/versions`.
- JSON output usually includes `selection: {kind: "run", run_index: N, version: V}` for deployment runs, where both `run_index` and `version` use the same zero-based CLI indexes accepted by the flags. If qz has to fall back to pure version history, it returns `selection: {kind: "version", version: V}`.
- `--series` includes sampled points in JSON output.
- `--text` prints a readable summary instead of JSON.

## Scaling

`qz deploy scale DEPLOYMENT_NAME REPLICAS` changes the replica count. Scale to 0 to pause the deployment without deleting it. Scale back up when needed.

- Throughput correction rule for this workspace:
  - when a live deployment only needs more serving throughput, prefer `qz deploy scale` over `stop -> create` or full recreate
  - increasing replicas does not require shutting the service down first
  - in current benchmark workflows, bounded live scale-up into `4..8` replicas is the preferred first response when the endpoint is too slow

```bash
qz deploy scale llm-serve 3    # scale up
qz deploy scale llm-serve 0    # pause (no GPUs consumed)
```

## Updating

`qz deploy update` modifies a deployment in place. You can change the command, image, cpu/mem/gpu count, or replica count. The deployment restarts with the new configuration.

```bash
qz deploy update llm-serve --image new-vllm-image --gpus 2
qz deploy update llm-serve --cpu 32 --mem 128         # right-size without changing GPUs
qz deploy update llm-serve --gpus 0 --cpu 8 --mem 16  # downgrade to cpu-only
```

When any of `--gpus` / `--cpu` / `--mem` is set, the deployment's `resource_spec_price` is rebuilt from the merged values. The pool itself can't be changed via update.

## API keys

Deployments are accessed through a reverse proxy that requires an API key.

```bash
# List all API keys
qz deploy api-key list

# Show a specific key's value
qz deploy api-key show KEY_ID
```

Use the API key in the `Authorization: Bearer <key>` header when calling the deployment URL.

- Readiness-probe correction for this workspace:
  - a deployment can be `RUNNING` and still return `401 Unauthorized` to anonymous
    `/v1/models` or `/v1/chat/completions` requests.
  - Do not treat that anonymous `401` as deployment breakage by itself.
  - First retry the same OpenAI-compatible probe with a deploy API key in the bearer header; if
    the authenticated probe returns `200` and the served model is present, the endpoint is healthy
    for benchmark smoke purposes.

## Defaults

`[deploy]` section in `config.toml` (see [config.md](config.md)):

| Key | Purpose | Fallback |
|-----|---------|----------|
| `default_workspace` | Default workspace alias for `qz deploy list` | (none) |
| `default_pool_type` | Pool type for auto-select | `[defaults].default_pool_type` → `h200` |
| `default_image` | Image spec when `--image` is omitted | (none, must pass `--image`) |
| `default_image_type` | Image type | `SOURCE_OFFICIAL` |
| `default_port` | Container port | `8000` |
| `default_priority` | Task priority | `10` |
| `default_replicas` | Replica count | `1` |
| `default_nodes_per_replica` | Nodes per replica | `1` |
| `default_gpus` | GPU count when `--gpus` omitted on a GPU pool | `8` |
| `default_cpu` | CPU cores when serving with `gpus > 0` | `168` |
| `default_mem` | Memory GiB when serving with `gpus > 0` | `1800` |
| `cpu_default_cpu` | CPU cores when serving with `gpus == 0` | `16` |
| `cpu_default_mem` | Memory GiB when serving with `gpus == 0` | `64` |
