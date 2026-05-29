# Check if all phases in .codex/task_plan.md are complete
# Always exits 0 — uses stdout for status reporting
# Used by Stop hook to report task completion status

param(
    [string]$PlanFile = ""
)

if (-not $PlanFile) {
    $workspaceRoot = if ($env:CODEX_WORKSPACE_ROOT) { $env:CODEX_WORKSPACE_ROOT } else {
        $gitRoot = git rev-parse --show-toplevel 2>$null
        if ($LASTEXITCODE -eq 0 -and $gitRoot) { $gitRoot } else { (Get-Location).Path }
    }
    $PlanFile = Join-Path $workspaceRoot ".codex/task_plan.md"
}

if (-not (Test-Path $PlanFile)) {
    Write-Host "[planning-with-files] No .codex/task_plan.md found — no active planning session."
    exit 0
}

# Read file content
$content = Get-Content $PlanFile -Raw

# Count total phases
$TOTAL = ([regex]::Matches($content, "### Phase")).Count

# Check for **Status:** format first
$COMPLETE = ([regex]::Matches($content, "\*\*Status:\*\* complete")).Count
$IN_PROGRESS = ([regex]::Matches($content, "\*\*Status:\*\* in_progress")).Count
$PENDING = ([regex]::Matches($content, "\*\*Status:\*\* pending")).Count

# Fallback: check for [complete] inline format if **Status:** not found
if ($COMPLETE -eq 0 -and $IN_PROGRESS -eq 0 -and $PENDING -eq 0) {
    $COMPLETE = ([regex]::Matches($content, "\[complete\]")).Count
    $IN_PROGRESS = ([regex]::Matches($content, "\[in_progress\]")).Count
    $PENDING = ([regex]::Matches($content, "\[pending\]")).Count
}

# Report status (always exit 0 — incomplete task is a normal state)
if ($COMPLETE -eq $TOTAL -and $TOTAL -gt 0) {
    Write-Host "[planning-with-files] ALL PHASES COMPLETE ($COMPLETE/$TOTAL)"
} else {
    Write-Host "[planning-with-files] Task in progress ($COMPLETE/$TOTAL phases complete)"
    if ($IN_PROGRESS -gt 0) {
        Write-Host "[planning-with-files] $IN_PROGRESS phase(s) still in progress."
    }
    if ($PENDING -gt 0) {
        Write-Host "[planning-with-files] $PENDING phase(s) pending."
    }
}
exit 0
