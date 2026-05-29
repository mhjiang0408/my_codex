---
name: develop-with-qzx
description: "Workflow guide for developing with qzx — worktrees, sync, launch, and run patterns for agents. Install this as a skill in your project's .claude/skills/ directory."
---

# Develop with qzx

This skill teaches agents the qzx workflow for running experiments on the QZ HPC platform.

## Core concepts

- **Workspace**: Either the main repo root or a git worktree under `.claude/worktrees/`. Each workspace has independent code but shares run state and data.
- **Run**: A tracked experiment with a state file (`runs/state/<id>.json`), asset directories, and a QZ job backend.
- **Template**: YAML job spec with platform config, env vars, and command — supports inheritance and `{placeholder}` interpolation.
- **Plan/execute**: All commands build an inspectable plan dict first, then execute. Use `--dry-run` to see the plan without acting.

## Workflow patterns

### 1. Worktree workflow (parallel experiments)

```bash
# Create a worktree for an experiment branch.
qzx worktree create ablation-lr --venv

# Work in the worktree.
cd .claude/worktrees/ablation-lr
# ... edit code ...

# Sync to remote and launch.
qzx run experiment-1 --note "lr=1e-4 baseline" --template train-8gpu

# Back in main, run a different experiment concurrently.
cd ../../..
qzx run experiment-2 --note "lr=3e-4 comparison" --template train-8gpu

# Check status across all workspaces.
qzx status --all
```

### 2. Quick launch (no worktree)

```bash
# From the repo root — sync + launch + wait in one command.
qzx run my-run --note "quick test" --template train-8gpu \
  --set platform.nodes=1 --wait --tail-logs

# Or build the plan and submit separately.
qzx launch my-run --note "manual control" --template train-8gpu --dry-run
qzx launch my-run --note "manual control" --template train-8gpu
```

### 3. Sync-only

```bash
# Preview what will sync.
qzx sync
# Execute the sync.
qzx sync --execute
# Sync a specific worktree.
qzx sync --worktree ablation-lr --execute
```

### 4. Monitoring

```bash
# List recent runs (featured: running, <24h old, or >15min runtime).
qzx status
# All runs, full detail.
qzx status --all --full
# Specific run by name.
qzx status experiment-1

# Wait for a run to reach a state.
qzx wait run --name experiment-1 --until terminal
qzx wait run --name experiment-1 --until running --timeout 300
```

### 5. Cleanup

```bash
# Stop a run's backend job.
qzx cleanup --name experiment-1
```

### 6. Worktree lifecycle

```bash
# List all worktrees.
qzx worktree list
# Health-check a worktree.
qzx worktree verify ablation-lr
# Remove local + remote worktree.
qzx worktree destroy ablation-lr --remote
```

## Template authoring

Templates live in `templates/qzx/` (preferred) or `templates/` in the repo root.

```yaml
# templates/qzx/base.yaml
platform:
  pool_type: h200
  nodes: 1
env:
  PYTHONUNBUFFERED: "1"
command:
  - python
  - train.py
```

```yaml
# templates/qzx/large.yaml
inherits: base.yaml
platform:
  nodes: 4
env:
  WANDB_RUN_NAME: "{name}-large"
```

Override at launch time: `qzx run test --template large --set platform.nodes=8 --set env.LR=1e-4`

## Agent integration notes

- All qzx output is JSON to stdout. Parse it; don't regex.
- Use `--dry-run` to inspect plans before executing.
- Use `--human` to get stderr progress messages (useful for interactive sessions).
- Use `--full` to bypass default summarization when you need the raw state dict for debugging.
- `qzx run` is the high-level command (sync + launch + wait + logs). Use `qzx launch` and `qzx sync` separately when you need finer control.
- Check exit codes: `qzx wait` exits 2 if the run failed, 0 otherwise.
- Run state files persist across sessions. Use `qzx status` to find previous runs.
- Worktrees under `.claude/worktrees/` integrate with Claude Code's agent worktree patterns.

## Workspace invariants

These are load-bearing — the launcher, sync, and status commands assume them.

- **Source repo `runs/` is canonical.** Worktrees expose run assets through symlinks, not copies. Write paths resolve back to the source repo.
- **Run state files are program-maintained.** Do not hand-edit `runs/state/<run_id>.json`; use `qzx` commands.
- **`run_id` = unique name.** No timestamp prefix. Timestamps live in `created_at` and the `runs/sorted/<ts>_<name>/` browsing index.
- **Shared data lives under `runs/data/`** in the source repo (not per-worktree).
- **Artifact roots are flat**: `runs/tensorboard/<name>`, `runs/wandb/<name>`, `runs/logs/<name>`, `runs/checkpoints/<name>`.
- **Run notes are human-editable** at `runs/notes/<name>.txt`; the sorted dir exposes them as `note.txt` symlinks.

## Escape hatch to raw `qz`

qzx is a thin orchestration layer over `qz`. If a qzx subcommand fails unexpectedly or doesn't expose what you need, fall back to the raw `qz` binary — use the `$qz-guide` skill for its command reference. Common cases: one-off image/notebook operations, debugging auth, inspecting pool availability.

## Defense against flaky platform services

- **Persist pod logs to files.** Live QZ service logs can randomly drop output. The launcher tees container logs to a shared-disk file so `qzx exec` / `exec-py` can read them after the fact regardless of log stream health.
- **Emit bootstrap artifacts immediately.** Write a zero-step tensorboard event and a wandb offline init at job start so inspection tooling works before the long run produces real metrics.
- **Separate infra noise from regressions.** A transient 2-node hang that clears on rerun is acceptable cluster behavior, not a launcher bug. Rerun with the same name (qzx auto-suffixes `-2`, `-3`) instead of adding retry logic.

## Directory layout

```
project/
├── .claude/worktrees/           # git worktrees (one per experiment)
│   └── ablation-lr/
│       ├── .git                 # git worktree marker
│       ├── .qzx-workspace.json  # workspace metadata
│       └── runs/                # symlinks to source runs/
├── runs/
│   ├── state/                   # run state files (*.json)
│   ├── sorted/                  # timestamped run dirs with symlinks
│   ├── scripts/                 # entrypoint scripts per run
│   ├── notes/                   # run notes
│   ├── logs/<name>/             # run logs
│   ├── checkpoints/<name>/      # model checkpoints
│   └── data/                    # shared data (symlinked into worktrees)
├── templates/qzx/               # job templates
└── tools/qzx/                   # qzx package
```
