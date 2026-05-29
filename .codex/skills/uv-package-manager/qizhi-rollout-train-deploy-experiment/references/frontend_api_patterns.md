# Frontend API Patterns

## 1. Login and cookie recovery
- Stable recovery path observed in production monitoring:
  - `qzcli.api.get_api().login_with_cas(username, password)`
  - `qzcli.api.validate_frontend_cookie(cookie) == True`
  - `qzcli.config.save_cookie(cookie, workspace_id=...)`
- Practical rule:
  - Prefer `qz.sii.edu.cn` domain session cookie
  - Parent-domain cookie is only a fallback
- Symptom:
  - `qzcli login` may report success while cookie validation still fails
- Recovery:
  - Re-run CAS login and validate before continuing train/deploy polling
  - If the `agent-browser` login path ends with `登录成功但 cookie 校验失败`, fall back to:
    - `qzcli.api.get_api().login_with_cas(username, password)`
    - `qzcli.api.get_api().validate_frontend_cookie(cookie) == True`
    - `qzcli.config.save_cookie(cookie, workspace_id=...)`
  - This fallback has recovered valid frontend cookies when saved browser/session state and `qzcli login` both failed.

## 2. Frontend internal endpoints
- Train:
  - `POST /api/v1/train_job/create`
  - `POST /api/v1/train_job/detail`
  - `POST /api/v1/train_job/stop`
  - `POST /api/v1/train_job/instance_list`
  - `POST /api/v1/logs/train`
- Deploy:
  - `POST /api/v1/inference_servings/create`
  - `GET /api/v1/inference_servings/{inference_serving_id}`
- Resource / spec:
  - `GET /api/v1/compute_resources/node_specs/logic_compute_groups/{logic_compute_group_id}`

## 3. requests vs browser fetch
- Observed behavior:
  - direct `requests` to `https://qz.sii.edu.cn/api/v1/inference_servings/*` may return `401` or `302` HTML
  - the same request in a logged-in browser context can return `200`
- Working fallback:
  - reproduce the frontend request in browser context
  - use `fetch(url, {credentials: 'include', headers: ...})`
  - `agent-browser` is the preferred capture / replay tool
- Non-goal:
  - do not replace this with `/openapi/v1/*`

## 4. qzcli local cache
- `qzcli avail` and `qzcli usage` depend on `~/.qzcli/resources.json`
- If `HOME` is switched to an isolated directory, resource cache can disappear and the command may fail with:
  - `未缓存工作空间资源`
- Practical rule:
  - do not isolate `HOME` for normal train/deploy monitoring
  - if cache is missing, refresh with `qzcli res -u` or reuse the normal home directory

## 5. Capacity and spec heuristics
- Recent observed preferred capacity pattern in the 专项 workspace:
  - recommended logic compute group: `1号机房GPU`
  - `logic_compute_group_id=lcg-b346e311-83ae-41f8-bed7-d7d649656f04`
  - `spec_id=2578a742-1215-4279-893c-df7a947d9238`
- Example command:
```bash
qzcli avail --lp -w ws-c6f77a66-a5f5-45dc-a4ce-1e856fe7a7b4 -n 2 -e
```
- Capacity reading rule:
  - effective nodes = free nodes + low-priority free nodes

## 6. Service-domain distinction
- A deploy result may contain a serving endpoint such as:
  - `https://glm-five.openapi-qb.sii.edu.cn`
- This is the user-facing model service domain after deployment.
- It is not the forbidden qizhi control-plane OpenAPI transport discussed in this skill.

## 7. Webshell entry patterns
- "进入容器" is not a separate REST button API. The frontend navigates to `/webshell?...`, then the page JS opens a websocket.
- Train webshell URL:
  - `/webshell?job_id=<job_id>&instance_name=<instance_name>&from=train`
- Deploy webshell URL:
  - `/webshell?inference_serving_id=<serving_id>&instance_id=<instance_id>&from=inference_servings`
- Instance discovery endpoints:
  - train: `POST /api/v1/train_job/instance_list`
  - deploy: `POST /api/v1/inference_servings/instances/list`
- Deploy instance list payload shape is proto-like and strict:
  - accepted: `{"inference_serving_id":"...", "page":1, "page_size":100}`
  - rejected: `page_num`, `pageSize`, `filter`, `pageNum`

## 8. Webshell websocket exec protocol
- Frontend websocket endpoints:
  - train: `wss://qz.sii.edu.cn/api/v1/train_job/remote_cmd?job_id=<job_id>&instance_name=<instance_name>`
  - deploy: `wss://qz.sii.edu.cn/api/v1/inference_servings/instances/exec?inference_serving_id=<serving_id>&instance_id=<instance_id>`
- Critical handshake rule:
  - do not connect to the websocket with only the saved cookie
  - first `GET /webshell?...` with the frontend session
  - then reuse the updated cookie jar for websocket upgrade
  - otherwise the websocket may return `401`
- Observed frame behavior:
  - server messages arrive as websocket `binary` frames, but payload is UTF-8 terminal text
  - the first frames include the Inspire Studio banner and prompt
  - shell echo, prompt, and command output all come through the same stream
- Shell init sequence used by frontend / qzcli exec:
  - `command -v bash >/dev/null 2>&1 && exec bash || exec sh\r`
  - `stty columns <cols> rows <rows>\r`
- Execution detail:
  - commands must end with `\r`
  - sending text without carriage return only produces input echo and will not execute
  - the echoed command string may contain your completion marker, so completion detection must match the real printed line (for example `\n__END__:<exit_code>`) instead of raw substring existence
- Output handling:
  - expect ANSI escape sequences and prompt control codes such as bracketed-paste toggles
  - strip ANSI before parsing markers / exit codes
  - keep raw session output when debugging timing issues

## 9. Suggested qzcli exec flow
- Resolve workspace and target instance from the frontend API.
- Build the correct `/webshell?...` URL for train or deploy.
- Open that URL once with the saved frontend session cookie.
- Upgrade to the corresponding websocket endpoint using the refreshed cookie jar.
- Drain banner / prompt frames.
- Send shell init and resize commands with trailing `\r`.
- Wrap the user command with random begin/end markers and an exit-code print.
- Read websocket frames until the real end-marker line appears.
- Strip ANSI, extract stdout, and return the parsed exit code.
