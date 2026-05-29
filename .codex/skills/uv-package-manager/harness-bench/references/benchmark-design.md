# Benchmark Design Checklist

## 1. Question
- What exact user scenario is being tested?
- What decision should the benchmark inform?

## 2. Comparison Groups
- Candidate mechanism.
- At least one meaningful baseline.
- Name each group exactly as it will appear in the report.

## 3. Inputs
- Prefer real archived inputs from the same pipeline.
- Define minimum sample constraints up front:
  - minimum stage count
  - minimum raw bytes / tokens
  - repository or task filters

## 4. Metrics
- Primary metric:
  - success rate
  - pass rate
  - score
  - latency
- Secondary metrics:
  - routing source type
  - injected token estimate
  - artifact counts

## 5. Pass/Fail Semantics
- Distinguish:
  - harness correctness
  - product effect
- A benchmark can pass as a harness even if the candidate does not outperform the baseline.
- If effect superiority must be enforced, make that an explicit env-gated assertion.

## 6. Artifact Contract
- Always emit:
  - benchmark name
  - generated time
  - status
  - summary
  - per-sample results
- For each run, record:
  - policy / group name
  - command or mode
  - success flag
  - primary metric value
  - key debug artifacts

## 7. Review Integration
- The benchmark command should be directly usable in `.codex/review_spec.md`.
- If the run is expensive, default review should validate the harness shape and artifact schema, while the real run is opt-in through env vars.
