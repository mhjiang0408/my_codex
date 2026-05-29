# Workspace Concept: Persistent Compute Environment

A "workspace" is a long-lived compute environment on the QZ platform, typically
backed by a training job that runs `sleep infinity` (or a Ray cluster + sleep).

## Why Workspaces?

QZ jobs are designed to run a command and exit. For iterative development,
debugging, or multi-step agent tasks, you want persistent compute:

- Start once, use many times
- Run commands interactively via `qz job exec` (WebSocket terminal)
- Keep state between commands (installed packages, running processes)

## Implementation Pattern

A workspace is just a QZ training job with a special entrypoint:

```python
# In your qzx CLI:
from qz import api, config, avail
from qz.output import json_out, error_exit

def cmd_workspace_start(name, pool_alias, nodes=1):
    pool = config.get_pool(pool_alias)
    payload = api.build_job_payload(
        name=f"ws-{name}",
        command=WORKSPACE_COMMAND,  # see below
        pool=pool,
        nodes=nodes,
    )
    result = api.create_job(payload)
    # Save state locally (job_id, name, etc.)
    save_workspace_state(name, result)
```

## Entrypoint Ideas

### Minimal: Just sleep
```bash
sleep infinity
```
Use `qz job exec JOB_ID "command"` to run commands.

### Ray Cluster
```bash
# Head node starts Ray + sleeps; workers join
if [ "$NODE_RANK" -eq 0 ]; then
    ray start --head --num-gpus 8
else
    ray start --address "$MASTER_ADDR:6379" --num-gpus 8
fi
sleep infinity
```

### With Dashboard Access via Model Deployment

**Idea (not implemented):** Use QZ's model deployment feature to expose a port
(e.g., Ray dashboard on 8265). Model deployments get a public URL with HTTPS,
which could serve as a convenient way to access services running inside the
workspace without SSH tunneling.

This would require:
1. Create a deployment with the same image
2. Set the command to forward traffic to the workspace job's pod
3. Use the deployment URL as the dashboard access point

This approach hasn't been tested but could be an elegant alternative to
SSH tunnels or Jupyter proxy workarounds.

## Local State Management

Track workspace state in `~/.cache/qz/workspaces/`:

```python
import json
from pathlib import Path
from qz import config

WORKSPACES_DIR = config.CACHE_DIR / "workspaces"

def save_workspace_state(name: str, state: dict):
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    state["name"] = name
    (WORKSPACES_DIR / f"{name}.json").write_text(json.dumps(state, indent=2))

def load_workspace_state(name: str) -> dict | None:
    path = WORKSPACES_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None
```

## Commands to Implement

- `qzx workspace start --name NAME [--pool ALIAS] [--nodes N]`
- `qzx workspace stop [NAME]`
- `qzx workspace status [NAME]`
- `qzx workspace exec COMMAND [-w NAME]`
- `qzx workspace wait [NAME]`
- `qzx workspace gc` — clean up state for dead workspaces
