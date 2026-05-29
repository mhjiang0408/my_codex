# Images

Docker Hub images cannot be used directly on the QZ platform — all images must be in the QZ platform registry.

## Commands

```
qz image list [--scope personal|public|official] [--mine] [--raw]
qz image search QUERY [--scope all|official|private|public] [--workspace ALIAS] [--mine] [--raw]
qz image create --name NAME --version V [--workspace ALIAS] [--visibility private|public]
qz image push LOCAL_IMAGE [--name NAME] [--version V] [--workspace ALIAS]
qz image delete IMAGE_ID [--workspace ALIAS]
qz image sync IMAGE_SPEC --workspace ALIAS
qz image preheat IMAGE_SPEC --pool ALIAS
```

## Key operations

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

## Workflow: custom image

1. Start a notebook with a base image.
2. Install your dependencies inside it.
3. Save the image with `qz notebook save-image`.
4. Use the saved image for future jobs/notebooks.
5. Alternatively, push a local image from your machine with `qz image push`.
