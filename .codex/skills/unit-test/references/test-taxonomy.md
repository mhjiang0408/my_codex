# Test Taxonomy

Use this reference to decide where a task acceptance test should live.

## Goal

Pick the directory that matches the task behavior, then apply the same `unit-test` contract:
- failing proof before the fix,
- passing proof after the fix,
- task-scoped lint and type gates.

## `tests/unit/**`

Use when:
- the contract is local logic,
- no real network or real external runtime is required,
- the test is fast and deterministic.

Examples:
- parser behavior,
- retry-family classification,
- patch-selection logic,
- config normalization.

## `tests/regression/**`

Use when:
- the task is a user-reported failure that should stay fixed,
- the important thing is reproducing the failure shape,
- the test may need a richer fixture or a more realistic execution path than a small unit test.

Examples:
- a timeout failure family that should now fail fast,
- a stale session log bug that should no longer pollute current metrics.

## `tests/performance/**`

Use when:
- the acceptance criterion is still correctness,
- but the requirement is expressed as a timing or throughput threshold.

Examples:
- "workspace clear must finish below the threshold on this fixture"
- "this helper must avoid the O(n^2) path for the controlled input"

Rules:
- assert the threshold in the test,
- keep the fixture fixed,
- do not turn this into a benchmark comparison unless the user asks for effect evaluation.

## `tests/integration/**`

Use when:
- the acceptance criterion depends on a real service or multi-component integration,
- mock-only coverage would miss the bug.

Examples:
- evaluator timeout reproduction against the configured real endpoint,
- real API request that used to fail and must now succeed.

Rules:
- default config source is `config/pipeline.yaml`,
- assert the exact regression signal,
- keep the sample set minimal and task-specific.

## `tests/bench/**`

Do not place `unit-test` deliverables here unless the user explicitly requested a benchmark.

`tests/bench/**` belongs to `harness-bench` and answers effect questions such as:
- which variant wins,
- what the production success rate is,
- whether a change improves quality at scale.

## Decision Checklist

Ask:
1. Is the task asking whether the implementation satisfies a requirement?
2. Is the proof local logic, a user regression, a threshold, or a real integration?
3. Does the user also want production-effect measurement?

If the answer to (3) is yes, split the work:
- use `unit-test` for the correctness gate,
- use `harness-bench` for the benchmark.
