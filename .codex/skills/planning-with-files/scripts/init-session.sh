#!/bin/bash
# Initialize planning files for a new session
# Usage: ./init-session.sh [project-name]

set -e

PROJECT_NAME="${1:-project}"
DATE=$(date +%Y-%m-%d)
WORKSPACE_ROOT="${CODEX_WORKSPACE_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PLAN_DIR="$WORKSPACE_ROOT/.codex"
TASK_PLAN_FILE="$PLAN_DIR/task_plan.md"
FINDINGS_FILE="$PLAN_DIR/findings.md"
PROGRESS_FILE="$PLAN_DIR/progress.md"

echo "Initializing planning files for: $PROJECT_NAME"
mkdir -p "$PLAN_DIR"

# Create .codex/task_plan.md if it doesn't exist
if [ ! -f "$TASK_PLAN_FILE" ]; then
    cat > "$TASK_PLAN_FILE" << 'EOF'
# Task Plan: [Brief Description]

## Goal
[One sentence describing the end state]

## Current Phase
Phase 1

## Phases

### Phase 1: Requirements & Discovery
- [ ] Understand user intent
- [ ] Identify constraints
- [ ] Document in .codex/findings.md
- **Status:** in_progress

### Phase 2: Planning & Structure
- [ ] Define approach
- [ ] Create project structure
- **Status:** pending

### Phase 3: Implementation
- [ ] Execute the plan
- [ ] Write to files before executing
- **Status:** pending

### Phase 4: Testing & Verification
- [ ] Verify requirements met
- [ ] Document test results
- **Status:** pending

### Phase 5: Delivery
- [ ] Review outputs
- [ ] Deliver to user
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|

## Errors Encountered
| Error | Resolution |
|-------|------------|
EOF
    echo "Created $TASK_PLAN_FILE"
else
    echo "$TASK_PLAN_FILE already exists, skipping"
fi

# Create .codex/findings.md if it doesn't exist
if [ ! -f "$FINDINGS_FILE" ]; then
    cat > "$FINDINGS_FILE" << 'EOF'
# Findings & Decisions

## Requirements
-

## Research Findings
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-
EOF
    echo "Created $FINDINGS_FILE"
else
    echo "$FINDINGS_FILE already exists, skipping"
fi

# Create .codex/progress.md if it doesn't exist
if [ ! -f "$PROGRESS_FILE" ]; then
    cat > "$PROGRESS_FILE" << EOF
# Progress Log

## Session: $DATE

### Current Status
- **Phase:** 1 - Requirements & Discovery
- **Started:** $DATE

### Actions Taken
-

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|
EOF
    echo "Created $PROGRESS_FILE"
else
    echo "$PROGRESS_FILE already exists, skipping"
fi

echo ""
echo "Planning files initialized!"
echo "Files: $TASK_PLAN_FILE, $FINDINGS_FILE, $PROGRESS_FILE"
