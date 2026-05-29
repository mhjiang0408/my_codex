# Code Review With Logs Request

- session_id: <CODEX_THREAD_ID>
- review_id: <optional-review-id>
- status_context: completed|runtime_issue|test_failure
- objective: <one-sentence task objective>
- permission_boundary: <allowed/blocked files, commands, tools, network, secrets>

## Test Commands
```bash
pytest -q tests/unit/path/test_file.py
```

## Changed Paths
- path/to/changed_file.py

## Log Paths
- logs/runtime.log
