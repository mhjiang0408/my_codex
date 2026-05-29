# QZ API Reference

Proto-based backend at `https://qz.sii.edu.cn`. All POST endpoints accept JSON.
Auth via `inspire-session` cookie (browser context carries it automatically).

## Train Jobs

```
POST /api/v1/train_job/list
  {page_num, page_size, workspace_id, created_by?, status?}
  → {code, data: {jobs: [...], total}}    — NOTE: data.jobs, NOT data.items

POST /api/v1/train_job/detail
  {job_id}
  → {code, data: {name, command, framework, framework_config, status, ...}}

POST /api/v1/train_job/create
  (see Job Schema below)
  Key fields in framework_config[0]:
    cpu           — CPU cores per node (form field: framework_config_0_cpu / framework_config_0_instance_count)
    shm_gi        — shared memory GiB (UI label: "共享内存(GB)"; form field: framework_config_0_shm_gi)
    mem_gi        — memory GiB per node
    gpu_count     — GPUs per node
    instance_count — node count
  NOTE: no cpu_elastic_ratio / cpu_limit_ratio for jobs — only for notebooks

POST /api/v1/train_job/stop
  {job_id}

POST /api/v1/train_job/delete
  {job_id}

POST /api/v1/train_job/instance_list
  {jobId, page_num, page_size}          — camelCase jobId! page_size=-1 for all
  → {code, data: {items: [...], total}}
  Instance names look like `job-<uuid>-worker-0`, `...-worker-1`, etc.

POST /api/v1/train_job/job_event_list
  {jobId}                               — camelCase jobId!
  → {code, data: {items: [...]}}

POST /api/v1/train_job/instance_event_list
POST /api/v1/train_job/instance_logs
  NOTE: frontend bundles still reference this path, but direct requests on `qz.sii.edu.cn`
  return HTTP 404. The current WebUI "实例" log viewer does NOT use it.
POST /api/v1/train_job/events/list
POST /api/v1/train_job/workdir
POST /api/v1/train_job/users           — {workspace_id} → creator list

POST /api/v1/logs/train
  {page_size, filter: {podNames: ["pod-..."], start_timestamp_ms: "...", end_timestamp_ms: "..."},
   sorter: [{field: "...", sort: "..."}]}
  NOTE: timestamps are STRING milliseconds, podNames is an array
  NOTE: the current WebUI "实例" tab fetches per-worker logs by calling this endpoint
  with exactly one pod name in `filter.podNames`

POST /api/v1/logs/train/download
```

## Compute Resources

```
POST /api/v1/logic_compute_groups/list
  {pageNum, pageSize, filter: {workspace_id, support_job_type, include_gpu_type_stats}}
  → {code, data: {logic_compute_groups: [...], total}}
  NOTE: camelCase pageNum/pageSize, NOT snake_case

GET  /api/v1/logic_compute_groups/{lcg_id}
GET  /api/v1/compute_resources/logic_compute_groups/{lcg_id}
  → {data: {gpu_type_stats: [{gpu_info: {...}, node_count}],
            logic_resouces: {cpu_total, cpu_used, gpu_total, gpu_used,
                             gpu_low_priority_used, memory_gi_total, memory_gi_used}}}
  NOTE: "logic_resouces" is misspelled (one 'r') in the actual API response
  gpu_low_priority_used = GPUs occupied by low-priority (preemptible) tasks across all users

GET  /api/v1/compute_resources/node_specs/logic_compute_groups/{lcg_id}
  → {data: {node_specs: [{cpu_count, gpu_count, gpu_info, memory_size, support_job_type}]}}

POST /api/v1/resource_prices/logic_compute_groups/
  Request pattern for train-job spec lookup:
    {workspace_id, logic_compute_group_id, schedule_config_type: "SCHEDULE_CONFIG_TYPE_TRAIN"}
  → {code, data: {lcg_resource_spec_prices: [{quota_id, cpu_count, gpu_count, memory_size_gib, ...}]}}
  NOTE: this is the correct source for train-job `spec_id` / quota resolution.
  NOTE: notebook pricing uses `SCHEDULE_CONFIG_TYPE_DSW`; do not mix the two when preparing qz train fallback.
POST /api/v1/cluster_nodes/list
GET  /api/v1/cluster_nodes/workspace/{ws_id}
POST /api/v1/cluster_nodes/distincts
POST /api/v1/cluster_metric/resource_metric_by_time
  {metric_types: ["gpu_usage_rate"],
   filter: {logic_compute_group_id: "lcg-...", task_type: "distributed_training", task_id: "job-..."},
   time_range: {start_timestamp: 1773242034, end_timestamp: 1773327335, interval_second: 3600}}
  → {code: 0, data: {time_seris_metric_groups: [
       {group_name: "job-...-worker-0", metric_type: "gpu_usage_rate",
        resource_name: "GPU", time_series: [{data: 0.15, timestamp: "1773252834"}, ...]}
     ]}}
  NOTE: "time_seris_metric_groups" is misspelled (seris, not series) in the actual API
  NOTE: timestamps are unix SECONDS (not ms), but timestamp in time_series is a STRING
  NOTE: data values are rates (0-1.0) for *_rate metrics, bytes/sec for IO metrics
  Available metric_types:
    gpu_usage_rate, gpu_memory_usage_rate, cpu_usage_rate, memory_usage_rate,
    disk_io_read, disk_io_write, network_io_read, network_io_write,
    network_storage_io_read, network_storage_io_write
  group_name is per worker: "job-{id}-worker-{N}"
  resource_name: GPU, GPU_Memory, CPU, Memory, Disk, Network
```

## Projects, Users, Images

```
POST /api/v1/project/list
  {filter?: {workspace_id, check_admin}, page?, page_size?}

POST /api/v1/image/list
  {page, page_size, filter: {source, source_list, registry_hint: {workspace_id}}}

GET  /api/v1/user/detail
  → {code: 0, data: {id, name, ...}}
  NOTE: "id" is a string like "user-..." (same format as creator.id in image responses)
GET  /api/v1/user/routes/{ws_id}
  → {code, data: {routes: [{name, routes: [...]}, ...]}}
  NOTE: workspace enumeration lives under `data.routes[name="userWorkspaceList"].routes[]`
  NOTE: each route item carries the visible workspace label and target `ws-*` id; this is a practical way to recover all currently accessible workspaces for qz config generation.
GET  /api/v1/user/permissions/{ws_id}
```

## Tensorboard

```
POST /api/v1/train_job/tb/create
POST /api/v1/train_job/tb/detail    {tb_id}
POST /api/v1/train_job/tb/by_job
  NOTE: historical jobs may still return HTTP 404 on this endpoint even when the train job
  itself still exists and `train_job/detail` / `logs/train` remain readable. Do not assume
  this is a stable source of retrospective loss curves.
POST /api/v1/train_job/tb/stop
POST /api/v1/train_job/tb/start
POST /api/v1/train_job/tb/delete
```

## Historical Log Retrieval

```
POST /api/v1/logs/train/download
  NOTE: returns a plain-text attachment body (`text/plain`), not JSON.
  Suitable for offline parsing when you need the full historical raw log stream.

POST /api/v1/train_job/detail
  NOTE: cookie-auth browser endpoint remains useful for read-only historical inspection
  alongside the bearer-token openapi detail path.
```

## OpenAPI Endpoints

```
POST /openapi/v1/train_job/detail
  {job_id: "..."}                       — NOTE: field is job_id, NOT id

POST /openapi/v1/train_job/stop
  {job_id: "..."}                       — NOTE: field is job_id, NOT id
```

## Model Deployments (Inference Serving)

```
POST /api/v1/inference_servings/list
  {workspace_id, page, page_size, filter_by?}
  filter_by: {my_serving?: true}

GET  /api/v1/inference_servings/{sv_id}
  → {code, data: {inference_serving_id, name, status, custom_domain, extra_info, ...}}

POST /api/v1/inference_servings/create
  {name, workspace_id, project_id, logic_compute_group_id, mirror_id,
   command, port, model_id, model_version, replicas, node_num_per_replica,
   task_priority, resource_spec_price, custom_domain?}
  NOTE: custom_domain sets the public URL subdomain prefix; if omitted,
        the platform auto-generates a random string.

POST /api/v1/inference_servings/update
  {inference_serving_id, mirror_id, model_id, model_version,
   command, port, replicas, node_num_per_replica, task_priority,
   resource_spec_price, custom_domain?}

POST /api/v1/inference_servings/scale
  {inference_serving_id, replica}

POST /api/v1/inference_servings/instances/list
  {inference_serving_id, page, page_size}

POST /api/v1/inference_servings/events/list
  {page, page_size, filter: {object_type: 0, object_ids: [sv_id]}}

POST /api/v1/logs/inference_serving
  {page_size, filter: {podNames: ["pod-..."]},
   sorter: [{field: "time", sort: "descend"|"ascend"}, ...],
   search_after?}
```

## Notebooks (Interactive Modeling)

```
POST /api/v1/notebook/list
  {workspace_id, page, page_size, filter_by?, order_by?}
  filter_by: {keyword?, user_id?: [...], logic_compute_group_id?: [...], status?: [...], mirror_url?: [...]}
  order_by: [{field: "created_at", order: "desc"}]
  → {code, data: {list: [...], total}}    — NOTE: data.list (NOT data.notebooks)
  NOTE: uses page/page_size (same as project/list, NOT page_num like train_job/list)
  NOTE: filter sub-object is "filter_by" (NOT "filter" like other endpoints)
  CAUTION: filter_by field is REQUIRED (even as empty {}), otherwise server panics (code 100000, nil pointer dereference)

GET  /api/v1/notebook/{notebook_id}
  → {code, data: {
       notebook_id,          — UUID string (no prefix)
       id,                   — numeric string e.g. "197896"
       name,
       status,               — "RUNNING"|"STOPPED"|"CREATING"|"STOPPING"|"FAILED"|"COMMITTING"
       sub_status,
       created_at,           — unix millis string
       updated_at,
       live_time,            — seconds running (string)
       left_time,            — "0" = no time limit
       cpu_elastic_ratio,    — int (NOTE: IS returned in detail response; contradicts earlier note)
       vscode_version,       — e.g. "1.101.2"
       mirror_url,           — docker pull URL (current running image)
       image: {address, name, version, source, visibility, image_id, ...},
       mirror: {address, name, version, source, visibility, image_id, created_at, status, ...},
       backup_image: {...},  — auto-saved image (empty if no auto-save)
       quota: {cpu_count, gpu_count, gpu_ram, memory_size, quota_id},
       resource_spec_price: {cpu_count, cpu_price, cpu_price_id, gpu_count, gpu_price,
                              memory_price, memory_price_id, memory_size_gib, quota_id, total_price_per_hour},
       start_config: {
         cpu_count, gpu_count, memory_size,
         shared_memory_size,    — GiB
         logic_compute_group_id, quota_id, mirror_id, mirror_url,
         allow_ssh,             — bool: whether SSH was enabled at start
         ssh_id,                — "ssh-..." if SSH key configured, "" otherwise
         auto_stop, slurm,
         node_id, queue_id,
         project_priority: {priority: int},
         runtime, save_image_id, mount_path, ...
       },
       extra_info: {          — runtime info (only populated when RUNNING)
         ContainerID,         — containerd://...
         HostIP,              — internal pod IP
         NodeName,            — e.g. "cpu-nat-399"
         PodName,             — k8s pod name
         ProxyJump,           — "jumpuser@proxy.sii.edu.cn:20033" for SSH access
         SshDomain,           — "{name}--{id_suffix}.{k8s_ns}.svc"
         SshPort,             — 0=not ready, -1=exhausted, >0=allocated port
       },
       creator: {id, name, name_en, global_role, ...},
       project: {id, name, en_name, ...},
       workspace: {id, name, ...},
       node: {id, name, cpu_count, gpu_count, memory_size, status, ...},
       logic_compute_group: {name, ...},
       dataset_info: [],
       save_mirror_status: {status: "SUCCESS"|..., ...},
       enable_notification: bool,
       description: string,
     }}

POST /api/v1/notebook/create
  {workspace_id, name, project_id, auto_stop,
   mirror_id, mirror_url,                     — NOTE: mirror_id NOT image_id
   logic_compute_group_id, quota_id,
   cpu_count, gpu_count, memory_size, shared_memory_size,
   cpu_elastic_ratio,                          — CPU burst/bounce factor (integer); form field id="cpu_elastic_ratio"
                                               — UI label: "CPU 弹性系数" (CPU elastic coefficient)
                                               — tooltip: "用于表示CPU资源保证分配的资源量和最大可用资源量的范围系数，
                                                           超过最大可用资源量时会被限速"
                                               — meaning: cpu_limit = cpu_count × cpu_elastic_ratio, cpu_request = cpu_count
                                               — NOT returned in GET /notebook/{id} or start_config
   task_priority,                              — project priority LEVEL (1|4|10), NOT raw priority
   vscode_version,                             — e.g. "1.101.2" or "1.85.1"
   mount_path,                                 — [] for none
   node_id,                                    — "" for auto
   allow_ssh, ssh_id,                          — SSH key setup
   stop_hour, stop_minute,                     — auto-stop time (0 = no auto-stop)
   resource_spec_price: {                      — REQUIRED (nil check), even for CPU notebooks
     logic_compute_group_id,                   — REQUIRED in this object
     cpu_count,                                — REQUIRED
     gpu_count,                                — REQUIRED
     — optional: quota_id (rejected), memory_size (rejected), id (rejected), price (rejected)
     — if the workspace has pricing configured, may also include price fields
   }}
  → {code, data: {notebook_id, sub_code, sub_msg}}
  NOTE: "description" field is rejected (not in proto schema).
  NOTE: "project_name" field is rejected (not in proto schema).
  NOTE: resource_spec_price.quota_id causes "record not found" — use logic_compute_group_id instead.
  NOTE: resource_spec_price.memory_size is rejected (unknown field).
  NOTE: resource_spec_price required even when workspace has no pricing (empty lcg_resource_spec_prices).
  NOTE: The resource_spec_price structure for workspaces WITH pricing comes from:
    POST /api/v1/resource_prices/logic_compute_groups/ {workspace_id, schedule_config_type: "SCHEDULE_CONFIG_TYPE_DSW", logic_compute_group_id}
    → {data: {lcg_resource_spec_prices: [...]}}  (empty [] for unpriced workspaces)
  EXAMPLE for CPU notebook (no pricing):
    resource_spec_price: {logic_compute_group_id: "lcg-...", cpu_count: 2, gpu_count: 0}

POST /api/v1/notebook/operate
  {notebook_id, operation}                    — field is "operation" NOT "action" or "type"
  operation: "START" | "STOP" | "COMMIT"
  → {code, data: {...}}

PUT  /api/v1/notebook/{notebook_id}
DELETE /api/v1/notebook/{notebook_id}

POST /api/v1/notebook/events  {notebook_id, ...}
GET  /api/v1/notebook/events/{notebook_id}    — SSE stream
GET  /api/v1/notebook/schedule/{ws_id}
  → {code, data: {
       workspace_id,
       config_id,            — UUID of the schedule config
       quota,                — JSON string (not object!): [{id, name, cpu_count, memory_size, gpu_count, gpu_type, cellId}]
       rayjob_quota,         — JSON string: same format as quota
       serving_quota,        — JSON string: same format
       auto_recycle,         — 0|1 whether auto-recycle is enabled
       open_ssh,             — bool: whether SSH feature is enabled for this workspace
       ssh_domain,           — custom SSH domain (empty = use default)
       ssh_limit,            — max SSH port number range
       recycle_config: {gate, conds: [{gate, conds: [{crit, hrs, thresh}]}]},
       recycle_standard,     — "CPU"|"GPU"
       enable_kata,          — bool
       left_time,            — "-1" = unlimited
       timed_shutdown, auto_recycle_rayjob, auto_recycle_train, ...
     }}
  NOTE: quota field is a JSON-encoded STRING, not an object. Must be JSON.parse()'d.
  NOTE: open_ssh controls whether the SSH section appears in the notebook create/edit form.
POST /api/v1/notebook/users   {workspace_id} → creator list

POST /api/v1/lifecycle/list
POST /api/v1/run_index/list   {notebook_id}
```

**Notebook lab (JupyterLab) proxy URL:**

```
GET /api/v1/notebook/lab/{notebook_id}
  → 301 redirect to: https://nat2-notebook-inspire.sii.edu.cn/{ws_id}/{project_id}/{user_id}/jupyter/{notebook_id}/{token}/lab?token={token}

URL detail page: /jobs/interactiveModelDetail/{notebook_id}?spaceId={ws_id}
```

The Jupyter server lives on `nat2-notebook-inspire.sii.edu.cn` (separate from `qz.sii.edu.cn`).
The `baseUrl` in the JupyterLab HTML embeds all path components plus a `{token}` (a UUID).

**Jupyter API access through the proxy:**
```
Base URL: https://nat2-notebook-inspire.sii.edu.cn/{ws_id}/{project_id}/{user_id}/jupyter/{notebook_id}/{token}

GET  {base}/api                   → {"version": "2.12.5"}   (no auth needed)
GET  {base}/api/terminals         → []  (requires Authorization header or ?token= query param)
POST {base}/api/terminals         → {"name": "1", "last_activity": "..."}
GET  {base}/api/sessions          → []
DELETE {base}/api/terminals/{n}   → 204

Auth options (both work):
  Header: Authorization: token {token}
  Query:  ?token={token}

WebSocket terminal URL:
  wss://nat2-notebook-inspire.sii.edu.cn/{ws_id}/{project_id}/{user_id}/jupyter/{notebook_id}/{token}/api/terminals/websocket/{n}?token={token}
```

Key fields from `/api/v1/notebook/{id}` (JupyterLab config):
- `token` is embedded in the redirect URL `?token=...` — this is the Jupyter server token
- `terminalsAvailable: true` in the HTML config data

**VS Code (IDE) URL:** `/ide?notebook_id={notebook_id}` (opens in new tab from the "打开" button in list)

## SSH Keys (for notebook SSH access)

SSH keys are user-level objects linked to a notebook at start time via `start_config.ssh_id`.

```
POST /api/v1/ssh/list
  {}                        — no params needed (user-scoped, ignore workspace_id field — it's rejected)
  → {code, data: {list: [{ssh_id, name, content, created_at}], total}}
  NOTE: list is EMPTY even when total > 0 (API bug observed). Use GET /api/v1/ssh/{id} for details.

GET  /api/v1/ssh/{ssh_id}
  → {code, data: {ssh_id, name, content, created_at}}
  content = the stored public key text

POST /api/v1/ssh/create
  {}                        — creates an empty key with auto-generated ssh_id
  {name, content}           — creates key with name and public key content
  → {code, data: {ssh_id}}
  NOTE: "public_key", "pub_key", "key", "pubkey" are all rejected. Use "content".

PUT  /api/v1/ssh/{ssh_id}
  {ssh_id, name, content}
  → 302 redirect (no JSON body on success)

DELETE /api/v1/ssh/{ssh_id}
  → {code: 0} on success
```

**SSH connection flow:**
1. Call `POST /api/v1/ssh/create {name, content}` to register an SSH public key → get `ssh_id`
2. Create/start notebook with `start_config.allow_ssh=true, start_config.ssh_id=<ssh_id>`
3. Poll notebook detail until `extra_info.SshPort != 0` (port is being allocated, shown as `SSHLianJieDuangKouChuangJianZhong`)
4. SSH connection: `ssh -o StrictHostKeyChecking=no -J {extra_info.ProxyJump} -p {extra_info.SshPort} root@{extra_info.SshDomain}`
5. `extra_info.SshPort == -1` means resource exhaustion (no port available)

Key `extra_info` fields in running notebook with SSH enabled:
- `ProxyJump`: `jumpuser@proxy.sii.edu.cn:20033`
- `SshDomain`: `{name}--{notebook_id_suffix}.{k8s_namespace}.svc`
- `SshPort`: allocated port number (0 = not ready, -1 = exhausted)
- `NodeName`: e.g. `cpu-nat-399`
- `HostIP`: internal pod IP
- `PodName`: k8s pod name
- `ContainerID`: containerd container ID

**Note:** No "rtunnel" binary or protocol is used in the WebUI SSH flow. SSH goes through a port-forwarded tunnel at `proxy.sii.edu.cn:20033`.
**However:** The platform ProxyJump approach only works in GPU workspaces (open_ssh=true). The jump host at proxy.sii.edu.cn:20033 cannot reach CPU notebook service DNS names (firewall/routing restricted).

**Working SSH via rtunnel (CPU + GPU notebooks):**
This is the reliable approach regardless of workspace type.
1. Install openssh-server in container (if absent). Use apt mirror: `http://nexus.sii.shaipower.online/repository/ubuntu/`
2. Write authorized_keys to `/root/.ssh/authorized_keys`
3. Start sshd: `nohup /usr/sbin/sshd -D -p <ssh_port> &`
4. Start fkqz (rtunnel server mode): `nohup /inspire/ssd/project/qproject-fundationmodel/public/zengji/home/qzssh/.bin/fkqz <ssh_port> <remote_port> -d &`
   - fkqz listens on `0.0.0.0:<remote_port>` and forwards connections to `127.0.0.1:<ssh_port>`
5. On local machine: `rtunnel <jupyter_proxy_url> 127.0.0.1:<local_port>`
   - Proxy URL pattern: `https://nat2-notebook-inspire.sii.edu.cn/{ws_id}/{proj_id}/{user_id}/jupyter/{nb_id}/{token}/proxy/<remote_port>/?token={token}`
   - Token comes from the Jupyter Lab redirect URL (GET /api/v1/notebook/lab/{nb_id})
6. SSH to `localhost:<local_port>` — tunnels via WebSocket through Jupyter proxy to sshd

**rtunnel URL format:**
- Jupyter proxy (requires `?token=` in query string): `https://nat2-notebook-inspire.sii.edu.cn/{path}/jupyter/{nb_id}/{token}/proxy/{port}/?token={token}`
- VS Code proxy (used by qz-cpu): `https://nat2-notebook-inspire.sii.edu.cn/{path}/vscode/{nb_id}/{token}/proxy/{port}/`
- Use `qz notebook tunnel {nb_id}` to automate the full flow (installs sshd, starts fkqz + rtunnel, updates ~/.ssh/config)

## Image Management

```
POST /api/v1/image/list
  {page, page_size, filter: {source?, source_list?, visibility?, registry_hint?: {workspace_id}}}
  → {code, data: {images: [...], total}}
  NOTE: total is a STRING ("53") not a number
  NOTE: pages are 0-INDEXED (page=0 is first page, page=1 is second page)
  NOTE: page_size > 5 returns empty images[] (server bug) — keep at 5
  NOTE: registry_hint is NOT needed for the image-management page, but the
        job/notebook create-form image picker does send registry_hint.workspace_id
  Filter combinations (from WebUI JS):
    Personal (个人可见): {source_list: ["SOURCE_PRIVATE", "SOURCE_PUBLIC"]}  (no visibility)
    Public (公开可见):   {source_list: ["SOURCE_PRIVATE", "SOURCE_PUBLIC"], visibility: "VISIBILITY_PUBLIC"}
    Official (官方镜像): {source: "SOURCE_OFFICIAL"}  (no source_list)
  NOTE: visibility filter is unreliable — total counts pre-filter, images[] is post-filter

  Create-form picker payloads (RE from 新建训练任务):
    Official:
      {page: 0, page_size: -1,
       filter: {source: "SOURCE_OFFICIAL", registry_hint: {workspace_id}}}
    Private / 个人可见:
      {page: 0, page_size: -1,
       filter: {source_list: ["SOURCE_PRIVATE", "SOURCE_PUBLIC"],
                visibility: "VISIBILITY_PRIVATE",
                registry_hint: {workspace_id}}}
    NOTE: typing in the image combobox did NOT trigger a second API call; the
          WebUI filters the preloaded picker results client-side.
    INFERENCE: Public / 公开可见 uses the same payload with
               visibility: "VISIBILITY_PUBLIC".

POST /api/v1/image/create
  {name, version, support_brand_list, visibility, add_method, registry_hint: {workspace_id}}
  name:               image base name (without version tag)
  version:            version string (e.g. "v0.2.3")
  support_brand_list: GPU vendor list (e.g. [""] for 通用/general, ["NVIDIA"] for NVIDIA-only)
  visibility:         "VISIBILITY_PRIVATE" | "VISIBILITY_PUBLIC"
  add_method:         "DIRECT_PUSH" | "FILE_UPLOAD"
  registry_hint:      {workspace_id: "ws-..."} — required
  → {code, data: {image: {
       image_id,       — "image-..."
       name,           — "{name}:{version}" combined
       version,
       address,        — full docker pull URL: "docker.sii.shaipower.online/inspire-studio/{name}:{version}"
       add_method,
       visibility,
       source,         — "SOURCE_PUBLIC" (default)
       status,         — "PENDING_SYNC" on create
       registry_id,    — "qbHarbor"
       region,         — ["七宝机房"] etc.
       created_at,     — "-62135596800" on create (epoch zero)
       publish_status, — "NOT_PUBLISHED" on create
       preheat_status, — "UNKNOWN_PREHEAT_STATUS" on create
       support_brand_info_list: [{brand, brand_name}],
       creator: {id, name, ...},
       size, description, preheat_node_num_all/fail/succ
     }}}
  NOTE: "source" is NOT a valid request field (proto rejects it). visibility uses VISIBILITY_ prefix enum.
  NOTE: field is "support_brand_list" (not vendor_id, brand, or brand_list)
  NOTE: field is "visibility" (not "type" or "access")
  NOTE: field is "add_method" (not "add_type" or "upload_type")
  NOTE: registry_hint takes {workspace_id} as an OBJECT (not a plain string)

POST /api/v1/image/update  {id, ...}   — NOTE: field is "id" NOT "image_id"
DELETE /api/v1/image/{image_id}
POST /api/v1/image/preheat
  {name, version, logic_compute_group_id, address?}
  name:    image base name (without version/tag, e.g. "cutlass" not "cutlass:0.1")
  version: version string (e.g. "0.1")
  logic_compute_group_id: target pool (lcg-...) to pre-cache on
  address: full registry URL (optional)
  → {code: 0} on success
  NOTE: does NOT take image_id — uses name+version to identify the image
GET  /api/v1/image/brands
POST /api/v1/image/robot
POST /api/v1/image/sync
  {workspaceId, imageName, imageVersion}   — NOTE: camelCase fields!
  workspaceId:  workspace ID (ws-...)
  imageName:    image base name (e.g. "cutlass")
  imageVersion: version (e.g. "0.1")
  → {code: 0, data: {image: {...}}} on success
  NOTE: does NOT take image_id — uses workspaceId+imageName+imageVersion
  NOTE: field names are camelCase (unlike most other endpoints)
  NOTE: previously documented as {image_id: "..."} — WRONG, causes "unknown field" error
```

**Image sync (同步镜像)**: After pushing to the registry, status stays `PENDING_SYNC` until
synced. The UI "同步镜像" button sends `POST /api/v1/image/sync` with body
`{workspaceId, imageName, imageVersion}` (camelCase fields!). The CLI can now call this
directly. Status goes SUCCESS once the registry content is confirmed; size field is populated.

**Verified full push flow (2026-03-18, using skopeo instead of docker due to ZFS/overlayfs)**:
```
1. qz image create --workspace gpu --name <name> --version <ver>  → image_id, PENDING_SYNC
2. skopeo copy --override-arch amd64 \
     docker://<source>  docker://docker-qb.sii.edu.cn/inspire-studio/<name>:<ver> \
     --dest-creds <robot_user>:<robot_pass> --dest-tls-verify=false
3. Click 同步镜像 in UI (or wait ~minutes for background sync) → status=SUCCESS
```
Robot credentials: decode `~/.docker/config.json` auth field for `docker-qb.sii.edu.cn`.

File upload flow (FILE_UPLOAD method):
```
POST /api/v1/file/sftpgo/connection_info  {storage_name, usage} → WebDAV credentials
POST /api/v1/file/check_before_upload
POST /api/v1/file/upload
POST /api/v1/file/upload_complete
POST /api/v1/file/check_upload_status
```
WebDAV upload: `PUT {webdav_address}:{webdav_port}/{path}/{filename}` with Basic auth.

Direct push registry: `docker-qb.sii.edu.cn/inspire-studio/<name>:<version>`

## Mirror / Notebook Commit

```
POST /api/v1/mirror/save   {notebook_id, name, version, description?, visibility?}
  → save running notebook container as new image
  NOTE: this is the endpoint behind `qz notebook save-image`
  NOTE: `visibility` accepts `VISIBILITY_PRIVATE` or `VISIBILITY_PUBLIC`
  NOTE: image creation is asynchronous; use image list/detail APIs to check for READY status
```

## Other

```
POST /api/v1/dataset/validate_dataset
```

---

## Job Detail Schema

Key fields from `/train_job/detail` response:

```
name                        string    job display name
job_id                      string    "job-..."
status                      string    job_pending|job_queued|job_running|job_failed|job_stopped
command                     string    shell command (newline-separated)
framework                   string    "pytorch"
workspace_id                string    "ws-..."
project_id                  string    "project-..."
logic_compute_group_id      string    "lcg-..."
logic_compute_group_name    string    pool display name
priority                    int       numeric (e.g. 35)
priority_level              string    "HIGH"|"LOW"|...
priority_name               string    display string ("10")
gpu_count                   int       total GPUs across all nodes
auto_fault_tolerance        bool
enable_vccl                 bool
enable_notification         bool
envs                        []        env var list
mounts                      []        volume mounts
dataset_info                []
framework_config            []{       PER-REPLICA config (array, not object):
  cpu                         int       CPU cores per node (= cpu_request)
  cpu_elastic_ratio           int       CPU burst multiplier; cpu_limit = cpu × ratio; max 2 in WebUI
  gpu_count                   int       GPUs per node
  image                       string    full image URL
  image_type                  string    SOURCE_OFFICIAL|SOURCE_PUBLIC|SOURCE_PRIVATE
  instance_count              int       number of nodes (THIS is the real node count)
  mem_gi                      int       memory GiB per node
  shm_gi                      int       shared memory GiB
  instance_spec_price_info    {}        resource spec with quota_id, pricing
}
created_at                  string    unix millis
finished_at                 string    unix millis
running_time_ms             string
timeline                    {}        job lifecycle timestamps
node_infos                  []        assigned node details
```

## Pool List Item Schema

From `/logic_compute_groups/list` → `data.logic_compute_groups[]`:

```
logic_compute_group_id    string    "lcg-..." (NOT "id")
name                      string    pool display name
compute_group_id          string    parent compute group
compute_group_name        string    parent group name
workspace_id              string
node_count                int       total nodes
abnormal_node_count       int
gpu_type_stats            []{gpu_info: {brand, gpu_product_simple, gpu_type, gpu_memory_size_gb}, node_count}
support_job_type_list     []string
support_node_type_list    []string
storage_disks             []
schedule_type             string
compute_net               string
```

## Image Source Types
- `SOURCE_OFFICIAL` — platform-provided images
- `SOURCE_PUBLIC` — publicly visible user images
- `SOURCE_PRIVATE` — personal/private images

## Job Status Values
- `job_pending` — submitted, waiting
- `job_queued` — in queue
- `job_running` — executing
- `job_failed` — failed
- `job_stopped` — user-stopped (已停止)
