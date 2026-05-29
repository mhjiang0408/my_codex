# Log Context and Failure Verification

## Goal
Use task execution logs to explain failures and support the closeout report. Logs are evidence for `command trace`, `Tests and evals`, `Cost and retries`, and `reliable check`.

## Procedure
1. Read caller-provided `--log-path` files only.
2. Summarize line count and bounded excerpts.
3. Pair failed unit-test commands with relevant log excerpts when possible.
4. If a log is missing, record the path as missing and let reliable check decide whether that blocks the review.

## Rule
Do not rerun arbitrary commands discovered in logs. Only execute commands supplied through `--test-command`.
