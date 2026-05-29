"""Workspace context discovery and layout management.

A *workspace* is either the main repo root or a git worktree created under
``.claude/worktrees/``.  Each workspace has a metadata file
(``.qzx-workspace.json``) and a ``runs/`` directory for state, logs, and assets.

Projects customize ``RUN_ASSET_DIRS`` to add experiment-specific directories
(e.g. tensorboard, wandb, evals).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

WORKSPACE_METADATA_FILENAME = ".qzx-workspace.json"

# Directories under runs/<name>/ managed per run.  Projects should extend
# this tuple for domain-specific assets (tensorboard, wandb, evals, etc.).
RUN_ASSET_DIRS = ("logs", "checkpoints")

# Asset dirs that are only populated on the remote (training) side.  Skip
# local mkdir so agents don't see misleading empty directories.
REMOTE_ONLY_ASSET_DIRS = frozenset({"logs", "checkpoints"})

WORKSPACE_LAYOUT_DIRS = RUN_ASSET_DIRS + ("notes",)


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    workspace_root: Path
    workspace_name: str
    source_root: Path
    metadata_path: Path

    @property
    def is_source_workspace(self) -> bool:
        return self.workspace_root == self.source_root

    @property
    def runs_root(self) -> Path:
        return self.source_root / "runs"

    @property
    def workspace_runs_root(self) -> Path:
        return self.workspace_root / "runs"


def default_repo_root() -> Path:
    try:
        return discover_workspace().source_root
    except FileNotFoundError:
        return Path(__file__).resolve().parents[4]


def default_runs_root(repo_root: Path | None = None) -> Path:
    resolved_repo = Path(repo_root or default_repo_root()).resolve()
    return resolved_repo / ".claude" / "worktrees"


def ensure_workspace_metadata(
    workspace_root: Path,
    *,
    source_root: Path,
    workspace_name: str,
) -> Path:
    metadata_path = workspace_root / WORKSPACE_METADATA_FILENAME
    payload = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_root": str(Path(source_root).resolve()),
        "version": 1,
        "workspace_name": workspace_name,
    }
    metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return metadata_path


def ensure_workspace_layout(workspace_root: Path) -> None:
    runs_root = workspace_runs_root(workspace_root)
    for dirname in WORKSPACE_LAYOUT_DIRS:
        (runs_root / dirname).mkdir(parents=True, exist_ok=True)


def workspace_runs_root(workspace_root: Path) -> Path:
    return Path(workspace_root).resolve() / "runs"


def load_workspace(workspace_root: Path) -> WorkspaceContext:
    root = Path(workspace_root).resolve()
    metadata_path = root / WORKSPACE_METADATA_FILENAME
    if metadata_path.is_file():
        payload = json.loads(metadata_path.read_text())
        source_root = Path(payload["source_root"])
        if not source_root.is_absolute():
            source_root = (root / source_root).resolve()
        workspace_name = str(payload.get("workspace_name") or root.name)
        return WorkspaceContext(
            workspace_root=root,
            workspace_name=workspace_name,
            source_root=source_root.resolve(),
            metadata_path=metadata_path,
        )
    return WorkspaceContext(
        workspace_root=root,
        workspace_name=root.name,
        source_root=root,
        metadata_path=metadata_path,
    )


def discover_workspace(start: Path | None = None) -> WorkspaceContext:
    start_path = Path(start or Path.cwd()).resolve()
    git_root: Path | None = None
    for candidate in (start_path, *start_path.parents):
        metadata_path = candidate / WORKSPACE_METADATA_FILENAME
        if metadata_path.is_file():
            return load_workspace(candidate)
        git_path = candidate / ".git"
        if git_root is None and (git_path.is_dir() or git_path.is_file()):
            git_root = candidate
    if git_root is not None:
        return load_workspace(git_root)
    raise FileNotFoundError(f"could not locate a workspace root above {start_path}")


def resolve_workspace(
    *,
    worktree: str | None = None,
    repo_root: Path | None = None,
    runs_root: Path | None = None,
    start: Path | None = None,
) -> WorkspaceContext:
    if worktree:
        source_root = Path(repo_root or default_repo_root()).resolve()
        resolved_runs_root = Path(runs_root or default_runs_root(source_root)).resolve()
        workspace_root = resolved_runs_root / worktree
        if not workspace_root.exists():
            raise FileNotFoundError(f"worktree does not exist: {workspace_root}")
        return load_workspace(workspace_root)
    if repo_root is not None and start is None:
        return load_workspace(Path(repo_root).resolve())
    return discover_workspace(start)
