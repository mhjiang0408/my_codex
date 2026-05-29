---
name: refactor-slice
description: Use for refactoring, large-file decomposition, module extraction, architecture cleanup, or behavior-preserving restructure. Prevents broad rewrites and enforces independently validated slices.
---

# Refactor Slice Skill

Use this skill when the user asks to refactor, split, extract, simplify, modularize, or reduce file size.

## 1. Default mode: plan first

Unless the user explicitly asks to implement immediately, first produce a refactor plan only.

The plan must include:

- Target responsibility to extract or simplify.
- Files likely affected.
- Behavior invariants that must not change.
- Validation command(s) for the slice.
- Risks and rollback strategy.

## 2. Slice constraints

A single slice should usually:

- Preserve behavior.
- Touch one responsibility or seam.
- Avoid public API changes.
- Avoid dependency changes.
- Avoid unrelated formatting churn.
- Stay reviewable, ideally under five production files unless the repository structure requires otherwise.

## 3. Safe extraction procedure

1. Identify the smallest cohesive responsibility.
2. Locate existing tests or add characterization tests if behavior is not already covered.
3. Extract code to a focused module/class/function.
4. Keep old public entry points delegating to the new implementation when needed.
5. Move or add tests near the new owner where practical.
6. Run focused validation.
7. Inspect diff for behavior changes and scope creep.

## 4. Large-file rule

When working in a file over the root `AGENTS.md` size budget:

- Do not add a new independent responsibility.
- Prefer extracting a helper module instead of growing the file.
- If only a surgical fix is needed, keep it surgical.
- If extraction would be too risky, document why and propose a separate future slice.

## 5. Completion criteria

A refactor slice is complete only when:

- Behavior is preserved.
- Focused validation passes or skipped validation is clearly explained.
- The diff is smaller and more modular, not merely moved around.
- The final response names the invariant preserved and the evidence.
