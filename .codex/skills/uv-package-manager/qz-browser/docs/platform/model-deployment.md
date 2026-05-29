# QZ Model Deployment (推理部署 / 模型部署)

Model deployment is distinct from training jobs: it exposes a reverse-proxied HTTP endpoint
(vllm / sglang compatible) secured with a per-user API key. The reverse proxy enforces
`Authorization: Bearer <api_key>` on every request and uses one-turn half-duplex transfer
(request body uploaded first, then response downloaded; no WebSocket).

## URL Routes

| Page | URL |
|------|-----|
| Deployment list | `/jobs/modelDeployment?spaceId={ws_id}` |
| Deployment detail | `/jobs/modelDeplayDetail/{sv_id}?spaceId={ws_id}` |

Note: "Deplay" is the actual typo in the URL — not "Deploy".

---

## API Endpoints

All endpoints are under `/api/v1/inference_servings/` except where noted.
Auth via `inspire-session` cookie (browser) or Bearer token for OpenAPI.

### List

```
POST /api/v1/inference_servings/list
  {
    workspace_id:  string,
    page:          int,
    page_size:     int,
    filter_by?:    {my_serving: bool}      # true = only your own
  }
  → {code, data: {inference_servings: [...InferenceServing], total: int}}
```

The default (no filter_by) returns all workspace deployments; `filter_by: {my_serving: true}` scopes to the caller's own.

### Detail

```
GET /api/v1/inference_servings/{sv_id}
  → {code, data: InferenceServing}
```

### Create

```
POST /api/v1/inference_servings/create
  (see InferenceServing Create Schema below)
  → {code, data: {inference_serving_id: "sv-..."}}
```

### Update

```
POST /api/v1/inference_servings/update
```

**NOT the same shape as create.** The update protobuf schema is stricter:
- Accepts: `inference_serving_id`, `mirror_id`, `model_id`, `model_version`, `command`, `port`,
  `replicas`, `node_num_per_replica`, `task_priority`, `resource_spec_price`
- Rejects: `name`, `workspace_id`, `project_id`, `logic_compute_group_id` (HTTP 400 unknown field)

### Delete

```
DELETE /api/v1/inference_servings/{sv_id}
  → {code}
```

### Start (部署)

```
POST /api/v1/inference_servings/{sv_id}/start
  (no body)
  → {code}
```

### Stop (下线)

```
POST /api/v1/inference_servings/{sv_id}/stop
  (no body)
  → {code}
```

### Instances

```
POST /api/v1/inference_servings/instances/list
  {inference_serving_id, page, page_size}
  → {code, data: {groups: [{items: [...Instance]}], total: string}}
```

`groups` are grouped by replica. For `node_num_per_replica == 1`, each group has one
item. For multi-node replicas, each group contains one `LEADER` plus one or more
`WORKER` items.

Instance fields: `name` (pod name), `node`, `status` (`INSTANCE_SUCCEEDED` etc.),
`ready` (bool), `restarts`, `running_time_ms`, `started_at`, `finished_at`,
`component_type` (`LEADER` or `WORKER`).

Observed naming:
- replica 0 leader: `{project_slug}/{sv_id}-0`
- replica 0 worker 1: `{project_slug}/{sv_id}-0-1`
- replica 1 leader: `{project_slug}/{sv_id}-1`

### Events

```
POST /api/v1/inference_servings/events/list
  {page, page_size,
   filter: {object_type: 0, object_ids: ["sv-..."]}}
  → {code, data: {items: [...]}}
```

### Logs

```
POST /api/v1/logs/inference_serving
  {page_size,
   filter: {podNames: ["namespace/pod-name"]},
   sorter?: [{field, sort}]}
  → {code, data: {logs: [{log_id, message, node, pod_name, time, timestamp_ms}], total}}
```

Pod names use the format: `{project_id_slug}/{sv_id}-{replica_index}`
e.g. `qproject-fundationmodel/sv-f252922d-...-0`

The current WebUI "实例" log viewer does not use a separate per-instance endpoint.
It calls this same endpoint with a single selected pod name in `filter.podNames`.
For multi-node replicas, worker `0` is the `LEADER` pod `{sv_id}-{replica}` and
worker `1+` maps to `{sv_id}-{replica}-{worker}`.

### User Project List (for create/filter dropdowns)

```
POST /api/v1/inference_servings/user_project/list
  {workspace_id}
  → {code, data: {projects: [{project_id, project_name}], users: [{user_id, user_name}]}}
```

---

## InferenceServing Schema

Key fields from GET detail and list responses:

```
inference_serving_id      string    "sv-..."
name                      string    service display name
status                    string    RUNNING | STOPPED | DEPLOYING | ...
                                    UI label: 运行中 | 已下线 | 部署中
custom_domain             string    subdomain prefix (auto-generated if not set)
port                      int       container port the vllm/sglang server listens on
command                   string    shell command; use ${PORT} for the port number
description               string
workspace_id              string    "ws-..."
project_id                string    "project-..."
logic_compute_group_id    string    "lcg-..."
mirror_id                 string    image ID ("image-...")
model_id                  string    model UUID
model_version             int       version number
inference_serving_type    string    "CUSTOM" (custom image+command)
replicas                  int       推理服务副本数 (total service replicas)
node_num_per_replica      int       单副本实例数 (nodes per replica)
task_priority             int       10 = high, lower = lower priority
enable_auto_scaling       bool
scale_status              string    "NO_SCALE" etc.
version                   int       config version (incremented on update)
created_time              string    unix millis string
updated_time              string    unix millis string
user_id                   string
resource_spec_price       {}        resource spec (see below)
extra_info                {}        runtime info (see below)
model                     {}        model metadata
mirror                    {}        image metadata
project                   {}        project metadata
```

### resource_spec_price

```
quota_id          string    "c168m1800g8t" (format: c{cpu}m{mem_gi}g{gpu_count}t)
cpu_count         int       CPU cores per node / instance within a replica
memory_size_gib   int       RAM GiB per node / instance within a replica
gpu_count         int       GPU cards per node / instance within a replica
gpu_info          {}        {brand, gpu_type, gpu_memory_size_gb, gpu_product_simple}
total_price_per_hour  int   quota unit price per hour per node / instance
```

### extra_info (runtime)

```
available_replicas    int        replicas currently in RUNNING state
node_names            []string   leader node hostnames for currently available replicas
service               string     full HTTPS URL of the proxy endpoint
```

---

## Replica Topology

The platform terminology is easy to misread. The observed runtime topology is:

- `replicas` = number of horizontal service copies behind one public deployment URL.
- `node_num_per_replica` = number of nodes used by each replica.
- Total reserved nodes = `replicas * node_num_per_replica`.

From live `instances/list` responses:

- Each `groups[]` entry corresponds to one replica.
- A single-node replica has one item named `{sv_id}-{replica_index}`.
- A multi-node replica has one `LEADER` item named `{sv_id}-{replica_index}` plus
  worker items named `{sv_id}-{replica_index}-1`, `{sv_id}-{replica_index}-2`, etc.

Example: a service with `replicas = 5` and `node_num_per_replica = 2` returns
5 groups, each with 2 items: one `LEADER` and one `WORKER`.

Operational interpretation:

- Increasing `replicas` adds more externally reachable serving copies.
- Increasing `node_num_per_replica` makes each replica a distributed serving group
  (for example, one leader node plus N-1 worker nodes), not more horizontal replicas.
- `resource_spec_price.gpu_count` should be treated as GPU count per node within the
  replica. This matches observed 2-node and 4-node services whose `gpu_count` is still `8`.

---

## Proxy URL and API Key

### Proxy URL

The deployed service is accessible at:
```
https://{custom_domain}.{datacenter-specific-suffix}
```

The suffix varies by datacenter (e.g., `openapi-qb-ai.sii.edu.cn`, `openapi-qb.sii.edu.cn`).
Always use `extra_info.service` from the GET detail response for the actual URL.

This URL is also returned in `extra_info.service` from the GET detail response.

The reverse proxy is OpenResty/APISIX. Every request must carry:
```
Authorization: Bearer <api_key>
```

Request style is **one-turn half-duplex**: the full request body is sent, then the response
is received. WebSocket upgrades are not supported.

### What the proxy targets

Confirmed from runtime/API data and user clarification:

- There is one public URL per deployment, not one URL per replica or per worker.
- `extra_info.node_names` exposes one node name per available replica, and for multi-node
  replicas that node matches the `LEADER` instance from `instances/list`.
- Multi-node replicas expose internal `WORKER` instances in `instances/list`, but those
  workers do not get separate public URLs.
- The external endpoint is load-balanced across replica `LEADER` instances.
- For `node_num_per_replica > 1`, the leader handles HTTP on the exposed `port` and
  talks to its worker nodes over the cluster network.

Operationally, treat the path as:

`public deployment URL` -> `gateway / reverse proxy` -> `nginx load balancer across leaders`

Workers are internal backend members of a replica and are not directly exposed.

### API Keys

API keys are per-user, not per-service. The same key works for any service you own.

```
GET /api/v1/user/my-api-key/list
  → {code, data: {items: [{key_id, name, value: "****", created_at}]}}

GET /api/v1/user/my-api-key/show/{key_id}
  → {code, data: {value: "<plaintext key>"}}
```

The `list` endpoint redacts the key value; use `show` to retrieve the plaintext.

---

## Create Schema (form fields)

From the 编辑服务 UI and XHR captures:

```
name                          string    service name (lowercase, alphanumeric + hyphen + dot, starts with letter)
workspace_id                  string    "ws-..."
project_id                    string    "project-..."
logic_compute_group_id        string    "lcg-..."
mirror_id                     string    image ID
command                       string    shell command (use ${PORT} for the container port)
port                          int       container port (default 8000)
model_id                      string    model UUID
model_version                 int       model version number
replicas                      int       number of service replicas (推理服务副本数)
node_num_per_replica          int       nodes per replica (单副本实例数, usually 1)
task_priority                 int       10 = high priority
resource_spec_price           {}        {quota_id, cpu_count, memory_size_gib, gpu_count, ...}
custom_domain?                string    custom subdomain prefix (optional, max 63 chars)
description?                  string
enable_auto_scaling?          bool
```

Note: `name` cannot be changed after creation (field is disabled in the edit form).

### LCG list filter for inference serving

When fetching compute groups for the create form:
```
POST /api/v1/logic_compute_groups/list
  {pageNum: 1, pageSize: 10000,
   filter: {workspace_id, support_job_type: "inference_serving_customize", include_gpu_type_stats: true}}
```

The `support_job_type` value `"inference_serving_customize"` is specific to model deployment
(training uses `"distributed_training"`).

### Resource price fetch for form

```
POST /api/v1/resource_prices/logic_compute_groups
  {workspace_id, logic_compute_group_id, schedule_config_type: "SCHEDULE_CONFIG_TYPE_SERVE"}
```

Response key is `lcg_resource_spec_prices` (not `resource_spec_prices`).

**IMPORTANT:** The `quota_id` format varies by workspace:
- Dedicated workspaces: compact format like `c168m1800g8t`, `c10m100g1tNVIDIA_4090_48G`
- Shared workspaces: UUID format like `8f2adc2a-d28b-485d-b64e-4bca4091bf44`

Both formats come from this endpoint and both are valid for create/update.

### Model Plaza

```
POST /api/v1/model_plaza/list
  {page, page_size}
  → {code, data: {items: [{model_id: "mp-...", name, version, ...}], total_count}}
```

Model plaza models use `mp-` prefixed IDs and `model_source: "MODEL_PLAZA"`.
Workspace model hub models use bare UUIDs and `model_source: "MODEL_HUB"`.
Both are accepted in create/update payloads.

---

## Create Payload — Protobuf Constraints

The create endpoint uses protobuf deserialization and **rejects unknown fields** with HTTP 400.

`resource_spec_price` MUST contain:
```
quota_id                string    e.g. "c168m1800g8t"
cpu_count               int
memory_size_gib         int
gpu_count               int
gpu_type                string    e.g. "NVIDIA_H200_SXM_141G" (from gpu_info.gpu_type in price response)
cpu_type                string    "" (empty string is fine)
logic_compute_group_id  string    "lcg-..." (same as top-level field)
```

Do NOT include: `cpu_info`, `gpu_info`, `total_price_per_hour`, `*_price`, `*_price_id`, `*_price_version_id`.
These fields appear in GET responses and `get_resource_prices` output but are rejected by create/update.

Create also requires `inference_serving_type: "CUSTOM"` in the top-level payload.

### Scale (live, no stop needed)

```
POST /api/v1/inference_servings/scale
  {inference_serving_id: "sv-...", replica: int}   # NOTE: "replica" singular
  → {code}
```

Works on RUNNING deployments. Returns error if another scale operation is in progress.

---

## Model Hub

Models for inference serving are managed separately from training job datasets:

```
POST /api/v1/model/list
  {page, page_size, filter_by: {}, workspace_id}
  → {code, data: {list: [{model: {...}, project_name, user_name}], total}}
```

Model fields: `model_id`, `name`, `version`, `model_path` (GPFS path), `model_source_type`
(1 = user-uploaded), `is_vllm_compatible`, `status` (2 = ready).

---

## Status Values

| Status | Meaning |
|--------|---------|
| `RUNNING` | Running (运行中) |
| `STOPPED` | Offline / stopped (已下线) |
| `DEPLOYING` | Deploying (部署中) |
| `FAILED` | Failed (部署失败) |
| `PENDING` | Pending (待部署) |

---

## Gotchas

- `custom_domain` in the create/edit form is the subdomain prefix; the full URL has suffix `.openapi-qb.sii.edu.cn`.
- `custom_domain` is auto-generated if left empty. The generated value is a random alphanumeric string.
- `port` is the **container port** that the vllm/sglang process listens on. The reverse proxy handles the HTTPS→HTTP translation. Use `${PORT}` as a shell variable in the command string so it can be overridden by the platform.
- The list endpoint with no `filter_by` and `page_size: -1` will return 0 items but correct `total`. Use `page_size: 10` + `page: 1` to get actual records.
- XHR captures show the correct list body: `{page: 1, page_size: 10, filter_by: {my_serving: true}, workspace_id: "..."}`.
- `GET /api/v1/inference_servings/{sv_id}` has a trailing `?` in some browser XHR calls — this is a UI artifact; the clean URL works fine.
- API keys are scoped to the user, not the service. One key works for all your deployed services.
- `DELETE /api/v1/inference_servings/{sv_id}` — uses HTTP DELETE method, not POST.
- Start/stop use HTTP POST to `/api/v1/inference_servings/{sv_id}/start` and `.../stop`.
