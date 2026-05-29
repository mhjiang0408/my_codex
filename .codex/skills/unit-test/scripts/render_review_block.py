#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


def _load_planner_module() -> Any:
    planner_path = Path(__file__).resolve().parent / "plan_task_tests.py"
    spec = importlib.util.spec_from_file_location("unit_test_planner", planner_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PLANNER = _load_planner_module()


def _render_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _render_commands(commands: list[str]) -> str:
    return "\n".join(commands or ["# no commands declared"])


def _load_plan(plan_path: Path) -> dict[str, Any]:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{plan_path} must decode to a JSON object")
    return payload


def _resolve_plan(
    plan_arg: Path | None, plan_option: Path | None, spec_arg: Path | None, spec_option: Path | None
) -> dict[str, Any]:
    plan_path = plan_option or plan_arg
    if plan_path is not None:
        return _load_plan(plan_path)
    spec_path = spec_option or spec_arg
    if spec_path is None:
        raise ValueError("either a plan or a spec path is required")
    return PLANNER.build_command_plan(PLANNER.load_acceptance_spec(spec_path))


def render_review_block(plan: dict[str, Any], template_path: Path) -> str:
    template = template_path.read_text(encoding="utf-8")
    return (
        template.format(
            task_id=plan["task_id"],
            title=plan["title"],
            test_kind=plan["test_kind"],
            requires_real_api=str(plan["requires_real_api"]).lower(),
            config_path=plan["config_path"],
            acceptance_criteria=_render_bullets(plan["acceptance_criteria"]),
            failure_before_change=_render_bullets(plan["failure_before_change"]),
            success_after_change=_render_bullets(plan["success_after_change"]),
            task_gate_commands=_render_commands(plan["task_gate_commands"]),
            repo_status_commands=_render_commands(plan["repo_status_commands"]),
        ).rstrip()
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a review-spec block from a unit-test task plan."
    )
    parser.add_argument(
        "input_arg", nargs="?", type=Path, help="Path to a task plan JSON or task spec"
    )
    parser.add_argument("--plan", dest="plan_option", type=Path, help="Path to a task plan JSON")
    parser.add_argument(
        "--spec", dest="spec_option", type=Path, help="Path to a task acceptance spec"
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "assets"
        / "templates"
        / "task_review_block.template.md",
        help="Path to the markdown template",
    )
    args = parser.parse_args()

    inferred_plan_arg = (
        args.input_arg if args.input_arg and args.input_arg.suffix == ".json" else None
    )
    inferred_spec_arg = args.input_arg if args.input_arg and inferred_plan_arg is None else None
    plan = _resolve_plan(inferred_plan_arg, args.plan_option, inferred_spec_arg, args.spec_option)
    print(render_review_block(plan, args.template), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
