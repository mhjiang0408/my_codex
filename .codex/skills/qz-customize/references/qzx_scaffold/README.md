# qzx

Project-specific QZ CLI extensions.

## Standard development workflow

Scaffold the package with `uv` and keep a dedicated environment for qzx:

```bash
uv init --package tools/qzx
uv venv tools/qzx/.venv
uv pip install --python tools/qzx/.venv/bin/python -e /path/to/qz
# or:
# uv pip install --python tools/qzx/.venv/bin/python "qz-cli @ git+ssh://git@<host>/<org>/myqz.git@<rev>"
uv pip install --python tools/qzx/.venv/bin/python -e tools/qzx
```

`uv init` creates `.gitignore` with `.venv` ignored. Keep that file so the qzx environment stays local to each checkout.

If the parent project also uses `.venv`, expose qzx there with a shim or symlink:

```bash
uv venv .venv
ln -sf ../../tools/qzx/.venv/bin/qzx .venv/bin/qzx
```

This makes `qzx` callable when the parent project venv is active, while `qzx` and `qz` still import from `tools/qzx/.venv`.

When qzx needs base qz behavior, prefer importing `qz` directly instead of spawning a `qz` subprocess from `PATH`.

## Core modules (included in scaffold)

- **templates.py** — YAML/JSON template loading with inheritance, interpolation, and `--set key=value` overrides.
- **context.py** — Workspace discovery, metadata, and layout management. Supports git worktrees.

## Architecture

qzx follows a **plan/execute** pattern: commands first build a plan dict (inspectable, serializable), then execute it. This enables `--dry-run`, agent inspection, and composition.

All output is JSON to stdout. Progress messages go to stderr (enabled with `--human`).
