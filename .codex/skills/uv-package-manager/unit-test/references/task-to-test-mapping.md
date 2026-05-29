# Task To Test Mapping

Use these examples to convert user criteria into acceptance tests.

## Example: workspace clear must be faster

User intent:
- "make `workspace clear` faster"

Correct `unit-test` translation:
- create a controlled fixture for the relevant workspace layout,
- add a test in `tests/performance/**`,
- record the threshold in the assertion,
- prove the old implementation exceeds the threshold,
- prove the new implementation stays below the threshold.

What not to do:
- do not move this to `tests/bench/**` unless the user asked for a benchmark,
- do not just print a timing value without an assertion.

Acceptance shape:
- before: duration is above threshold or the test fails the threshold assertion,
- after: duration is at or below threshold and the same test passes.

## Example: evaluator timeout must be diagnosed and fixed

User intent:
- "find the evaluator timeout cause and fix it"

Correct `unit-test` translation:
- add a real regression test in `tests/regression/**` or `tests/integration/**`,
- use the configured real endpoint from `config/pipeline.yaml`,
- run the smallest real request that reproduces the timeout,
- assert the timeout or failure signal before the fix,
- assert the same call no longer emits that signal after the fix.

What not to do:
- do not replace the real regression with a pure mock if the bug depends on the actual API,
- do not call this a benchmark unless the user asks to compare production outcomes.

Acceptance shape:
- before: timeout, blocked verdict, or known error family appears,
- after: the same command completes without that signal.

## Example: invalid tool-parameter loop should fail fast

User intent:
- "stop repeated invalid parameter retries"

Correct `unit-test` translation:
- add a regression or unit test that feeds the failing family text,
- assert the old logic keeps retrying or misses the family,
- assert the new logic classifies the failure and stops retrying.

## Mapping Rule

Start from the user criterion, then ask:
1. Is the criterion about state or logic? Use `logic_regression`.
2. Is the criterion a threshold? Use `performance_threshold`.
3. Is the criterion only meaningful against a real service? Use `real_api_regression`.

Then write the spec so the same task command proves both:
- not fixed before,
- fixed after.
