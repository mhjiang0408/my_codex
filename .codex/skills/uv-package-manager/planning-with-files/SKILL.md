---
name: planning-with-files
description: Implements Manus-style file-based planning to organize and track progress on complex tasks. Creates .codex/task_plan.md, .codex/findings.md, and .codex/progress.md. Use when asked to plan out, break down, or organize a multi-step project, research task, or any work requiring >5 tool calls. Supports automatic session recovery after /clear.
user-invocable: true
allowed-tools: "Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch"
hooks:
  PreToolUse:
    - matcher: "Write|Edit|Bash|Read|Glob|Grep"
      hooks:
        - type: command
          command: "WORKSPACE_ROOT=\"${CODEX_WORKSPACE_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}\"; cat \"$WORKSPACE_ROOT/.codex/task_plan.md\" 2>/dev/null | head -30 || true"
  PostToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: "echo '[planning-with-files] File updated. If this completes a phase, update .codex/task_plan.md status.'"
  Stop:
    - hooks:
        - type: command
          command: |
            WORKSPACE_ROOT="${CODEX_WORKSPACE_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
            SKILL_DIR="${CODEX_SKILL_ROOT:-$WORKSPACE_ROOT/.codex/skills/planning-with-files}"
            SCRIPT_DIR="$SKILL_DIR/scripts"
            PLAN_FILE="${CODEX_PLAN_FILE:-$WORKSPACE_ROOT/.codex/task_plan.md}"

            IS_WINDOWS=0
            if [ "${OS-}" = "Windows_NT" ]; then
              IS_WINDOWS=1
            else
              UNAME_S="$(uname -s 2>/dev/null || echo '')"
              case "$UNAME_S" in
                CYGWIN*|MINGW*|MSYS*) IS_WINDOWS=1 ;;
              esac
            fi

            if [ "$IS_WINDOWS" -eq 1 ]; then
              if command -v pwsh >/dev/null 2>&1; then
                pwsh -ExecutionPolicy Bypass -File "$SCRIPT_DIR/check-complete.ps1" -PlanFile "$PLAN_FILE" 2>/dev/null ||
                powershell -ExecutionPolicy Bypass -File "$SCRIPT_DIR/check-complete.ps1" -PlanFile "$PLAN_FILE" 2>/dev/null ||
                sh "$SCRIPT_DIR/check-complete.sh" "$PLAN_FILE"
              else
                powershell -ExecutionPolicy Bypass -File "$SCRIPT_DIR/check-complete.ps1" -PlanFile "$PLAN_FILE" 2>/dev/null ||
                sh "$SCRIPT_DIR/check-complete.sh" "$PLAN_FILE"
              fi
            else
              sh "$SCRIPT_DIR/check-complete.sh" "$PLAN_FILE"
            fi
metadata:
  version: "2.16.2"
---

# Planning with Files

Work like Manus: Use persistent markdown files as your "working memory on disk."

## FIRST: Check for Previous Session (v2.2.0)

**Before starting work**, check for unsynced context from a previous session:

```bash
# Linux/macOS (auto-detects python3 or python)
WORKSPACE_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
$(command -v python3 || command -v python) "$WORKSPACE_ROOT/.codex/skills/planning-with-files/scripts/session-catchup.py" "$WORKSPACE_ROOT"
```

```powershell
# Windows PowerShell
$workspaceRoot = (git rev-parse --show-toplevel 2>$null)
if (-not $workspaceRoot) { $workspaceRoot = (Get-Location).Path }
python "$workspaceRoot\.codex\skills\planning-with-files\scripts\session-catchup.py" $workspaceRoot
```

If catchup report shows unsynced context:
1. Run `git diff --stat` to see actual code changes
2. Read current planning files
3. Update planning files based on catchup + git diff
4. Then proceed with task

## Important: Where Files Go

- **Templates** are in `.codex/skills/planning-with-files/templates/`
- **Your planning files** go in `.codex/` under your project root

| Location | What Goes There |
|----------|-----------------|
| Skill directory (`.codex/skills/planning-with-files/`) | Templates, scripts, reference docs |
| Project `.codex/` directory | `.codex/task_plan.md`, `.codex/findings.md`, `.codex/progress.md` |

## Quick Start

Before ANY complex task:

1. **Create `.codex/task_plan.md`** — Use [templates/task_plan.md](templates/task_plan.md) as reference
2. **Create `.codex/findings.md`** — Use [templates/findings.md](templates/findings.md) as reference
3. **Create `.codex/progress.md`** — Use [templates/progress.md](templates/progress.md) as reference
4. **Re-read plan before decisions** — Refreshes goals in attention window
5. **Update after each phase** — Mark complete, log errors

> **Note:** Planning files go in `.codex/` under your project root, not the skill installation folder.

## The Core Pattern

```
Context Window = RAM (volatile, limited)
Filesystem = Disk (persistent, unlimited)

→ Anything important gets written to disk.
```

## File Purposes

| File | Purpose | When to Update |
|------|---------|----------------|
| `.codex/task_plan.md` | Phases, progress, decisions | After each phase |
| `.codex/findings.md` | Research, discoveries | After ANY discovery |
| `.codex/progress.md` | Session log, test results | Throughout session |

## Critical Rules

### 1. Create Plan First
Never start a complex task without `.codex/task_plan.md`. Non-negotiable.

### 1.1 Explicit Dependencies For Parallel Agent Execution
When the implementation will be delegated across subagents or workers, the plan must include:
- an explicit dependency graph for every task,
- clear ownership for each worker/subagent,
- a statement that the main agent acts as orchestrator only,
- and a merge point that waits for all prerequisite tasks before synthesis/reporting.

Do not write vague phase lists like "analyze, summarize, report" when the real execution will be parallelized. The plan must be decision-complete enough that the main agent can dispatch workers immediately without re-planning.

### 2. The 2-Action Rule
> "After every 2 view/browser/search operations, IMMEDIATELY save key findings to text files."

This prevents visual/multimodal information from being lost.

### 3. Read Before Decide
Before major decisions, read the plan file. This keeps goals in your attention window.

### 4. Update After Act
After completing any phase:
- Mark phase status: `in_progress` → `complete`
- Log any errors encountered
- Note files created/modified

### 5. Log ALL Errors
Every error goes in the plan file. This builds knowledge and prevents repetition.

```markdown
## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| FileNotFoundError | 1 | Created default config |
| API timeout | 2 | Added retry logic |
```

### 6. Never Repeat Failures
```
if action_failed:
    next_action != same_action
```
Track what you tried. Mutate the approach.

### 7. Freeze User-Corrected Time Windows
If the user narrows or corrects a date/time scope during planning or execution, rewrite the active plan with the exact absolute window immediately.

Example:
- user first says "since 03-16"
- then clarifies "03-16 and 03-20 only"

Correct handling:
- update `.codex/task_plan.md` to the exact frozen windows
- reflect the same absolute dates in findings/progress/output docs
- do not silently continue using the broader relative interpretation

## The 3-Strike Error Protocol

```
ATTEMPT 1: Diagnose & Fix
  → Read error carefully
  → Identify root cause
  → Apply targeted fix

ATTEMPT 2: Alternative Approach
  → Same error? Try different method
  → Different tool? Different library?
  → NEVER repeat exact same failing action

ATTEMPT 3: Broader Rethink
  → Question assumptions
  → Search for solutions
  → Consider updating the plan

AFTER 3 FAILURES: Escalate to User
  → Explain what you tried
  → Share the specific error
  → Ask for guidance
```

## Read vs Write Decision Matrix

| Situation | Action | Reason |
|-----------|--------|--------|
| Just wrote a file | DON'T read | Content still in context |
| Viewed image/PDF | Write findings NOW | Multimodal → text before lost |
| Browser returned data | Write to file | Screenshots don't persist |
| Starting new phase | Read plan/findings | Re-orient if context stale |
| Error occurred | Read relevant file | Need current state to fix |
| Resuming after gap | Read all planning files | Recover state |

## The 5-Question Reboot Test

If you can answer these, your context management is solid:

| Question | Answer Source |
|----------|---------------|
| Where am I? | Current phase in `.codex/task_plan.md` |
| Where am I going? | Remaining phases |
| What's the goal? | Goal statement in plan |
| What have I learned? | `.codex/findings.md` |
| What have I done? | `.codex/progress.md` |

## When to Use This Pattern

**Use for:**
- Multi-step tasks (3+ steps)
- Research tasks
- Building/creating projects
- Tasks spanning many tool calls
- Anything requiring organization

**Skip for:**
- Simple questions
- Single-file edits
- Quick lookups

## Templates

Copy these templates to start:

- [templates/task_plan.md](templates/task_plan.md) — Phase tracking
- [templates/findings.md](templates/findings.md) — Research storage
- [templates/progress.md](templates/progress.md) — Session logging

## Scripts

Helper scripts for automation:

- `scripts/init-session.sh` — Initialize all planning files
- `scripts/check-complete.sh` — Verify all phases complete
- `scripts/session-catchup.py` — Recover context from previous session (v2.2.0)

## Companion Skills

Load companion skills only when the task reaches their trigger:

- `code-review-with-logs`
  - Trigger: the task reaches anchored review / final validation.
  - Pass in: `.codex/review_spec.md`, the intended anchor commit SHA, and the deliverable paths.
  - Expected output: `.codex/reviews/<review_id>/` artifacts with one commit-anchored verdict.
- `harness-bench`
  - Trigger: the task explicitly requires benchmark methodology, `tests/bench` work, or benchmark commands in `.codex/review_spec.md`.
  - Pass in: the benchmark question, explicit baselines, control variables, artifact path, and any env gate.
  - Expected output: a bounded benchmark design and auditable benchmark artifacts, or a documented decision that benchmark work is out of scope.

## Advanced Topics

- **Manus Principles:** See [references/reference.md](references/reference.md)
- **Real Examples:** See [references/examples.md](references/examples.md)

## Anti-Patterns

| Don't | Do Instead |
|-------|------------|
| Use TodoWrite for persistence | Create `.codex/task_plan.md` |
| State goals once and forget | Re-read plan before decisions |
| Hide errors and retry silently | Log errors to plan file |
| Stuff everything in context | Store large content in files |
| Start executing immediately | Create plan file FIRST |
| Repeat failed actions | Track attempts, mutate approach |
| Create files in skill directory | Create files in `.codex/` under your project |
