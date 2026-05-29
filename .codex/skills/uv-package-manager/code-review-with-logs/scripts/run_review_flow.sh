#!/usr/bin/env bash
set -uo pipefail

SPEC_PATH=".codex/review_spec.md"
WORKSPACE="."
REVIEW_TARGET_SHA=""
REVIEW_ID=""
ROOT_REVIEW_ID=""
OWNER_ID="run-review-flow"
OWNER_LABEL="run-review-flow"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --spec)
      SPEC_PATH="$2"
      shift 2
      ;;
    --workspace)
      WORKSPACE="$2"
      shift 2
      ;;
    --review-target-sha)
      REVIEW_TARGET_SHA="$2"
      shift 2
      ;;
    --review-id)
      REVIEW_ID="$2"
      shift 2
      ;;
    --root-review-id)
      ROOT_REVIEW_ID="$2"
      shift 2
      ;;
    --owner-id)
      OWNER_ID="$2"
      shift 2
      ;;
    --owner-label)
      OWNER_LABEL="$2"
      shift 2
      ;;
    --retarget-attempt)
      echo "[WARN] --retarget-attempt is ignored in anchor-commit review mode"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--spec <path>] [--workspace <path>] [--review-target-sha <sha>] [--review-id <id>] [--root-review-id <id>] [--owner-id <id>] [--owner-label <label>]" >&2
      exit 2
      ;;
  esac
done

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ABS="$(cd "$WORKSPACE" && pwd)"

sanitize_review_id() {
  python - "$SKILL_ROOT" "$1" <<'PY'
import importlib.util
import sys
from pathlib import Path

skill_root = Path(sys.argv[1])
review_id = sys.argv[2]
module_path = skill_root / "review_session.py"
spec = importlib.util.spec_from_file_location("review_session", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None
assert spec.loader is not None
spec.loader.exec_module(module)
print(module.sanitize_review_id(review_id))
PY
}

resolve_session_review_target_sha() {
  python - "$WORKSPACE_ABS" "$1" <<'PY'
import json
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
review_id = sys.argv[2]
session_dir = workspace / ".codex" / "reviews" / review_id

candidates = (
    session_dir / "session.json",
    session_dir / "review_result_report.json",
    session_dir / "validation_results.json",
    session_dir / "test_results.json",
    session_dir / "benchmark_results.json",
)

for candidate in candidates:
    if not candidate.is_file():
        continue
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        continue
    value = payload.get("review_target_sha")
    if isinstance(value, str) and value.strip():
        print(value.strip())
        raise SystemExit(0)
PY
}

inspect_review_target_state() {
  python - "$SKILL_ROOT" "$WORKSPACE_ABS" "$SPEC_PATH" "$1" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

skill_root = Path(sys.argv[1])
workspace = Path(sys.argv[2])
spec_arg = Path(sys.argv[3])
requested = sys.argv[4]
if not spec_arg.is_absolute():
    spec_path = (workspace / spec_arg).resolve()
else:
    spec_path = spec_arg.resolve()

module_path = skill_root / "validate_naming_and_outputs.py"
spec = importlib.util.spec_from_file_location("validator", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None
assert spec.loader is not None
spec.loader.exec_module(module)

deliverable_section = ""
if spec_path.is_file():
    sections = module.parse_sections(spec_path.read_text(encoding="utf-8"))
    deliverable_section = sections.get("final_deliverables", "")

requested_sha = module.resolve_revision_sha(workspace, requested or "HEAD")
head_sha = module.resolve_head_sha(workspace)
focus_paths = module.extract_codex_focus_paths(workspace, deliverable_section)
diverged = module.list_committed_focus_path_differences(
    workspace,
    base_revision=requested_sha,
    current_revision=head_sha,
    focus_paths=focus_paths,
)
dirty_focus_paths = module.list_dirty_focus_paths(workspace, focus_paths)
print(
    json.dumps(
        {
            "requested_review_target_sha": requested_sha,
            "head_sha": head_sha,
            "dirty_focus_paths": dirty_focus_paths,
            "committed_diverged_focus_paths": diverged,
        }
    )
)
PY
}

target_has_drift() {
  local phase_label="$1"
  local state_json
  state_json="$(inspect_review_target_state "$REVIEW_TARGET_SHA")"
  local head_sha
  local dirty_paths
  local diverged_paths
  head_sha="$(python - "$state_json" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
print(payload.get("head_sha") or "")
PY
)"
  dirty_paths="$(python - "$state_json" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
paths = payload.get("dirty_focus_paths") or []
print(", ".join(paths))
PY
)"
  diverged_paths="$(python - "$state_json" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
paths = payload.get("committed_diverged_focus_paths") or []
print(", ".join(paths))
PY
)"
  if [[ -n "$dirty_paths" || -n "$diverged_paths" ]]; then
    echo "[WARN] review_target_drift_detected phase=$phase_label review_target_sha=$REVIEW_TARGET_SHA head=$head_sha"
    if [[ -n "$dirty_paths" ]]; then
      echo "[WARN] dirty_focus_paths=$dirty_paths"
    fi
    if [[ -n "$diverged_paths" ]]; then
      echo "[WARN] committed_diverged_focus_paths=$diverged_paths"
    fi
    return 0
  fi
  return 1
}

if [[ -n "$REVIEW_ID" ]]; then
  REVIEW_ID="$(sanitize_review_id "$REVIEW_ID")"
fi

if [[ -n "$ROOT_REVIEW_ID" ]]; then
  ROOT_REVIEW_ID="$(sanitize_review_id "$ROOT_REVIEW_ID")"
fi

if [[ -z "$REVIEW_TARGET_SHA" && -n "$REVIEW_ID" ]]; then
  REVIEW_TARGET_SHA="$(resolve_session_review_target_sha "$REVIEW_ID")"
fi

if [[ -z "$REVIEW_TARGET_SHA" ]]; then
  REVIEW_TARGET_SHA="$(git -C "$WORKSPACE_ABS" rev-parse HEAD 2>/dev/null || true)"
fi

readonly REVIEW_TARGET_SHA

if [[ -z "$REVIEW_ID" ]]; then
  REVIEW_ID="$(python - "$SKILL_ROOT" "$WORKSPACE_ABS" "${REVIEW_TARGET_SHA:-HEAD}" <<'PY'
import importlib.util
import sys
from pathlib import Path

skill_root = Path(sys.argv[1])
workspace = Path(sys.argv[2])
target = sys.argv[3]
module_path = skill_root / "review_session.py"
spec = importlib.util.spec_from_file_location("review_session", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None
assert spec.loader is not None
spec.loader.exec_module(module)
print(module.generate_review_id(target))
PY
)"
fi

REVIEW_ID="$(sanitize_review_id "$REVIEW_ID")"
if [[ -z "$ROOT_REVIEW_ID" ]]; then
  ROOT_REVIEW_ID="$REVIEW_ID"
fi
SESSION_REVIEW_TARGET_SHA="$REVIEW_TARGET_SHA"

SESSION_DIR="$WORKSPACE_ABS/.codex/reviews/$REVIEW_ID"
RUN_LOG="$SESSION_DIR/review_run.log"
SUMMARY="$SESSION_DIR/review_summary.md"
VALIDATION_JSON="$SESSION_DIR/validation_results.json"
TEST_JSON="$SESSION_DIR/test_results.json"
BENCHMARK_JSON="$SESSION_DIR/benchmark_results.json"
REPRO_MD="$SESSION_DIR/repro_steps.md"
REPRO_JSON="$SESSION_DIR/repro_results.json"
REPORT_RESULT_JSON="$SESSION_DIR/review_result_report.json"
SESSION_METADATA_JSON="$SESSION_DIR/session.json"

mkdir -p "$SESSION_DIR"
: > "$RUN_LOG"
: > "$SUMMARY"
: > "$REPRO_MD"

python - "$SESSION_METADATA_JSON" "$REVIEW_ID" "$ROOT_REVIEW_ID" "$SESSION_REVIEW_TARGET_SHA" "$WORKSPACE_ABS" "$SPEC_PATH" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {}
if path.is_file():
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(existing, dict):
            payload.update(existing)
    except Exception:
        pass

payload.update(
    {
        "review_id": sys.argv[2],
        "root_review_id": sys.argv[3],
        "review_target_sha": sys.argv[4],
        "workspace": sys.argv[5],
        "spec": sys.argv[6],
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY

exec > >(tee -a "$RUN_LOG") 2>&1

echo "[INFO] $(date -u +"%Y-%m-%dT%H:%M:%SZ") Starting code-review-with-logs flow"
echo "[INFO] workspace=$WORKSPACE_ABS"
echo "[INFO] spec=$SPEC_PATH"
echo "[INFO] review_id=$REVIEW_ID"
echo "[INFO] root_review_id=$ROOT_REVIEW_ID"
echo "[INFO] session_dir=$SESSION_DIR"
echo "[INFO] review_target_sha=${REVIEW_TARGET_SHA:-HEAD}"
echo "[INFO] review_target_mode=single_anchored_commit"
echo "[INFO] review_steps=deliverables_then_tests"

report_review_result() {
  local original_rc="$1"
  python "$SKILL_ROOT/report_review_result.py" \
    --workspace "$WORKSPACE_ABS" \
    --review-id "$REVIEW_ID" \
    --root-review-id "$ROOT_REVIEW_ID" \
    --validation-json "$VALIDATION_JSON" \
    --summary "$SUMMARY" \
    --output-json "$REPORT_RESULT_JSON" \
    --review-target-sha "${SESSION_REVIEW_TARGET_SHA:-HEAD}" \
    --exit-code "$original_rc" || true
}

_report_on_exit() {
  local rc="$?"
  report_review_result "$rc"
}

trap _report_on_exit EXIT

run_validator_phase() {
  local phase="$1"
  python "$SKILL_ROOT/validate_naming_and_outputs.py" \
    --phase "$phase" \
    --workspace "$WORKSPACE_ABS" \
    --spec "$SPEC_PATH" \
    --review-id "$REVIEW_ID" \
    --summary "$SUMMARY" \
    --run-log "$RUN_LOG" \
    --validation-json "$VALIDATION_JSON" \
    --test-results-json "$TEST_JSON" \
    --benchmark-results-json "$BENCHMARK_JSON" \
    --repro-results-json "$REPRO_JSON" \
    --review-target-sha "${SESSION_REVIEW_TARGET_SHA:-HEAD}"
}

emit_blocked_test_results() {
  local blocked_summary="$1"
  python - "$TEST_JSON" "$BENCHMARK_JSON" "$SESSION_REVIEW_TARGET_SHA" "$blocked_summary" <<'PY'
import json
import sys
from pathlib import Path

test_json = Path(sys.argv[1])
benchmark_json = Path(sys.argv[2])
review_target_sha = sys.argv[3]
details = sys.argv[4]

blocked_payload = {
    "status": "BLOCKED",
    "details": details,
    "failed_items": [],
    "results": [],
    "command_count": 0,
    "review_target_sha": review_target_sha,
}
test_json.parent.mkdir(parents=True, exist_ok=True)
test_json.write_text(json.dumps(blocked_payload, ensure_ascii=False, indent=2), encoding="utf-8")

benchmark_payload = {
    "required": False,
    "status": "NOT_REQUESTED",
    "details": "Benchmark validation was not requested because functional review stopped before benchmark execution.",
    "failed_items": [],
    "results": [],
    "command_count": 0,
    "review_target_sha": review_target_sha,
}
benchmark_json.parent.mkdir(parents=True, exist_ok=True)
benchmark_json.write_text(json.dumps(benchmark_payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY
}

finalize_and_exit() {
  run_validator_phase finalize
  local final_validate_rc=$?
  echo "[INFO] final_validate_rc=$final_validate_rc"
  echo "[INFO] summary=$SUMMARY"
  echo "[INFO] validation_json=$VALIDATION_JSON"
  echo "[INFO] report_result_json=$REPORT_RESULT_JSON"
  exit "$final_validate_rc"
}

run_validator_phase deliverables
DELIVERABLE_RC=$?
echo "[INFO] deliverable_phase_rc=$DELIVERABLE_RC"
if [[ "$DELIVERABLE_RC" -ne 0 ]]; then
  exit "$DELIVERABLE_RC"
fi

if target_has_drift "pre_tests"; then
  emit_blocked_test_results "Review deliverables changed after the anchored review target commit before tests started."
  finalize_and_exit
fi

run_validator_phase tests
TEST_PHASE_RC=$?
echo "[INFO] test_phase_rc=$TEST_PHASE_RC"
if [[ "$TEST_PHASE_RC" -ne 0 ]]; then
  exit "$TEST_PHASE_RC"
fi

if target_has_drift "post_tests"; then
  finalize_and_exit
fi

finalize_and_exit
