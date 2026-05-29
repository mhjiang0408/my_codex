# Qizhi Transport Boundary Notes

## Allowed transport
- Base web domain: `https://qz.sii.edu.cn`
- Authentication: frontend session cookie obtained from CAS / frontend login
- Active control-plane API surface: frontend internal `/api/v1/*`
- Preferred automation wrapper: `qzcli ... -w <workspace_id> --json`

## Forbidden transport
- Do not use `/openapi/v1/*`
- Do not call `/auth/token`
- Do not use `Authorization: Bearer ...`
- Do not add new code paths that depend on qizhi OpenAPI PDF examples

## How this skill maps requests
- Train create:
  - logical path accepted by `orchestrate.py`: `POST /api/v1/train_job/create`
  - actual transport: `qzcli train create -w <workspace_id> --payload-file <json> --json`
- Train detail:
  - logical path accepted by `orchestrate.py`: `POST /api/v1/train_job/detail`
  - actual transport: `qzcli train get <job_id> -w <workspace_id> --json`
- Deploy create:
  - logical path accepted by `orchestrate.py`: `POST /api/v1/inference_servings/create`
  - actual transport: `qzcli deploy create -w <workspace_id> --payload-file <json> --json`
- Deploy detail:
  - logical path accepted by `orchestrate.py`: `POST /api/v1/inference_servings/detail`
  - actual transport: `qzcli deploy get <inference_serving_id> -w <workspace_id> --json`

## Browser-captured frontend APIs
- When the workflow needs a request that `qzcli` does not wrap, inspect the frontend and reuse the browser request shape.
- Allowed examples:
  - `GET /api/v1/compute_resources/node_specs/logic_compute_groups/{logic_compute_group_id}`
  - Browser `fetch(..., {credentials:'include'})` calls captured from DevTools / `agent-browser`

## Debugging rule
- If direct `requests` with a valid cookie still receives `401` or `302` HTML, prefer reproducing the browser request with `agent-browser`.
- Do not interpret that failure as permission to switch back to OpenAPI.

## Historical references
- Legacy PDFs under `.codex/doc/*.pdf` may still be useful for field naming cross-checks.
- They are not an allowed transport contract for this skill.
