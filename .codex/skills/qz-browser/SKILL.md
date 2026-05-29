---
name: qz-browser
description: Navigate the QZ (启智) HPC platform WebUI via agent-browser. Use for RE'ing APIs, gathering platform context, or performing infrequent UI actions that aren't wrapped in the CLI.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
metadata:
  argument_hint: "[action: explore | jobs | pools | detail <job-id> | re-api <action-description> | raw <url>]"
---

# QZ Platform Browser Navigation

You are navigating the QZ (启智) HPC platform at `https://qz.sii.edu.cn` via `agent-browser`.

This skill is **self-maintaining** — update its reference files as you discover new
platform context. See [Self-Maintenance Protocol](#self-maintenance-protocol) below.

## Companion Skill Contract

- This skill may be invoked by another skill when the `qz` CLI path is insufficient or when platform information must be extracted from the WebUI/API layer.
- Parent skills should pass:
  - the parent workflow or skill name
  - the target page, API, or user action to inspect
  - any known workspace/job/deploy/spec IDs
  - why the CLI path was insufficient
- This skill should return:
  - the IDs, endpoints, payloads, or replay steps that were discovered
  - any browser-only gotchas that the parent workflow must preserve
  - updates to the reference docs when new platform facts are learned
- Route away when:
  - the subproblem is only about `qz` command syntax/config semantics -> use `qz-guide`
  - the recurring sequence should become reusable project tooling -> use `qz-customize`

## Setup

Read the cookie from the `qz` CLI auth cache and open a session:

```bash
CACHE_DIR="${QZ_CACHE_DIR:-$HOME/.cache/qz}"
COOKIE=$(python3 -c "import json; from pathlib import Path; c=json.load(open(Path('$CACHE_DIR') / 'auth.json')).get('cookie',''); print(c.split('=',1)[1] if '=' in c else c)")
agent-browser cookies set inspire-session "$COOKIE" --url https://qz.sii.edu.cn
agent-browser open "https://qz.sii.edu.cn"
```

**Success**: page title is "光语启智", URL stays on `qz.sii.edu.cn`.
**Failure**: redirected to `keycloak-inspire-prod.sii.edu.cn` → cookie expired, tell user to run `qz login -d`.

If the user explicitly requires evidence "through Qizhi" for a specific `job_id`, do not
substitute local checkpoint directories or naming heuristics as the primary evidence source.
Validate Qizhi auth first; if the browser lands on `keycloak` or `cas.sii.edu.cn`, report the
auth blocker immediately and request a refreshed login state before continuing.

A release-notes modal may appear on first visit — dismiss it (find the 关闭 button).

## Routing

Navigate directly by URL rather than clicking through menus:

| Page | URL |
|------|-----|
| Training jobs | `/jobs/distributedTraining?spaceId={ws_id}` |
| Create training job | `/jobs/distributedTrainingCreate?spaceId={ws_id}` |
| Job detail | `/jobs/distributedTrainingDetail/{job_id}?spaceId={ws_id}` |
| Space overview | `/jobs/spacesOverview?spaceId={ws_id}` |
| Scheduling (resource specs) | `/jobs/scheduling?spaceId={ws_id}` |
| Interactive modeling | `/jobs/interactiveModeling?spaceId={ws_id}` |
| Notebook detail | `/jobs/interactiveModelDetail/{notebook_id}?spaceId={ws_id}` |
| Notebook JupyterLab | `GET /api/v1/notebook/lab/{notebook_id}` → redirects to `nat2-notebook-inspire.sii.edu.cn/...` |
| Notebook VS Code IDE | `/ide?notebook_id={notebook_id}` (opens in new tab) |
| Image management | `/jobs/imageManagement?spaceId={ws_id}` |
| Model deployment list | `/jobs/modelDeployment?spaceId={ws_id}` |
| Model deployment detail | `/jobs/modelDeplayDetail/{sv_id}?spaceId={ws_id}` (note: "Deplay" typo is real) |

Workspace IDs are user-specific — see `account.md` (copy from `account.md.example` if missing).

## Handling $ARGUMENTS

- **explore**: Open the main page, snapshot the sidebar, report what's visible.
- **jobs**: Go to distributed training list, snapshot the table.
- **pools**: Call the pool list API, report availability.
- **detail `<job-id>`**: Fetch job detail via API.
- **re-api `<description>`**: Set up XHR interceptor, perform the described UI action, capture the request.
- **raw `<url>`**: Navigate to the given URL and snapshot.
- *(no args)*: Open the main page and explore interactively.

## API Calls from Browser Context

When you need data, prefer calling APIs directly via `eval` over clicking through UI.
The browser session carries the auth cookie automatically.

```bash
agent-browser eval "(async () => {
  var r = await fetch('/api/v1/...', {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({...})
  });
  return await r.text();
})()"
```

## RE'ing Unknown APIs

Install the XHR interceptor (**must re-install after every page navigation**):

```bash
agent-browser eval "var captures = []; var origSend = XMLHttpRequest.prototype.send; var origOpen = XMLHttpRequest.prototype.open; XMLHttpRequest.prototype.open = function(method, url) { this._capUrl = url; this._capMethod = method; return origOpen.apply(this, arguments); }; XMLHttpRequest.prototype.send = function(body) { captures.push({url: this._capUrl, method: this._capMethod, body: body}); return origSend.apply(this, arguments); }; window._captures = captures; 'ok'"
```

The app uses **fetch**, not XHR, for most API calls. Install a fetch interceptor too:

```bash
agent-browser eval "
window._fetchCaptures = [];
var origFetch = window.fetch;
window.fetch = function() {
  var url = arguments[0];
  var opts = arguments[1] || {};
  window._fetchCaptures.push({url: typeof url === 'string' ? url : url.url, method: opts.method || 'GET', body: opts.body});
  return origFetch.apply(this, arguments);
};
'ok'
"
```

**Both interceptors are lost on page navigation** — re-install after every `navigate` call.

Then trigger the UI action and read captures:
```bash
agent-browser eval "JSON.stringify(window._captures)"
```

Fallback — URLs from Performance API (no request bodies, but shows all endpoints hit):
```bash
agent-browser eval "JSON.stringify(performance.getEntriesByType('resource').filter(function(e) { return e.name.indexOf('/api/') !== -1; }).map(function(e) { return e.name; }))"
```

## Reference

For account-specific IDs, see `account.md` in this skill directory
(copy from `account.md.example` and fill in your own IDs if missing).

For API endpoint details and field name gotchas, see the platform reference docs:

- `docs/platform/api-reference.md` — full endpoint map with request/response schemas
- `docs/platform/gotchas.md` — field name quirks, common pitfalls
- `docs/platform/model-deployment.md` — inference serving / model deployment endpoints
- `docs/platform/notebooks-images.md` — notebook endpoints, SSH/rtunnel, image management

## Self-Maintenance Protocol

This skill's reference files are the team's shared knowledge of the QZ platform.
Every browser session is an opportunity to improve them — the next agent (or you, next week)
benefits from what you record now.

### What to update

| Discovered... | Update file | How |
|---------------|-------------|-----|
| New API endpoint, request/response fields | `docs/platform/api-reference.md` | Add under existing section or create a new `## Section` |
| New workspace, pool, project ID | `account.md` (local, gitignored) | Add to the relevant table |
| New URL route (sidebar menu item, etc.) | `SKILL.md` → Routing table | Add a row |
| Field name quirk, pagination style, auth edge case | `docs/platform/gotchas.md` | Append to the relevant section |
| Entirely new UI area (e.g., dataset management) | New file `docs/platform/<area>.md` + link from SKILL.md Reference section | See below |

### Adding a new UI area

When you encounter a UI section not covered by existing docs:

1. Explore it: snapshot the page, identify the sidebar/tab structure, RE the APIs it calls.
2. Create `docs/platform/<area>.md` with:
   - URL routes
   - API endpoints with request/response schemas
   - Key IDs and field names
   - Any gotchas
3. Add a link to the Reference section in this file.
4. Add any new URL routes to the Routing table.

After updating any files, commit them to the repo.

## Cleanup

Always close the browser when done:
```bash
agent-browser close
```
