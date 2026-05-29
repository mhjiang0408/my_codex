# Initialize planning files for a new session
# Usage: .\init-session.ps1 [project-name]

param(
    [string]$ProjectName = "project"
)

$DATE = Get-Date -Format "yyyy-MM-dd"
$WorkspaceRoot = if ($env:CODEX_WORKSPACE_ROOT) { $env:CODEX_WORKSPACE_ROOT } else {
    $gitRoot = git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and $gitRoot) { $gitRoot } else { (Get-Location).Path }
}
$PlanDir = Join-Path $WorkspaceRoot ".codex"
$TaskPlanFile = Join-Path $PlanDir "task_plan.md"
$FindingsFile = Join-Path $PlanDir "findings.md"
$ProgressFile = Join-Path $PlanDir "progress.md"

Write-Host "Initializing planning files for: $ProjectName"
New-Item -ItemType Directory -Path $PlanDir -Force | Out-Null

# Create .codex/task_plan.md if it doesn't exist
if (-not (Test-Path $TaskPlanFile)) {
    @"
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
| Error | Attempt | Resolution |
|-------|---------|------------|
"@ | Out-File -FilePath $TaskPlanFile -Encoding UTF8
    Write-Host "Created $TaskPlanFile"
} else {
    Write-Host "$TaskPlanFile already exists, skipping"
}

# Create .codex/findings.md if it doesn't exist
if (-not (Test-Path $FindingsFile)) {
    @"
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
"@ | Out-File -FilePath $FindingsFile -Encoding UTF8
    Write-Host "Created $FindingsFile"
} else {
    Write-Host "$FindingsFile already exists, skipping"
}

# Create .codex/progress.md if it doesn't exist
if (-not (Test-Path $ProgressFile)) {
    @"
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
"@ | Out-File -FilePath $ProgressFile -Encoding UTF8
    Write-Host "Created $ProgressFile"
} else {
    Write-Host "$ProgressFile already exists, skipping"
}

Write-Host ""
Write-Host "Planning files initialized!"
Write-Host "Files: $TaskPlanFile, $FindingsFile, $ProgressFile"
