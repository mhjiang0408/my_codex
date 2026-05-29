# QZ Notebook and Image Management APIs

Discovered by RE'ing `interactiveModel.BuYXnAwd.js`, `constant.B6SFsCDm.js`, `ftpgoService.XbBxmFNC.js`,
and `webdavClient.BjpXOz-7.js` lazy-loaded chunks, plus inspecting `inspire-cli` source.

---

## Notebook Endpoints

All POST/GET to `https://qz.sii.edu.cn`. Cookie auth via `inspire-session`.

```
POST /api/v1/notebook/list
  {workspace_id, page, page_size,
   filter_by: {keyword?, user_id?, logic_compute_group_id?, status?, mirror_url?},
   order_by: [{field, order}]?}
  → {code, data: {notebooks: [...], total}}
  NOTE: uses page/page_size (not page_num/pageNum — different from train_job/list!)

GET  /api/v1/notebook/{notebook_id}
  → {code, data: {notebook_id, name, status, workspace_id, project_id, ...}}

POST /api/v1/notebook/create
  (see Notebook Create Schema below)
  → {code, data: {notebook_id, ...}}

POST /api/v1/notebook/operate
  {notebook_id, operation}
  operation values: "START" | "STOP" | "COMMIT"
  NOTE: field is "operation" NOT "action" or "operate" or "type"
  → {code, data: {...}}

PUT  /api/v1/notebook/{notebook_id}
  (update notebook)

DELETE /api/v1/notebook/{notebook_id}

POST /api/v1/notebook/events
  {notebook_id, ...}

GET  /api/v1/notebook/events/{notebook_id}    — SSE stream
GET  /api/v1/notebook/{notebook_id}/events
GET  /api/v1/notebook/event/{notebook_id}
  → recent notebook events; response shape varies (`[]` or `{events|list: [...]}`)
  NOTE: these are best-effort helper endpoints seen in `inspire-cli`, distinct from the SSE stream above

GET  /api/v1/notebook/schedule/{ws_id}
GET  /api/v1/notebook/schedule?workspace_id={ws_id}
  → {code, data: {schedules: [{quota_id, logic_compute_group_id, name, cpu_count,
                                gpu_count, memory_size_gib, ...}]}}
  Use this to discover valid quota_ids for a workspace.
  NOTE: path-param form is what the WebUI usually uses; query-param form is a fallback seen in `inspire-cli`.

POST /api/v1/notebook/compute_groups
  {workspace_id}
  → notebook-compatible compute group list
  NOTE: if missing or empty, clients fall back to `/api/v1/logic_compute_groups/list`

POST /api/v1/notebook/users
  {workspace_id}
  → creator list

POST /api/v1/lifecycle/list

POST /api/v1/run_index/list
  {notebook_id}
```

### Notebook Create Schema

```json
{
  "workspace_id": "ws-...",
  "name": "my-notebook",
  "project_id": "project-...",
  "project_name": "...",
  "auto_stop": false,
  "mirror_id": "...",           // image ID (NOT "image_id")
  "mirror_url": "...",          // full image URL (NOT "image_url")
  "logic_compute_group_id": "lcg-...",
  "quota_id": "...",            // from notebook/schedule/{ws_id}
  "cpu_count": 160,
  "gpu_count": 8,
  "memory_size": 1800,          // GiB
  "shared_memory_size": 64,     // GiB
  "task_priority": 10,          // project priority LEVEL (1|4|10), NOT raw priority (e.g. 35)
  "resource_spec_price": {      // REQUIRED for GPU notebooks, nil → error 100002
    "quota_id": "...",
    "cpu_count": 160,
    "gpu_count": 8,
    "memory_size_gib": 1800,
    "gpu_price": 1,
    "cpu_price": 0,
    "memory_price": 0,
    "gpu_price_id": "rpc_...",
    "gpu_price_version_id": 1,
    "cpu_price_id": "rpc_...",
    "cpu_price_version_id": 1,
    "memory_price_id": "rpc_...",
    "memory_price_version_id": 1,
    "total_price_per_hour": 8,
    "gpu_info": {
      "brand": "NVIDIA",
      "gpu_type": "NVIDIA_H200_SXM_141G",
      "gpu_product_simple": "H200",
      "gpu_memory_size_gb": 141
    },
    "cpu_info": {"brand": "", "cpu_type": "", "cpu_product_simple": ""}
  }
}
```

**How to get resource_spec_price**: copy it from an existing notebook's detail response
(`GET /api/v1/notebook/{id}` → `data.resource_spec_price`), or from
`GET /api/v1/notebook/schedule/{ws_id}` → adapt from the schedule entry.

### Notebook Detail Schema

Key fields from `GET /api/v1/notebook/{notebook_id}` → `data`:

```
notebook_id           string    "notebook-..."
name                  string
status                string    see Status Values below
workspace_id          string
project_id            string
project_name          string
logic_compute_group_id string   "lcg-..."
quota_id              string
mirror_id             string    image ID
mirror_url            string    full image URL
cpu_count             int
gpu_count             int
memory_size           int       GiB
shared_memory_size    int       GiB
task_priority         int       project priority level
resource_spec_price   {}        spec with pricing (see create schema above)
created_at            string    unix millis
running_time_ms       string
```

### Notebook Status Values

- `notebook_pending` — submitted, waiting
- `notebook_running` — running (Jupyter/VSCode accessible)
- `notebook_stopped` — stopped
- `notebook_failed` — failed

### Notebook Proxy URLs

When `status == notebook_running`, the notebook is accessible via reverse proxy:

```
Jupyter Lab:  {base_url}/api/v1/notebook/lab/{notebook_id}/proxy/{jupyter_port}/
VSCode:       {base_url}/api/v1/notebook/lab/{notebook_id}/proxy/{vscode_port}/
```

Ports are container-internal. Default Jupyter: 8888. Default VSCode: varies.

---

## SSH / rtunnel

The QZ notebook SSH (rtunnel) feature creates a reverse tunnel so you can SSH into the container:

```
POST /api/v1/ssh/list    {workspace_id?, ...}
GET  /api/v1/ssh/{ssh_id}
POST /api/v1/ssh/create  {notebook_id, ...}
PUT  /api/v1/ssh/{ssh_id}
DELETE /api/v1/ssh/{ssh_id}
```

### rtunnel Binary

- Release URL: `https://github.com/Sarfflow/rtunnel/releases/download/nightly/rtunnel-{os}-{arch}.tar.gz`
  - OS: `linux` | `darwin`; arch: `amd64` | `arm64`
- Installed to `/tmp/rtunnel` inside the notebook container
- Bootstrap sentinel: `/tmp/.inspire_rtunnel_bootstrap_v1`
- Setup done marker echoed to stdout: `INSPIRE_RTUNNEL_SETUP_DONE`

### rtunnel Launch Commands (inside container)

```bash
# Start sshd (local-only, key auth)
/usr/sbin/sshd -p "$SSH_PORT" \
  -o ListenAddress=127.0.0.1 \
  -o PermitRootLogin=yes \
  -o PasswordAuthentication=no \
  -o PubkeyAuthentication=yes

# Start rtunnel (reverse tunnel)
nohup /tmp/rtunnel "$SSH_PORT" "$PORT" >/tmp/rtunnel-server.log 2>&1 &
```

`$PORT` is the externally visible port exposed via the notebook proxy URL.

---

## Image Management Endpoints

```
POST /api/v1/image/list
  {page, page_size, filter: {source?, source_list?, visibility?, registry_hint?: {workspace_id}}}
  → {code, data: {images: [...], total}}
  NOTE: total is a STRING ("53"), not a number
  NOTE: pages are 0-INDEXED (page=0 is first page)
  NOTE: page_size > 5 returns empty images[] (server bug) — keep at 5
  NOTE: the image-management page does NOT need registry_hint, but create-form
        image pickers do send registry_hint.workspace_id
  Filter combinations (from WebUI JS):
    Personal: {source_list: ["SOURCE_PRIVATE", "SOURCE_PUBLIC"]}
    Public:   {source_list: ["SOURCE_PRIVATE", "SOURCE_PUBLIC"], visibility: "VISIBILITY_PUBLIC"}
    Official: {source: "SOURCE_OFFICIAL"}

POST /api/v1/image/create
  {name, version, source, description?, add_method, ...}
  add_method: "DIRECT_PUSH" | "FILE_UPLOAD"
  → {code, data: {id, ...}}

POST /api/v1/image/update   (NOTE: uses {id} not {image_id})
  {id, name?, description?, ...}
  → {code: 0}

DELETE /api/v1/image/{image_id}

POST /api/v1/image/preheat
  {name, version, logic_compute_group_id, address?}
  NOTE: uses name+version (NOT image_id)
  → {code: 0}

GET  /api/v1/image/brands   → GPU brand list

POST /api/v1/image/robot    (robot/automated image actions)

POST /api/v1/image/sync
  {workspaceId, imageName, imageVersion}   — camelCase!
  NOTE: uses workspaceId+imageName+imageVersion (NOT image_id)
  → {code: 0, data: {image: {...}}}
```

### Create-Form Image Picker

RE from the distributed-training create dialog (`新建训练任务`):

```json
// 官方镜像
{
  "page": 0,
  "page_size": -1,
  "filter": {
    "source": "SOURCE_OFFICIAL",
    "registry_hint": {"workspace_id": "ws-..."}
  }
}

// 个人可见镜像
{
  "page": 0,
  "page_size": -1,
  "filter": {
    "source_list": ["SOURCE_PRIVATE", "SOURCE_PUBLIC"],
    "visibility": "VISIBILITY_PRIVATE",
    "registry_hint": {"workspace_id": "ws-..."}
  }
}
```

- The create-form picker uses the same `/api/v1/image/list` endpoint, but with
  `page_size: -1` and `filter.registry_hint.workspace_id`.
- The in-dropdown search box did NOT issue an extra API call while typing; the
  picker filters the preloaded image list client-side.
- Inference: the `公开可见镜像` radio uses the same payload pattern as above but
  swaps `visibility` to `VISIBILITY_PUBLIC`.

### Image Source Types

- `SOURCE_OFFICIAL` — platform-provided images
- `SOURCE_PUBLIC` — publicly visible user images
- `SOURCE_PRIVATE` — personal/private images

### Image Add Methods

**DIRECT_PUSH** — push via docker:
```
Registry: docker-qb.sii.edu.cn/inspire-studio/<name>:<version>
```
Create the image record first, then `docker push` to the registry URL.

**FILE_UPLOAD** — upload a `.tar` image file via WebDAV:
1. `POST /api/v1/file/sftpgo/connection_info` with `{storage_name, usage}` → WebDAV credentials
2. `PUT {webdav_address}:{webdav_port}/{path}/{filename}` with Basic auth (username/password from step 1)
3. `POST /api/v1/file/check_before_upload` — pre-upload check
4. `POST /api/v1/file/upload` — (chunked upload initiation)
5. `POST /api/v1/file/upload_complete` — finalize
6. `POST /api/v1/file/check_upload_status` — poll status

### Image List Schema

From `/image/list` → `data.images[]`:

```
id            string    image UUID
name          string    image name
version       string    image version tag
source        string    SOURCE_OFFICIAL|SOURCE_PUBLIC|SOURCE_PRIVATE
mirror_url    string    full registry URL (e.g. docker.sii.shaipower.online/inspire-studio/name:ver)
registry      string    registry host
description   string
status        string    image build/preheat status
created_at    string    unix millis
workspace_id  string
```

### Image Registries

- Internal (training use): `docker.sii.shaipower.online/inspire-studio/`
- Upload/push registry: `docker-qb.sii.edu.cn/inspire-studio/`

---

## Notebook Compute Schedules (Quota IDs)

From `GET /api/v1/notebook/schedule/{ws_id}`. Quota IDs vary per workspace and pool.

### 分布式训练空间 (`ws-9dcc0e1f-80a4-4af2-bc2f-0e352e7b17e6`) — H200 pools

From an existing H200 notebook (H200-3号机房 pool):
- **quota_id**: `ac94be38-3192-4273-928d-3b69c08a0abe`
- Spec: 160 CPU, 8× H200 GPU, 1800 GiB RAM, 64 GiB shared memory
- `gpu_price_id`: `rpc_a0c3d7e2-5f8b-4a19-9dc6-89f4e7b3d20e`
- `cpu_price_id`: `rpc_1f54b8c9-3d2a-4e67-90c8-7b2e4a5d91ca`
- `memory_price_id`: `rpc_8a23e9d1-4c7f-4b1a-bf54-3d0c7e1a2f87`

To discover quota IDs for other pools/workspaces: call `GET /api/v1/notebook/schedule/{ws_id}`
and read the `schedules[]` array entries.

---

## Mirror / Commit from Notebook

Save a running notebook's filesystem state as a new image:

```
POST /api/v1/notebook/operate
  {notebook_id, operation: "COMMIT"}

POST /api/v1/mirror/save
  {notebook_id, name, version, description?, visibility?}
  → creates a new image from the running container snapshot
  NOTE: this is the endpoint behind `qz notebook save-image`
  NOTE: `visibility` accepts `VISIBILITY_PRIVATE` or `VISIBILITY_PUBLIC`
  NOTE: image creation is asynchronous; poll image status until `READY`
```

---

## Field Name Gotchas (Notebooks)

| Field | Wrong | Right |
|-------|-------|-------|
| Image ID in create | `image_id` | `mirror_id` |
| Image URL in create | `image_url` | `mirror_url` |
| Operate action | `action`, `operate`, `type` | `operation` |
| Priority in create | `priority`, `project_priority`, `priority_value`, `priority_level` | `task_priority` |
| Pagination | `page_num`, `pageNum` | `page`, `page_size` |
| Image update ID | `image_id` | `id` |

- `task_priority` takes the project priority **level** (1, 4, 10), NOT the raw internal priority number (e.g. 35).
- `resource_spec_price` is **required** for GPU notebooks (error 100002 if nil).
- `description` is NOT a valid field for notebook create (proto rejection).
- `image/list` → `data.total` is a STRING, not a number.
