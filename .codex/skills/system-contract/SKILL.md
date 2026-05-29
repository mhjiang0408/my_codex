---
name: system-contract
description: Run and maintain AgentSwarm repository contract checks for AGENTS.md, skill routing, uv execution discipline, repo hygiene, secret-like content, and tests/bench boundaries. Use before closing agent-rule, skill, workflow, or repository-hygiene changes.
---

# System Contract

Use this skill when a task changes repository rules, skills, workflow hooks, test surfaces, or
other shared infrastructure. It turns the hard parts of `AGENTS.md` into a local static gate.

This skill is the AgentSwarm version of a system contract. It lives entirely under
`.codex/skills/system-contract/`; do not add a root `scripts/check_system_contract.py`.

## What It Checks

- `AGENTS.md` keeps the required workflow anchors: `uv`, `linear-cli`, `.codex_record`,
  `.codex_idea`, `code-review-with-logs`, `unit-test`, `harness-bench`,
  `experiment-handbook`, `refinement`, `system-contract`, Feishu/Lark reporting, and
  Conventional Commits.
- AgentSwarm does not adopt incompatible record surfaces such as `.agent_record` or a standalone
  `idea_record` directory.
- Local Python execution examples in the core workflow files use `uv run`, `uvx`, or `uv tool run`
  instead of bare `python3`, `python -m`, `pytest`, `ruff`, `mypy`, or `pip`.
- `tests/bench/**` remains reserved for `harness-bench`.
- Tracked files do not include common caches, runtime artifacts, or obvious secret-like content.
- ContextSwarm-specific experiment/gateway/dataset rules are not copied into AgentSwarm as
  repository hard rules.

The checker is intentionally conservative: it checks stable, low-noise repository contracts and
the workflow files that own them. Do not expand it into task correctness tests or benchmarks.

## Command

```bash
uv run python .codex/skills/system-contract/scripts/check_system_contract.py --workspace .
```

Use this command as a task-scoped gate for agent-rule and skill changes. It is local, static,
and must not call network services, Docker, qz, Feishu, Linear, or long-running benchmarks.

## Maintenance Rules

- When `AGENTS.md` adds or removes a hard repository rule, update this skill and its checker in
  the same change.
- When a rule is only advisory or task-specific, keep it in the owning skill rather than adding
  a global system-contract check.
- Prefer exact file/path checks over broad full-repo grep rules when broad scanning would flag
  historical references or remote-platform examples.
- If a contract check fails, fix the rule or the code. Do not weaken the checker just to pass a
  task unless the repository rule itself intentionally changed.

## Companion Skills

- `change-gate`: use before making material repository changes; it owns scope control and final
  diff hygiene.
- `uv-package-manager`: owns Python and uv execution policy.
- `unit-test`: owns task-level acceptance commands.
- `code-review-with-logs`: consumes this skill's command as closeout evidence.
