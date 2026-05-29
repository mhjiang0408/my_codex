#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  migrate_codex_hooks.sh [--source PATH] [--dry-run] [--no-backup] [--force] TARGET_WORKSPACE

Migrates only:
  - .codex/skills/
  - .codex/config.toml
  - .codex/auth.json
  - AGENTS.md

Options:
  --source PATH   Source workspace. Defaults to the current git root or cwd.
  --dry-run       Print actions without changing the target workspace.
  --no-backup     Overwrite target paths without creating .codex_migration_backup.
  --force         Allow a target workspace that is not a git repository.
  -h, --help      Show this help.
EOF
}

log() {
  printf '[migrate-codex-hooks] %s\n' "$*"
}

die() {
  printf '[migrate-codex-hooks] ERROR: %s\n' "$*" >&2
  exit 1
}

make_abs() {
  local path="$1"
  if [ -d "$path" ]; then
    (cd "$path" && pwd -P)
  else
    local parent
    parent="$(dirname "$path")"
    local base
    base="$(basename "$path")"
    (cd "$parent" && printf '%s/%s\n' "$(pwd -P)" "$base")
  fi
}

copy_path() {
  local source_path="$1"
  local target_path="$2"
  if [ "$DRY_RUN" -eq 1 ]; then
    log "would copy ${source_path#$SOURCE_ROOT/} -> ${target_path#$TARGET_ROOT/}"
    return
  fi
  rm -rf "$target_path"
  mkdir -p "$(dirname "$target_path")"
  cp -a "$source_path" "$target_path"
}

backup_existing_path() {
  local relative_path="$1"
  local target_path="$TARGET_ROOT/$relative_path"
  [ -e "$target_path" ] || return 0
  if [ "$NO_BACKUP" -eq 1 ]; then
    log "backup disabled for $relative_path"
    return 0
  fi
  local backup_path="$BACKUP_ROOT/$relative_path"
  if [ "$DRY_RUN" -eq 1 ]; then
    log "would backup $relative_path -> ${backup_path#$TARGET_ROOT/}"
    return 0
  fi
  mkdir -p "$(dirname "$backup_path")"
  rm -rf "$backup_path"
  cp -a "$target_path" "$backup_path"
  log "backed up $relative_path -> ${backup_path#$TARGET_ROOT/}"
}

require_source_path() {
  local relative_path="$1"
  [ -e "$SOURCE_ROOT/$relative_path" ] || die "missing source path: $relative_path"
}

require_target_file_contains() {
  local relative_path="$1"
  local needle="$2"
  local label="$3"
  local path="$TARGET_ROOT/$relative_path"
  [ -f "$path" ] || die "missing target file for $label: $relative_path"
  grep -Fq "$needle" "$path" || die "target $label does not contain expected text: $needle"
}

validate_target() {
  [ -d "$TARGET_ROOT/.codex/skills" ] || die "missing target .codex/skills"
  [ -f "$TARGET_ROOT/.codex/config.toml" ] || die "missing target .codex/config.toml"
  [ -f "$TARGET_ROOT/.codex/auth.json" ] || die "missing target .codex/auth.json"
  [ -f "$TARGET_ROOT/AGENTS.md" ] || die "missing target AGENTS.md"

  require_target_file_contains ".codex/skills/linear-cli/SKILL.md" "PreToolUse:" "linear-cli hook"
  require_target_file_contains ".codex/skills/linear-cli/SKILL.md" "start_task_hook.sh" "linear-cli hook"
  require_target_file_contains ".codex/skills/planning-with-files/SKILL.md" "PostToolUse:" "planning hook"
  require_target_file_contains ".codex/skills/planning-with-files/SKILL.md" "Stop:" "planning hook"
  require_target_file_contains ".codex/skills/code-review-with-logs/SKILL.md" "Stop:" "review hook"
  require_target_file_contains ".codex/skills/code-review-with-logs/SKILL.md" "end_task_review_hook.sh" "review hook"
  require_target_file_contains ".codex/config.toml" "[features]" "config"
  require_target_file_contains ".codex/config.toml" "skills = true" "config"
  require_target_file_contains "AGENTS.md" "linear-cli" "AGENTS"
  require_target_file_contains "AGENTS.md" "code-review-with-logs" "AGENTS"
  require_target_file_contains "AGENTS.md" ".codex_record/<CODEX_THREAD_ID>/" "AGENTS"

  local executable_scripts=(
    ".codex/skills/linear-cli/scripts/start_task_hook.sh"
    ".codex/skills/code-review-with-logs/scripts/end_task_review_hook.sh"
    ".codex/skills/code-review-with-logs/scripts/run_code_review_with_logs.sh"
    ".codex/skills/planning-with-files/scripts/check-complete.sh"
  )
  local script
  for script in "${executable_scripts[@]}"; do
    [ -f "$TARGET_ROOT/$script" ] || die "missing target hook script: $script"
    [ -x "$TARGET_ROOT/$script" ] || die "target hook script is not executable: $script"
  done
}

SOURCE_ARG=""
DRY_RUN=0
NO_BACKUP=0
FORCE=0
TARGET_ARG=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source)
      [ "$#" -ge 2 ] || die "--source requires a path"
      SOURCE_ARG="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-backup)
      NO_BACKUP=1
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      if [ -n "$TARGET_ARG" ]; then
        die "multiple target workspaces provided: $TARGET_ARG and $1"
      fi
      TARGET_ARG="$1"
      shift
      ;;
  esac
done

if [ "$#" -gt 0 ]; then
  if [ -n "$TARGET_ARG" ]; then
    die "multiple target workspaces provided"
  fi
  TARGET_ARG="$1"
fi

[ -n "$TARGET_ARG" ] || die "TARGET_WORKSPACE is required"

if [ -n "$SOURCE_ARG" ]; then
  [ -d "$SOURCE_ARG" ] || die "source workspace does not exist: $SOURCE_ARG"
  SOURCE_ROOT="$(make_abs "$SOURCE_ARG")"
else
  if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    SOURCE_ROOT="$(make_abs "$git_root")"
  else
    SOURCE_ROOT="$(pwd -P)"
  fi
fi

[ -d "$TARGET_ARG" ] || die "target workspace does not exist: $TARGET_ARG"
TARGET_ROOT="$(make_abs "$TARGET_ARG")"

[ "$SOURCE_ROOT" != "$TARGET_ROOT" ] || die "source and target workspaces are the same"

if [ "$FORCE" -ne 1 ] && ! git -C "$TARGET_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
  die "target workspace is not a git repository; pass --force to allow this"
fi

require_source_path ".codex/skills"
require_source_path ".codex/config.toml"
require_source_path ".codex/auth.json"
require_source_path "AGENTS.md"

STAMP="${CODEX_MIGRATION_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
BACKUP_ROOT="$TARGET_ROOT/.codex_migration_backup/$STAMP"

log "source: $SOURCE_ROOT"
log "target: $TARGET_ROOT"
if [ "$DRY_RUN" -eq 1 ]; then
  log "dry-run enabled; no target files will be changed"
fi

migration_paths=(
  ".codex/skills"
  ".codex/config.toml"
  ".codex/auth.json"
  "AGENTS.md"
)

for relative_path in "${migration_paths[@]}"; do
  backup_existing_path "$relative_path"
done

for relative_path in "${migration_paths[@]}"; do
  copy_path "$SOURCE_ROOT/$relative_path" "$TARGET_ROOT/$relative_path"
done

if [ "$DRY_RUN" -eq 1 ]; then
  log "dry-run complete"
  exit 0
fi

chmod +x \
  "$TARGET_ROOT/.codex/skills/linear-cli/scripts/start_task_hook.sh" \
  "$TARGET_ROOT/.codex/skills/code-review-with-logs/scripts/end_task_review_hook.sh" \
  "$TARGET_ROOT/.codex/skills/code-review-with-logs/scripts/run_code_review_with_logs.sh" \
  "$TARGET_ROOT/.codex/skills/planning-with-files/scripts/check-complete.sh"

validate_target

cat <<EOF
[migrate-codex-hooks] migration complete
[migrate-codex-hooks] backup: ${BACKUP_ROOT#$TARGET_ROOT/}
[migrate-codex-hooks] suggested validation from target workspace:
  linear --version
  .codex/skills/linear-cli/scripts/start_task_hook.sh --workspace . --objective "迁移钩子冒烟验证" --issue-title "迁移钩子冒烟验证" --dry-run
  python .codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/linear-cli
  python .codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/planning-with-files
  python .codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/code-review-with-logs
EOF
