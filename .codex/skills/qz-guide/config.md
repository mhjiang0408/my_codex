# Config

## Files

| File | Purpose |
|------|---------|
| `~/.config/qz/config.toml` | All configuration: pools, defaults, sync, deploy, notebook settings |
| `~/.cache/qz/auth.json` | Auth cache (token + cookie). Managed by `qz login`. Do not edit manually. |

## Environment variables

Credentials are never stored in config files. Set these in your shell:

| Variable | Purpose |
|----------|---------|
| `QZ_API_USERNAME` | Username for Bearer token auth (OpenAPI) |
| `QZ_API_PASSWORD` | Password for Bearer token auth |
| `QZ_COOKIE_USERNAME` | Username for CAS cookie auth (internal API) |
| `QZ_COOKIE_PASSWORD` | Password for CAS cookie auth |

## Config sections

### Pools

```toml
[pools.h200]
type = "h200"
workspace_id = "ws-..."
logic_compute_group_id = "lcg-..."
spec_id = "..."

[pools.h100]
type = "h100"
workspace_id = "ws-..."
logic_compute_group_id = "lcg-..."
spec_id = "..."

[pools.cpu]
type = "cpu"
workspace_id = "ws-..."
logic_compute_group_id = "lcg-..."
spec_id = "..."
```

Prefer `--type` over `--pool` in normal usage. When `--pool` is omitted, qz ranks matching pools by current availability. File order is only a tiebreaker when pools have the same ranking.

### Defaults

```toml
[defaults]
image = "docker.sii.shaipower.online/inspire-studio/cu128-base:v1"
image_type = "SOURCE_PUBLIC"
default_pool_type = "h200"
priority = 10
project_id = "project-..."
```

### Account

```toml
[account]
project_id = "..."
```

### Workspaces

```toml
[workspaces]
main = "workspace-id-1"
dev = "workspace-id-2"
```

Maps short aliases to workspace IDs. Used by `--workspace ALIAS` flags.

### Notebook defaults

```toml
[notebook]
default_pool_type = "cpu"
default_cpu = 2
default_mem = 8
default_workspace = "cpu"
```

### Deploy defaults

```toml
[deploy]
default_workspace = "gpu"
default_port = 8000
default_replicas = 1
default_priority = 10
```

### Sync

```toml
[sync]
remote_host = "qz-cpu"
remote_prefix = "~/project"
```

See [sync.md](sync.md) for details.

## Auth commands

```bash
# Refresh both token and cookie
qz login

# Debug mode (verbose CAS flow to stderr)
qz login -v

# Run auth daemon (refreshes proactively every hour)
qz login -d
```

## Pool commands

```bash
# List configured pools
qz pools

# Show availability (pick either --nodes or --gpus)
qz avail [--nodes N] [--gpus N] [--type TYPE]
```

- Current CLI gotcha: `qz config pools` is not a valid subcommand in this workspace. Use
  `qz pools` for configured pool aliases.
- Current CLI gotcha: `qz avail` rejects commands that pass both `--nodes` and `--gpus`.
  Use exactly one sizing mode per command.
- `qz avail --type h200 --nodes 1` or `--nodes 2` shows which pools can fit whole-node requests using free-node counts.
- `qz avail --type h200 --gpus 1` shows which pools have enough aggregate free GPUs for a partial-node workload.
- `qz avail --type h200 --gpus 8` also uses whole-node availability because it is a full-node request.
- Capacity probe instability gotcha:
  - For full-node H200 scans, `qz avail --type h200 --nodes N` calls the node-dimension API for every configured matching pool. A slow pool or backend pressure can make the whole command time out even when deployment status queries still work.
  - If a full scan times out while monitoring an existing deployment, do not reinterpret that as either "no capacity" or "deployment failed". Keep `qz deploy status/instances/events` as the deployment source of truth.
  - For diagnostics, split probes by pool or use aggregate-only inspection from `qz.avail._gpu_aggregate_pool_availability` to identify obvious shortages. Treat aggregate output as advisory only because it does not prove full-node schedulability.
  - Backend `Error 1040: Too many connections` from capacity APIs means the capacity snapshot is inconclusive for that pool, not a usable availability signal.
- If `--type` is omitted on `qz avail`, `qz job create`, or `qz deploy create`, qz uses `[defaults].default_pool_type`, falling back to `h200`.
- If `TYPE` is not present in config, qz prints an error that includes the available configured types.
