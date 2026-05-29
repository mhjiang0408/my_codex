---
name: qz-customize
description: "Create project-specific qzx CLI extensions on top of qz. Use this skill when the user wants to add project-specific sync, worktrees, workspaces, job templates, or run workflows. Trigger on mentions of 'qzx', 'customize qz', 'project-specific commands', 'job templates', 'sync setup', or when a user wants to extend the qz CLI for their particular project needs. Also trigger proactively when you notice the agent (yourself or a subagent) repeatedly executing the same multi-step qz sequences in a project — e.g. sync+create+wait+logs, or always passing the same --pool/--image/--exclude flags. This is a signal that a qzx wrapper would save tokens and reduce errors."
---

## Overview

qzx is the pattern for project-specific CLI extensions built on top of qz. Philosophy: **code is configuration** -- qzx imports qz as an SDK, no config file DSL needed.

qzx lives in `tools/qzx/` within the user's project, is installable via `uv pip install -e tools/qzx`, and provides a `qzx` console entry point.

## Companion Skill Contract

- This skill may be invoked by another skill when a QZ workflow stops being one-off and should be captured as reusable project-specific `qzx` commands or templates.
- Use it for:
  - repeated multi-step QZ sequences
  - stable project defaults that should stop being retyped
  - reusable job templates or workflow wrappers
  - project-specific sync/worktree/workspace/run helpers
- Parent skills should pass:
  - the repeated sequence that is worth extracting
  - what inputs are fixed vs variable
  - the relevant project paths and runtime assumptions
  - the desired output contract for the new `qzx` command
- This skill should return:
  - the `qzx` scaffold/design/implementation path
  - the exact reusable commands or modules to add
  - any assumptions the caller must preserve when invoking the new wrapper
- Do not use this skill for one-off `qz` syntax questions; that belongs to `qz-guide`.
- Do not use this skill for WebUI/API reverse engineering; that belongs to `qz-browser`.

## qz SDK Surface

Functions available for qzx authors:

| Module | Function | Purpose |
|--------|----------|---------|
| `qz.api` | `build_job_payload(...)` | Build job creation payload from pool config |
| `qz.api` | `create_job(payload)` | Submit job to QZ |
| `qz.api` | `get_job_detail(job_id)` | Get job status |
| `qz.api` | `stop_job(job_id)` | Stop a job |
| `qz.api` | `job_logs(job_id, page_size)` | Fetch container logs |
| `qz.api` | `exec_command(job_id, cmd)` | Execute command in running job via WebSocket |
| `qz.avail` | `resolve_pool(alias, nodes, pool_type)` | Resolve pool from alias or auto-select |
| `qz.avail` | `select_pool(nodes, type)` | Auto-select best available pool |
| `qz.config` | `get_pool(alias)` | Get pool config by alias |
| `qz.config` | `get_pools(type)` | List pools, optionally filtered by type |
| `qz.config` | `get_defaults()` | Get default job settings |
| `qz.config` | `get_sync_config()` | Get [sync] config section |
| `qz.output` | `json_out(data)` | Print JSON to stdout |
| `qz.output` | `error_exit(msg)` | Print JSON error and exit 1 |

## Routing Based on User Request

Route based on what the user asks for:

### `scaffold` (or no specific args)

Read the reference scaffold at `references/qzx_scaffold/` and create a basic delegating qzx in `tools/qzx/` within the user's project. The scaffold includes a `pyproject.toml` with a console entry point and a minimal CLI that delegates to qz.

After scaffolding, ask the user what capabilities they want to add (sync, worktrees, job templates, etc.).

### `add-sync`

Read `references/sync_ref.py` first. Then ask the user about:

- Local project directory structure (what directories exist, which matter)
- Remote paths on the cluster (where their project lives on GPFS)
- What to exclude from sync (data dirs, checkpoints, venvs, etc.)

Implement a sync module in their qzx that wraps rsync with project-specific paths and exclusions.

### `add-worktree`

Read `references/worktree_ref.py` first. Then ask the user about:

- Remote host and project paths on the cluster
- Shared vs isolated venvs (does each worktree get its own, or share one?)
- Symlink targets (data directories, model weights, shared caches that should be symlinked into the worktree)

Implement a worktree module that manages GPFS git worktrees via SSH.

### `add-workspace`

Read `references/workspace_ideas.md` first. This is a design document, not tested code. Be upfront about this with the user.

Discuss the workspace concept with the user -- help them think through:

- What long-running compute they need (Ray head, Jupyter, dev containers)
- How they want to interact with it (exec commands, port forwarding, attach)
- Whether they need workspace lifecycle management

Implement only if the user wants to proceed after understanding the design.

### `add-job-template`

Read `references/job_templates_ref.py` first. Then ask the user about:

- What experiments or jobs they run repeatedly
- What parameters vary between runs (learning rate, model size, dataset, etc.)
- What pool types they target (GPU count, memory requirements)

Implement a TEMPLATES dict and a `qzx run TEMPLATE [--overrides]` command.

### `add-run`

Read `references/run_ref.py` first. Implement an all-in-one command that combines:

1. sync push (get code to cluster)
2. job create (from template or inline command)
3. job wait --start (block until running or terminal failure)
4. tail logs (stream output back)

This is the "one command to rule them all" for experiment launching.

## Key Points

- Always read the relevant reference file before implementing. The references are in this skill's `references/` directory.
- The reference files contain placeholders (paths, project names, pool aliases). Ask the user for their specific values before writing code.
- `workspace_ideas.md` describes a concept, not a tested implementation. Be explicit about this maturity difference.
- qzx is a proper installable Python package with `pyproject.toml` and a console entry point -- not a loose script.
- Each qzx project is unique. Adapt reference code to the user's specific project structure and needs; do not copy verbatim.
- All qzx commands should follow the same output contract as qz: JSON to stdout, errors as `{"error": "..."}` + exit 1.
