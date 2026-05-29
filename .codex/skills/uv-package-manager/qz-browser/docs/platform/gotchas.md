# QZ Browser Gotchas

Things that took time to figure out. Save yourself the pain.

## Field Name Quirks

The backend uses protobuf — wrong field names give `unknown field` errors, not silent ignores.

| Endpoint | Pagination fields | Notes |
|----------|-------------------|-------|
| `train_job/list` | `page_num`, `page_size` | snake_case, returns `data.jobs` |
| `train_job/instance_list` | `page_num`, `page_size` | snake_case, but `jobId` is camelCase! returns `data.items` |
| `logic_compute_groups/list` | `pageNum`, `pageSize` | camelCase! |
| `project/list` | `page`, `page_size` | different again |
| `image/list` | `page`, `page_size` | **0-indexed** (page=0 is first page!) |
| `notebook/list` | `page`, `page_size` | same as project/image |

- `train_job/list` returns `data.jobs` (NOT `data.items`). But `instance_list` returns `data.items`.
- `/openapi/v1/train_job/{detail,stop}` use field `job_id` (NOT `id`).
- `instance_list` and `job_event_list` use camelCase `jobId` (NOT `job_id`).
- `logs/train` uses `filter.podNames` (array of strings), timestamps as string milliseconds.
- The WebUI "实例" log modal still uses `logs/train` / `logs/inference_serving` with a
  single pod in `filter.podNames`; it does not call a hidden per-instance log endpoint.
- `train_job/instance_logs` still appears in frontend bundles, but direct requests currently
  return HTTP 404 on `qz.sii.edu.cn`.
- Pool ID field is `logic_compute_group_id`, NOT `id`, in list responses.
- `logic_compute_groups/list` requires a `filter` wrapper: `{filter: {workspace_id: "..."}}`
- `train_job/list` takes `workspace_id` at top level (no filter wrapper).
- Node count lives in `framework_config[0].instance_count`, NOT top-level `node_count`.
- `resource_metric_by_time` response uses `time_seris_metric_groups` (typo: "seris" not "series").
- `resource_metric_by_time` timestamps are unix **seconds** (not ms), but `timestamp` in `time_series` is a **string**.
- The API uses XHR (XMLHttpRequest), not fetch — browser fetch interceptor won't capture it.
- `image/list` → `data.total` is a **STRING** (e.g. `"53"`), not a number.
- `image/update` uses field `id`, NOT `image_id`.
- `image/sync` uses `{workspaceId, imageName, imageVersion}` — camelCase! NOT `image_id`.
- `image/preheat` uses `{name, version, logic_compute_group_id}` — NOT `image_id`.
- `image/list` pages are **0-indexed** (page=0 is first page, NOT page=1). The WebUI JS does `page: s.page-1`.
- The job/notebook create-form image picker uses the SAME `image/list` endpoint,
  but with `page_size: -1` plus `filter.registry_hint.workspace_id`, and then
  filters the result client-side while you type. There is no separate keyword-search
  API call from the picker.
- Deployment instance names include the project slug in requests, e.g.
  `qproject-fundationmodel/sv-...-2-1`, but `logs/inference_serving` responses may
  return `pod_name` without that prefix.

## Notebook Field Gotchas

- Notebook create: image fields are `mirror_id` / `mirror_url` (NOT `image_id` / `image_url`).
- Notebook operate: action field is `operation` (NOT `action`, `operate`, or `type`).
- Notebook create: priority field is `task_priority`, takes project priority **level** (1/4/10), NOT raw priority (35).
- Notebook create: `resource_spec_price` is **required** for GPU notebooks (error 100002 if absent).
- Notebook create: `description` field is rejected (not in proto schema).
- `notebook/list` filter uses `filter_by` sub-object (NOT `filter` like other endpoints).
- `notebook/list` returns `data.list` (NOT `data.notebooks`).
- CPU elastic ratio (overcommit): field is `cpu_elastic_ratio` (int), top-level on notebook object.
  - UI label: "CPU 弹性系数" (CPU elastic coefficient). HTML form `id="cpu_elastic_ratio"`.
  - 1 = no overcommit (default for GPU notebooks), 2 = 2× burst (default for CPU-only notebooks).
  - Meaning: `cpu_request = cpu_count`, `cpu_limit = cpu_count × cpu_elastic_ratio`.
  - Field IS in detail responses (contradicts earlier note). Also in list responses.
  - Training jobs (`train_job/detail`, `framework_config`) do NOT expose this field — only notebooks have it.
- `notebook/list` panics (HTTP 500, code 100000, nil pointer dereference) when `filter_by` field is
  omitted from the payload. The server's Go code dereferences `filter_by` without a nil check.
  **Fix**: always include `"filter_by": {}` in the request body (even when no filters are needed).
  The browser always sends `filter_by`, so the bug only manifests with hand-crafted requests.
- `notebook/schedule/{ws_id}` returns `quota` as a **JSON-encoded string**, not an object. Must be `JSON.parse()`'d.
- `notebook/schedule/{ws_id}` field `open_ssh` controls whether SSH form appears in the UI.
- SSH `extra_info.SshPort == -1` means SSH port resource exhaustion (not "port is 1").
- `ssh/list` with `workspace_id` in body is REJECTED (unknown field). Use empty body `{}`.
- `ssh/list` `data.list` is always empty (API bug), but `data.total` shows the real count. Use `GET /api/v1/ssh/{id}` to fetch individual keys.
- `ssh/create` with empty body `{}` creates a key with auto-generated ID but empty name/content.
- `ssh/create` field for public key text is `content` (NOT `public_key`, `pub_key`, `key`, or `pubkey`).
- `ssh/delete` returns `{"code": 0}` on success (not empty/204).
- Jupyter proxy is on a different host: `nat2-notebook-inspire.sii.edu.cn` (NOT `qz.sii.edu.cn`).
  `/api/v1/notebook/lab/{id}` redirects to `https://nat2-notebook-inspire.sii.edu.cn/...`
- Jupyter token is a UUID in the redirect URL: `?token={uuid}`. Use it as `Authorization: token {uuid}` header.
- Jupyter `/api/terminals` POST with empty body `{}` creates a new terminal (returns `{"name": "1", ...}`).

## Cookie Setup

- The cookie value in `${QZ_CACHE_DIR:-~/.cache/qz}/auth.json` is stored as `inspire-session=<value>` (key=value format). If `QZ_CACHE_DIR` is unset, the default path is `~/.cache/qz/auth.json`.
- **`agent-browser cookies set` expects just the VALUE** — strip the `inspire-session=` prefix first:
  ```bash
  COOKIE_VALUE=$(python3 -c "c=...; print(c.split('=',1)[1] if '=' in c else c)")
  agent-browser cookies set inspire-session "$COOKIE_VALUE" --url https://qz.sii.edu.cn
  ```
  Passing the full `inspire-session=<value>` string as the value will silently fail (browser sends
  `inspire-session=inspire-session%3D<value>` and QZ rejects it with a redirect to keycloak).
- Must use `--url https://qz.sii.edu.cn` when setting cookie.
- Do NOT combine `--url` and `--domain` — Playwright rejects it.
- Cookie name is `inspire-session` (not `session`).
- `cookie_expires_at` in auth.json is unreliable (often 0). Test with a fetch after setting.
- If `${QZ_CACHE_DIR:-~/.cache/qz}/auth.json` has no `cookie` field, tell user to `qz login -d`.

## XHR Interceptor

- Lost on every `agent-browser open` / page navigation. Re-install after.
- The page binds its own fetch early — your interceptor may miss calls made during page load.
- `performance.getEntriesByType('resource')` always works as a fallback (shows URLs but not bodies).
- Write the interceptor script to a temp file to avoid shell quoting issues with `eval`.

## UI Annoyances

- Release-notes modal on first visit blocks everything — close with 关闭 button.
- Create-job drawer blocks sidebar clicks — press Escape first.
- Dropdown options sometimes time out with `click @ref` — use `find text "..." click` instead.
- For `find text` with multiple matches, add `--exact` for exact match.

## JS Bundle

- Main bundle: `/assets/index.CCqZT6FB.js` (hash changes on deploy).
- Find current filename: `document.querySelectorAll('script')[0].src`
- Endpoint map is defined as `or={...}` near `co="/api/v1"` in the main bundle.
- Some endpoints are in lazy-loaded chunks (e.g., `computeTypesService.*.js`, `interactiveModel.*.js`).
- Search for the endpoint path string (e.g., `logic_compute_groups/list`) across all chunks.

## Auth

- Bearer token (`Authorization: Bearer ...`) works for API calls from outside the browser.
- Cookie (`inspire-session`) works for browser-context `fetch()` with `credentials: 'include'`.
- Calling QZ APIs via `curl` from outside the browser needs the cookie set correctly:
  `curl -b "inspire-session=..." https://qz.sii.edu.cn/api/v1/...`
  But this may fail with 302 if APISIX routing requires the full cookie jar (observed).
  Prefer calling from browser context.

## Image CLI Limitations (as of 2026-03)

| Command | Status | Notes |
|---------|--------|-------|
| `qz image list` | ✓ works | pagination bug: server ignores `page_size > 3`, iterate with `page_size=1` |
| `qz image create` | ✓ works | returns PENDING_SYNC; requires push + sync before usable |
| `qz image delete` | ✓ works | |
| `qz image push` | ✓ works (with skopeo) | docker pull from Docker Hub fails on this machine (ZFS/overlayfs TLS error); use skopeo instead. `qz image push` auto-detects and falls back to skopeo if docker daemon is broken. |
| `qz image sync` | ✗ broken | `POST /api/v1/image/sync {"image_id":"..."}` returns HTTP 400 "unknown field image_id" from non-browser clients. Workaround: use QZ UI 镜像管理 → 同步镜像 button. Background auto-sync happens in ~minutes anyway. |

**Image push workflow that works end-to-end:**
1. `qz image create --name X --version Y` → gets `image_id`
2. `skopeo copy docker://<src> docker://docker-qb.sii.edu.cn/inspire-studio/X:Y --dest-creds <robot> --dest-tls-verify=false`
3. Click 同步镜像 in QZ UI, or wait a few minutes → status becomes SUCCESS

(`qz image push` automates steps 1+2 but not step 3 — sync must be done via UI.)



- `spec_id` in job creation payloads is actually a **UUID** (the `quota_id` from `instance_spec_price_info`).

## argparse

- If a subparser uses `dest="command"`, any `--command` argument on child parsers shadows it.
  The subparser's `dest` value gets overwritten by the flag's value. Use a different dest name
  (e.g., `dest="subcmd"`) or avoid `--command` as a flag name.
  The old `c168m1800g8t` format was only used by the model-deploy CLI, NOT for training jobs.
- spec_id differs **per workspace AND per datacenter** within a workspace:
  - Shared DC1 (120 CPU, 1600GB): `f23c8d53-395f-473c-81e0-dbd132711861`
  - Shared DC2/DC3 (180 CPU, 1800GB): `b618f5cb-c119-4422-937e-f39131853076`
  - Dedicated all pools (168 CPU, 1800GB): `2578a742-1215-4279-893c-df7a947d9238`
- To discover spec_ids for new pools: find a real job in that pool via `train_job/list`,
  then read `framework_config[0].instance_spec_price_info.quota_id`.
- The `/openapi/v1/specs/list` endpoint (from old docs) returns **404** — it doesn't exist.
- The `/api/v1/resource_prices/logic_compute_groups/` endpoint returns empty for training pools
  (may only work for inference/interactive specs).
- The scheduling page (`/jobs/scheduling?spaceId={ws_id}`) shows specs per pool in the WebUI.
