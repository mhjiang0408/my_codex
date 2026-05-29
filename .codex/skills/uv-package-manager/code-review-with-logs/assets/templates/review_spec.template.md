# Review Spec

> `code-review-with-logs` now writes session-scoped outputs into `.codex/reviews/<review_id>/`.
> Run `run_review_flow.sh` with an explicit `--review-id` and a committed review target SHA.
> If you intentionally review a non-`HEAD` commit, pass the same explicit SHA into `run_review_flow.sh --review-target-sha <SHA>`.
> Do not list `.codex/task_plan.md`, `.codex/progress.md`, or `.codex/findings.md` in `Final Deliverables`; they are traceability files, not deliverables.
> Use the `unit-test` skill to generate task acceptance coverage before review. The blocking
> commands below should prove the task failed before the fix and pass after the fix.

## Final Deliverables
- path: src/path/to/target_file.py
- path: tests/path/to/target_test.py

## Test Commands
> Blocking task-scoped acceptance commands only. Put the `unit-test`-generated pytest, ruff,
> mypy, regression, performance-threshold, or real-API reproducer commands here.
> Keep repository-wide status reporting outside this section so formal review stays scoped to the
> task.

```bash
uv run pytest -q tests/unit/path/to/target_test.py
uv run ruff check src/path/to/target_file.py tests/path/to/target_test.py
uv run mypy src/path/to/target_file.py
```

## Benchmark Commands
> Optional. Only filled and validated when `Final Deliverables` explicitly requires benchmark output, for example a `tests/bench/**` file or benchmark artifact.
> Benchmark methodology should be designed with the `harness-bench` skill first.
> Do not put task acceptance tests here; those belong in `Test Commands` via `unit-test`.

```bash
uv run pytest -q tests/bench/path/to/task_specific_benchmark.py
```

## Naming Rules
- code_scopes: src/**/*.py,tests/**/*.py
- code_file_regex: ^[a-z0-9_]+\.py$
- python_function_regex: ^[a-z_][a-z0-9_]*$
- python_class_regex: ^[A-Z][A-Za-z0-9]*$
- python_variable_regex: ^[a-z_][a-z0-9_]*$
- output_file_regex: ^[a-z0-9_.-]+$

## Required Output Files
- .codex/reviews/<review_id>/review_run.log
- .codex/reviews/<review_id>/review_summary.md
- .codex/reviews/<review_id>/validation_results.json
- .codex/reviews/<review_id>/test_results.json
- .codex/reviews/<review_id>/benchmark_results.json

## Constraints
- command: uv run ruff check src/path/to/target_file.py tests/path/to/target_test.py
- command: uv run mypy src/path/to/target_file.py

## Uncertainty Handling
- required_levels: High,Medium,Low
- require_mitigation: true
- default_mitigation_action: Record the remaining risk and mitigation in the session summary.
- note: emit markers like `RiskLevel:Medium` and `Mitigation:<action>` in run logs.
