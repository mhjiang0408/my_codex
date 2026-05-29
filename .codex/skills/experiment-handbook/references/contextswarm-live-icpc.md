# ContextSwarm Live ICPC Runs

## Purpose

Run the paper-faithful ContextSwarm ICPC path: live contexts scheduled by the controller,
AISW-wrapped Codex workers, and judge-backed ICPC scoring. This method does not validate the
auxiliary public replay path.

## Preconditions

- Run local Python commands through `uv run python`.
- `codex` is available on `PATH`.
- AISW shim is executable at the configured `aisw.shim_binary`, default `~/.local/bin/aisw`.
- AISW node config exists and parses as TOML at the configured `aisw.node_config`, default
  `~/.aisw-codex/node.toml`.
- ContextSwarmJudge ICPC package root exists at the configured `judge.icpc_package_root`, default
  `/home/ubuntu/scratch/jingao/ContextSwarmJudge/packages` in the checked-in ICPC fixture config.
- ContextSwarmJudge serves `/healthz` and `/api/judge/evaluate` at the configured endpoint,
  default `http://127.0.0.1:8081/api/judge/evaluate`.
- The ICPC repo surface is available, for example `/tmp/openai-icpc-2025`.

Do not record secrets, private tokens, or one-off private endpoints in tracked configs.

## Artifact Location Contract

- Live ICPC readiness and run commands default to persistent run directories under
  `data/swarm_YYYYMMDDTHHMMSSZ/`.
- Do not use `/tmp` for final controller, gateway, worker, or judge artifacts. Temporary
  artifact directories are only for local debugging and require the explicit
  `--allow-ephemeral-artifact-dir` flag.
- A completed run's controller trajectory is `controller_react_trace.jsonl` inside the same
  `data/swarm_*` directory as `live_context_report.json`, `controller_state_machine.json`,
  worker sessions, gateway ledgers, and score-time telemetry.
- The 2026-05-28 live ICPC run was backfilled from `/tmp/contextswarm_live_full_current` to
  `data/swarm_20260528T144359Z/`; the `/tmp` copy is not the durable location.

## API Profiles: live gateway upstreams

Use these profiles for `run-icpc --runtime live_context` controller/gateway runs. The live path
does not use replay-only `--backend-model`, `--backend-base-url`, or `--backend-api-key` flags.
For live workers, set the upstream with the gateway flags and set the worker-facing model through
the experiment config's `[runtime].model`.

### Profile: GPT-5.5 local upstream
- Model name: `gpt-5.5`.
- Gateway upstream URL: `http://127.0.0.1:18081/v1`.
- Auth source: `.codex/auth.json#OPENAI_API_KEY` or another operator secret-store export; never
  record or print the raw key value.
- Config requirement:
  ```toml
  [runtime]
  model = "gpt-5.5"
  ```
- Command flags:
  ```bash
  --gateway-upstream-url http://127.0.0.1:18081/v1 \
  --gateway-upstream-auth-json .codex/auth.json \
  --gateway-upstream-key-field OPENAI_API_KEY
  ```
- Wire API note: the current live gateway preflight probes `/preflight-worker/v1/responses`.
  Keep the default `responses` wire API unless the upstream profile is explicitly validated with
  another OpenAI-compatible request shape.

### Profile: GLM-5.1 remote upstream
- Model name: `GLM-5.1`.
- Gateway upstream URL: `https://glm51-instruct.openapi-qb-ai.sii.edu.cn/v1`.
- Auth source: an operator-provided temporary auth JSON or secret-store export; never commit,
  paste, log, or print the raw API key. Prefer a separate field such as `GLM_API_KEY` instead of
  reusing the GPT-5.5 field name.
- Config requirement: derive a GLM-specific experiment config from the active paper ICPC config
  and set only the worker model field unless another runtime change is intentionally being tested.
  ```toml
  [runtime]
  model = "GLM-5.1"
  ```
  - Readiness command shape:
  ```bash
  uv run python -m contextswarm.cli live-icpc-readiness \
    --repo /tmp/openai-icpc-2025 \
    --experiment-config <paper-icpc-config-glm51.toml> \
    --icpc-package-root legacy/ContextSwarm/icpc_wf_2025 \
    --icpc-judge-endpoint http://127.0.0.1:8081/api/judge/evaluate \
    --gateway-base-url http://127.0.0.1:8080/v1 \
    --official-eval-base-url http://127.0.0.1:8080/v1 \
    --gateway-project-rpm-limit 64 \
    --gateway-upstream-url https://glm51-instruct.openapi-qb-ai.sii.edu.cn/v1 \
    --gateway-upstream-auth-json <operator-secret-auth.json> \
    --gateway-upstream-key-field GLM_API_KEY
  ```
- Launch command shape:
  ```bash
  uv run python -m contextswarm.cli run-icpc \
    --repo /tmp/openai-icpc-2025 \
    --runtime live_context \
    --experiment-config <paper-icpc-config-glm51.toml> \
    --require-ready \
    --task-limit 12 \
    --icpc-package-root legacy/ContextSwarm/icpc_wf_2025 \
    --icpc-judge-endpoint http://127.0.0.1:8081/api/judge/evaluate \
    --gateway-base-url http://127.0.0.1:8080/v1 \
    --official-eval-base-url http://127.0.0.1:8080/v1 \
    --gateway-project-rpm-limit 64 \
    --gateway-upstream-url https://glm51-instruct.openapi-qb-ai.sii.edu.cn/v1 \
    --gateway-upstream-auth-json <operator-secret-auth.json> \
    --gateway-upstream-key-field GLM_API_KEY
  ```
- Wire API note: first run readiness with the existing `responses` preflight. The Codex version
  used by this workspace currently rejects `model_providers.gateway.wire_api="chat_completions"`
  with a config parse error, so do not use that as the GLM fallback path. If GLM accepts small
  `/responses` requests but rejects Codex-shaped streaming `/responses` worker requests, stop
  before launching workers and use either a local Responses-compatible adapter or a provider that
  supports the Codex streaming Responses contract.

## Run Method: host-native local ICPC judge
- Use when: ContextSwarmJudge source is unavailable, Docker validation is not desired, and the
  operator has a certified ICPC package root such as `legacy/ContextSwarm/icpc_wf_2025`.
- Preconditions:
  - `g++` is available on `PATH`.
  - The package root contains `problem.yaml`, `tests/public` or `tests/hidden`, and any
    package-owned `checker/checker.cpp` or `interactor/interactor.cpp`.
  - Interactive packages are supported when the package ships a repository-authored
    statement-derived interactor and hidden cases, as in `wf2025_i_slot_machine`.
- Inputs:
  - ICPC package root: `<package-root>`.
  - Judge endpoint: normally `http://127.0.0.1:8081/api/judge/evaluate`.
- Command record:
  - Working directory: repository root.
  - Environment variables: none required.
  - Config file or generated script: none required.
  - Dry-run or preflight command:
    ```bash
    curl -fsS http://127.0.0.1:8081/healthz
    ```
  - Launch command:
    ```bash
    uv run python -m contextswarm.cli serve-local-icpc-judge \
      --package-root legacy/ContextSwarm/icpc_wf_2025 \
      --host 127.0.0.1 \
      --port 8081
    ```
  - Monitor command:
    ```bash
    curl -fsS http://127.0.0.1:8081/healthz
    ```
  - Stop or cleanup command: stop the foreground process with SIGINT/SIGTERM.
- Artifacts:
  - `/healthz` JSON with `service=contextswarm-judge`, `api_version=v1`,
    `evaluate_endpoint=/api/judge/evaluate`, and the resolved `package_root`.
  - `live_preflight_report.json` from `live-icpc-readiness`.
  - `live_context_report.json` from `run-icpc`.
- Validation:
  - Readiness with `--icpc-package-root <package-root>` and `--icpc-judge-endpoint` returns
    `ready=true` and no blockers.
  - A direct reference submission call to `/api/judge/evaluate` returns AC for non-interactive
    package references.
  - Current package-root sweep: 11 non-interactive WF 2025 public AC references return AC; the
    interactive Slot Machine package returns AC/WA through the host-native interactive runner.
- Failure modes:
  - `UNSUPPORTED`: interactive ICPC package missing a repository-authored interactor.
  - `CE`: submitted C++ failed to compile.
  - `TLE`: submitted program timed out on a case.
  - `OLE`: submitted output exceeded the configured output byte limit.
  - `JUDGE_ERROR`: package files or checker infrastructure failed.
- Scope boundaries:
  - This path does not provide Docker isolation or memory enforcement.
  - It is valid for host-native protocol/readiness and repository-authored interactive package
    validation, not a replacement for an official contest judge.
  - Do not claim upstream official interactor parity; the Slot Machine interactor and hidden
    tests are repository-authored statement-derived assets with explicit provenance boundaries.

## Run Method: controller/gateway 12-task diagnostic
- Use when: validating the paper controller/gateway resource-allocation surface on ICPC WF 2025
  before claiming full ContextSwarm reproduction.
- Preconditions:
  - The Rust ContextSwarm gateway is running and exposes `/version`, `/metrics`,
    `/control/projects/{project_id}/registry`, `/control/projects/{project_id}/runtime-policy`,
    and official-eval permit endpoints.
  - AISW/Codex worker calls are routed through the configured gateway base URL.
  - The ICPC judge endpoint is ready; host-native non-interactive judge is acceptable for this
    diagnostic when Docker is intentionally out of scope.
  - The experiment config enables `[gateway]`, `[controller]`, and context pieces.
- Inputs:
  - ICPC repo: `/tmp/openai-icpc-2025` or another frozen A-L surface.
  - Package root: `legacy/ContextSwarm/icpc_wf_2025` for host-native judge, or the operator's
    ContextSwarmJudge package root.
  - Gateway base URL: normally `http://127.0.0.1:8080/v1`.
  - Gateway upstream API profile: choose one of the live gateway upstream profiles above. This
    upstream URL is not the worker-facing gateway URL and must be passed as gateway upstream
    configuration.
  - Gateway upstream key source: auth JSON path plus field name from the chosen API profile;
    never record or print the raw key value.
  - RPM contract: start with `--gateway-project-rpm-limit 64`.
  - Gateway control-plane token: export or configure the master token only; the current client
    derives the per-project bearer token with the legacy `sha256(master_token + ":" + project_id)`
    formula before calling registry/runtime-policy endpoints.
  - Gateway live data-plane readiness: required live gateway runs must successfully complete a
    minimal `/preflight-worker/v1/responses` probe before launching ICPC workers.
- Command record:
  - Working directory: repository root.
  - Environment variables: gateway credentials if required by the deployed gateway; never record
    token values.
  - Config file or generated script: paper runtime config with `[gateway].enabled=true`,
    `[controller].enabled=true`, `[runtime].scheduler="contextswarm_controller_gateway"`, and
    context pieces enabled.
  - Dry-run or preflight command:
    ```bash
    uv run python -m contextswarm.cli live-icpc-readiness \
      --repo /tmp/openai-icpc-2025 \
      --experiment-config <paper-icpc-config.toml> \
      --icpc-package-root legacy/ContextSwarm/icpc_wf_2025 \
      --icpc-judge-endpoint http://127.0.0.1:8081/api/judge/evaluate \
      --gateway-base-url http://127.0.0.1:8080/v1 \
      --official-eval-base-url http://127.0.0.1:8080/v1 \
      --gateway-project-rpm-limit 64 \
      --gateway-upstream-url http://127.0.0.1:18081/v1 \
      --gateway-upstream-auth-json .codex/auth.json \
      --gateway-upstream-key-field OPENAI_API_KEY
    ```
  - Launch command:
    ```bash
    uv run python -m contextswarm.cli run-icpc \
      --repo /tmp/openai-icpc-2025 \
      --runtime live_context \
      --experiment-config <paper-icpc-config.toml> \
      --require-ready \
      --task-limit 12 \
      --icpc-package-root legacy/ContextSwarm/icpc_wf_2025 \
      --icpc-judge-endpoint http://127.0.0.1:8081/api/judge/evaluate \
      --gateway-base-url http://127.0.0.1:8080/v1 \
      --official-eval-base-url http://127.0.0.1:8080/v1 \
      --gateway-project-rpm-limit 64 \
      --gateway-upstream-url http://127.0.0.1:18081/v1 \
      --gateway-upstream-auth-json .codex/auth.json \
      --gateway-upstream-key-field OPENAI_API_KEY
    ```
  - Monitor command:
    ```bash
    curl -fsS http://127.0.0.1:8080/metrics
    ```
  - Stop or cleanup command: stop controller/supervisor/gateway foreground processes cleanly;
    keep JSONL/SQLite artifacts.
- Artifacts:
  - Gateway JSONL ledger and observer DB rows keyed by `project_id`, `quota_scope_id`, and
    `scheduler_group_id`.
  - All durable run artifacts live under one `data/swarm_YYYYMMDDTHHMMSSZ/` directory unless an
    operator explicitly opts into temporary debugging with `--allow-ephemeral-artifact-dir`.
  - `observation_latest.json`, `policy_snapshot.json`, `controller_events.jsonl`, and
    `controller_state_machine.json`, plus `controller_state.json`.
  - `controller_react_trace.jsonl`, the public `Observation` / `Action` / `Outcome` controller
    trajectory for the run.
  - `context_graph_events.jsonl`, `context_graph_state.json`, `context_pieces.sqlite3`, and
    `knowledge_run_summary.json`.
  - `official_eval_admission.jsonl`, `evaluation_ledger.jsonl`, `model_requests.jsonl`,
    `worker_episodes.jsonl`, `worker_heartbeats.jsonl`, `resource_capacity.json`,
    `deliverable_registry.json`, `deliverable_mutations.jsonl`, `allocation_history.jsonl`,
    `scoreboard_history.jsonl`, `score_time_telemetry.jsonl`,
    `gateway_observer_ledger.jsonl`, `project_focus_surface.json`,
    `dashboard_observer_snapshot.json`,
    `resource_diagnostics.json`, and
    `paper_capability_matrix.json`.
  - `contest_latest.json`, `final.json`, and per-worker `contextswarm_request_context.json`.
  - `request_context_contracts.jsonl`, the controller-visible public contract ledger for
    per-worker `contextswarm_request_context.json` payloads.
- Validation:
  - The run creates 12 task contexts and at least one gateway-ledger row per active context.
  - With 12 tasks and a worker capacity above 12, `resource_diagnostics.json` must still report
    `task_count=12` while `worker_episode_count` can exceed 12; tasks with
    `desired_parallelism > 1` are the tasks that received more worker episodes/context
    attempts.
  - Runtime policy revisions include task priority weights for ICPC tasks.
  - Official judge calls have permit lifecycle rows before verdict rows.
  - `evaluation_ledger.jsonl` records candidate hashes, request metadata, verdicts,
    queue/execution timing, and evaluator config for each paper-facing judge call.
  - `score_time_telemetry.jsonl` joins each worker episode / score event across
    `model_requests.jsonl`, `worker_episodes.jsonl`, `worker_heartbeats.jsonl`,
    `evaluation_ledger.jsonl`, and `scoreboard_history.jsonl` by lineage keys. Complete
    deterministic runs should report `join_status=complete`, empty `missing_sources`, gateway
    dispatch facts, heartbeat active/finished facts, official-eval permit/queue/verdict facts,
    scoreboard solved-count facts, and summary counts exposed through
    `live_context_report.json`, `controller_state.json`, `resource_diagnostics.json`, and
    `paper_capability_matrix.json`.
  - `gateway_observer_ledger.jsonl` normalizes model dispatch rows and official-eval
    evaluation rows into a current-package gateway observer ledger. Rows must cover both
    `llm_api` and `official_eval_worker`, expose `project_id`, `task_id`, `context_id`,
    `intent_id`, `lease_id`, `worker_id`, `quota_scope_id`, `scheduler_group_id`,
    `task_priority_weight`, `desired_parallelism`, runtime-policy revision, rpm limit,
    gateway routing facts, permit id, queue wait, verdict/accepted status, and source
    artifact. `live_context_report.json`, `controller_state.json`,
    `resource_diagnostics.json`, `dashboard_observer_snapshot.json`, and
    `paper_capability_matrix.json` must expose the ledger path and summary counts. In the
    deterministic 12-task rpm=64 diagnostic, expect 32 observer rows: 16 model requests and
    16 official-eval rows across 12 task contexts.
  - `request_context_contracts.jsonl` records one legacy-aligned public worker request context
    contract per bounded worker episode. Rows must use
    `schema_version=contextswarm_request_context_public_v1` and
    `worker_surface=worker_public_context_v1`, expose controller stop policy, gateway/provider
    auth mode, requested/resolved model facts, selected-context availability, public artifact
    availability, `./context_piece` helper/writeback contract, and an explicit claim boundary.
    `resource_diagnostics.json`, `live_context_report.json`, `controller_state.json`,
    `dashboard_observer_snapshot.json`, `project_focus_surface.json`,
    `project_gateway_snapshot.json`, and `paper_capability_matrix.json` must expose row,
    public-surface, gateway-managed, selected-context, helper, and unsafe-private-path counts.
    In the deterministic 12-task rpm=64 diagnostic, expect 12 unique task ids, 16 request
    context contract rows, 16 public worker surfaces, 16 gateway-managed contexts, 16
    selected-context links, and `unsafe_private_path_count=0`.
  - `worker_heartbeats.jsonl` records controller-visible worker lease heartbeat rows before and
    after bounded execution. Controller observations, policy snapshots, diagnostics, and the
    paper capability matrix must expose the heartbeat artifact path plus active, finished,
    stale, and blocker counts. Externally seeded stale heartbeat rows are deterministic
    controller inputs and should shape policy through `blocked_context_cooldown`.
  - `resource_capacity.json` records the controller-visible launch-limiter surface derived from
    gateway limits and heartbeat pressure. `observation_latest.json`, `policy_snapshot.json`,
    `resource_diagnostics.json`, `live_context_report.json`, and `paper_capability_matrix.json`
    must expose the resource capacity artifact path, `launch_limiter`, and
    `launchable_deficit`. Pre-existing active heartbeat rows may reduce new worker launches
    without being treated as new ICPC AC evidence.
  - `deliverable_registry.json` contains one deliverable per active ICPC task and derives
    workflow status from runtime facts: ready before launch, running from active heartbeat
    leases, completed from AC verdicts, and blocked from non-AC verdicts or stale heartbeat
    blockers. `deliverable_mutations.jsonl` records project status projection rows, and
    `observation_latest.json`, `policy_snapshot.json`, `controller_state.json`,
    `resource_diagnostics.json`, `live_context_report.json`, and
    `paper_capability_matrix.json` must expose the registry path, mutation log path,
    deliverable count, mutation count, ready/running/blocked/completed counts, and claim
    boundary.
  - `dashboard_observer_snapshot.json` exposes a current-package project live summary with
    `ready`, `reason`, `dashboard`, `project`, `governor`, `tasks`, `score_time`,
    `gateway_observer_ledger`, `project_focus_surface`, `controller`, `gateway`, `artifacts`,
    and claim-boundary fields.
    `live_context_report.json`, `controller_state.json`, `resource_diagnostics.json`, and
    `paper_capability_matrix.json` must expose the snapshot path and observer request /
    official-eval / score-time / gateway-ledger summary counts without requiring Docker,
    Grafana, or the legacy dashboard service.
  - `project_focus_surface.json` exposes a controller/dashboard-visible focus projection over
    active ICPC task focuses, materialized context graph state, governor facts, deliverable
    frontier, resource capacity, score-time telemetry, and gateway observer ledger summaries.
    `live_context_report.json`, `controller_state.json`, `resource_diagnostics.json`,
    `dashboard_observer_snapshot.json`, and `paper_capability_matrix.json` must expose the focus
    surface path and summary counts. In the deterministic 12-task rpm=64 diagnostic, expect 12
    focuses, 12 completed focuses, context graph event counts from `context_graph_state.json`,
    16 score-time rows, 32 gateway observer rows, and `live_icpc_ac_claimed=false`.
  - `paper_capability_matrix.json` maps every paper capability to implementation status and
    evidence paths, and keeps the claim boundary explicit.
  - `controller_state_machine.json.phases` includes `tick_started`, `observation_recorded`,
    `context_graph_governed`, `policy_decided`, `policy_applied`,
    `worker_supervision_finished`, `post_writeback_decided`, and `tick_finished`.
  - `policy_snapshot.json` includes `current_managed_project_policy`,
    `desired_managed_project_policy`, `effective_managed_project_policy`,
    `current_parallelism_policy`, `desired_parallelism_policy`, `apply`,
    `deliverable_mutation`, and `governor`.
  - `context_graph_state.json` includes `pending_proposal_ids`, `proposals_by_id`,
    `latest_decision_by_proposal_id`, `latest_reply_by_proposal_id`,
    `reply_inbox_by_submitter`, `proposal_fingerprints`, `revision_history`, `receipt_index`,
    `score_observations`, `activation_hints`, `pain_signals`, `graceful_stop_requests`, and
    `signal_counts`.
  - `context_graph_state.json.event_count` and `event_families` are materialized from
    `context_graph_events.jsonl`; accepted worker writebacks emit proposal, decision, reply,
    revision, and score-observation event families, while unresolved proposals remain in
    `pending_proposal_ids`.
  - Controller/governor context graph checks must distinguish proposal materialization from
    proposal resolution: externally appended proposals remain pending until the governor appends
    decision/reply events, matching-base graph deltas commit exactly one revision, stale
    `base_revision` replies include `resubmit_from_revision`, duplicate accepted fingerprints
    merge without a second revision, and proposals missing `evidence_refs` resolve as
    `needs_more_evidence` without committing a revision.
  - Non-graph proposal signal checks must prove `activation_hint`, `pain_signal`, and
    `graceful_stop_request` proposals are accepted with decision/reply rows, appear in their
    materialized signal indexes, update `signal_counts`, and do not commit graph revisions.
  - Signal-driven controller actuation checks must prove materialized `activation_hints`,
    `pain_signals`, and `graceful_stop_requests` feed pre-worker controller task facts:
    activation hints can raise weight/priority and desired parallelism, pain signals hold the
    affected task at cooldown capacity, and graceful-stop requests produce
    `desired_parallelism=0` so no worker/model-request episode is launched for that task.
  - `allocation_history.jsonl`, `policy_snapshot.json`, `model_requests.jsonl`, and
    `resource_diagnostics.json` must make signal-driven effects auditable through task-level
    `decision`, `reason`, `desired_parallelism`, episode counts, and model-request counts.
  - `controller_actuation_requests.jsonl` must make legacy-style actuation explicit: every
    active controller decision writes a `parallelism_control` row with `desired_parallelism`,
    `source`, `reason`, `requested_at`, `task_id`, controller phase, and prior desired
    parallelism; stop decisions from graceful stop or terminal state also write a `stop_request`
    row. `policy_snapshot.json.apply`, `live_context_report.json`, and
    `resource_diagnostics.json.diagnostic_artifacts` must expose this artifact path.
  - Controller-runtime governor checks must prove the controller tick consumes pending proposals
    from the run artifact's `context_graph_events.jsonl`: the `context_graph_governed` event,
    `observation_latest.json.context_graph.governor`, `policy_snapshot.json.governor`,
    `controller_state_machine.json.governor`, `controller_state.json.context_graph.governor`,
    and `resource_diagnostics.json.context_graph_governor` must agree on processed counts, while
    later worker writebacks continue from the post-governor graph revision. For signal proposals,
    these same artifacts must expose `signal_counts`; `observation_latest.json` and
    `controller_state.json` must also expose the materialized activation, pain, and graceful-stop
    indexes.
  - Worker Codex requests include gateway provider overrides and ContextSwarm lineage headers
    when `[gateway].base_url` is set.
  - Worker Codex requests use a per-worker gateway URL such as
    `http://127.0.0.1:8080/<worker-id>/v1`; the legacy gateway records the worker id from that
    path in its JSONL ledger.
  - Per-task diagnostics can answer: model requests, official eval permits, worker episodes,
    context-piece counts, queue wait, weight trajectory, desired-parallelism trajectory, verdict,
    and time-to-accepted when accepted.
- Failure modes:
  - Gateway unreachable or runtime policy unreadable: controller active mode must fail closed or
    remain in shadow mode; do not silently bypass gateway while claiming controller/gateway
    reproduction.
  - `gateway_llm_dataplane:gateway_dataplane_http_error:<status>` in readiness means the gateway
    process is up but its live upstream `/responses` path is not usable. First verify that
    `gateway_service.mode=live` receives `GATEWAY_UPSTREAM_URL=http://127.0.0.1:18081/v1` and
    `GATEWAY_UPSTREAM_KEY` from the auth JSON field `OPENAI_API_KEY`; do not set
    `--gateway-base-url` to `18081`, because that bypasses the ContextSwarm gateway and loses
    controller/gateway resource coordination.
  - Gateway control-plane readiness can pass dataplane probes while registry/runtime-policy writes
    still fail if the controller client and gateway service do not share the same control-plane
    token source. In live runs, sync `gateway.control_plane_token` and
    `gateway_service.control_plane_token` from the same operator token source and make preflight
    verify `/control/projects/{project_id}/registry` and `/runtime-policy` before treating the
    gateway as ready.
  - `Authorization header is not supported on gateway data-plane requests`: the Codex worker is
    leaking client auth into the gateway. Gateway-routed workers must use a per-session isolated
    `CODEX_HOME` so the gateway remains the component that adds upstream authorization.
  - Official-eval permit response missing legacy fields: the run must block the official judge
    call before execution rather than judge without a valid permit.
  - Judge/evaluator exception after a permit is granted: the admission wrapper must attempt
    `finish(status="error")` and preserve local `finished` evidence.
  - Empty context pieces: the diagnostic cannot validate paper context reuse.
  - Sequential worker launch only: the diagnostic cannot validate worker/runtime capacity shaping.
- Scope boundaries:
  - A dry-run diagnostic proves artifact shape only. It does not prove score-time performance.
  - A live ICPC run with `WA` verdicts can prove resource coordination, but not solved-task
    completion.

## Run Method: host-native Rust gateway control plane
- Use when: validating the paper gateway control-plane and official-eval admission contract
  without Docker dashboard/observer, or when `legacy/ContextSwarm/scripts/gateway_service.sh
  precheck` is blocked by missing Docker/cargo but the release gateway binary is present.
- Preconditions:
  - `legacy/ContextSwarm/gateway/target/release/contextswarm-gateway` exists.
  - A free local port is available for the gateway.
  - A gateway control-plane master token is available from an operator secret source.
  - This validates gateway-only `/health`, `/version`, `/control/projects/...`,
    `/admission/official-evals/...`, and `/v1/...` routing; it does not start Grafana/observer.
- Inputs:
  - Gateway root: `legacy/ContextSwarm`.
  - Gateway port: for example `18100`.
  - Gateway RPM limit: for the user's 12-task diagnostic, use `64`.
  - Control-plane token: pass via `--control-plane-token-env <ENV_NAME>` whenever possible.
- Command record:
  - Working directory: repository root.
  - Environment variables: `CONTEXTSWARM_GATEWAY_TOKEN` or another operator-selected token env
    name; never record the token value.
  - Config file or generated script: none required for gateway-only smoke.
  - Dry-run or preflight command:
    ```bash
    uv run python -m contextswarm.cli gateway-service status \
      --root legacy/ContextSwarm \
      --mode mock \
      --port 18100 \
      --readiness gateway_only \
      --rpm-limit 64 \
      --control-plane-token-env CONTEXTSWARM_GATEWAY_TOKEN
    ```
  - Launch command:
    ```bash
    uv run python -m contextswarm.cli gateway-service gateway-only-up \
      --root legacy/ContextSwarm \
      --mode mock \
      --host 127.0.0.1 \
      --health-host 127.0.0.1 \
      --port 18100 \
      --readiness gateway_only \
      --required \
      --rpm-limit 64 \
      --control-plane-token-env CONTEXTSWARM_GATEWAY_TOKEN \
      --artifact-dir <debug-gateway-service-dir>
    ```
  - Monitor command:
    ```bash
    curl -fsS http://127.0.0.1:18100/version
    curl -fsS http://127.0.0.1:18100/metrics
    ```
  - Stop or cleanup command:
    ```bash
    uv run python -m contextswarm.cli gateway-service gateway-only-down \
      --root legacy/ContextSwarm \
      --port 18100 \
      --artifact-dir <debug-gateway-service-dir>
    ```
- Artifacts:
  - `gateway_service.json` in ICPC runtime artifact directories when gateway service is enabled.
  - Gateway-only stdout log and pid file under `<artifact-dir>/gateway-service/`.
  - Gateway JSONL and project registry under `<artifact-dir>/gateway-data/`.
- Validation:
  - `gateway-service gateway-only-up` returns `ready=true` and a `base_url`.
  - `GatewayClient` can write `/control/projects/{project_id}/registry` and
    `/control/projects/{project_id}/runtime-policy` using the project-scoped token formula.
  - Official-eval permit acquire and finish return a permit id and `released=true`.
- Failure modes:
  - `gateway_port_in_use:<host>:<port>`: choose another port or stop the existing service.
  - `gateway_version_unreachable:JSONDecodeError`: usually means the port is occupied by a
    non-ContextSwarm service; the adapter now reports this as blocked rather than ready.
  - `gateway_binary_missing:<path>`: build or restore the legacy gateway binary.
  - `gateway_service_missing_bin:cargo` / `gateway_service_missing_bin:docker`: full resident
    script mode is blocked; use gateway-only mode only if dashboard/observer evidence is not the
    claim being validated.
- Scope boundaries:
  - Gateway-only mode is sufficient for control-plane/admission/proxy semantics.
  - It does not prove Grafana dashboard or SQLite observer ingestion.
  - It does not prove ICPC task acceptance without AISW/Codex workers and a ready judge.

## Command Shape

Readiness:

```bash
uv run python -m contextswarm.cli live-icpc-readiness \
  --repo /tmp/openai-icpc-2025 \
  --experiment-config tests/fixtures/contextswarm_live/config/experiments/aisw/icpc_wf_2025_all_5min_aisw.toml
```

When AISW or judge dependencies live outside the checked-in defaults, pass operator-local
overrides on both readiness and run commands:

```bash
uv run python -m contextswarm.cli live-icpc-readiness \
  --repo /tmp/openai-icpc-2025 \
  --experiment-config tests/fixtures/contextswarm_live/config/experiments/aisw/icpc_wf_2025_all_5min_aisw.toml \
  --aisw-shim-binary /path/to/aisw \
  --aisw-node-config /path/to/node.toml \
  --icpc-package-root /path/to/ContextSwarmJudge/packages \
  --icpc-judge-endpoint http://127.0.0.1:8081/api/judge/evaluate
```

The readiness output includes these same override flags in the emitted smoke/full commands.
Keep such operator-local paths out of tracked fixture configs unless they are stable public
defaults.

### AISW deployment note

The `burakdede/aisw` project is a profile and context manager for Claude Code, Codex CLI, and
Gemini CLI. It is not the ContextSwarm worker shim by itself. For ContextSwarm live ICPC use:

1. Install the upstream `aisw` release binary to a separate location, for example
   `/root/.local/lib/aisw-profile/bin/aisw`.
2. Put a ContextSwarm compatibility wrapper at `~/.local/bin/aisw` that forwards
   `aisw codex exec ...` to the local `codex exec ...` binary and delegates other invocations to
   the upstream profile manager binary.
3. Create a valid `~/.aisw-codex/node.toml` for the local node contract. A minimal file can
   satisfy preflight, but real ICPC still needs the judge package root and healthz endpoint.

Validation for the deployment:

```bash
/root/.local/bin/aisw --version
/root/.local/bin/aisw codex exec --help
uv run python -m contextswarm.cli live-icpc-readiness \
  --repo /tmp/openai-icpc-2025 \
  --experiment-config tests/fixtures/contextswarm_live/config/experiments/aisw/icpc_wf_2025_all_5min_aisw.toml
```

Known limitation:

- This deployment clears the AISW shim and node-config blockers, but it does not replace
  ContextSwarmJudge. Live ICPC remains blocked until the judge package root and healthz endpoint
  are available.
- On this host, child Codex workers need `--sandbox danger-full-access`; the default sandbox can
  fail before writing `solution.cpp` with `bwrap: Failed to make / slave: Permission denied`.
  The checked-in AISW fixture sets `aisw.codex_sandbox_mode = "danger-full-access"`.
- Bounded ICPC workers should use low reasoning effort for first-artifact latency:
  `aisw.codex_reasoning_effort = "low"`. This does not guarantee AC; it only makes the worker
  more likely to produce a complete judged artifact inside the smoke timeout.

Smoke after readiness is `ready=true`:

```bash
uv run python -m contextswarm.cli run-icpc \
  --repo /tmp/openai-icpc-2025 \
  --runtime live_context \
  --experiment-config tests/fixtures/contextswarm_live/config/experiments/aisw/icpc_wf_2025_all_5min_aisw.toml \
  --require-ready \
  --smoke \
  --max-workers 1
```

Full run after smoke produces worker and judge evidence:

```bash
uv run python -m contextswarm.cli run-icpc \
  --repo /tmp/openai-icpc-2025 \
  --runtime live_context \
  --experiment-config tests/fixtures/contextswarm_live/config/experiments/aisw/icpc_wf_2025_all_aisw.toml \
  --require-ready
```

The bench wrapper is env-gated:

```bash
CONTEXTSWARM_RUN_ICPC_AISW_SMOKE=1 uv run python -m pytest -q \
  tests/bench/test_icpc_contextswarm_live_benchmark.py --import-mode=importlib
```

```bash
CONTEXTSWARM_RUN_ICPC_AISW_FULL=1 uv run python -m pytest -q \
  tests/bench/test_icpc_contextswarm_live_benchmark.py --import-mode=importlib
```

## Outputs

- `live_preflight_report.json`: readiness status, checks, blockers, scheduler, and task count.
- `controller_state.json`: controller state, store counts, and preflight evidence.
- `controller_state_machine.json`: explicit controller tick phases from observation through
  policy apply, worker supervision, post-writeback decision, and terminal state.
- `observation_latest.json` and `policy_snapshot.json`: controller observation plus current,
  desired, and effective managed policy/parallelism surfaces.
- `live_context_report.json`: per-task `worker_command`, `worker_returncode`,
  `selected_context_path`, `solution_artifact_path`, `codex_events_path`, stdout/stderr paths,
  `judge_status`, and `accepted`.
- `context_pieces.sqlite3`: persistent live context, intent, lease, score, and controller samples.
- `resource_diagnostics.json`: task-level resource accounting for model requests, worker
  episodes, official-eval permits, queue wait, context pieces, controller weights, desired
  parallelism, verdicts, and time-to-accepted.
- `worker_heartbeats.jsonl`: controller-visible worker lease heartbeat rows, including
  prelaunch/acquired, finished, stale, and blocker fields.
- `resource_capacity.json`: controller-visible capacity report with pre-worker and post-writeback
  phases, target inflight, observed active leases, stale blockers, admission/outstanding
  capacity, `launch_limiter`, and `launchable_deficit`.
- `deliverable_registry.json`: controller-visible deliverable registry with one deliverable per
  active ICPC task and ready/running/completed/blocked workflow status.
- `deliverable_mutations.jsonl`: deliverable status projection mutations that make registry
  status changes auditable beside context graph events.
- `score_time_telemetry.jsonl`: joined score-time rows across model dispatch, worker episode,
  heartbeat, evaluation ledger, and scoreboard-history surfaces.
- `gateway_observer_ledger.jsonl`: normalized current-package gateway observer rows for model
  dispatch and official-eval requests.
- `agent_runtime_observability.jsonl`: one row per bounded worker episode, joining command,
  stdout/stderr/events paths, request/selected context files, solution SHA-256, heartbeat,
  gateway/model request, official-eval verdict, score-time, gateway observer linkage, and
  missing-source status.
- `context_piece_dsl.jsonl`: one row per newly created context piece, carrying the raw piece
  identity plus normalized DSL payload, canonical kind, lifecycle status, scope key, typed
  evidence refs, feedback/link lists, diagnostics, and `live_icpc_ac_claimed=false`.
- `knowledge_run_summary.json`: context-piece activity summary. Current live runs include a
  `context_piece_dsl` nested summary with row count, lifecycle counts, kind counts, diagnostic
  count, and evidence-ref count.
- `project_focus_surface.json`: legacy-style focus projection over deliverables, materialized
  graph state, governor facts, resource capacity, score-time telemetry, and gateway observer
  summaries, with a link to the project gateway snapshot when generated.
- `dashboard_observer_snapshot.json`: current-package dashboard observer snapshot with project,
  task, score-time, gateway observer, project focus, project gateway snapshot, controller,
  gateway, artifact, and claim boundary fields.
- `project_gateway_snapshot.json`: controller/dashboard-visible gateway live snapshot joining
  gateway apply/service status, runtime policy revision, rpm limit, controller tick/apply facts,
  gateway observer request distribution, resource capacity, score-time, project focus, agent
  runtime observability, dashboard observer, and artifact paths.
- `task_roi.json`: controller/dashboard-visible per-task ROI projection derived from existing
  gateway observer, score-time, and diagnostics artifacts. It records model request count,
  official-eval request count, worker episode count, accepted count, score-time latency, context
  piece count, desired parallelism, priority weight, estimated structural request cost units,
  contest submission cost units, and ROI status. These are deterministic structural units, not
  provider billing charges.
- `contest_submission_cost.json`: project-level contest submission cost projection with
  attempted/accepted tasks, official-eval submissions, chargeable submissions after the first
  submission per task, structural request cost units, combined cost units, cost per accepted
  task, rpm limit, runtime policy revision, and per-task cost rows.
- `evaluation_ledger.jsonl`: candidate SHA-256, request metadata, permit id, verdict, timing,
  and evaluator config for paper-facing judge/checker calls.
- `paper_capability_matrix.json`: paper capability inventory with implementation status,
  evidence paths, and a claim boundary separating runtime reproduction from live 12-task AC.
- `context_graph_state.json`: event-sourced graph-native proposal/decision/reply/revision
  indexes, pending proposal ids, accepted proposal fingerprints, reply inboxes, event-family
  counts, and score observations materialized from `context_graph_events.jsonl`.

## Validation

Completion requires stronger evidence than a passing harness:

- `live_preflight_report.json` has `ready=true`.
- Smoke run has non-empty `tasks[]` and at least one AISW Codex worker/judge record.
- Full run covers the intended 12 ICPC tasks unless the task limit is explicitly changed.
- `live_context_report.json` records real worker artifacts and judge verdicts.
- If the worker times out after writing `solution.cpp`, the judge verdict is still meaningful
  evidence and should be recorded; do not collapse it back to `worker_not_completed`.
- Replay, dry-run workers, fake workers, or `preflight_blocked` artifacts are not accepted as
  paper-faithful ICPC completion evidence.

## Known Failure Modes

- `aisw_shim:missing_aisw_shim:<path>`: install or point config at the AISW shim.
- `aisw_node_config:missing_aisw_node_config:<path>`: create/provide AISW node config.
- `aisw_node_config:invalid_aisw_node_config:<error>`: fix TOML syntax.
- `icpc_judge_package_root:missing_icpc_package_root:<path>`: stage ContextSwarmJudge packages or
  use an operator-local config with the correct package root.
- `icpc_judge_healthz:judge_unreachable:<error>`: start ContextSwarmJudge or correct endpoint.
- `judge_healthz_protocol_mismatch:*`: the service is not the expected ContextSwarmJudge v1 ICPC
  judge or points at the wrong package root.
- `gateway_llm_dataplane:gateway_dataplane_http_error:401` or `:403`: the required live gateway
  data-plane probe reached the gateway/upstream path but the configured upstream credential or
  plan cannot call `/responses`. Do not launch the 12-task run until a valid OpenAI-compatible
  upstream is configured.
- `worker_timeout` with `solution_artifact_path=null`: worker did not leave a judgeable artifact
  inside the configured time budget.
- `worker_timeout` with `solution_artifact_path=<path>` and `judge_status=WA`: worker produced a
  real artifact and the judge ran; the remaining issue is solution quality or time budget, not
  Docker/Judge deployment.

When these blockers appear, keep the task/result status blocked. Do not fall back to replay while
claiming live ICPC success.

## Run Method: repository-authored interactive host-native judge
- Use when: the package root includes a statement-derived `interactor/interactor.cpp` and hidden
  interaction cases, and Docker is intentionally out of scope.
- Preconditions:
  - `g++` is available on `PATH`.
  - The interactive package ships both `interactor/interactor.cpp` and hidden `.in/.ans`
    cases, as in `wf2025_i_slot_machine`.
  - The package provenance must explicitly say the assets are repository-authored and
    statement-derived; do not use this method to claim official upstream judge parity.
- Inputs:
  - Interactive package root: `<package-root>`.
  - Judge endpoint: normally `http://127.0.0.1:8081/api/judge/evaluate`.
- Command record:
  - Working directory: repository root.
  - Environment variables: none required.
  - Config file or generated script: none required.
  - Dry-run or preflight command:
    ```bash
    curl -fsS http://127.0.0.1:8081/healthz
    ```
  - Launch command:
    ```bash
    uv run python -m contextswarm.cli serve-local-icpc-judge \
      --package-root legacy/ContextSwarm/icpc_wf_2025 \
      --host 127.0.0.1 \
      --port 8081
    ```
  - Monitor command:
    ```bash
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --with pytest --with pyyaml python -m pytest -q \
      tests/unit/test_local_icpc_judge.py::test_local_judge_interactive_runs_statement_derived_interactor \
      tests/unit/test_local_icpc_judge.py::test_local_judge_interactive_rejects_wrong_answer_candidate
    ```
  - Stop or cleanup command: stop the foreground process with SIGINT/SIGTERM.
- Artifacts:
  - Per-case `interaction.log` and `report.txt` files in the temporary judge workspace.
  - Local verdict payloads with `AC` / `WA` / `JUDGE_ERROR` semantics.
- Validation:
  - AC reference from `wf2025_i_slot_machine/references/public/openai_submission_ac.cpp`
    returns `AC`.
  - `validation/candidates/wrong_answer.cpp` returns `WA`.
  - The judge no longer returns `UNSUPPORTED` for the package when the interactor asset exists.
- Failure modes:
  - Missing interactor asset: return `UNSUPPORTED` and do not fake interactive support.
  - Interactor timeout or contestant timeout: return `TLE`.
  - Broken pipe / protocol mismatch: return `JUDGE_ERROR`.
- Scope boundaries:
  - This is host-native validation only; it still is not an upstream official judge.
  - The provenance boundary remains important: the interactor and hidden cases are
    repository-authored assets derived from the statement protocol, not upstream-distributed
    testing tools.

## Run Method: live controller gateway 12-task diagnostic
- Use when: inspecting whether an active controller uses gateway policy to split capacity across
  different ICPC tasks under rpm 64.
- Preconditions:
  - AISW shim and node config are installed.
  - Gateway service control-plane token is available.
  - ICPC judge package root and `/healthz` endpoint are reachable.
  - The active-controller fixture is isolated from gateway-only runs by project id.
- Inputs:
  - ICPC repo: `/tmp/openai-icpc-2025`
  - Experiment config:
    `tests/fixtures/contextswarm_live/config/experiments/aisw/icpc_wf_2025_all_aisw_controller_gateway.toml`
  - Task limit: `12`
  - Max workers: `16`
  - Gateway RPM limit: `64`
- Command record:
  - Working directory: repository root.
  - Environment variables: `CODEX_THREAD_ID`, gateway control-plane token env if used by the
    experiment config, and any upstream provider auth env required by the gateway service.
  - Config file:
    ```toml
    [definition]
    name = "coding/icpc_wf_2025/controller_gateway"

    [identity]
    task_id = "coding/icpc_wf_2025/controller_gateway"

    [runtime]
    scheduler = "contextswarm_controller_gateway"
    context_pieces = "on"

    [controller]
    enabled = true
    mode = "active"
    tick_interval_seconds = 30
    min_apply_interval_seconds = 30
    weight_min = 1
    weight_max = 32
    target_fill_ratio = 0.9
    ```
  - Dry-run or preflight command:
    ```bash
    uv run python -m contextswarm.cli live-icpc-readiness \
      --repo /tmp/openai-icpc-2025 \
      --experiment-config tests/fixtures/contextswarm_live/config/experiments/aisw/icpc_wf_2025_all_aisw_controller_gateway.toml \
      --icpc-package-root legacy/ContextSwarm/icpc_wf_2025 \
      --icpc-judge-endpoint http://127.0.0.1:8081/api/judge/evaluate \
      --gateway-base-url http://127.0.0.1:8080/v1 \
      --official-eval-base-url http://127.0.0.1:8080/v1 \
      --gateway-project-rpm-limit 64 \
      --gateway-upstream-url http://127.0.0.1:18081/v1 \
      --gateway-upstream-auth-json .codex/auth.json \
      --gateway-upstream-key-field OPENAI_API_KEY
    ```
  - Launch command:
    ```bash
    uv run python -m contextswarm.cli run-icpc \
      --repo /tmp/openai-icpc-2025 \
      --runtime live_context \
      --experiment-config tests/fixtures/contextswarm_live/config/experiments/aisw/icpc_wf_2025_all_aisw_controller_gateway.toml \
      --require-ready \
      --task-limit 12 \
      --max-workers 16 \
      --icpc-package-root legacy/ContextSwarm/icpc_wf_2025 \
      --icpc-judge-endpoint http://127.0.0.1:8081/api/judge/evaluate \
      --gateway-base-url http://127.0.0.1:8080/v1 \
      --official-eval-base-url http://127.0.0.1:8080/v1 \
      --gateway-project-rpm-limit 64 \
      --gateway-control-plane-token-env CONTEXTSWARM_LIVE_GATEWAY_TOKEN \
      --gateway-service-action gateway-only-up \
      --gateway-service-mode live \
      --gateway-service-host 0.0.0.0 \
      --gateway-service-health-host 127.0.0.1 \
      --gateway-service-port 8080 \
      --gateway-service-readiness gateway_only \
      --gateway-service-required \
      --gateway-service-rpm-limit 64 \
      --gateway-upstream-url http://127.0.0.1:18081/v1 \
      --gateway-upstream-auth-json .codex/auth.json \
      --gateway-upstream-key-field OPENAI_API_KEY
    ```
  - Monitor command:
    ```bash
    latest_run_dir="$(ls -td data/swarm_* | head -1)"
    find "$latest_run_dir/sessions" -name solution.cpp | wc -l
    tail -n 1 "$latest_run_dir/allocation_history.jsonl"
    ```
  - Stop or cleanup command: let the worker timeout or stop the run only after the controller
    and resource evidence has been captured.
- Artifacts:
  - `live_preflight_report.json`
  - `allocation_history.jsonl`
  - `model_requests.jsonl`
  - `worker_heartbeats.jsonl`
  - `controller_actuation_requests.jsonl`
  - `policy_snapshot.json`
  - `resource_capacity.json`
  - `request_context_contracts.jsonl`
  - final `live_context_report.json`, `resource_diagnostics.json`, `controller_state.json`
    when the run closes
- Validation:
  - `allocation_history.jsonl` shows `gateway_status=applied`, `supervisor_capacity=16`,
    `runtime_policy_revision=6`, and `I/J/K/L desired_parallelism=2`.
  - The task stream shows 16 model requests and 16 worker episodes for the 12-task diagnostic.
- Failure modes:
  - Long-tail workers can keep the run in flight until the worker timeout boundary, so final
    report files may lag behind the controller evidence.
- Scope boundaries:
  - This diagnostic proves controller/gateway resource coordination and per-task parallelism
    shaping.
  - It does not by itself prove full 12/12 AC.
