# Rollout Memory Example

Current repository example:
- Benchmark file: `tests/bench/test_rollout_external_memory.py`

This benchmark follows the recommended pattern:
- sample discovery comes from real staged query files plus archived rollout directories,
- the comparison groups are explicit:
  - `memory`
  - `truncate_raw_128k`
  - `truncate_raw_256k`
- it separates:
  - storage integrity
  - routing integrity
  - effectiveness comparison
- expensive real execution is gated by `RUN_SII_ROLLOUT_MEMORY_BENCH=1`,
- strict superiority assertions are optional behind `SII_ROLLOUT_MEMORY_BENCH_ENFORCE_THRESHOLDS=1`.

Use this pattern when the question is:
- does the new context mechanism actually route through the new path?
- does it persist the expected artifacts?
- does it help continuation success relative to direct raw-context truncation?
