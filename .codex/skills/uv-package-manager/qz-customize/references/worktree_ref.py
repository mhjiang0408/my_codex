"""Reference: SSH-managed GPFS git worktree lifecycle on cluster.

This is a reference implementation for qzx projects that need isolated
git worktrees on a shared filesystem (GPFS) accessed via SSH.

Adapt REMOTE_HOST, GPFS_AG, and project paths to match your layout.

Usage from qzx CLI:
    qzx worktree create NAME [--isolated-venv]
    qzx worktree list
    qzx worktree verify NAME
    qzx worktree destroy NAME
"""

import subprocess
import sys

from qz.output import json_out, error_exit

# === CUSTOMIZE THESE ===

REMOTE_HOST = "qz-cpu"       # SSH host alias
GPFS_AG = "$HOME/project"    # Base path on cluster
MAIN_REPO = f"{GPFS_AG}/main-repo"
SHARED_VENV = "$HOME/venvs/main"
SHARED_DATA = f"{MAIN_REPO}/data"

# === IMPLEMENTATION ===


def _ssh(command: str, *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", REMOTE_HOST, command],
        capture_output=True, text=True, check=check,
    )


def _ssh_output(command: str) -> str:
    result = _ssh(command, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def create(name: str, *, isolated_venv: bool = False) -> dict:
    """Create a worktree on GPFS with proper symlinks and directory structure.

    Creates:
      <GPFS_AG>/main-repo-runs/<name>/  (git worktree)
      <GPFS_AG>/main-repo-runs/<name>/.venv → shared or isolated venv
      <GPFS_AG>/main-repo-runs/<name>/data → <MAIN_REPO>/data
      <GPFS_AG>/main-repo-runs/<name>/logs/
      <GPFS_AG>/main-repo-runs/<name>/checkpoints/
    """
    wt_path = f"{GPFS_AG}/main-repo-runs/{name}"

    # Check if already exists as git worktree
    check = _ssh(f'test -d "{wt_path}/.git" || test -f "{wt_path}/.git"', check=False)
    is_git_wt = check.returncode == 0
    dir_exists = _ssh(f'test -d "{wt_path}"', check=False).returncode == 0

    if is_git_wt:
        print(f"Worktree '{name}' already exists, ensuring setup...", file=sys.stderr)
    elif dir_exists:
        print(f"Directory exists (from sync), setting up worktree...", file=sys.stderr)
    else:
        r = _ssh(
            f'cd {MAIN_REPO} && git worktree add "{wt_path}" -b "wt-{name}" HEAD',
            check=False,
        )
        if r.returncode != 0:
            err = r.stderr.strip()
            if "already exists" in err:
                r = _ssh(
                    f'cd {MAIN_REPO} && git worktree add "{wt_path}" HEAD --detach',
                    check=False,
                )
                if r.returncode != 0:
                    return {"error": f"git worktree add failed: {r.stderr.strip()}"}
            else:
                return {"error": f"git worktree add failed: {err}"}

    # Determine venv target
    if isolated_venv:
        venv_target = f"$HOME/venvs/main-{name}"
        r = _ssh(f'test -d "{venv_target}"', check=False)
        if r.returncode != 0:
            print(f"Creating isolated venv: {venv_target}...", file=sys.stderr)
            r = _ssh(f'cp -a {SHARED_VENV} "{venv_target}"', check=False)
            if r.returncode != 0:
                return {"error": f"venv copy failed: {r.stderr.strip()}"}
    else:
        venv_target = SHARED_VENV

    # Ensure directories and symlinks (idempotent)
    commands = [
        f'mkdir -p "{wt_path}/logs" "{wt_path}/checkpoints"',
        f'rm -rf "{wt_path}/.venv" && ln -sn {venv_target} "{wt_path}/.venv"',
        f'rm -rf "{wt_path}/data" && ln -sn {SHARED_DATA} "{wt_path}/data"',
    ]

    for cmd in commands:
        result = _ssh(cmd, check=False)
        if result.returncode != 0:
            return {"error": f"command failed: {cmd}\n{result.stderr.strip()}"}

    return {
        "name": name,
        "path": wt_path,
        "venv": f"{wt_path}/.venv -> {venv_target}",
        "data": f"{wt_path}/data -> {SHARED_DATA}",
    }


def list_worktrees() -> dict:
    wts = _ssh_output(f'ls -1 {GPFS_AG}/main-repo-runs/ 2>/dev/null || true')
    names = [n for n in wts.split("\n") if n] if wts else []
    return {"worktrees": [{"name": n} for n in sorted(names)]}


def verify(name: str) -> dict:
    wt_path = f"{GPFS_AG}/main-repo-runs/{name}"
    checks = {}

    r = _ssh(f'test -d "{wt_path}"', check=False)
    checks["worktree_exists"] = r.returncode == 0
    if not checks["worktree_exists"]:
        return {"name": name, "checks": checks, "ok": False}

    r = _ssh(f'test -L "{wt_path}/.venv"', check=False)
    checks["venv_is_symlink"] = r.returncode == 0
    checks["venv_target"] = _ssh_output(f'readlink "{wt_path}/.venv"')

    r = _ssh(f'test -d "{wt_path}/.venv/bin"', check=False)
    checks["venv_valid"] = r.returncode == 0

    for d in ["logs", "checkpoints"]:
        r = _ssh(f'test -d "{wt_path}/{d}"', check=False)
        checks[f"{d}_exists"] = r.returncode == 0

    all_ok = all(v for k, v in checks.items() if isinstance(v, bool))
    return {"name": name, "checks": checks, "ok": all_ok}


def destroy(name: str) -> dict:
    wt_path = f"{GPFS_AG}/main-repo-runs/{name}"

    r = _ssh(f'test -d "{wt_path}"', check=False)
    if r.returncode != 0:
        return {"error": f"worktree '{name}' not found"}

    r = _ssh(f'cd {MAIN_REPO} && git worktree remove "{wt_path}" --force', check=False)
    if r.returncode != 0:
        _ssh(f'rm -rf "{wt_path}"', check=False)
        _ssh(f'cd {MAIN_REPO} && git worktree prune', check=False)

    _ssh(f'cd {MAIN_REPO} && git branch -D "wt-{name}" 2>/dev/null || true', check=False)
    return {"name": name, "removed": True}
