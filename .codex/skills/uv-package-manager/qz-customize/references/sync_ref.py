"""Reference: multi-project rsync sync with excludes and worktree support.

This is a reference implementation for qzx projects that need structured
multi-project sync with excludes, worktree paths, and parallel push.

Adapt LOCAL_BASE, REMOTE_BASE, REMOTE_HOST, PROJECTS, and EXCLUDES
to match your project layout.

Usage from qzx CLI:
    qzx sync push [--worktree NAME] [--project rllm,r2e-gym]
    qzx sync pull-logs [--worktree NAME]
    qzx sync push-path PATH
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from qz.output import json_out, error_exit

# === CUSTOMIZE THESE ===

LOCAL_BASE = Path.home() / "Projects" / "MyOrg" / "MyProject"
REMOTE_BASE = "~/project"
REMOTE_HOST = "qz-cpu"  # SSH host alias from ~/.ssh/config

# Project definitions: (local_dir, remote_dir, worktree_pattern)
PROJECTS = {
    "main-repo": {
        "local": "main-repo",
        "remote": "main-repo",
        "worktree_remote": "main-repo-runs/{name}",
    },
    # Add more projects here:
    # "dep-repo": {
    #     "local": "DependencyRepo",
    #     "remote": "DependencyRepo",
    #     "worktree_remote": "DependencyRepo-runs/{name}",
    # },
}

DEFAULT_PROJECTS = ["main-repo"]

EXCLUDES = [
    ".git/",
    ".venv",
    "__pycache__/",
    "*.pyc",
    "checkpoints/",
    "*.pt",
    "*.safetensors",
    "*.parquet",
    "wandb/",
    "*.egg-info/",
    "logs/",
]

LOG_DIRS = ["main-repo/logs"]
MAX_LOG_SIZE = "50m"

RSYNC_BASE_OPTS = ["-rlpt", "--delete", "--keep-dirlinks"]

# === IMPLEMENTATION (generally no need to change) ===


def _build_excludes():
    args = []
    for e in EXCLUDES:
        args.extend(["--exclude", e])
    return args


def _resolve_remote(project_key: str, worktree: str | None) -> str:
    proj = PROJECTS[project_key]
    if worktree:
        remote_dir = proj["worktree_remote"].format(name=worktree)
    else:
        remote_dir = proj["remote"]
    return f"{REMOTE_HOST}:{REMOTE_BASE}/{remote_dir}/"


def _rsync(src: str, dst: str, *, excludes: list[str] | None = None,
           dry_run: bool = False, verbose: bool = False,
           extra_opts: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = ["rsync"] + RSYNC_BASE_OPTS
    if dry_run:
        cmd.append("--dry-run")
    if verbose:
        cmd.append("-v")
    if excludes:
        cmd.extend(excludes)
    if extra_opts:
        cmd.extend(extra_opts)
    cmd.extend([src, dst])
    return subprocess.run(cmd, check=True)


def _push_project(project_key: str, worktree: str | None,
                  dry_run: bool, verbose: bool) -> dict:
    proj = PROJECTS[project_key]
    src = str(LOCAL_BASE / proj["local"]) + "/"
    dst = _resolve_remote(project_key, worktree)
    label = project_key
    if worktree:
        label += f" (worktree: {worktree})"
    print(f">> push {label}", flush=True)
    try:
        _rsync(src, dst, excludes=_build_excludes(),
               dry_run=dry_run, verbose=verbose)
        return {"project": project_key, "status": "ok", "dst": dst}
    except subprocess.CalledProcessError as e:
        return {"project": project_key, "status": "error",
                "returncode": e.returncode, "dst": dst}


def push(projects: list[str] | None = None, worktree: str | None = None,
         dry_run: bool = False, verbose: bool = False) -> list[dict]:
    if projects is None:
        projects = list(DEFAULT_PROJECTS)

    for p in projects:
        if p not in PROJECTS:
            print(f"Unknown project: {p}. Available: {', '.join(PROJECTS.keys())}",
                  file=sys.stderr)
            sys.exit(1)

    if len(projects) == 1:
        return [_push_project(projects[0], worktree, dry_run, verbose)]

    results = []
    with ThreadPoolExecutor(max_workers=len(projects)) as executor:
        futures = {
            executor.submit(_push_project, p, worktree, dry_run, verbose): p
            for p in projects
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results


def pull_logs(worktree: str | None = None,
              dry_run: bool = False, verbose: bool = False) -> list[dict]:
    results = []
    for logdir in LOG_DIRS:
        proj_prefix = logdir.split("/")[0]
        if worktree and logdir.startswith(f"{proj_prefix}/"):
            suffix = logdir[len(f"{proj_prefix}/"):]
            src = f"{REMOTE_HOST}:{REMOTE_BASE}/{proj_prefix}-runs/{worktree}/{suffix}/"
        else:
            src = f"{REMOTE_HOST}:{REMOTE_BASE}/{logdir}/"

        dst_path = LOCAL_BASE / logdir
        dst_path.mkdir(parents=True, exist_ok=True)
        dst = str(dst_path) + "/"

        label = logdir
        if worktree:
            label += f" (worktree: {worktree})"
        print(f">> pull-logs {label}", flush=True)

        try:
            _rsync(src, dst, dry_run=dry_run, verbose=verbose,
                   extra_opts=["--max-size", MAX_LOG_SIZE])
            results.append({"logdir": logdir, "status": "ok"})
        except subprocess.CalledProcessError as e:
            results.append({"logdir": logdir, "status": "error",
                            "returncode": e.returncode})
    return results


def push_path(path: str, dry_run: bool = False, verbose: bool = False) -> dict:
    src_path = LOCAL_BASE / path
    if src_path.is_dir():
        src = str(src_path).rstrip("/") + "/"
        dst = f"{REMOTE_HOST}:{REMOTE_BASE}/{path.rstrip('/')}/"
    else:
        src = str(src_path)
        dst = f"{REMOTE_HOST}:{REMOTE_BASE}/{path}"

    print(f">> push-path {path}", flush=True)
    try:
        _rsync(src, dst, excludes=_build_excludes(),
               dry_run=dry_run, verbose=verbose)
        return {"path": path, "status": "ok"}
    except subprocess.CalledProcessError as e:
        return {"path": path, "status": "error", "returncode": e.returncode}
