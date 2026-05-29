"""qzx — project-specific QZ CLI extensions.

This is a scaffold that delegates all base commands to `qz` and provides
a place to add project-specific commands (sync, worktree, workspace,
job templates, run workflows).

Install in your project:
    uv pip install -e tools/qzx

Usage:
    qzx <command>              # project-specific commands
    qzx qz <qz-args>          # pass-through to base qz CLI
"""

import argparse
import subprocess
import sys


def cmd_qz_passthrough(args):
    """Pass all arguments through to the base qz CLI."""
    result = subprocess.run(["qz"] + args.qz_args)
    sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        prog="qzx",
        description="Project-specific QZ CLI extensions",
    )
    sub = parser.add_subparsers(dest="subcmd")

    # Pass-through to base qz CLI
    p_qz = sub.add_parser("qz", help="Pass-through to base qz CLI")
    p_qz.add_argument("qz_args", nargs=argparse.REMAINDER, help="Arguments for qz")

    # === Add your project-specific commands below ===

    # Example: uncomment to add sync
    # p_sync = sub.add_parser("sync", help="Project-aware code sync")
    # sync_sub = p_sync.add_subparsers(dest="sync_command")
    # p_push = sync_sub.add_parser("push", help="Push code to cluster")
    # p_push.add_argument("--worktree", default=None)
    # p_push.add_argument("-n", "--dry-run", action="store_true")
    # p_push.add_argument("-v", "--verbose", action="store_true")

    # Example: uncomment to add job templates
    # p_run = sub.add_parser("run", help="Run from template")
    # p_run.add_argument("template", help="Template name")
    # p_run.add_argument("--set", action="append", dest="overrides",
    #                     help="Parameter override: key=value")
    # p_run.add_argument("--name", default=None, help="Job name")
    # p_run.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if not args.subcmd:
        parser.print_help()
        sys.exit(1)

    if args.subcmd == "qz":
        cmd_qz_passthrough(args)
    # elif args.subcmd == "sync":
    #     from qzx import sync
    #     ...
    # elif args.subcmd == "run":
    #     from qzx import templates
    #     ...


if __name__ == "__main__":
    main()
