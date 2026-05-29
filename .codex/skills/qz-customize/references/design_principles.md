# qzx design principles (battle-tested in myrl)

These are the non-obvious design rules behind the reference modules. Read before implementing a new qzx subcommand or changing output shape.

## 1. Default output is summarized — not full state

Agents already know `name`, `workspace`, `template`, and `command` from their own invocation. Echoing them back burns context for no gain.

- Summarize launch/run/wait/status payloads to: `run_id`, `status`, `kind`, `template`, backend IDs (`job_id` / `deployment_id` / `notebook_id`), `sync_ok`, `waited_for`, `logs`.
- `--full` gates the unsummarized payload (for debugging).
- `--dry-run` still emits the full plan — that is the inspection path.
- `--human` adds stderr progress; composite lifecycles (deploy + notebook + driver) need a `progress` callback threaded through the submit functions so intermediate stages are visible.

### Agent-first ≠ JSON-only

- stdout: one machine-parseable JSON object. Required fields always present; optional fields can be omitted.
- stderr: hints, warnings, "next step" suggestions, progress.
- Errors: `{"error": "<code>"}` + exit 1. Use semantic codes agents can branch on (`"job_not_found"`), not free-form strings.

## 2. The real integration test is an agent following the skill end-to-end

Unit tests cover function correctness. They **do not** catch output-verbosity drift, skill-doc misalignment, or workflow contract breakage.

- When you change a qzx command, walk the full workflow (EnterWorktree → sync → exec → run → status → cleanup) with a real agent against real QZ resources.
- Treat the skill doc as the contract. If an agent can't follow it without reading qz source, the doc is wrong, not the agent.
- Output shape, verbosity, and skill-doc examples are part of the test surface — not just return values.

## 3. One source of truth for launch policy

Template owns launch policy. Launcher is pure passthrough. CLI flags override template.

- Values like `shm_gi`, context caps, `max_turns` live in the template (or an explicit CLI flag), never as a hidden default inside `launch.py`.
- Add regression tests that assert: template value reaches `create_job()`, CLI override beats template.
- If slime/your-framework needs different values for different launch shapes, express that in templates, not hidden code defaults.

## 4. Thin templates + repo-owned scripts — not generic abstractions

The stable shape is `platform + env + command`. Imperative runtime logic belongs in a repo-owned shell script, not in a richer template schema.

- A rollout-only or custom-launcher variant = new template + new script. No qzx change.
- New launch topologies (model deploy, composite job+notebook) = extend qzx directly for that concrete case. Update `launch.py` / `runs.py` narrowly.
- Do **not** introduce a generic backend-switching abstraction up front. Add it only when a second concrete backend actually lands.

## 5. Retry posture: rerun, don't automate

- Name conflicts auto-suffix (`-2`, `-3`) so retries just reuse the name.
- Transient hardware / allocation hangs → user reruns. Do not add retry machinery inside qzx.
- Treat "bad node" reruns as acceptable infra noise. Don't overfit launcher code to rare cluster misbehavior.
