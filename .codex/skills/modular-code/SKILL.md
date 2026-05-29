---
name: modular-code
version: 1.0.0
description: "Write modular Python code that is easy to understand, test, and safely modify with AI agents."
---

Write modular Python code that is easy to understand, test, and safely modify with AI agents.

Each module must have:

- **One responsibility**
- **One primary input**
- **One primary output**
- **One explicit edit boundary**

A module should represent a clear unit of behavior, not just a random group of functions.

---

### Core Rules

#### 1. One Module = One Responsibility

Each module must own one clear concern and have only one reason to change.

Good examples:

- `validate_order.py`
- `calculate_price.py`
- `persist_invoice.py`
- `build_response.py`

Avoid vague modules such as:

- `utils.py`
- `helpers.py`
- `common.py`
- `misc.py`

---

#### 2. Single Input / Single Output

Each module should expose one primary public entry point.

The entry point must:

- Accept **one input object**
- Return **one output object**
- Avoid loose tuples, global state, or hidden dependencies

Recommended pattern:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidateOrderInput:
    order_id: str
    item_ids: list[str]


@dataclass(frozen=True)
class ValidateOrderOutput:
    is_valid: bool
    errors: list[str]


def run(input_data: ValidateOrderInput) -> ValidateOrderOutput:
    ...
```

Rules:

- Prefer `run`, `execute`, or `handle` as the single public entry point.
- Keep helper functions private with `_helper_name`.
- Do not expose multiple unrelated public functions from one module.
- Do not mix validation, computation, persistence, and presentation in one file.

---

### Module Contract

Every non-trivial module must declare its contract.

Use this format:

```python
"""
Responsibility:
    Validate an order request.

Input:
    ValidateOrderInput

Output:
    ValidateOrderOutput

Allowed side effects:
    None.

Forbidden:
    - Do not write to the database.
    - Do not call external APIs.
    - Do not mutate the input object.
    - Do not format user-facing responses.
"""
```

The contract defines what the module may and may not change.

---

### File Size Guidelines

| Lines | Status | Action |
|---:|---|---|
| 150-500 | Good | Keep if responsibility is clear |
| 500-1000 | Large | Look for split points |
| 1000-2000 | Too large | Refactor into focused modules |
| 2000+ | Critical | Must split or document exception |

Do not split by line count alone. Split by responsibility, input/output flow, and edit safety.

---

### When to Split

Split a file when any of these apply:

- It has more than one responsibility.
- It has more than one primary input/output flow.
- It mixes pure logic with side effects.
- It contains unrelated validation, computation, storage, or response logic.
- Tests are hard to organize.
- AI agents cannot safely modify one part without touching another.
- A requested change cannot be limited to one module or one field.

---

### Preferred Split Pattern

```text
feature/
├── __init__.py          # Minimal exports only
├── models.py            # Shared input/output types
├── validate_input.py    # Input -> validation result
├── compute_result.py    # Validated input -> computed result
├── persist_result.py    # Computed result -> persistence result
└── build_response.py    # Internal result -> external response
```

Expected data flow:

```text
raw_input
  -> validate_input.run()
  -> compute_result.run()
  -> persist_result.run()
  -> build_response.run()
  -> response
```

Each module receives one input object and returns one output object.

---

### AI Agent Edit Boundary

When asking an AI agent to modify code, always define the edit boundary.

Required format:

```text
Target module:
    feature/validate_input.py

Target field:
    ValidateOrderInput.item_ids

Allowed change:
    Add validation that item_ids must not be empty.

Allowed files:
    - feature/validate_input.py

Forbidden files:
    - feature/compute_result.py
    - feature/persist_result.py
    - feature/build_response.py
    - feature/models.py

Contract changes allowed:
    No.

Behavior changes outside target:
    No.

Import changes allowed:
    Only inside the target module if required.

Test changes allowed:
    Only tests directly covering the target field.
```

---

### Agent Rules

The agent must:

- Modify only the declared module.
- Modify only the declared field, function, or class.
- Preserve all unrelated behavior.
- Preserve input/output contracts unless explicitly allowed.
- Avoid touching sibling modules.
- Avoid broad refactors.
- Avoid unrelated formatting changes.
- Stop and report if the change requires cross-module updates.

The agent must not:

- Edit other modules for consistency.
- Rename files, functions, classes, or fields unless requested.
- Change public APIs unless requested.
- Move shared types unless requested.
- Add dependencies unless requested.
- Modify unrelated tests.
- Reformat unrelated code.
- Combine multiple module changes into one patch.

---

### Field-Level Rule

For field-specific tasks, the field is the maximum edit scope.

Example:

```text
Target field:
    UserProfile.email

Allowed:
    - Add email normalization.
    - Add email validation.
    - Update tests for UserProfile.email.

Forbidden:
    - Changing UserProfile.name.
    - Changing UserProfile.phone.
    - Changing persistence behavior.
    - Changing API response format.
    - Changing unrelated validation rules.
```

If a field change requires schema, migration, serializer, API, or cross-module changes, the agent must report the required changes instead of editing them automatically.

---

### DO

- Use meaningful module names.
- Keep each module focused.
- Use one input object and one output object.
- Keep side effects explicit.
- Keep `__init__.py` minimal.
- Use explicit imports.
- Keep pure logic separate from I/O.
- Require strict agent edit boundaries.

---

### DON'T

- Do not create generic dumping-ground modules.
- Do not expose many unrelated public functions.
- Do not hide dependencies with wildcard imports.
- Do not over-split into meaningless tiny files.
- Do not let agents modify neighboring modules without permission.
- Do not let agents change multiple modules in one task unless explicitly allowed.

---

### Refactoring Rule

When splitting a large file:

1. Identify one responsibility.
2. Extract only that responsibility.
3. Define its input and output.
4. Add a module contract.
5. Update only required imports.
6. Run targeted tests.
7. Do not change unrelated behavior.

---

### Sources

- [Python documentation: Modules](https://docs.python.org/3/tutorial/modules.html)
- [PEP 8: Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [The Hitchhiker's Guide to Python: Structuring Your Project](https://docs.python-guide.org/writing/structure/)
