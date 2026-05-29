# Deployments

## Commands

```
qz deploy create --name NAME [--pool ALIAS] [--type TYPE] --image IMG [--gpus N] --command CMD [--port N] [--url-prefix PREFIX] [--replicas N]
qz deploy list [--workspace ALIAS] [--mine] [--raw]
qz deploy status DEPLOYMENT_NAME [--raw]
qz deploy start DEPLOYMENT_NAME
qz deploy stop DEPLOYMENT_NAME
qz deploy wait DEPLOYMENT_NAME
qz deploy delete DEPLOYMENT_NAME
qz deploy scale DEPLOYMENT_NAME REPLICAS
qz deploy logs DEPLOYMENT_NAME [--replica N] [--worker N] [--instance POD] [--lines N] [--follow] [--text] [--raw]
qz deploy url DEPLOYMENT_NAME
qz deploy update DEPLOYMENT_NAME [--command CMD] [--image IMG] [--gpus N] [--url-prefix PREFIX] [--replicas N]
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

# Get API key for authenticated access
qz deploy api-key list
```

## Name resolution

Deployment names and deployment IDs are interchangeable in all commands. If you pass a name, qz resolves it to the most recent deployment with that name.

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
  - while `/health` is not healthy yet, the deployment stays in `DEPLOYING`
  - once `/health` responds healthy, the deployment transitions to `RUNNING`
  - make sure your server exposes `/health`, or the deployment may never become ready

## URL prefix

- `--url-prefix PREFIX` sets the deployment URL subdomain prefix (`custom_domain` in the platform API).
- If omitted, QZ auto-generates a random prefix for the public URL.
- `qz deploy update DEPLOYMENT_NAME --url-prefix PREFIX` changes the prefix later.

## Pool selection

- `--pool` is optional. If omitted, deployment creation auto-selects a pool from the requested type.
- Prefer `--type` over `--pool`; use `--pool` only when you need to pin an exact pool.
- `--type` defaults to `[defaults].default_pool_type`, falling back to `h200`.
- `--gpus N` is required for single-node deployments.
- If `replicas * nodes-per-replica > 1`, `--gpus` becomes optional and defaults to `8`.
- Full-node deployment requests (`--gpus 8` or multi-node deploys) use full-node availability; partial-node deploys (`--gpus < 8`) use aggregate GPU availability.
- If `--type` is unknown, qz exits with an error listing configured types.

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

## Scaling

`qz deploy scale DEPLOYMENT_NAME REPLICAS` changes the replica count. Scale to 0 to pause the deployment without deleting it. Scale back up when needed.

```bash
qz deploy scale llm-serve 3    # scale up
qz deploy scale llm-serve 0    # pause (no GPUs consumed)
```

## Updating

`qz deploy update` modifies a deployment in place. You can change the command, image, GPU count, or replica count. The deployment restarts with the new configuration.

```bash
qz deploy update llm-serve --image new-vllm-image --gpus 2
```

## API keys

Deployments are accessed through a reverse proxy that requires an API key.

```bash
# List all API keys
qz deploy api-key list

# Show a specific key's value
qz deploy api-key show KEY_ID
```

Use the API key in the `Authorization: Bearer <key>` header when calling the deployment URL.

## Defaults

Default values for port, replicas, and priority come from the `[deploy]` section in config.toml. See [config.md](config.md).
