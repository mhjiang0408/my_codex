---
name: refinement
description: Record AGENTS.md or skill usability failure modes, design a minimal improvement, and require a separate agent or independent pass to verify the failure mode no longer reproduces after the refinement.
---

# Refinement

Use this skill when the user says an `AGENTS.md` rule, skill, hook, checklist, or workflow is
confusing, brittle, too broad, too narrow, hard to use, or produced a bad agent behavior.

The purpose is to turn user feedback into a reproducible failure mode and then improve the
relevant rule or skill with evidence that the failure mode is fixed.

## Canonical Location

Record reusable failure modes and refinements under:

```text
.codex/skills/refinement/references/failure-modes.md
```

Task-local investigation and logs still go in `.codex_record/<session_id>/`.

## Workflow

1. Capture the failure mode:
   - user-visible bad behavior,
   - triggering wording or task shape,
   - expected behavior,
   - actual behavior,
   - affected files or skills,
   - why existing rules did not prevent it.
2. Freeze a falsifiable regression scenario in one sentence.
3. Identify the owning rule or skill. Do not patch multiple skills if one owns the behavior.
4. Make the smallest rule, template, hook, or checker change that would prevent recurrence.
5. Validate the failure mode:
   - Prefer a focused test, static checker, fixture, or command.
   - If no automated test is appropriate, use a separate agent or independent review pass with
     only the failure-mode prompt and the refined rule.
6. Append the final failure-mode entry to `references/failure-modes.md`.
7. Hand final closeout to `code-review-with-logs`.

## Execution Trace Curation

When the task is to summarize multiple Codex executions or a multi-day trace window:

- Freeze the absolute time window first, including timezone.
- Build a task-local evidence index in `.codex_record/<session_id>/` from `.codex_record/`,
  `.codex_idea/`, runtime artifacts, and `~/.codex` session logs when present.
- Group by reproducible behavior, not by individual shell command, worker id, or session id.
- Prefer 5-8 reusable failure modes over a comprehensive transcript inventory.
- Do not paste raw `codex_stdout.jsonl`, `codex_stderr.txt`, or `codex_events.jsonl` content into
  this skill. Summarize only the durable lesson and keep detailed evidence in task-local records.
- If the owning skill already contains the fix, cite that skill and the validation command. If
  the user only asked to catalog historical traces, make the changed artifact the failure-mode
  reference itself and use a source-assertion regression check.

## Required Failure-Mode Entry

Use this shape:

```markdown
## <short title>
- Date:
- Trigger:
- Expected:
- Actual:
- Root cause:
- Changed rule or skill:
- Regression check:
- Verification result:
```

## Hard Rules

- Do not treat a vague preference as a refinement until it is converted into a reproducible
  failure mode or a concrete rule ambiguity.
- Do not bury AGENTS/skill corrections only in chat; update the owning skill or AGENTS.
- If the user corrects a workflow concept, update the corresponding skill in the same task.
- For high-impact rule changes, run `system-contract` after the refinement.

## Companion Skills

- `system-contract`: update or run when the refinement changes repository hard rules.
- `skill-creator`: use when creating or significantly restructuring a skill.
- `unit-test`: use when the failure mode can be captured as a deterministic acceptance test.
- `code-review-with-logs`: use for final review evidence and Feishu report.
