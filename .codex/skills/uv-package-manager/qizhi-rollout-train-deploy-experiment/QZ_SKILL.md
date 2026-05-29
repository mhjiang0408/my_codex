# QZ / myqz Notes For `qizhi-rollout-train-deploy-experiment`

This file records the `myqz` facts that this skill depends on.

## Source Of Truth
- `myqz` repo: `/inspire/hdd/project/qproject-fundationmodel/public/mhjiang/myqz`
- CLI executable name: `qz`
- Relevant modules:
  - `src/qz/cli.py`
  - `src/qz/api.py`
  - `src/qz/avail.py`
  - `src/qz/deploy.py`
  - `src/qz/config.py`

## QZ Skill Routing
- Load companion skills on demand; do not read all QZ skills up front when only one of them matches the current subproblem.

| Need | Skill | Expected result |
|---|---|---|
| End-to-end rollout/train/deploy orchestration | `qizhi-rollout-train-deploy-experiment` | The workflow state machine and its task-specific control flow |
| `qz` CLI syntax, config semantics, command mapping, pool/type usage | `qz-guide` | Exact commands, flags, and config constraints |
| WebUI/API reverse engineering, page-derived IDs, browser replay fallback | `qz-browser` | IDs, endpoints, payloads, replay steps, and platform gotchas |
| Repeated project-specific QZ flows that should become `qzx` wrappers/templates | `qz-customize` | Reusable project tooling design or implementation path |

## Output Contract
- All `qz` commands print JSON to stdout.
- Errors are emitted as `{"error": "..."}` and exit non-zero.
- Always check exit code before parsing stdout.
- `--raw` should be used when the orchestrator needs platform-shaped detail payloads instead of the curated brief output.
- `qz pools` returns JSON items keyed by `pool`, with `type`, `workspace_id`, and `lcg_id`.
- `qz avail` returns per-pool availability entries keyed by `pool`; GPU pools include ranking signals such as `tier` and free-node / free-gpu counters.

## Auth And Runtime
- `qz login` refreshes both token and cookie state.
- Credentials come from env vars:
  - `QZ_API_USERNAME`
  - `QZ_API_PASSWORD`
  - `QZ_COOKIE_USERNAME`
  - `QZ_COOKIE_PASSWORD`
- Config path defaults to `~/.config/qz/config.toml`.
- Auth cache defaults to `~/.cache/qz/auth.json`.
- The orchestrator may override config/cache roots via `QZ_CONFIG_DIR` and `QZ_CACHE_DIR`.

## Commands Used By This Skill
- Capacity:
  - `qz pools`
  - `qz avail --type <type> --nodes <n>`
- Training:
  - `qz job create ...`
  - `qz job status <job_id> --raw`
  - `qz job wait <job_id> --interval <seconds> --timeout <seconds>`
  - `qz job logs <job_id> --worker 0 --lines 100`
- Deployment:
  - `qz deploy create ...`
  - `qz deploy status <serving_id> --raw`
  - `qz deploy wait <serving_id> --interval <seconds> --timeout <seconds>`
  - `qz deploy logs <serving_id> --replica 0 --worker 0 --lines 100`

## Old -> New Mapping
- `qzcli train create` -> `qz job create`
- `qzcli train get` -> `qz job status --raw`
- `qzcli logs <job_id>` -> `qz job logs <job_id> --worker 0 --lines 100`
- `qzcli deploy create` -> `qz deploy create`
- `qzcli deploy get` -> `qz deploy status --raw`
- `qzcli deploy logs <serving_id>` -> `qz deploy logs <serving_id> --replica 0 --worker 0 --lines 100`
- `qzcli avail` -> `qz avail`
- `qzcli usage` -> no direct replacement
- Legacy alias compatibility is documentation-only; the orchestrator must not shell out to `qzcli`.

## User-Corrected Migration Rules
- Do not add or emulate `usage` in this skill.
- All capacity scan, submit precheck, and monitor snapshots must use `qz avail`.
- Use `pool` to lock the workspace first, then use `type` to filter or rank candidate pools.
- Do not emit or document a `qz_usage_snapshot`-style event after migration.

## Pool And Type Semantics
- Pools live in qz config; each pool alias already carries:
  - `workspace_id`
  - `logic_compute_group_id`
  - `type`
- `qz avail` supports `--type`, not `--pool`.
- `qz pools` is the canonical operator-facing way to inspect those configured aliases before orchestration.
- Therefore the migration pattern is:
  1. enumerate candidate pool aliases from qz config,
  2. resolve workspace with pool metadata first,
  3. run `qz avail` for the chosen `type`,
  4. filter the returned availability list back to the desired pool alias.

This rule is mandatory for this skill and replaces the old `qzcli res -u/-l` cache model.

## Notes About Missing `usage`
- `myqz` currently exposes no `qz usage` command.
- This skill must not claim:
  - workspace running task count
  - workspace GPU-in-use count
- Monitoring claims must be limited to:
  - pool availability snapshots
  - capacity warnings
  - train/deploy status polling

## Command Examples
```bash
source .codex/skills/qizhi-rollout-train-deploy-experiment/env.sh
qz login
qz pools
qz avail --type h200 --nodes 1
qz job status <job_id> --raw
qz deploy status <serving_id> --raw
```

## Recommended Validation
- `qz login`
- `qz pools`
- `qz avail --type <type> --nodes <required_nodes>`
- `qz job status <job_id> --raw`
- `qz deploy status <serving_id> --raw`
