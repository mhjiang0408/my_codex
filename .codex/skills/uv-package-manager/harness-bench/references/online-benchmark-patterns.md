# Online Benchmark Patterns

## Environment Gate
- Use an explicit env var such as:
  - `RUN_<BENCH_NAME>=1`
- When disabled:
  - write a skipped report,
  - include the skip reason,
  - call `pytest.skip(...)`.

## Real Sample Discovery
- Discover samples from archived artifacts instead of hardcoding raw payloads whenever possible.
- Sort candidates by the property that matters to the scenario:
  - trajectory length
  - bytes
  - stage depth
  - failure rarity

## Separation Of Concerns
- Storage integrity:
  - did the benchmarked mechanism persist the expected files?
- Routing integrity:
  - did the runtime actually choose the intended path?
- Effectiveness:
  - did the candidate improve or preserve the outcome metric?

## Reporting
- Keep a top-level summary for quick review.
- Keep per-sample detail for debugging.
- Include enough artifact paths that another agent can replay the case.

## Assertions
- Always assert harness integrity.
- Only assert candidate superiority when:
  - the user explicitly wants that gate, or
  - an env var enables strict enforcement.
