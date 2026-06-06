---
name: error-roadmap
description: Use when writing code, fixing bugs, changing pipelines, diagnosing runtime failures, designing try-except boundaries, avoiding fallback or hard-coded workarounds, and using tee or complete logs to localize the core failing module by roadmap path.
---

# Error Roadmap

Use this skill before implementation work that can fail at runtime. Its job is to make failures
locatable by stage, module, function, and input contract before any fallback, hard-coded bypass, or
catch-all patch is considered.

## First-Order Rule

Implementation starts by making failure location observable.

Before writing or changing behavior, define the execution roadmap:

- pipeline or caller path,
- stage/module/function boundary,
- responsibility at each boundary,
- primary input and output shape,
- expected failure classes,
- complete log location for the run.

Do not implement a fallback, hard-coded special case, or silent recovery before the failing roadmap
path and original exception evidence are known.

## Required Boundaries

Every implementation must add or preserve structured error context at these boundaries:

- public entrypoints,
- pipeline stages,
- external I/O and API calls,
- parsing, serialization, and schema conversion,
- non-trivial public functions,
- private functions that enforce type assumptions, perform complex transforms, call external
  resources, mutate state, or branch on critical invariants.

Private pure helpers do not need mechanical try-except wrappers when the caller boundary already
provides an equivalent roadmap path and input contract. Add local validation or local context when
the helper can fail in a way that would otherwise be ambiguous.

## Error Classes

Classify failures with the narrowest useful category:

- `input_contract_error`: wrong type, missing field, invalid shape, invalid value range.
- `precondition_error`: state or ordering assumption is not satisfied.
- `external_io_error`: filesystem, network, subprocess, or platform I/O failed.
- `dependency_api_error`: dependency, service, or API contract changed or returned an error.
- `parse_or_serialization_error`: JSON/YAML/CSV/text parsing or encoding failed.
- `timeout_or_resource_error`: timeout, memory, disk, quota, or rate limit.
- `invariant_violation`: internal assumption is false after validated inputs.
- `unexpected_bug`: unknown failure after known classes were ruled out.

Prefer typed exceptions or a small domain-specific error class over string matching.

## Catch Rules

Use `try` / `except` to add context and preserve causality, not to hide failures.

Required catch behavior:

- Catch the narrowest exception type that can be classified.
- Include `roadmap_path`, `module`, `function`, `stage`, `error_class`, and a small input summary.
- Preserve the original traceback with `raise NewError(...) from exc` or an equivalent cause chain.
- Record enough context to find the matching location in the complete log.
- Re-raise after adding context unless the user-visible contract explicitly allows degradation.

Forbidden behavior:

- `except Exception: return default`
- swallowing an exception and marking a pipeline stage successful,
- hard-coding a value only because the current failing case needs it,
- broad fallback that makes the run pass without proving the original failure is understood,
- logging only a high-level message while discarding the original traceback.

## Input Contract Checks

Validate important boundary inputs before running business logic. If a function accepts a `list`,
passing a `dict` should produce a local error that names:

- roadmap path,
- function and parameter,
- expected type or shape,
- actual type or shape,
- relevant keys/counts without dumping secrets or huge payloads.

This is part of the function contract, not a last-minute production bug patch.

## Complete Logs

For any runnable workflow, keep the full stdout/stderr stream with `tee` or an equivalent logging
mechanism. A structured error summary is only an index.

Diagnosis order:

1. Read the structured exception summary.
2. Identify the core error class and roadmap path.
3. Open the complete log saved by `tee` or the workflow logger.
4. Find the original traceback and surrounding stage logs.
5. Fix the smallest module responsible for that failure class.

Do not report a fix until the complete log and structured error agree about the failing boundary.

## Minimal Python Pattern

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorContext:
    roadmap_path: str
    stage: str
    module: str
    function: str
    error_class: str
    input_summary: str


class ModuleBoundaryError(RuntimeError):
    def __init__(self, context: ErrorContext, message: str) -> None:
        self.context = context
        super().__init__(
            f"{context.roadmap_path} [{context.error_class}] "
            f"{context.module}.{context.function}: {message}; input={context.input_summary}"
        )


def normalize_items(items: list[str]) -> list[str]:
    context = ErrorContext(
        roadmap_path="ingest.validate.normalize_items",
        stage="validate",
        module="ingest",
        function="normalize_items",
        error_class="input_contract_error",
        input_summary=f"type={type(items).__name__}",
    )
    if not isinstance(items, list):
        raise ModuleBoundaryError(context, "expected list[str]")

    try:
        return [item.strip() for item in items]
    except AttributeError as exc:
        raise ModuleBoundaryError(context, "all items must support strip()") from exc
```

## Report Shape

When closing a runtime failure or fix, state:

- core error class,
- roadmap path,
- failing stage/module/function,
- original traceback or complete-log location,
- why fallback or hard-coding was not used,
- the smallest module changed and the validation command.

## Companion Skills

- `software-architecture`: define the business capability and module boundaries before the
  roadmap is written.
- `modular-code`: keep each failing boundary tied to a single responsibility and edit boundary.
- `unit-test`: freeze the failure mode and prove the corrected boundary behavior.
- `change-gate`: keep the final diff scoped and reviewable.
