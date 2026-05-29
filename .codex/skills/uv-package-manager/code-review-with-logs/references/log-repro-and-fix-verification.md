# Log Reproduction and Fix Verification

## Goal
Use task execution logs to reproduce failures, verify fixes, and analyze behavior changes.

## Source
Primary source file:
- `logs/review_run.log`

## Procedure
1. Extract failing command entries and exit codes from log markers:
- `[FUNC_TEST] COMMAND: ...`
- `[FUNC_TEST] EXIT_CODE: ...`
- `[BENCH] COMMAND: ...`
- `[BENCH] EXIT_CODE: ...`
- Backward compatibility: `[TEST] ...` should still be treated as functional test markers.

2. Re-run each failed functional test or benchmark command in the same workspace.
- Record rerun exit code, stdout/stderr snippets, and timestamp.
- If the rerun requires code changes, verify those fixes landed in a new commit before rerunning the anchored review workflow.

3. Classify outcomes:
- `reproduced`: rerun still fails.
- `verified-fix`: previous failure now passes.
- `not-needed`: no failing command found.
- `blocked`: cannot extract runnable commands.

4. Write reproduction report:
- `logs/repro_steps.md`
- Include command-by-command behavior analysis (previous vs rerun), and preserve whether the command came from functional tests or benchmark validation.

## Behavior Analysis Expectations
For each reproduced command, include:
- Expected behavior
- Actual behavior
- Difference from previous run
- Suggested next action

## Fix Verification Rule
A fix is considered verified only when:
- previous run failed (`exit_code != 0`), and
- rerun exits `0` under equivalent conditions.
