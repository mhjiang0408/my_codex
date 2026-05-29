---
name: high-signal-review
description: Use when reviewing a diff, pull request, branch, or agent-generated change. Focuses only on consequential, well-supported issues and avoids noisy style feedback.
---

# High-Signal Review Skill

Use this skill for review-only tasks. For task closeout, use `code-review-with-logs`; it owns the
same high-signal review stance plus command logs, `.codex_record`, `.codex_idea`, and Feishu
reporting.

This skill intentionally delegates the canonical criteria to `code-review-with-logs` to avoid
two review protocols drifting apart.

## Review Scope

Review only the changed files unless the issue requires nearby context. Apply the root `AGENTS.md`
and any nearer `AGENTS.md` files that govern changed paths.

## High-Signal Criteria

Flag an issue only when it is likely real and consequential:

- Compile, parse, type, import, or unresolved reference failure.
- Definite logic error or broken invariant.
- Security/privacy bug with plausible exploit or leakage path.
- Public API/schema/behavior change that is not documented or intended.
- Test that does not actually test the changed behavior.
- Clear violation of an explicit repository rule.

Do not flag:

- Subjective style preferences.
- Nitpicks a linter/formatter will handle.
- Speculative issues that require unlikely inputs without evidence.
- Broad "you should add more tests" comments unless the missing test creates clear risk.
- Pre-existing issues outside the diff unless they are activated by the change.

If uncertain, label as a question or omit it.

## Evidence Format

For each issue, provide:

- Severity: blocker, major, minor.
- Location: file and symbol or line range if available.
- Problem: concise factual description.
- Impact: what can go wrong.
- Fix direction: concrete, minimal remediation.
- Confidence: high or medium.

## Final Output

Group findings by severity. If no issues are found, say that no high-signal issues were found and list what was checked.
