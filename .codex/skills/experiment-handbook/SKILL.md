---
name: experiment-handbook
description: Record and maintain AgentSwarm experiment run methods, commands, artifacts, environment prerequisites, and validation evidence. Use whenever an experiment, benchmark run, training/deployment run, qz/tau run, or repeatable evaluation procedure is introduced, changed, or explained.
---

# Experiment Handbook

Use this skill whenever a task defines, changes, runs, explains, or debugs an experiment
procedure. The goal is to keep repeatable experiment knowledge in one place instead of scattered
across chat, AGENTS, ad hoc notes, or task-specific reports.

## Canonical Location

Store reusable experiment run methods under this skill:

```text
.codex/skills/experiment-handbook/references/
```

Use one focused Markdown file per experiment family or platform. Examples:

```text
references/qz-training.md
references/deployment-benchmarks.md
references/tau-bench.md
references/contextswarm-live.md
```

Do not put long-lived experiment procedures into `AGENTS.md`. `AGENTS.md` should only route
experiment work to this skill.

## What To Record

Each run-method entry should include:

- Purpose: what question or hypothesis this run method answers.
- Preconditions: required credentials, environment, data, config, model, service, and access.
- Command shape: exact `uv run ...`, qz, deployment, or benchmark command patterns.
- Inputs: config files, manifests, datasets, model ids, endpoint requirements, and env vars.
- Outputs: expected artifacts, logs, metrics, report files, and where to find them.
- Validation: the smallest command or artifact check that proves the run completed correctly.
- Failure modes: known blockers, symptoms, and repair paths.
- Scope boundaries: what this method does not validate.

Do not record secrets, bearer tokens, private keys, tokenized URLs, or raw private endpoints.
Use placeholders and explain where the operator should source values.

## Run Method Entry Contract

Every reusable experiment reference must contain one or more entries in this shape:

```markdown
## Run Method: <short name>
- Use when:
- Preconditions:
- Inputs:
- Command record:
  - Working directory:
  - Environment variables: names only; never values for secrets or private endpoints.
  - Config file or generated script:
  - Dry-run or preflight command:
  - Launch command:
  - Monitor command:
  - Stop or cleanup command:
- Artifacts:
- Validation:
- Failure modes:
- Scope boundaries:
```

The command block must be copy-pastable except for explicit placeholders such as
`<model-id>`, `<absolute/train.parquet>`, `<config.yaml>`, `<run-id>`, or environment variables
that the operator exports from a secret store. If an experiment requires a generated shell
script, record the script path and the script body or template, not only "run training".

Keep reusable run mechanics in this skill's references. Keep task-specific results, metrics, and
one-off paths in `.codex_record/<session_id>/progress.md` unless they are needed as a reusable
example.

## Required Example Patterns

When a reference covers tau-bench or tau2, include a concrete run example like this and adapt the
checkout, config path, domains, and artifact paths to the actual repo:

```markdown
## Run Method: tau2 single-domain smoke
- Use when: checking whether `<model-id>` can complete a small tau2/tau-bench run.
- Preconditions: agent endpoint is deployed; user-simulator endpoint is available; required
  credentials are exported from the operator's secret store.
- Inputs: `<model-id>`, `<domain>`, `<trial-count>`, `<agentic-eval-checkout>`,
  `<configs/tau2-run.yaml>`.
- Command record:
  - Working directory: `<agentic-eval-checkout>`
  - Environment variables: `AGENT_BASE_URL`, `AGENT_API_KEY`, `USER_SIM_BASE_URL`,
    `USER_SIM_API_KEY`
  - Config file:
    ```yaml
    defaults:
      benchmarks: ["tau2"]
    tau2:
      domains: ["<domain>"]
      agent_llm: "openai/<model-id>"
      user_llm: "openai/<user-simulator-model-id>"
      num_trials: <trial-count>
    ```
  - Dry-run or preflight command: `test -f <configs/tau2-run.yaml>`
  - Launch command: `bash run.sh --config <configs/tau2-run.yaml> --benchmark tau2`
  - Monitor command: `tail -f runs/tau2/<run-id>/results.txt`
  - Stop or cleanup command: record only if the run starts a persistent service.
- Artifacts: `runs/tau2/<run-id>/tau2-command.json`, `summary.json`, `report.json`,
  `results.txt`, and any simulation JSON.
- Validation: `results.txt` contains completed simulations and `report.json` has the expected
  model, domain, and trial count.
- Failure modes: missing user-simulator credentials, stale config model id, empty wrapper
  counters despite non-empty `results.txt`.
- Scope boundaries: smoke success does not prove all tau2 domains or production readiness.
```

When a reference covers training from parquet, record both the script skeleton and the submit
command. Example:

```markdown
## Run Method: train model from parquet
- Use when: fine-tuning `<model-id>` on an existing parquet dataset.
- Preconditions: `<absolute/train.parquet>` exists; tokenizer/model access is available; output
  storage is writable; cluster or local GPU requirements are satisfied.
- Inputs: `<model-id>`, `<absolute/train.parquet>`, `<output-dir>`, `<train-config.yaml>`,
  `<training_entrypoint>`.
- Command record:
  - Working directory: repository root or training checkout.
  - Environment variables: `MODEL_ID`, `TRAIN_PARQUET`, `OUTPUT_DIR`, `TRAIN_CONFIG`
  - Generated script: `scripts/train_<run-id>.sh`
    ```bash
    #!/usr/bin/env bash
    set -euo pipefail

    MODEL_ID="${MODEL_ID:?set MODEL_ID}"
    TRAIN_PARQUET="${TRAIN_PARQUET:?set TRAIN_PARQUET}"
    OUTPUT_DIR="${OUTPUT_DIR:?set OUTPUT_DIR}"
    TRAIN_CONFIG="${TRAIN_CONFIG:?set TRAIN_CONFIG}"

    uv run python -m <training_entrypoint> \
      --model "$MODEL_ID" \
      --train-parquet "$TRAIN_PARQUET" \
      --output-dir "$OUTPUT_DIR" \
      --config "$TRAIN_CONFIG"
    ```
  - Dry-run or preflight command: `test -f "$TRAIN_PARQUET" && test -f "$TRAIN_CONFIG"`
  - Launch command:
    `MODEL_ID=<model-id> TRAIN_PARQUET=<absolute/train.parquet> OUTPUT_DIR=<output-dir> TRAIN_CONFIG=<train-config.yaml> bash scripts/train_<run-id>.sh`
  - Monitor command: `tail -f <output-dir>/train.log`
  - Stop or cleanup command: document the scheduler cancel command if the launch command submits
    a remote job.
- Artifacts: rendered script, resolved train config, stdout/stderr log, checkpoint directory,
  metrics file, and submit payload if a scheduler is used.
- Validation: resolved command references the intended model and absolute parquet path; logs show
  nonzero samples loaded; checkpoint and metrics artifacts exist.
- Failure modes: relative parquet path inside a remote container, config overriding the intended
  model id, parquet schema incompatible with the training entrypoint.
- Scope boundaries: a completed train run does not validate downstream benchmark quality.
```

## Workflow

1. Before running or modifying an experiment, search this skill's `references/` for an existing
   method.
2. If no method exists, create one before or alongside the first repeatable run.
3. If the run reveals a new flag, artifact, failure mode, or validation requirement, update the
   relevant reference file in the same task.
4. For task-specific results, keep results in `.codex_record/<session_id>/progress.md` and final
   review artifacts; keep only reusable method knowledge here.
5. Hand correctness gates to `unit-test`, effect evaluation to `harness-bench`, and closeout to
   `code-review-with-logs`.

## Companion Skills

- `harness-bench`: use when the experiment is a quantitative benchmark or writes to `tests/bench`.
- `qizhi-rollout-train-deploy-experiment`: use for qizhi rollout/train/deploy automation.
- `deployment-benchmark-workflow`: use for post-deploy API benchmark runs.
- `cpt-experiment-workflow`: use for CPT checkpoint experiment orchestration.
- `code-review-with-logs`: include changed handbook files and run evidence at closeout.
