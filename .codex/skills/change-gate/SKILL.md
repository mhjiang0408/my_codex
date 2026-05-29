---
name: change-gate
description: Use for any code, test, config, dependency, build, release, docs-with-behavior, or agent-rule change. Enforces scoped edits, validation, and final diff review.
---

# Change Gate Skill

Use this skill before making any material repository change.

## Engineering Loop

Default to a small, verifiable, reviewable loop:

1. Understand: identify the user-visible goal, impact surface, existing constraints, and the
   narrowest meaningful validation command.
2. Scope: choose the minimum coherent change; do not include unrelated cleanup, formatting,
   dependency upgrades, or historical entrypoint restoration.
3. Plan: before cross-module, public API, data/security, build/release, experiment-contract, or
   large-file changes, write a short plan and confirm it does not weaken repository rules.
4. Implement: follow existing local patterns and keep diffs reviewable.
5. Validate: run focused static or task tests first; add heavier validation only when the impact
   surface requires it.
6. Review: inspect `git diff --stat` and the actual diff for unrelated churn, generated/cache
   files, secrets, private endpoints, and oversized additions.
7. Report: state what changed, validation results, skipped validation with reason, and residual
   risk.

## Core Principles

- Think before coding: state assumptions, surface ambiguity, and ask only when local context
  cannot answer the question.
- Simplicity first: implement the minimum requested behavior; do not add speculative flexibility,
  abstractions, or defensive branches for impossible states.
- Surgical changes: touch only files that trace directly to the task; do not refactor, reformat,
  or clean adjacent code unless needed to complete the request.
- Goal-driven execution: define a falsifiable success criterion and loop until the focused gate
  passes or a real blocker is recorded.

## 1. Define the change

State internally, then act on:

- Goal: what user-visible outcome is required?
- Scope: which files/subsystems are likely in scope?
- Non-goals: what should not be changed?
- Risk: public API, data, security, dependency, build, performance, or release impact?
- Done when: what objective check proves the task is complete?

If the user asked for plan-only or research-only, do not edit files.

## 2. Read the right context

- Read the root `AGENTS.md` and any nearer `AGENTS.md` files for target paths.
- Read local README, architecture notes, test examples, and config files that govern the touched area.
- Use targeted search for large files. Do not scan or modify unrelated areas.

## 3. Choose a validation ladder

Select the narrowest meaningful checks before editing:

- Source-only change: focused unit/static check.
- Public behavior change: regression or behavior test.
- Cross-package change: package build/type/lint plus affected tests.
- Dependency/build/config change: lockfile/config validation and at least one affected build/test.
- Security-sensitive change: targeted negative tests or review of unsafe inputs when feasible.

## 4. Implement with scope control

- Make the smallest coherent diff.
- Do not combine unrelated refactor, formatting, dependency, or docs changes.
- Preserve public interfaces unless explicitly directed otherwise.
- Avoid adding new responsibilities to files that already exceed the size budget in `AGENTS.md`.
- Prefer existing project patterns over new abstractions.
- New production files should usually stay below 700 lines; new test files should usually stay
  below 900 lines; new functions or methods should usually stay below 80 lines.
- If an existing source file exceeds 1,000 lines, avoid adding an independent responsibility. If
  it exceeds 2,000 lines, prefer a surgical change or plan a separate extraction slice.
- Do not create generic catch-all helpers, utility modules, or god objects. Add abstractions only
  when they remove real complexity, reduce meaningful duplication, or match an established local
  pattern.

## 5. Validate

- Run focused checks first.
- If checks fail, fix the cause if it is in scope.
- If a failure is unrelated, record the evidence and avoid hiding it.
- If validation cannot be run, state the exact command that should be run and why it was skipped.

## 6. Final self-review

Before final response, inspect:

- `git diff --stat`
- actual diff for all changed files
- generated files, snapshots, lockfiles, and fixtures
- secret-like strings or private endpoints
- public API/schema/doc/release implications
- oversized additions or new monoliths

For agent-rule, skill, workflow, or repo-hygiene changes, run the `system-contract` skill's gate
before closeout:

```bash
uv run python .codex/skills/system-contract/scripts/check_system_contract.py --workspace .
```

## 7. Final report

Report:

- Summary of change
- Files changed by purpose
- Validation run with result
- Validation not run with reason
- Risks/follow-ups/human review points
