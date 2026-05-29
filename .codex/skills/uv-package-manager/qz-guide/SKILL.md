---
name: qz-guide
description: "Usage guide for the qz CLI (QZ/启智 HPC platform). Use this skill when the user asks how to use qz commands, wants workflow examples, or needs help with jobs, notebooks, deployments, images, sync, pools, or config. Trigger on mentions of 'qz', 'QZ platform', '启智', or any qz subcommand like 'qz job', 'qz notebook', etc."
---

# qz CLI Usage Guide

`qz` is a minimal CLI for the QZ (启智) platform, a HPC platform based on k8s and shared GPFS storage but only exposes HTTPS APIs to users. It provides job management, notebook lifecycle, model deployment, sync, and pool availability.

## Companion Skill Contract

- This skill may be invoked by another skill that already owns the main workflow but needs authoritative `qz` CLI/config guidance for one subproblem.
- Use it for:
  - exact `qz` command syntax
  - config semantics
  - pool/type selection rules
  - `qzcli` -> `qz` command mapping
- Parent skills should pass:
  - the parent skill or workflow name
  - the current step that is blocked
  - any known workspace/pool/type constraints
  - the command family in question
- This skill should return:
  - exact `qz` commands and flags
  - assumptions that the parent must preserve
  - any config or resource-selection constraints that affect the parent workflow
- Route away when:
  - the CLI cannot do the task or IDs must be recovered from WebUI/API traffic -> use `qz-browser`
  - the sequence should become reusable project tooling rather than one-off guidance -> use `qz-customize`

## Output contract

- All commands emit a single JSON object or array to stdout.
- Errors: `{"error": "..."}` + exit 1. Always check exit code before parsing.
- Use `--raw` where available for full API response; default output is curated.
- `--text` flag on log/metrics commands gives plain-text instead of JSON.

## Topic index

| Topic | File | Covers |
|-------|------|--------|
| Jobs | [jobs.md](jobs.md) | create, wait, logs, metrics, stop, events |
| Notebooks | [notebooks.md](notebooks.md) | create, exec, tunnel, save-image |
| Images | [images.md](images.md) | list, search, create, push, delete, sync, preheat |
| Deployments | [deployments.md](deployments.md) | create, scale, url, api-key, logs |
| Sync | [sync.md](sync.md) | rsync wrapper for cluster file transfer |
| Config | [config.md](config.md) | config.toml, env vars, pools, auth, defaults |
| Offline GPU | [offline-gpu.md](offline-gpu.md) | internal mirrors, HF/wandb/pip cache, GPFS download pattern |

## When to use what

- **Running training / batch compute**: Use `qz job`. Create a job with a command, wait for it, check logs.
- **Interactive development / installing packages**: Use `qz notebook`. Create a notebook, exec commands inside, save the image when done if needed.
- **Serving a model for inference**: Use `qz deploy`. Create a deployment with a port and command, get the URL, use API keys for access.
- **Transferring files to/from cluster**: Use `qz sync`. Wrap rsync with config-based remote host expansion.
- **Finding available compute**: Use `qz avail --type h200 --nodes 1` or `--nodes 2` for whole-node checks, or `qz avail --type h200 --gpus 1` for partial-node GPU checks. Prefer `--type` over `--pool`; qz can auto-select a matching pool for jobs, notebooks, and deployments.
- **Finding/managing container images**: Use `qz image search` to find images on the QZ platform (Docker Hub images cannot be used directly — images must be in the QZ registry). Use `qz notebook save-image` to snapshot a configured notebook into a reusable image.
