---
name: linear-cli
description: Manage Linear issues from the command line using the linear cli. This skill allows automating linear management.
allowed-tools: Bash(linear:*), Bash(curl:*)
hooks:
  PreToolUse:
    - matcher: "Write|Edit|Bash|Read|Glob|Grep"
      hooks:
        - type: command
          command: |
            WORKSPACE_ROOT="${CODEX_WORKSPACE_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
            SCRIPT="$WORKSPACE_ROOT/.codex/skills/linear-cli/scripts/start_task_hook.sh"
            if [ -x "$SCRIPT" ]; then
              "$SCRIPT" --workspace "$WORKSPACE_ROOT"
            elif [ -f "$SCRIPT" ]; then
              bash "$SCRIPT" --workspace "$WORKSPACE_ROOT"
            else
              echo "[linear-cli] BLOCKED: missing start_task_hook.sh at $SCRIPT" >&2
              exit 1
            fi
---

# Linear CLI

A CLI to manage Linear issues from the command line, with git and jj integration.

## Prerequisites

The `linear` command must be available on PATH. To check:

```bash
linear --version
```

If not installed globally, you can run it without installing via npx:

```bash
npx @schpet/linear-cli --version
```

All subsequent commands can be prefixed with `npx @schpet/linear-cli` in place of `linear`. Otherwise, follow the install instructions at:\
https://github.com/schpet/linear-cli?tab=readme-ov-file#install

## Branch Stability Rules

- Unless the user explicitly asks for git branch operations, Linear issue management must not
  change the current git branch.
- Do not use `linear issue create --start` for normal issue creation in this repo.
- Do not use `linear issue start` unless the user explicitly asked you to create or switch to an
  issue branch.
- Treat `linear issue pull-request` and other branch-coupled helpers as opt-in only.
- Prefer:
  - `linear issue create ...` without `--start`
  - `linear issue update ... --state ...`
  - `linear issue comment add ...`
- In this workspace, `linear issue create --start` was observed to create and switch to a new
  branch automatically. Treat that as a forbidden side effect for ordinary issue tracking.
- If an issue already has a `branchName` recorded in Linear, treat it as metadata only. Do not
  switch the local repo to match it unless the user explicitly requested that branch action.

## Best Practices for Markdown Content

When working with issue descriptions or comment bodies that contain markdown, prefer direct
`--description` / `--body` writes over creating extra description files in the repo.

- Use `--description` for `issue create` and `issue update`.
- Use `--body` for `comment add` and `comment update`.

**Why prefer direct writes here:**

- Avoids leaving redundant description files in `.codex/` or the repo root.
- Keeps the Linear mutation and its text payload in one place.
- Still preserves markdown formatting as long as you pass actual newlines rather than literal
  escaped `\n` text.

**Example workflow:**

```bash
DESC=$(cat <<'EOF'
## Summary

- First item
- Second item
EOF
)

linear issue update COD-123 --description "$DESC"

BODY=$(cat <<'EOF'
## Progress

- Updated the task state
EOF
)

linear issue comment add COD-123 --body "$BODY"
```

## Repository Workflow Ownership

In this workspace, `linear-cli` is the owning source for detailed Linear workflow rules.
`AGENTS.md` should only keep summary-level repository obligations and should defer the detailed
mechanics here to avoid duplication drift.

Rules owned here include:
- the start-task hook fields and recording contract,
- reuse / reopen / sub-issue / new-main-issue branching,
- issue topology ownership,
- title / description language rules,
- default project / due-date behavior,
- child dedup and `children.nodes` inspection,
- progress-comment expectations,
- review / close-out state transitions,
- and the requirement to mirror the active `.codex/task_plan.md` into the active main issue
  description.

Avoid one-line escaped payloads like `--description "line1\nline2"`, because they can surface as
literal `\n` sequences in `linear issue view`.

- When the markdown body contains backticks, do not wrap the whole `--body` payload in double
  quotes directly at the shell prompt. Shell command substitution will strip the backticked
  segments before `linear` sees them.
- Prefer one of these safer forms for comment bodies with markdown code spans:
  - use a single-quoted multiline shell string when the body itself does not contain `'`
  - or build the payload with `cat <<'EOF' ... EOF` and pass `--body "$BODY"`
- If a `linear issue comment add --body "..."` write succeeds but the viewed comment is missing
  code spans or key identifiers, suspect shell quoting first and rewrite the mutation using a
  heredoc-backed variable before assuming a Linear CLI bug.
- The same shell-quoting hazard applies to `linear issue update --description ...`.
  If the description body contains backticks from markdown code spans, do not compose the final
  payload in an unquoted heredoc or interpolated shell block that allows command substitution.
  Build the markdown with a single-quoted heredoc first, then pass the fully materialized string
  via `--description "$DESC"`.
- Do not try to mirror a file into Linear by wrapping `$(cat path/to/file)` inside a
  single-quoted heredoc such as:
  - `DESC=$(cat <<'EOF' ... $(cat file) ... EOF)`
  because the single-quoted heredoc preserves that `$(cat ...)` text literally.
- If the source of truth is already a file, prefer:
  - `DESC=$(cat path/to/file)`
  - then `linear issue update ... --description "$DESC"`
  This avoids accidental literal writes like `$(cat .codex/task_plan.md)` appearing in the
  issue description.

## Mutation Output Gotcha

- In the current `linear-cli` version used by this workspace, write commands such as:
  - `linear issue comment add`
  - `linear issue update`
  do not accept `--json`.
- Reserve `--json` for read/query commands such as `linear issue query` and
  `linear issue view`.
- For write operations, use direct mutation flags like `--body`, `--description`, and `--state`,
  then confirm exact structured state with a follow-up read when needed.

## `issue view` JSON Gotcha

- In the current CLI version used here, `linear issue view <ISSUE> --json` emits the full JSON
  payload only.
- It does not accept a trailing field-selection list like
  `linear issue view COD-184 --json id,title,state`; that form fails with `Too many arguments`.
- If you need a subset of fields, read the full JSON first and filter locally with shell or
  Python tooling.

## Issue Language Rules

- All issue titles must be written in Chinese.
- The main issue description must be written in Chinese.
- If a product name or code identifier is important but would make the title partly English,
  keep it in the description instead of the title unless the user explicitly says otherwise.
- If the user did not specify a project, default directly to the project slug `3a33cd7c7d0d`.
- In this workspace, that slug currently resolves to `CoPR Midtrain`.
- Prefer the slug itself for `issue create` / `issue update` / `issue query`; do not rely on the
  display name as the default write value.

## Issue Topology Ownership And Timing

- In repos that use plan mode, plan mode may inspect, query, create, or reuse Linear issues.
- Plan mode may also set parents or dependency edges when the plan needs a real issue topology,
  but every such mutation must be preceded by query + dedup.
- Linear issue topology is owned by the main agent only:
  - only the main agent may create or reuse the main issue,
  - only the main agent may create or reuse sub-issues,
  - only the main agent may set `--parent` or dependency relations.
- Subagents may work on an assigned issue, but they must not create new issues or mutate the
  issue tree. They report back to the main agent instead.
- Do not force sub-issues for simple tasks. If the task does not need real decomposition or
  parallel execution, keep a single main issue only.
- Freeze one absolute task date (`YYYY-MM-DD`) before the first Linear mutation. If the user did
  not specify a due date, use that same frozen date as the default `--due-date` for all plan-time
  and implement-time issue writes in the task.
- If the user did not specify a project, use `3a33cd7c7d0d` as the default `--project` value for
  both plan-time and implement-time issue writes.

## Start-Task Linear Hook Workflow

- Every non-casual task must be registered by the Codex start-task Linear hook before
  substantive implementation.
- This replaces the old manual Linear entry workflow. Do not require agents to pause and run a
  separate registration command by hand when the hook can perform the registration.
- Repos that mirror this workflow in `AGENTS.md` should keep `AGENTS.md` summary-level and keep
  the detailed hook fields and branching rules here to avoid duplication drift.
- Treat these as tasks that require hook registration:
  - any repo edit,
  - any multi-step investigation or monitoring task,
  - any request that will use `.codex/task_plan.md`,
  - any work that needs more than a trivial one-shot command or answer.
- Only skip Linear hook registration for clearly non-tracked interactions such as:
  - greetings,
  - casual chat,
  - one-shot explanations that do not change the repo and do not require ongoing tracking.
- The main agent owns the hook result and issue topology. Subagents must not make the
  create-vs-reuse decision.
- The hook output must be written to the active `.codex_record/<session_id>/task_plan.md`,
  `.codex_record/<session_id>/progress.md`, and `hook_state.json` before implementation starts.
- After the hook result is recorded and the active plan exists, mirror the current active
  `.codex/task_plan.md` into the chosen main issue description before substantive implementation
  continues.
- Treat the Linear main-issue description as the durable remote mirror of the current task plan.
  When the plan materially changes, update the description again rather than leaving Linear on an
  outdated phase list.
- Hook failure policy is hard-blocking in this workspace. If Linear query/create/update fails, if
  the hook cannot write session records, or if the issue id cannot be determined, the hook returns
  non-zero and implementation must not silently continue. Manual Linear CLI use is then the repair
  path, not the default entry workflow.

### Required Hook Steps

1. Freeze the execution date and the Chinese issue title candidate.
2. Read the current active task context from `.codex_record/<session_id>/task_plan.md` and
   `hook_state.json`.
3. Query Linear with `linear issue query --team COD --search "<title-or-keywords>" --project 3a33cd7c7d0d --json`.
4. Apply a local exact-title filter.
5. Choose exactly one of the following actions and record the rationale:
   - reuse the current main issue,
   - reopen that exact issue and add a follow-up comment,
   - create or reuse a sub-issue under the current main issue,
   - create a new main issue.
6. Only after that hook decision is recorded may implementation continue.
7. Update the chosen main issue description so it reflects the current active `task_plan.md` or
   thread-scoped task plan.

### Hook Script

The canonical local entrypoint is:

```bash
.codex/skills/linear-cli/scripts/start_task_hook.sh --workspace .
```

The wrapper is a bash script (`set -euo pipefail`), so hook frontmatter fallbacks must invoke it
with `bash "$SCRIPT"` when the executable bit is missing; do not use plain `sh`.

Useful controlled modes:
- `--dry-run`: exercise classification and record writes without mutating Linear.
- `--skip-linear`: hard-block tracked tasks without Linear mutation; useful for testing failure
  behavior.
- `--objective "<task>"`: explicit task objective when the Codex hook payload or session log does
  not expose the user request.
- `--force`: force tracking even if the classifier would skip.

The script appends a start-hook note to `.codex_record/<session_id>/progress.md` and writes
`.codex_record/<session_id>/hook_state.json`. `hook_state.json` is the handoff consumed by the
end-task review hook.

### Reuse vs Create Rules

- Age gate comes before reuse/reopen: if a found issue's `createdAt` is two calendar days old or older relative to the frozen `task_date`, do not reuse it and do not reopen it for the new task loop. Create a new issue instead.
- Treat `two calendar days old or older` as an absolute-date rule, not a rolling 48-hour timestamp comparison. Example: if `task_date=2026-04-19`, then any matching issue created on `2026-04-17` or earlier is considered too old to reuse.
- Record this age-gate decision explicitly in the start-task hook rationale whenever it changes the outcome.

- Reuse the current main issue only when the user is clearly continuing the same primary goal, deliverable, or review/follow-up loop that is already active in `.codex/task_plan.md` and the active issue is not blocked by the two-day age gate.
- Reuse the current main issue when the user is correcting the workflow, acceptance criteria, or reporting behavior of that same task, unless the active issue is already two days old or older under the frozen `task_date`.
- If the exact matching issue already exists, is newer than the two-day age gate, and is `Done`, and the user is continuing the same topic, reopen that exact issue and add a follow-up comment instead of creating a duplicate.
- Only create or reuse a sub-issue when the user is still inside the same main issue but the work
  has become a genuinely separate parallelizable slice.
- When the current main issue enters a long-running monitoring or waiting state and the user wants
  continued watch, treat that monitoring loop as a separate parallelizable slice:
  - create or reuse a dedicated monitoring sub-issue under the same main issue,
  - let the main agent own the topology mutation,
  - then delegate the polling loop to a worker/default subagent instead of blocking the main
    thread in foreground polling.
- Create a new main issue when the user changes the primary goal, deliverable set, monitored
  object, or acceptance scope enough that the old main issue would no longer be the right top-level
  tracker.
- If search returns fuzzy matches but no exact-title match and the current active issue is not the same task, create a new main issue.
- When applying local exact-title filtering, also inspect `createdAt` on exact matches before deciding reuse vs reopen. Exact-title alone is not sufficient if the issue is too old under the age gate.

### Required Recorded Fields

- `task_date`
- `issue_title_candidate`
- `query_command`
- `exact_match_result`
- `chosen_action`
- `chosen_issue_id`
- `rationale`

## Main-Issue And Sub-Issue Workflow

1. During planning:
   - freeze the task date,
   - decide the Chinese main-issue title,
   - decide whether sub-issues are actually needed,
   - decide the intended dependency graph,
   - query for same-task main-issue candidates,
   - locally exact-filter by title before deciding reuse vs create,
   - reuse and update an exact-title match when it exists,
   - otherwise create the main issue during plan mode with a Chinese title, Chinese description,
     `--due-date <task-date>`, and `--project 3a33cd7c7d0d` unless the user specified overrides,
   - when creating that issue, do not pass `--start`; the current branch must stay unchanged.
2. During planning or implementation, for each sub-issue candidate:
   - inspect the current main issue via `linear issue view <MAIN-ID> --json`,
   - look at `children.nodes`,
   - use `parent + exact Chinese title` as the dedup key,
   - if a match exists, reuse that issue and update its state / assignee / due date / description
     / project as needed,
   - only create a new sub-issue when no exact-title child exists under that parent, and create
     it with the default project when the user did not override the project.
3. During implementation:
   - continue to maintain issue status, descriptions, parents, dependencies, and assignees,
   - keep the main issue description aligned with the active `.codex/task_plan.md` rather than
     treating the description as a one-time bootstrap note,
   - make sure to mark the issue as done once the main task is finished, and mark the sub-issues as done once their sub-tasks are finished,
   - if new decomposition is discovered, it is valid to add new issues or sub-issues,
   - for long-running monitoring slices under the same main issue, prefer a dedicated monitoring
     sub-issue before spawning the worker/default subagent that will keep polling,
   - every new mutation still starts with query / dedup rather than blind creation.
4. Never skip dedup just because an issue is being touched in plan mode, and never let multiple
   subagents race to create the same sub-issue.

## Query Gotcha

- For issue discovery / dedup, prefer:

```bash
linear issue query --team COD --search "关键词" --project 3a33cd7c7d0d --json
```

- Do not pass the search text as a bare positional tail after `linear issue query`.
  In this workspace the reliable filter is `--search`; bare text can be ignored or parsed
  unexpectedly and leads to false "no issue found" conclusions.
- `linear issue query` results are fuzzy-ranked, not exact-title matches. After every search,
  apply a local exact-title filter before deciding whether to reuse or create an issue.

## Companion Skills

- `planning-with-files`
  - Trigger: the repo requires `.codex/task_plan.md`, `.codex/progress.md`, and
    `.codex/findings.md` traceability alongside Linear issue tracking.
  - Input context: frozen task goal, issue title, acceptance criteria, and whether the task is
    read-only or implementation work.
  - Expected output: task-plan entries that reference the Linear issue id and keep the on-disk
    execution log aligned with the Linear progress history. After planning updates the on-disk
    plan, come back to `linear-cli` to mirror that plan into the main issue description.
- `code-review-with-logs`
  - Trigger: an active tracked task reaches completion, runtime failure, or test failure.
  - Input context: `hook_state.json`, task-scoped unit-test commands, changed paths, runtime logs,
    and the active `.codex_record/<session_id>/` files.
  - Expected output: an end-task hook review session under `.codex/reviews/<review_id>/` plus the
    standard report appended to `.codex_record/<session_id>/progress.md`.

## Available Commands

Compact command list, generated from `linear --help`:

```bash
linear auth
linear auth login
linear auth logout
linear auth list
linear auth default
linear auth token
linear auth whoami
linear auth migrate

linear issue
linear issue id
linear issue mine
linear issue query
linear issue title
linear issue start
linear issue view
linear issue url
linear issue describe
linear issue commits
linear issue pull-request
linear issue delete
linear issue create
linear issue update
linear issue comment
linear issue comment add
linear issue comment delete
linear issue comment update
linear issue comment list
linear issue attach
linear issue link
linear issue relation
linear issue relation add
linear issue relation delete
linear issue relation list
linear issue agent-session
linear issue agent-session list
linear issue agent-session view

linear team
linear team create
linear team delete
linear team list
linear team id
linear team autolinks
linear team members

linear project
linear project list
linear project view
linear project create
linear project update
linear project delete

linear project-update
linear project-update create
linear project-update list

linear cycle
linear cycle list
linear cycle view

linear milestone
linear milestone list
linear milestone view
linear milestone create
linear milestone update
linear milestone delete

linear initiative
linear initiative list
linear initiative view
linear initiative create
linear initiative archive
linear initiative update
linear initiative unarchive
linear initiative delete
linear initiative add-project
linear initiative remove-project

linear initiative-update
linear initiative-update create
linear initiative-update list

linear label
linear label list
linear label create
linear label delete

linear document
linear document list
linear document view
linear document create
linear document update
linear document delete

linear config

linear schema

linear api
```

## Reference Documentation

- [auth](references/auth.md) - Manage Linear authentication
- [issue](references/issue.md) - Manage Linear issues
- [team](references/team.md) - Manage Linear teams
- [project](references/project.md) - Manage Linear projects
- [project-update](references/project-update.md) - Manage project status updates
- [cycle](references/cycle.md) - Manage Linear team cycles
- [milestone](references/milestone.md) - Manage Linear project milestones
- [initiative](references/initiative.md) - Manage Linear initiatives
- [initiative-update](references/initiative-update.md) - Manage initiative status updates (timeline posts)
- [label](references/label.md) - Manage Linear issue labels
- [document](references/document.md) - Manage Linear documents
- [config](references/config.md) - Interactively generate .linear.toml configuration
- [schema](references/schema.md) - Print the GraphQL schema to stdout
- [api](references/api.md) - Make a raw GraphQL API request

For curated examples of organization features (initiatives, labels, projects, bulk operations), see [organization-features](references/organization-features.md).

## Discovering Options

To see available subcommands and flags, run `--help` on any command:

```bash
linear --help
linear issue --help
linear issue list --help
linear issue create --help
```

Each command has detailed help output describing all available flags and options.

Some commands have required flags that aren't obvious. Notable examples:

- `issue list` requires a sort order — provide it via `--sort` (valid values: `manual`, `priority`), the `issue_sort` config option, or the `LINEAR_ISSUE_SORT` env var. Also requires `--team <key>` unless the team can be inferred from the directory — if unknown, run `linear team list` first.
- `--no-pager` is only supported on `issue list` — passing it to other commands like `project list` will error.

## Repo Workflow Notes

- For simple repo task tracking, one Linear issue is usually enough:
  - let the start-task hook register or reuse the task issue,
  - create the task issue,
  - move it to `In Progress` when execution starts,
  - add at least one progress comment,
  - move it to `Done` when the report/review closes.
- `linear issue create` prints the created issue URL. Capture that URL or issue id immediately so
  follow-up `issue update` and `comment add` calls can stay scoped to the same task.
- For repos that split work into sub-issues, follow this exact sequence:
  - create or reuse the main issue in execution,
  - inspect `linear issue view <main> --json`,
  - dedupe sub-issues against `children.nodes` using exact Chinese titles,
  - reuse and update on match,
  - only then create any missing sub-issues.
- If the user did not specify a due date, set `--due-date` to the execution day by default.
- If the user did not specify a project, resolve `CoPR Midtrain` from `linear project list` and
  set `--project <resolved-slug>` by default.
- For low-risk CLI connectivity checks, prefer:

```bash
linear --version
linear auth whoami
linear team list
linear project list
```

These commands are read-only and avoid the extra `--sort` / `--team` requirements of
`linear issue list`.

## Using the Linear GraphQL API Directly

**Prefer the CLI for all supported operations.** The `api` command should only be used as a fallback for queries not covered by the CLI.

### Check the schema for available types and fields

Write the schema to a tempfile, then search it:

```bash
linear schema -o "${TMPDIR:-/tmp}/linear-schema.graphql"
grep -i "cycle" "${TMPDIR:-/tmp}/linear-schema.graphql"
grep -A 30 "^type Issue " "${TMPDIR:-/tmp}/linear-schema.graphql"
```

### Make a GraphQL request

**Important:** GraphQL queries containing non-null type markers (e.g. `String` followed by an exclamation mark) must be passed via heredoc stdin to avoid escaping issues. Simple queries without those markers can be passed inline.

```bash
# Simple query (no type markers, so inline is fine)
linear api '{ viewer { id name email } }'

# Query with variables — use heredoc to avoid escaping issues
linear api --variable teamId=abc123 <<'GRAPHQL'
query($teamId: String!) { team(id: $teamId) { name } }
GRAPHQL

# Search issues by text
linear api --variable term=onboarding <<'GRAPHQL'
query($term: String!) { searchIssues(term: $term, first: 20) { nodes { identifier title state { name } } } }
GRAPHQL

# Numeric and boolean variables
linear api --variable first=5 <<'GRAPHQL'
query($first: Int!) { issues(first: $first) { nodes { title } } }
GRAPHQL

# Complex variables via JSON
linear api --variables-json '{"filter": {"state": {"name": {"eq": "In Progress"}}}}' <<'GRAPHQL'
query($filter: IssueFilter!) { issues(filter: $filter) { nodes { title } } }
GRAPHQL

# Pipe to jq for filtering
linear api '{ issues(first: 5) { nodes { identifier title } } }' | jq '.data.issues.nodes[].title'
```

### Advanced: Using curl directly

For cases where you need full HTTP control, use `linear auth token`:

```bash
curl -s -X POST https://api.linear.app/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: $(linear auth token)" \
  -d '{"query": "{ viewer { id } }"}'
```
