# Notebooks

## Commands

```
qz notebook create --name NAME --image IMG [--pool ALIAS] [--type TYPE] [--gpus N] [--cpu N] [--mem N] [--shm-size N]
qz notebook list [--workspace ALIAS] [--raw]
qz notebook status NOTEBOOK_NAME [--raw]
qz notebook start NOTEBOOK_NAME
qz notebook stop NOTEBOOK_NAME
qz notebook wait NOTEBOOK_NAME
qz notebook url NOTEBOOK_NAME
qz notebook delete NOTEBOOK_NAME
qz notebook exec NOTEBOOK_NAME "command" [--timeout N]
qz notebook tunnel NOTEBOOK_NAME
qz notebook save-image NOTEBOOK_NAME --name IMAGE_NAME [--version V] [--visibility public]
```

## Lifecycle

```bash
# Create a notebook with a QZ platform image (search for available images first)
qz image search ubuntu
qz notebook create --name dev --image ubuntu-22.04-cu128:v1
qz notebook create --name dev-gpu --image ubuntu-22.04-cu128:v1 --type h200 --gpus 1 --shm-size 48

# Wait until running
qz notebook wait dev

# Execute commands inside
qz notebook exec dev "pip install torch"

# Get Jupyter URL for browser access
qz notebook url dev

# Save the configured environment as a reusable image
qz notebook save-image dev --name my-env --version v1 -d "My custom environment with PyTorch"

# Stop when done (container state is discarded)
qz notebook stop dev

# Delete permanently
qz notebook delete dev
```

## Name resolution

Notebook names and notebook IDs are interchangeable in all commands. If you pass a name, qz resolves it to the most recent notebook with that name.

## Pool selection

- `--pool` is optional. If omitted, notebook creation auto-selects a pool from the requested type.
- Prefer `--type` over `--pool`; use `--pool` only when you need to pin an exact pool.
- `--type` defaults to `[notebook].default_pool_type` from config, usually `cpu`.
- `--gpus N` enables GPU notebooks and selects a GPU pool of that type.
- For GPU notebooks, qz also resolves the matching notebook quota/resource spec and fills the final CPU and memory values from the platform schedule when available.
- `--shm-size N` sets `shared_memory_size` in GiB. If omitted, qz defaults it to 80% of the final notebook memory after quota/resource resolution.
- If `--type` is unknown, qz exits with an error listing configured types.

## Exec

`qz notebook exec` runs a command inside the running notebook container via WebSocket. The command runs synchronously and returns stdout/stderr as JSON.

- `--timeout N` sets a timeout in seconds for the command (default varies).
- The notebook must be in RUNNING state. Run `qz notebook wait` first.

## Tunnel

`qz notebook tunnel NOTEBOOK_NAME` sets up an SSH tunnel via rtunnel, giving you direct SSH access to the notebook container. Useful for file transfer or port forwarding.

## Save image

`qz notebook save-image` snapshots the current notebook container state into a new image.

```bash
qz notebook save-image dev --name my-custom-env --version v2
qz notebook save-image dev --name shared-env --visibility public
```

- `--version V` tags the image version (default: auto-generated).
- `--visibility public` makes the image visible to all users (default: private).
- The notebook must be running when you save.

## Image management

Images are managed with the `qz image` subcommand. Docker Hub images cannot be used directly — all images must be in the QZ platform registry.

```
qz image list [--scope personal|public|official] [--mine] [--raw]
qz image search QUERY [--scope all|official|private|public] [--workspace ALIAS] [--mine] [--raw]
qz image create --name NAME --version V [--workspace ALIAS] [--visibility private|public]
qz image push LOCAL_IMAGE [--name NAME] [--version V] [--workspace ALIAS]
qz image delete IMAGE_ID [--workspace ALIAS]
qz image sync IMAGE_SPEC --workspace ALIAS
qz image preheat IMAGE_SPEC --pool ALIAS
```

### Key operations

- `search` finds images available in the job/notebook create-form picker. Use this to discover base images on the platform:
  ```bash
  qz image search ubuntu --workspace gpu     # find Ubuntu-based images
  qz image search cu128 --scope official      # find official CUDA images
  qz image search "" --mine                   # list all your own images
  ```
- `list` shows images in the management view. `--mine` filters to your images.
- `push` registers an image record and pushes a local Docker image to the QZ registry (via docker push or skopeo fallback).
- `sync` copies an image to another pool's registry. Required when using an image on a different cluster/datacenter.
- `preheat` pulls the image to pool nodes ahead of time, reducing job/notebook startup latency.

### Workflow: custom image

1. Start a notebook with a base image.
2. Install your dependencies inside it.
3. Save the image with `qz notebook save-image`.
4. Use the saved image for future jobs/notebooks.
5. Alternatively, push a local image from your machine with `qz image push`.
