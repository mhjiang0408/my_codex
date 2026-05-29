#!/usr/bin/env python3
"""Qizhi automation orchestrator for rollout->parquet->train->deploy->experiment."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from legacy_config_loader import (  # noqa: E402
    apply_mapping_rules,
    load_legacy_run_config,
    load_mapping_tables,
    merge_mapping_overrides,
)
from state_store import RunStateStore  # noqa: E402

# scripts/orchestrate.py -> skill/scripts -> qizhi skill -> skills -> .codex -> repo root
REPO_ROOT = SCRIPT_DIR.parents[3]
SKILL_ROOT = SCRIPT_DIR.parents[1]
RUNS_ROOT = REPO_ROOT / "logs" / "runs"
QZ_DEFAULT_BIN = "qz"
QZ_DEFAULT_ENV_SH = str(SKILL_ROOT / "env.sh")
QZ_DEFAULT_WORKING_DIR = Path(
    "/inspire/hdd/project/qproject-fundationmodel/public/mhjiang/myqz"
)
QZ_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "qz"
QZ_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "qz"
QZ_AUTH_FAILURE_MARKERS = (
    "login required",
    "unauthorized",
    "forbidden",
    "http 401",
    "\"error\": \"http 401\"",
    "\"error\": \"http 403\"",
    "set qz_api_username",
    "set qz_api_password",
    "set qz_cookie_username",
    "set qz_cookie_password",
)
QZ_TIER_PRIORITY = {
    "immediate": 0,
    "preemption": 1,
    "wait": 2,
    "info": 3,
    "reject": 4,
    "error": 5,
}

DEFAULT_MAPPING_RULES: list[dict[str, Any]] = [
    {
        "source_key": "space_id",
        "map_key": "space_id",
        "target_key": "workspace_id",
        "required": True,
    },
    {
        "source_key": "logic_compute_group",
        "map_key": "logic_compute_group",
        "target_key": "logic_compute_group_id",
        "required": True,
    },
    {
        "source_key": "project_id",
        "map_key": "project_id",
        "target_key": "project_id",
        "required": True,
    },
    {
        "source_key": "spec_id",
        "map_key": "spec_id",
        "target_key": "spec_id",
        "required": True,
    },
    {
        "source_key": "model",
        "map_key": "model_id",
        "target_key": "model_id",
        "required": False,
    },
    {
        "source_key": "task_name",
        "map_key": "task_name",
        "target_key": "task_name_api",
        "required": False,
    },
]

DEFAULT_TRAIN_JOB_ID_CANDIDATES = [
    "data.job_id",
    "job_id",
    "data.id",
    "id",
]
DEFAULT_SERVING_ID_CANDIDATES = [
    "data.inference_serving_id",
    "inference_serving_id",
    "data.id",
    "id",
]
DEFAULT_STATUS_CANDIDATES = [
    "data.status",
    "data.state",
    "data.phase",
    "status",
    "state",
    "phase",
]
DEFAULT_ENDPOINT_CANDIDATES = [
    "data.endpoint",
    "data.url",
    "data.domain",
    "data.service_url",
    "endpoint",
    "url",
    "domain",
]


class QizhiApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        qizhi_code: int | None = None,
        response_payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.qizhi_code = qizhi_code
        self.response_payload = response_payload


class StageFailure(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


class _StrictFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> Any:
        raise KeyError(key)


def _extract_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def extract_first(payload: dict[str, Any], candidates: list[str]) -> Any:
    for candidate in candidates:
        value = _extract_path(payload, candidate)
        if value is not None:
            return value
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _resolve_path(path_like: str | Path, *, base_dir: Path) -> Path:
    candidate = Path(path_like)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def _load_yaml_object(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object at {path}")
    return data


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        try:
            return value.format_map(_StrictFormatDict(context))
        except KeyError as exc:
            raise ValueError(f"Template variable missing: {exc.args[0]}") from exc
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {str(k): _render_value(v, context) for k, v in value.items()}
    return value


def _normalize_status_set(values: list[str] | None) -> set[str]:
    if not values:
        return set()
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _safe_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _extract_runtime_ms_from_response(response: dict[str, Any]) -> int | None:
    runtime_ms = _safe_int(
        extract_first(
            response,
            ["data.running_time_ms", "running_time_ms", "data.running_ms", "running_ms"],
        )
    )
    if runtime_ms is not None:
        return runtime_ms

    runtime_s = _safe_int(
        extract_first(
            response,
            [
                "data.running_time_s",
                "running_time_s",
                "data.running_seconds",
                "running_seconds",
            ],
        )
    )
    if runtime_s is not None:
        return runtime_s * 1000

    created_ms = _safe_int(
        extract_first(response, ["data.timeline.created", "timeline.created"])
    )
    finished_ms = _safe_int(
        extract_first(
            response,
            ["data.timeline.finished", "timeline.finished", "data.finished_at", "finished_at"],
        )
    )
    if created_ms is not None and finished_ms is not None and finished_ms >= created_ms:
        return finished_ms - created_ms
    return None


def _run_subprocess(
    command: list[str] | str,
    *,
    shell: bool,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        shell=shell,
        text=True,
        capture_output=True,
        check=False,
    )


def _count_rollout_json_files(rollouts_path: Path) -> int:
    count = 0
    try:
        for entry in rollouts_path.iterdir():
            if not entry.is_file() or entry.suffix.lower() != ".json":
                continue
            if entry.name.lower() == "summary.json":
                continue
            count += 1
    except OSError:
        return 0
    return count


def _extract_data_pipeline_sample_count(stdout_text: str) -> int | None:
    patterns = [
        r"sample_count:\s*(\d+)",
        r"samples written:\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, stdout_text)
        if match:
            return int(match.group(1))
    return None


def _strip_ansi(text: str) -> str:
    ansi_pattern = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
    return ansi_pattern.sub("", text)


def _normalize_qz_str_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _looks_like_legacy_qzcli_path(raw: Any) -> bool:
    normalized = str(raw or "").strip().lower()
    if not normalized:
        return False
    return any(
        marker in normalized
        for marker in ("qzcli_tool", "/.qzcli", ".qzcli/", "/qzcli/")
    )


def _resolve_qz_config(automation_config: dict[str, Any]) -> dict[str, Any]:
    native_cfg = automation_config.get("qz")
    legacy_cfg = automation_config.get("qzcli")
    merged: dict[str, Any] = {}
    if isinstance(legacy_cfg, dict):
        merged.update(legacy_cfg)
    if isinstance(native_cfg, dict):
        merged.update(native_cfg)
    raw_bin = str(merged.get("bin") or "").strip()
    if not raw_bin or Path(raw_bin).name == "qzcli":
        merged["bin"] = QZ_DEFAULT_BIN
    raw_env_script_path = str(merged.get("env_script_path") or "").strip()
    if not raw_env_script_path or _looks_like_legacy_qzcli_path(raw_env_script_path):
        merged["env_script_path"] = QZ_DEFAULT_ENV_SH
    raw_working_dir = str(merged.get("working_dir") or "").strip()
    if not raw_working_dir or _looks_like_legacy_qzcli_path(raw_working_dir):
        merged["working_dir"] = str(QZ_DEFAULT_WORKING_DIR)
    raw_config_dir = str(merged.get("config_dir") or "").strip()
    if not raw_config_dir or _looks_like_legacy_qzcli_path(raw_config_dir):
        merged["config_dir"] = str(QZ_DEFAULT_CONFIG_DIR)
    raw_cache_dir = str(merged.get("cache_dir") or "").strip()
    if not raw_cache_dir or _looks_like_legacy_qzcli_path(raw_cache_dir):
        merged["cache_dir"] = str(QZ_DEFAULT_CACHE_DIR)
    merged.setdefault("workspace_keyword", "专项")
    merged.setdefault("refresh_login_before_run", True)
    if "pool_allowlist" not in merged and "pools" in merged:
        merged["pool_allowlist"] = list(_normalize_qz_str_list(merged.get("pools")))
    if "type_preference" not in merged:
        merged["type_preference"] = ["h100", "h200"]
    return merged


def _resolve_qz_runtime(qz_cfg: dict[str, Any]) -> tuple[str, str, Path, dict[str, str]]:
    bin_name = str(qz_cfg.get("bin") or QZ_DEFAULT_BIN).strip() or QZ_DEFAULT_BIN
    env_script_path = str(qz_cfg.get("env_script_path") or QZ_DEFAULT_ENV_SH).strip()
    working_dir_raw = str(qz_cfg.get("working_dir") or str(QZ_DEFAULT_WORKING_DIR)).strip()
    working_dir = _resolve_path(working_dir_raw, base_dir=REPO_ROOT) if working_dir_raw else REPO_ROOT
    env_exports: dict[str, str] = {}
    config_dir = str(qz_cfg.get("config_dir") or "").strip()
    cache_dir = str(qz_cfg.get("cache_dir") or "").strip()
    if config_dir:
        env_exports["QZ_CONFIG_DIR"] = str(_resolve_path(config_dir, base_dir=REPO_ROOT))
    if cache_dir:
        env_exports["QZ_CACHE_DIR"] = str(_resolve_path(cache_dir, base_dir=REPO_ROOT))
    return bin_name, env_script_path, working_dir, env_exports


def _build_qz_shell_steps(
    *,
    env_script_path: str,
    env_exports: dict[str, str],
    command_parts: list[str],
) -> list[str]:
    shell_steps: list[str] = []
    if env_script_path and Path(env_script_path).exists():
        shell_steps.append(f"source {shlex.quote(env_script_path)}")
    for key, value in env_exports.items():
        shell_steps.append(f"export {key}={shlex.quote(value)}")
    shell_steps.append(" ".join(shlex.quote(part) for part in command_parts))
    return shell_steps


def _sanitize_qz_args(qz_args: list[str]) -> list[str]:
    if not qz_args or qz_args[0] != "avail":
        return list(qz_args)
    sanitized: list[str] = []
    skip_next = False
    for index, arg in enumerate(qz_args):
        if skip_next:
            skip_next = False
            continue
        if arg in {"--pool", "--pool-id", "--group", "-g", "--workspace", "-w"}:
            if index + 1 < len(qz_args):
                skip_next = True
            continue
        if arg.startswith("--pool=") or arg.startswith("--pool-id=") or arg.startswith("--group="):
            continue
        if arg.startswith("--workspace="):
            continue
        sanitized.append(arg)
    return sanitized


def _is_qz_auth_failure(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode == 0:
        return False
    combined = _strip_ansi("\n".join([result.stdout or "", result.stderr or ""])).lower()
    return any(marker in combined for marker in QZ_AUTH_FAILURE_MARKERS)


def _extract_qz_error_text(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip() or result.stdout.strip() or "unknown qz error"


def _run_qz(
    *,
    qz_cfg: dict[str, Any],
    qz_args: list[str],
    state: RunStateStore,
    phase: str,
) -> subprocess.CompletedProcess[str]:
    def _run_once(*, attempt: int) -> subprocess.CompletedProcess[str]:
        bin_name, env_script_path, working_dir, env_exports = _resolve_qz_runtime(qz_cfg)
        shell_qz_args = _sanitize_qz_args(qz_args)
        command_parts = [bin_name, *shell_qz_args]
        if Path(bin_name).name == "qz" and (working_dir / "src" / "qz").exists():
            pythonpath = os.environ.get("PYTHONPATH", "").strip()
            env_exports = {
                **env_exports,
                "PYTHONPATH": f"src:{pythonpath}" if pythonpath else "src",
            }
            command_parts = [sys.executable, "-m", "qz", *shell_qz_args]
        shell_steps = _build_qz_shell_steps(
            env_script_path=env_script_path,
            env_exports=env_exports,
            command_parts=command_parts,
        )
        result = _run_subprocess(
            ["bash", "-lc", " && ".join(shell_steps)],
            shell=False,
            cwd=working_dir,
        )
        state.append_event(
            "qz_command_result",
            phase=phase,
            qz_args=qz_args,
            shell_qz_args=shell_qz_args,
            attempt=attempt,
            working_dir=str(working_dir),
            env_script_path=env_script_path,
            return_code=result.returncode,
            stdout_tail=result.stdout[-4000:],
            stderr_tail=result.stderr[-4000:],
        )
        return result

    def _refresh_login() -> subprocess.CompletedProcess[str]:
        bin_name, env_script_path, working_dir, env_exports = _resolve_qz_runtime(qz_cfg)
        command_parts = [bin_name, "login"]
        if Path(bin_name).name == "qz" and (working_dir / "src" / "qz").exists():
            pythonpath = os.environ.get("PYTHONPATH", "").strip()
            env_exports = {
                **env_exports,
                "PYTHONPATH": f"src:{pythonpath}" if pythonpath else "src",
            }
            command_parts = [sys.executable, "-m", "qz", "login"]
        state.append_event(
            "qz_login_refresh_start",
            phase=phase,
            working_dir=str(working_dir),
            env_script_path=env_script_path,
        )
        shell_steps = _build_qz_shell_steps(
            env_script_path=env_script_path,
            env_exports=env_exports,
            command_parts=command_parts,
        )
        result = _run_subprocess(
            ["bash", "-lc", " && ".join(shell_steps)],
            shell=False,
            cwd=working_dir,
        )
        state.append_event(
            "qz_login_refresh_success" if result.returncode == 0 else "qz_login_refresh_failed",
            phase=phase,
            working_dir=str(working_dir),
            env_script_path=env_script_path,
            return_code=result.returncode,
            stdout_tail=result.stdout[-4000:],
            stderr_tail=result.stderr[-4000:],
        )
        return result

    result = _run_once(attempt=1)
    if not _is_qz_auth_failure(result) or (qz_args and qz_args[0] == "login"):
        return result
    state.append_event(
        "qz_command_retry_after_login",
        phase=phase,
        qz_args=qz_args,
        initial_return_code=result.returncode,
    )
    login_result = _refresh_login()
    if login_result.returncode == 0:
        return _run_once(attempt=2)
    return subprocess.CompletedProcess(
        [str(qz_cfg.get("bin") or QZ_DEFAULT_BIN), *qz_args],
        login_result.returncode,
        stdout=login_result.stdout or result.stdout,
        stderr=login_result.stderr or result.stderr,
    )


def _load_qz_json(stdout_text: str, *, phase: str) -> Any:
    stdout = str(stdout_text or "").strip()
    if not stdout:
        raise QizhiApiError(f"qz {phase} returned empty stdout")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise QizhiApiError(f"qz {phase} returned non-JSON stdout: {stdout[-800:]}") from exc
    if isinstance(payload, dict) and payload.get("error"):
        raise QizhiApiError(str(payload.get("error")))
    return payload


def _qz_config_path(qz_cfg: dict[str, Any]) -> Path:
    _, _, _, env_exports = _resolve_qz_runtime(qz_cfg)
    return Path(env_exports.get("QZ_CONFIG_DIR") or QZ_DEFAULT_CONFIG_DIR) / "config.toml"


def _load_qz_configured_workspaces(qz_cfg: dict[str, Any]) -> list[dict[str, str]]:
    config_path = _qz_config_path(qz_cfg)
    if not config_path.exists():
        return []
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    workspaces_raw = payload.get("workspaces")
    if not isinstance(workspaces_raw, dict):
        return []
    out: list[dict[str, str]] = []
    for alias, workspace_id in workspaces_raw.items():
        alias_text = str(alias).strip()
        workspace_text = str(workspace_id or "").strip()
        if alias_text and workspace_text:
            out.append({"alias": alias_text, "id": workspace_text})
    return out


def _load_qz_cached_pools(qz_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    config_path = _qz_config_path(qz_cfg)
    if not config_path.exists():
        return []
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    workspaces = {
        item["id"]: item["alias"]
        for item in _load_qz_configured_workspaces(qz_cfg)
    }
    pools_raw = payload.get("pools")
    if not isinstance(pools_raw, dict):
        return []
    out: list[dict[str, Any]] = []
    for pool_alias, pool_cfg_raw in pools_raw.items():
        if not isinstance(pool_cfg_raw, dict):
            continue
        workspace_id = str(pool_cfg_raw.get("workspace_id") or "").strip()
        if not workspace_id:
            continue
        out.append(
            {
                "pool_alias": str(pool_alias).strip(),
                "workspace_id": workspace_id,
                "workspace_name": str(workspaces.get(workspace_id) or workspace_id),
                "logic_compute_group_id": str(
                    pool_cfg_raw.get("logic_compute_group_id")
                    or pool_cfg_raw.get("lcg_id")
                    or ""
                ).strip(),
                "type": str(pool_cfg_raw.get("type") or "").strip(),
                "spec_id": str(pool_cfg_raw.get("spec_id") or "").strip(),
            }
        )
    return out


def _load_qz_candidate_pools(
    *,
    qz_cfg: dict[str, Any],
    workspace_ids: list[str] | None = None,
    pool_allowlist: list[str] | None = None,
) -> list[dict[str, Any]]:
    cached = qz_cfg.get("_resolved_workspace_pools")
    if isinstance(cached, list):
        pools = [dict(item) for item in cached if isinstance(item, dict)]
    else:
        pools = [dict(item) for item in _load_qz_cached_pools(qz_cfg)]
    allowed_workspace_ids = {str(item).strip() for item in (workspace_ids or []) if str(item).strip()}
    if allowed_workspace_ids:
        pools = [pool for pool in pools if str(pool.get("workspace_id") or "").strip() in allowed_workspace_ids]
    allowset = set(pool_allowlist or _normalize_qz_pool_allowlist(qz_cfg))
    if allowset:
        pools = [pool for pool in pools if str(pool.get("pool_alias") or "").strip() in allowset]
    return pools


def _normalize_qz_pool_allowlist(qz_cfg: dict[str, Any]) -> list[str]:
    raw = qz_cfg.get("pool_allowlist")
    if raw is None:
        raw = qz_cfg.get("pools")
    return _normalize_qz_str_list(raw)


def _resolve_workspace_id_from_alias(qz_cfg: dict[str, Any], raw_value: str) -> str:
    candidate = str(raw_value or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("ws-"):
        return candidate
    for item in _load_qz_configured_workspaces(qz_cfg):
        if item["alias"] == candidate:
            return item["id"]
    return candidate


def _resolve_qz_workspace(
    *,
    qz_cfg: dict[str, Any],
    legacy_run: dict[str, Any],
    state: RunStateStore,
) -> tuple[str, str]:
    if not bool(qz_cfg.get("enabled", False)):
        return "", ""
    allowlist = set(_normalize_qz_pool_allowlist(qz_cfg))
    pools = _load_qz_candidate_pools(
        qz_cfg=qz_cfg,
        pool_allowlist=sorted(allowlist) if allowlist else None,
    )
    requested_workspace = _resolve_workspace_id_from_alias(
        qz_cfg,
        str(legacy_run.get("workspace_id") or legacy_run.get("space_id") or qz_cfg.get("workspace_id") or ""),
    )
    if requested_workspace:
        pools = [pool for pool in pools if pool["workspace_id"] == requested_workspace]
    keyword = str(qz_cfg.get("workspace_keyword") or "专项").strip()
    matched_workspace_ids = {
        item["id"]
        for item in _load_qz_configured_workspaces(qz_cfg)
        if keyword in item["alias"] or keyword in item["id"]
    }
    if matched_workspace_ids:
        pools = [pool for pool in pools if pool["workspace_id"] in matched_workspace_ids]
    if not pools:
        raise StageFailure(
            "qz_workspace_resolve",
            f"No qz pools matched workspace_keyword={keyword!r} and pool_allowlist={sorted(allowlist)}",
        )
    workspace_ids = sorted({str(pool["workspace_id"]) for pool in pools})
    if len(workspace_ids) != 1:
        raise StageFailure(
            "qz_workspace_resolve",
            f"Candidate pools span multiple workspaces: {workspace_ids}. Narrow pool_allowlist first.",
        )
    workspace_id = workspace_ids[0]
    workspace_name = next(
        (str(pool.get("workspace_name") or workspace_id) for pool in pools if pool["workspace_id"] == workspace_id),
        workspace_id,
    )
    qz_cfg["workspace_id"] = workspace_id
    qz_cfg["pool_allowlist"] = [pool["pool_alias"] for pool in pools]
    qz_cfg["_resolved_workspace_pools"] = [dict(pool) for pool in pools]
    state.append_event(
        "qz_workspace_resolved",
        workspace_keyword=keyword,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        pool_allowlist=qz_cfg["pool_allowlist"],
    )
    return workspace_id, workspace_name


def _infer_qz_free_nodes(entry: dict[str, Any]) -> int:
    for key in ("full_free_nodes", "free_nodes", "available_nodes", "nodes"):
        value = _safe_int(entry.get(key))
        if value is not None:
            return value
    gpu_free = _safe_int(entry.get("gpu_free"))
    gpu_per_node = _safe_int(entry.get("gpu_per_node")) or 8
    if gpu_free is not None and gpu_per_node > 0:
        return gpu_free // gpu_per_node
    return 0


def _infer_qz_capacity_entry(
    *,
    payload: list[dict[str, Any]],
    pool_alias: str,
) -> dict[str, Any]:
    selected = next(
        (
            item for item in payload
            if str(
                item.get("pool")
                or item.get("group_name")
                or item.get("group")
                or ""
            ).strip()
            == pool_alias
        ),
        {},
    )
    gpu_per_node = _safe_int(selected.get("gpu_per_node")) or 8
    raw_free_nodes = _infer_qz_free_nodes(selected) if selected else 0
    gpu_low_pri = _safe_int(selected.get("gpu_low_pri"))
    low_priority_nodes = (gpu_low_pri // gpu_per_node) if gpu_low_pri is not None and gpu_per_node > 0 else 0
    return {
        **selected,
        "pool": pool_alias,
        "tier": str(selected.get("tier") or ("error" if not selected else "wait")),
        "raw_free_nodes": raw_free_nodes,
        "low_priority_nodes": low_priority_nodes,
        "effective_nodes": raw_free_nodes + low_priority_nodes,
        "matched_pools": len(payload),
    }


def _run_qz_avail(
    *,
    qz_cfg: dict[str, Any],
    state: RunStateStore,
    phase: str,
    pool_type: str,
    required_nodes: int,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    result = _run_qz(
        qz_cfg=qz_cfg,
        qz_args=["avail", "--type", pool_type, "--nodes", str(required_nodes)],
        state=state,
        phase=phase,
    )
    payload: list[dict[str, Any]] = []
    if result.returncode == 0:
        loaded = _load_qz_json(result.stdout, phase=phase)
        if isinstance(loaded, list):
            payload = [item for item in loaded if isinstance(item, dict)]
        elif isinstance(loaded, dict):
            payload = [loaded]
    return result, payload


def _discover_qz_capacity_candidates(
    *,
    qz_cfg: dict[str, Any],
    state: RunStateStore,
    workspace_ids: list[str],
    required_nodes: int,
    use_low_priority: bool,
    logic_group_id_to_key: dict[str, str],
    type_preference: list[str] | None = None,
    pool_allowlist: list[str] | None = None,
) -> list[dict[str, Any]]:
    del use_low_priority
    pools = _load_qz_candidate_pools(
        qz_cfg=qz_cfg,
        workspace_ids=workspace_ids,
        pool_allowlist=pool_allowlist,
    )
    preferred_types = _normalize_qz_str_list(type_preference or qz_cfg.get("type_preference"))
    ordered_types = preferred_types + [
        pool["type"] for pool in pools if pool.get("type") and pool["type"] not in preferred_types
    ]
    candidates: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for type_rank, pool_type in enumerate(ordered_types):
        if not pool_type or pool_type in seen_types:
            continue
        seen_types.add(pool_type)
        typed_pools = [pool for pool in pools if pool.get("type") == pool_type]
        if not typed_pools:
            continue
        result, payload = _run_qz_avail(
            qz_cfg=qz_cfg,
            state=state,
            phase="qz_capacity_scan",
            pool_type=pool_type,
            required_nodes=required_nodes,
        )
        for pool in typed_pools:
            lcg_id = str(pool.get("logic_compute_group_id") or "").strip()
            logic_group_key = str(logic_group_id_to_key.get(lcg_id) or "").strip()
            capacity = _infer_qz_capacity_entry(payload=payload, pool_alias=str(pool["pool_alias"]))
            candidates.append(
                {
                    "workspace_id": pool["workspace_id"],
                    "workspace_name": pool.get("workspace_name") or pool["workspace_id"],
                    "logic_compute_group_id": lcg_id,
                    "logic_compute_group": logic_group_key,
                    "group_name": pool["pool_alias"],
                    "pool_alias": pool["pool_alias"],
                    "room_id": _infer_room_id_from_group(logic_group_key, pool["pool_alias"]),
                    "type": pool_type,
                    "type_rank": type_rank,
                    "tier": str(capacity.get("tier") or ("error" if result.returncode != 0 else "wait")),
                    "free_nodes": int(capacity.get("effective_nodes") or 0),
                    "raw_free_nodes": int(capacity.get("raw_free_nodes") or 0),
                    "low_priority_nodes": int(capacity.get("low_priority_nodes") or 0),
                    "qz_return_code": result.returncode,
                    "raw_entry": capacity,
                }
            )
    candidates.sort(
        key=lambda item: (
            int(item.get("type_rank") or 0),
            QZ_TIER_PRIORITY.get(str(item.get("tier") or "error"), 99),
            0 if _normalize_room_id(item.get("room_id")) == "1" else 1 if _normalize_room_id(item.get("room_id")) == "3" else 2 if _normalize_room_id(item.get("room_id")) == "2" else 3,
            -int(item.get("free_nodes") or 0),
            str(item.get("pool_alias") or ""),
        )
    )
    return candidates


def _report_qz_capacity_candidates(
    *,
    state: RunStateStore,
    required_nodes: int,
    candidates: list[dict[str, Any]],
) -> None:
    state.append_event(
        "qz_capacity_candidates_report",
        required_nodes=required_nodes,
        candidate_count=len(candidates),
        candidates=[
            {
                "workspace_id": item.get("workspace_id"),
                "workspace_name": item.get("workspace_name"),
                "logic_compute_group": item.get("logic_compute_group"),
                "logic_compute_group_id": item.get("logic_compute_group_id"),
                "pool_alias": item.get("pool_alias"),
                "type": item.get("type"),
                "room_id": item.get("room_id"),
                "tier": item.get("tier"),
                "free_nodes": item.get("free_nodes"),
            }
            for item in candidates
        ],
    )


def _collect_qz_avail_snapshot(
    *,
    qz_cfg: dict[str, Any],
    state: RunStateStore,
    stage: str,
    workspace: str,
    required_nodes: int,
    use_low_priority: bool,
) -> None:
    del use_low_priority
    if not bool(qz_cfg.get("enabled", False)) or required_nodes <= 0:
        return
    selected_pool = str(qz_cfg.get("selected_pool") or "").strip()
    selected_type = str(qz_cfg.get("selected_type") or "").strip()
    if not selected_pool or not selected_type:
        return
    result, payload = _run_qz_avail(
        qz_cfg=qz_cfg,
        state=state,
        phase=f"{stage}_qz_avail",
        pool_type=selected_type,
        required_nodes=required_nodes,
    )
    capacity = _infer_qz_capacity_entry(payload=payload, pool_alias=selected_pool)
    if result.returncode != 0:
        state.append_event(
            "qz_monitor_error",
            stage=stage,
            command="avail",
            selected_pool=selected_pool,
            return_code=result.returncode,
        )
    tier = str(capacity.get("tier") or ("error" if result.returncode != 0 else "wait"))
    raw_free_nodes = int(capacity.get("raw_free_nodes") or 0)
    low_priority_nodes = int(capacity.get("low_priority_nodes") or 0)
    effective_nodes = int(capacity.get("effective_nodes") or 0)
    state.append_event(
        "qz_avail_snapshot",
        stage=stage,
        workspace=workspace,
        selected_pool=selected_pool,
        pool_type=selected_type,
        required_nodes=required_nodes,
        free_nodes_total=effective_nodes,
        effective_free_nodes_total=effective_nodes,
        raw_free_nodes_total=raw_free_nodes,
        low_priority_nodes_total=low_priority_nodes,
        tier=tier,
        matched_pools=int(capacity.get("matched_pools") or 0),
        free_cards_estimated=effective_nodes * 8 if effective_nodes > 0 else 0,
        return_code=result.returncode,
    )
    if result.returncode != 0 or tier not in {"immediate", "preemption"} or effective_nodes < required_nodes:
        state.append_event(
            "qz_capacity_warning",
            stage=stage,
            workspace=workspace,
            selected_pool=selected_pool,
            pool_type=selected_type,
            required_nodes=required_nodes,
            free_nodes_total=effective_nodes,
            raw_free_nodes_total=raw_free_nodes,
            low_priority_nodes_total=low_priority_nodes,
            tier=tier,
            return_code=result.returncode,
        )


def _maybe_collect_qz_monitor(
    *,
    qz_cfg: dict[str, Any],
    state: RunStateStore,
    stage: str,
    poll_index: int,
    workspace: str,
    required_nodes: int,
) -> None:
    if not bool(qz_cfg.get("enabled", False)) or not workspace:
        return
    interval = _int_or_default(qz_cfg.get("monitor_interval_polls"), 5)
    if interval <= 0:
        interval = 5
    if poll_index != 1 and poll_index % interval != 0:
        return
    _collect_qz_avail_snapshot(
        qz_cfg=qz_cfg,
        state=state,
        stage=stage,
        workspace=workspace,
        required_nodes=required_nodes,
        use_low_priority=False,
    )


class QzWorkflowClient:
    """Use qz / myqz CLI commands as the orchestration transport."""

    def __init__(
        self,
        *,
        qz_cfg: dict[str, Any],
        state: RunStateStore,
        workspace_id: str,
        pool_alias: str = "",
        pool_type: str = "",
    ) -> None:
        self._qz_cfg = qz_cfg
        self._state = state
        self._workspace_id = str(workspace_id).strip()
        self._pool_alias = str(pool_alias).strip()
        self._pool_type = str(pool_type).strip()
        if not self._workspace_id:
            raise StageFailure("qz_workspace_resolve", "Resolved workspace_id is empty before qz client init")

    @staticmethod
    def _normalize_frontend_path(path: str) -> str:
        normalized = str(path or "").strip()
        if not normalized:
            raise QizhiApiError("qz mapped path is empty")
        return normalized

    def _write_payload_file(self, phase: str, payload: dict[str, Any]) -> Path:
        payload_path = self._state.run_paths.run_dir / f"{phase}_payload.json"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._state.append_event(
            "qz_payload_written",
            phase=phase,
            workspace_id=self._workspace_id,
            payload_path=str(payload_path),
        )
        return payload_path

    def _resolve_pool_alias(self, payload: dict[str, Any]) -> str:
        explicit_pool = str(payload.get("pool") or self._pool_alias or self._qz_cfg.get("selected_pool") or "").strip()
        if explicit_pool:
            return explicit_pool
        workspace_id = str(payload.get("workspace_id") or self._workspace_id).strip()
        logic_compute_group_id = str(payload.get("logic_compute_group_id") or "").strip()
        spec_id = str(payload.get("spec_id") or "").strip()
        workspace_ids = [workspace_id] if workspace_id else None
        for item in _load_qz_candidate_pools(qz_cfg=self._qz_cfg, workspace_ids=workspace_ids):
            if workspace_id and item.get("workspace_id") != workspace_id:
                continue
            if logic_compute_group_id and item.get("logic_compute_group_id") != logic_compute_group_id:
                continue
            if spec_id and item.get("spec_id") and item.get("spec_id") != spec_id:
                continue
            return str(item.get("pool_alias") or "")
        return ""

    def _run_json(
        self,
        *,
        phase: str,
        qz_args: list[str],
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if payload is not None:
            self._write_payload_file(phase, payload)
        result = _run_qz(
            qz_cfg=self._qz_cfg,
            qz_args=qz_args,
            state=self._state,
            phase=phase,
        )
        if result.returncode != 0:
            raise QizhiApiError(f"qz {phase} failed: {_extract_qz_error_text(result)[-800:]}")
        parsed = _load_qz_json(result.stdout, phase=phase)
        if not isinstance(parsed, dict):
            raise QizhiApiError(f"qz {phase} returned non-object JSON")
        return parsed

    def _first_framework_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        framework_cfg = payload.get("framework_config")
        if isinstance(framework_cfg, list) and framework_cfg and isinstance(framework_cfg[0], dict):
            return framework_cfg[0]
        return {}

    def _build_train_args(self, payload: dict[str, Any]) -> list[str]:
        framework_cfg = self._first_framework_config(payload)
        pool_alias = self._resolve_pool_alias(payload)
        args = [
            "job",
            "create",
            "--name",
            str(payload.get("name") or "").strip(),
            "--command",
            str(payload.get("command") or "").strip(),
        ]
        if pool_alias:
            args.extend(["--pool", pool_alias])
        elif self._pool_type:
            args.extend(["--type", self._pool_type])
        nodes = max(1, _int_or_default(framework_cfg.get("instance_count"), 1))
        args.extend(["--nodes", str(nodes)])
        image = str(framework_cfg.get("image") or "").strip()
        if image:
            args.extend(["--image", image])
        image_type = str(framework_cfg.get("image_type") or "").strip()
        if image_type:
            args.extend(["--image-type", image_type])
        project_id = str(payload.get("project_id") or "").strip()
        if project_id:
            args.extend(["--project-id", project_id])
        priority = _safe_int(payload.get("task_priority"))
        if priority is not None:
            args.extend(["--priority", str(priority)])
        shm_gi = _safe_int(framework_cfg.get("shm_gi"))
        if shm_gi is not None:
            args.extend(["--shm-gi", str(shm_gi)])
        return args

    def _build_deploy_args(self, payload: dict[str, Any]) -> list[str]:
        pool_alias = self._resolve_pool_alias(payload)
        replicas = max(1, _int_or_default(payload.get("replicas"), 1))
        nodes_per_replica = max(1, _int_or_default(payload.get("node_num_per_replica"), 1))
        gpu_count = _safe_int(payload.get("gpus"))
        if gpu_count is None:
            resource_spec = payload.get("resource_spec_price")
            if isinstance(resource_spec, dict):
                gpu_count = _safe_int(resource_spec.get("gpu_count"))
        if gpu_count is None or gpu_count <= 0:
            gpu_count = 8
        args = [
            "deploy",
            "create",
            "--name",
            str(payload.get("name") or "").strip(),
            "--command",
            str(payload.get("command") or "").strip(),
            "--image",
            str(payload.get("image") or "").strip(),
        ]
        if pool_alias:
            args.extend(["--pool", pool_alias])
        elif self._pool_type:
            args.extend(["--type", self._pool_type])
        args.extend(
            [
                "--gpus",
                str(gpu_count),
                "--replicas",
                str(replicas),
                "--nodes-per-replica",
                str(nodes_per_replica),
            ]
        )
        port = _safe_int(payload.get("port"))
        if port is not None:
            args.extend(["--port", str(port)])
        model_id = str(payload.get("model_id") or "").strip()
        if model_id:
            args.extend(["--model-id", model_id])
        model_version = _safe_int(payload.get("model_version"))
        if model_version is not None:
            args.extend(["--model-version", str(model_version)])
        url_prefix = str(payload.get("custom_domain") or payload.get("api_domain_prefix") or "").strip()
        if url_prefix:
            args.extend(["--url-prefix", url_prefix])
        priority = _safe_int(payload.get("task_priority"))
        if priority is not None:
            args.extend(["--priority", str(priority)])
        return args

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_frontend_path(path)
        if normalized in {"/api/v1/train_job/create", "/openapi/v1/train_job/create"}:
            return self._run_json(
                phase="train_submit",
                qz_args=self._build_train_args(payload),
                payload=payload,
            )
        if normalized in {"/api/v1/train_job/detail", "/openapi/v1/train_job/detail"}:
            job_id = str(payload.get("job_id") or payload.get("id") or "").strip()
            if not job_id:
                raise QizhiApiError("train detail payload missing job_id")
            return self._run_json(
                phase="train_detail",
                qz_args=["job", "status", job_id, "--raw"],
            )
        if normalized in {"/api/v1/inference_servings/create", "/openapi/v1/inference_servings/create"}:
            return self._run_json(
                phase="deploy_submit",
                qz_args=self._build_deploy_args(payload),
                payload=payload,
            )
        if normalized in {"/api/v1/inference_servings/detail", "/openapi/v1/inference_servings/detail"}:
            serving_id = str(payload.get("inference_serving_id") or payload.get("id") or "").strip()
            if not serving_id:
                raise QizhiApiError("deploy detail payload missing inference_serving_id")
            return self._run_json(
                phase="deploy_detail",
                qz_args=["deploy", "status", serving_id, "--raw"],
            )
        raise QizhiApiError(f"Unsupported qz mapped path: {normalized}")

    def job_wait(self, job_id: str, *, interval: int = 10, timeout: int = 0) -> dict[str, Any]:
        return self._run_json(
            phase="train_wait",
            qz_args=["job", "wait", job_id, "--interval", str(interval), "--timeout", str(timeout)],
        )

    def job_logs(self, job_id: str, *, worker: int = 0, lines: int = 100) -> dict[str, Any]:
        return self._run_json(
            phase="train_logs",
            qz_args=["job", "logs", job_id, "--worker", str(worker), "--lines", str(lines)],
        )

    def deploy_wait(self, serving_id: str, *, interval: int = 10, timeout: int = 0) -> dict[str, Any]:
        return self._run_json(
            phase="deploy_wait",
            qz_args=["deploy", "wait", serving_id, "--interval", str(interval), "--timeout", str(timeout)],
        )

    def deploy_logs(
        self,
        serving_id: str,
        *,
        replica: int = 0,
        worker: int = 0,
        lines: int = 100,
    ) -> dict[str, Any]:
        return self._run_json(
            phase="deploy_logs",
            qz_args=[
                "deploy",
                "logs",
                serving_id,
                "--replica",
                str(replica),
                "--worker",
                str(worker),
                "--lines",
                str(lines),
            ],
        )

def _normalize_room_id(raw_value: Any) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""
    pattern = re.search(r"(\d+)\s*号机房", text)
    if pattern:
        return pattern.group(1)
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or text


def _derive_api_base(*, prefix: str, room_id: str) -> str:
    clean_prefix = str(prefix).strip()
    clean_room = _normalize_room_id(room_id)
    if not clean_prefix:
        raise ValueError("deploy_api_prefix is required")
    if not clean_room:
        raise ValueError("room_id is required")
    suffix = "openapi-qb-ai.sii.edu.cn" if clean_room == "3" else "openapi-qb.sii.edu.cn"
    return f"https://{clean_prefix}.{suffix}"


def _infer_room_id_from_group(logic_group: str, group_name: str) -> str:
    key = str(logic_group or "").strip()
    if key == "one_gpu":
        return "1"
    if key == "two_gpu":
        return "2"
    if key in {"three_gpu", "h200_three_gpu"}:
        return "3"
    return _normalize_room_id(group_name)




def _apply_runtime_context_defaults(
    *,
    context: dict[str, Any],
    runtime_defaults: dict[str, Any],
    state: RunStateStore,
) -> None:
    room_id = _normalize_room_id(
        context.get("room_id")
        or context.get("compute_room_id")
        or runtime_defaults.get("room_id")
    )
    if room_id:
        context["room_id"] = room_id

    if not str(context.get("logic_compute_group") or "").strip():
        mapping_raw = runtime_defaults.get("room_to_logic_compute_group")
        mapping = mapping_raw if isinstance(mapping_raw, dict) else {}
        logic_group = str(mapping.get(room_id) or "").strip() if room_id else ""
        if room_id and not logic_group:
            raise StageFailure(
                "runtime_defaults",
                f"No logic_compute_group mapping for room_id={room_id!r}",
            )
        if logic_group:
            context["logic_compute_group"] = logic_group
            state.append_event(
                "logic_group_resolved",
                room_id=room_id,
                logic_compute_group=logic_group,
            )

    deploy_prefix = str(
        context.get("deploy_api_prefix")
        or runtime_defaults.get("deploy_api_prefix")
        or context.get("api_domain_prefix")
        or ""
    ).strip()
    if deploy_prefix:
        context["deploy_api_prefix"] = deploy_prefix
    api_domain_prefix = str(
        context.get("api_domain_prefix")
        or deploy_prefix
        or runtime_defaults.get("api_domain_prefix")
        or ""
    ).strip()
    if api_domain_prefix:
        context["api_domain_prefix"] = api_domain_prefix
    if deploy_prefix and room_id:
        api_base = _derive_api_base(prefix=deploy_prefix, room_id=room_id)
        context["deploy_api_base"] = api_base
        context["experiment_api_base"] = api_base
        state.append_event(
            "api_base_derived",
            deploy_api_prefix=deploy_prefix,
            room_id=room_id,
            api_base=api_base,
        )


def _extract_parquet_path(stdout: str, dataset_path: Path) -> Path | None:
    pattern = re.compile(r"\bparquet_path\b\s*:\s*(.+)")
    for line in stdout.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        raw = match.group(1).strip()
        candidate = Path(raw)
        if candidate.exists():
            return candidate.resolve()

    parquet_candidates = sorted(
        dataset_path.glob("*.parquet"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if parquet_candidates:
        return parquet_candidates[0].resolve()
    return None


def _extract_last_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        loaded = json.loads(stripped)
    except json.JSONDecodeError:
        loaded = None
    if isinstance(loaded, dict):
        return loaded

    # Fallback: try tail lines to tolerate extra logs before JSON.
    lines = [line for line in text.splitlines() if line.strip()]
    for start in range(len(lines)):
        candidate = "\n".join(lines[start:])
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return loaded
    return None


class FeishuNotifier:
    def __init__(self, config: dict[str, Any]) -> None:
        feishu_cfg = (config.get("notify") or {}).get("feishu") or {}
        self.enabled = bool(feishu_cfg.get("enabled", False))
        self.chat_id = str(feishu_cfg.get("chat_id") or "").strip()
        self.webhook_url = str(feishu_cfg.get("webhook_url") or "").strip()
        self.app_id = str(
            feishu_cfg.get("app_id") or os.getenv("FEISHU_APP_ID") or ""
        ).strip()
        self.app_secret = str(
            feishu_cfg.get("app_secret") or os.getenv("FEISHU_APP_SECRET") or ""
        ).strip()
        self._tenant_access_token: str | None = None
        self._token_expire_epoch: float = 0.0

    def notify(
        self,
        *,
        run_id: str,
        stage: str,
        status: str,
        message: str,
        extras: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return

        payload_text = self._build_text(
            run_id=run_id,
            stage=stage,
            status=status,
            message=message,
            extras=extras or {},
        )
        try:
            if self.webhook_url:
                self._send_webhook(payload_text)
                return
            self._send_with_app(payload_text)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Feishu notify failed: {exc}")

    def _build_text(
        self,
        *,
        run_id: str,
        stage: str,
        status: str,
        message: str,
        extras: dict[str, Any],
    ) -> str:
        lines = [
            "[qizhi-automation]",
            f"run_id: {run_id}",
            f"stage: {stage}",
            f"status: {status}",
            f"message: {message}",
        ]
        for key, value in extras.items():
            if value is None:
                continue
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def _send_webhook(self, text: str) -> None:
        response = requests.post(
            self.webhook_url,
            json={"msg_type": "text", "content": {"text": text}},
            timeout=10,
        )
        response.raise_for_status()

    def _send_with_app(self, text: str) -> None:
        if not self.chat_id:
            raise RuntimeError("feishu.notify.chat_id is required")
        if not self.app_id or not self.app_secret:
            raise RuntimeError("feishu app_id/app_secret are required for app-mode notify")

        token = self._ensure_tenant_token()
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        response = requests.post(
            url,
            params={"receive_id_type": "chat_id"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": self.chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code", 0)) != 0:
            raise RuntimeError(f"Feishu send failed: {payload}")

    def _ensure_tenant_token(self) -> str:
        now = time.time()
        if self._tenant_access_token and now < self._token_expire_epoch:
            return self._tenant_access_token

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        response = requests.post(
            url,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code", 0)) != 0:
            raise RuntimeError(f"Feishu token fetch failed: {payload}")

        token = payload.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Feishu token fetch returned empty token")
        expire = int(payload.get("expire", 7200))
        self._tenant_access_token = token
        self._token_expire_epoch = now + max(60, expire - 120)
        return token


def _require_section(config: dict[str, Any], key: str) -> dict[str, Any]:
    section = config.get(key)
    if not isinstance(section, dict):
        raise ValueError(f"Missing object config section: {key}")
    return section


def _run_data_pipeline(
    *,
    automation_config: dict[str, Any],
    rollouts_path: Path,
    context: dict[str, Any],
    state: RunStateStore,
) -> Path:
    data_cfg = _require_section(automation_config, "data_pipeline")
    dataset_date = str(context.get("dataset_date") or "").strip()
    if not re.fullmatch(r"\d{8}", dataset_date):
        raise StageFailure(
            "data_pipeline",
            f"dataset_date must be YYYYMMDD, got: {dataset_date!r}",
        )
    dataset_base_rendered = _render_value(
        str(data_cfg.get("dataset_path") or "data/train/dataset"),
        context,
    )
    dataset_base_path = Path(str(dataset_base_rendered))
    if re.fullmatch(r"\d{8}", dataset_base_path.name):
        dataset_target = dataset_base_path
    else:
        dataset_target = dataset_base_path / dataset_date
    dataset_path = _resolve_path(dataset_target, base_dir=REPO_ROOT)
    tokenizer_path = str(data_cfg.get("tokenizer_path") or "").strip()
    if not tokenizer_path:
        raise StageFailure("data_pipeline", "data_pipeline.tokenizer_path is required")

    command = [
        "uv",
        "run",
        "python",
        "-m",
        "src.cli.data_pipeline_cli",
        "--dataset-path",
        str(dataset_path),
        "--tokenizer-path",
        tokenizer_path,
        "--rollouts-path",
        str(rollouts_path),
    ]

    min_parquet_samples = _int_or_default(data_cfg.get("min_parquet_samples"), 64)
    configured_duplicate_times = _int_or_default(data_cfg.get("duplicate_times"), 2)
    rollout_count = _count_rollout_json_files(rollouts_path)
    required_duplicate_times = configured_duplicate_times
    if min_parquet_samples > 0 and rollout_count > 0:
        required_duplicate_times = max(
            configured_duplicate_times,
            int(math.ceil(min_parquet_samples / rollout_count)),
        )
    state.append_event(
        "data_pipeline_duplicate_times_resolved",
        configured_duplicate_times=configured_duplicate_times,
        resolved_duplicate_times=required_duplicate_times,
        rollout_count=rollout_count,
        min_parquet_samples=min_parquet_samples,
    )

    if "max_tokens" in data_cfg:
        command += ["--max-tokens", str(data_cfg["max_tokens"])]
    command += ["--duplicate-times", str(required_duplicate_times)]
    if "raw_dir_name" in data_cfg:
        command += ["--raw-dir-name", str(data_cfg["raw_dir_name"])]
    if "openai_dir_name" in data_cfg:
        command += ["--openai-dir-name", str(data_cfg["openai_dir_name"])]
    if "rollouts_dir_name" in data_cfg:
        command += ["--rollouts-dir-name", str(data_cfg["rollouts_dir_name"])]
    if bool(data_cfg.get("mv_duplicates", False)):
        command.append("--mv-duplicates")
    if not bool(data_cfg.get("include_tools", True)):
        command.append("--no-tools")

    working_dir = _resolve_path(
        str(data_cfg.get("working_dir") or str(REPO_ROOT)),
        base_dir=REPO_ROOT,
    )
    state.append_event("data_pipeline_command", command=command, cwd=str(working_dir))

    result = _run_subprocess(command, shell=False, cwd=working_dir)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    state.append_event(
        "data_pipeline_result",
        return_code=result.returncode,
        stdout_tail=result.stdout[-4000:],
        stderr_tail=result.stderr[-4000:],
    )

    if result.returncode != 0:
        raise StageFailure(
            "data_pipeline",
            f"data_pipeline_cli failed with exit code {result.returncode}",
        )

    sample_count = _extract_data_pipeline_sample_count(result.stdout)
    if sample_count is not None and min_parquet_samples > 0 and sample_count < min_parquet_samples:
        raise StageFailure(
            "data_pipeline",
            f"parquet sample_count={sample_count} is below min_parquet_samples={min_parquet_samples}",
        )
    if sample_count is not None:
        state.set_artifact("parquet_sample_count", sample_count)
        state.append_event(
            "data_pipeline_sample_count",
            sample_count=sample_count,
            min_parquet_samples=min_parquet_samples,
        )

    parquet_path = _extract_parquet_path(result.stdout, dataset_path)
    if parquet_path is None:
        raise StageFailure(
            "data_pipeline",
            "Unable to locate parquet_path from data pipeline output",
        )

    context["parquet_path"] = str(parquet_path)
    state.set_artifact("parquet_path", str(parquet_path))
    state.set_artifact("dataset_path", str(dataset_path))
    state.set_artifact("dataset_date", dataset_date)
    return parquet_path


def _run_compose_rollouts(
    *,
    automation_config: dict[str, Any],
    registry_path: Path,
    run_id: str,
    context: dict[str, Any],
    state: RunStateStore,
    compose_output_dir_override: Path | None = None,
    compose_chain_id: str | None = None,
    compose_exp_id: str | None = None,
) -> Path:
    compose_cfg_raw = automation_config.get("compose")
    if compose_cfg_raw is None:
        compose_cfg: dict[str, Any] = {}
    elif isinstance(compose_cfg_raw, dict):
        compose_cfg = compose_cfg_raw
    else:
        raise StageFailure("compose_rollouts", "compose config must be an object")

    if not bool(compose_cfg.get("enabled", True)):
        raise StageFailure(
            "compose_rollouts",
            "compose.enabled=false but rollouts_path was not provided",
        )

    if compose_output_dir_override is not None:
        output_dir = compose_output_dir_override.resolve()
    else:
        output_pattern = str(
            compose_cfg.get("output_dir_pattern")
            or ".codex/skills/qizhi-rollout-train-deploy-experiment/runs/{run_id}/composed_rollouts"
        ).strip()
        rendered_output = _render_value(
            output_pattern,
            {"run_id": run_id, "timestamp": context.get("timestamp", _slug_now())},
        )
        output_dir = _resolve_path(str(rendered_output), base_dir=REPO_ROOT)

    command = [
        "uv",
        "run",
        "python",
        "scripts/compose_rollout_trajectory.py",
        "--registry",
        str(registry_path),
        "--output-dir",
        str(output_dir),
    ]
    if compose_chain_id:
        command += ["--chain-id", compose_chain_id]
    if compose_exp_id:
        command += ["--exp-id", compose_exp_id]
    if not bool(compose_cfg.get("update_registry", True)):
        command.append("--no-update-registry")

    working_dir = _resolve_path(
        str(compose_cfg.get("working_dir") or str(REPO_ROOT)),
        base_dir=REPO_ROOT,
    )
    state.append_event(
        "compose_rollouts_command",
        command=command,
        cwd=str(working_dir),
    )

    result = _run_subprocess(command, shell=False, cwd=working_dir)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    state.append_event(
        "compose_rollouts_result",
        return_code=result.returncode,
        stdout_tail=result.stdout[-4000:],
        stderr_tail=result.stderr[-4000:],
    )
    if result.returncode != 0:
        raise StageFailure(
            "compose_rollouts",
            f"compose_rollout_trajectory failed with exit code {result.returncode}",
        )

    summary_path = output_dir / "summary.json"
    summary_payload: dict[str, Any] = {}
    if summary_path.exists():
        try:
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                summary_payload = loaded
        except (json.JSONDecodeError, OSError):
            summary_payload = {}
    if not summary_payload:
        parsed = _extract_last_json_object(result.stdout)
        if isinstance(parsed, dict):
            summary_payload = parsed

    chain_files = sorted(
        [
            path
            for path in output_dir.glob("*.json")
            if path.is_file() and path.name != "summary.json"
        ]
    )
    if not chain_files:
        raise StageFailure(
            "compose_rollouts",
            f"compose output has no chain json files: {output_dir}",
        )

    chain_count = len(chain_files)
    if isinstance(summary_payload.get("chain_count"), int):
        chain_count = int(summary_payload["chain_count"])

    state.set_artifact("compose_output_dir", str(output_dir))
    state.set_artifact("compose_summary_path", str(summary_path))
    state.set_artifact("compose_chain_count", chain_count)
    state.set_artifact("rollouts_path", str(output_dir))
    context["rollouts_path"] = str(output_dir)
    return output_dir


def _poll_until_terminal(
    *,
    client: Any,
    detail_path: str,
    id_field: str,
    resource_id: str,
    polling_cfg: dict[str, Any],
    stage: str,
    state: RunStateStore,
    on_poll=None,
) -> tuple[dict[str, Any], str]:
    interval = float(polling_cfg.get("poll_interval_seconds", 30))
    timeout = float(polling_cfg.get("timeout_seconds", 7200))
    accept_failed_minutes = float(
        polling_cfg.get("accept_failed_if_runtime_minutes", 0)
    )
    status_candidates = list(
        polling_cfg.get("status_field_candidates") or DEFAULT_STATUS_CANDIDATES
    )
    success_statuses = _normalize_status_set(
        polling_cfg.get("success_statuses")
        or ["succeeded", "success", "completed", "finished"]
    )
    failed_statuses = _normalize_status_set(
        polling_cfg.get("failed_statuses")
        or ["failed", "error", "canceled", "cancelled", "stopped", "timeout"]
    )
    running_statuses = _normalize_status_set(
        polling_cfg.get("running_statuses")
        or ["pending", "queued", "created", "running", "initializing", "starting"]
    )
    # Compatibility aliases returned by different qizhi endpoints.
    success_statuses.update({"job_succeeded", "job_success"})
    failed_statuses.update({"job_failed", "train_failed", "deploy_failed", "service_failed"})
    running_statuses.update({"job_running"})

    started = time.time()
    poll_index = 0
    while True:
        poll_index += 1
        response = client.post(detail_path, {id_field: resource_id})
        status_raw = extract_first(response, status_candidates)
        status_text = str(status_raw).strip().lower() if status_raw is not None else ""

        state.append_event(
            f"{stage}_poll",
            id_field=id_field,
            resource_id=resource_id,
            status=status_text,
            response_preview=json.dumps(response, ensure_ascii=False)[:1200],
        )
        if on_poll is not None:
            try:
                on_poll(poll_index, status_text, response)
            except Exception as exc:  # noqa: BLE001
                state.append_event(
                    "qz_monitor_error",
                    stage=stage,
                    command="poll_hook",
                    error=str(exc),
                )

        if status_text and status_text in success_statuses:
            return response, status_text
        if status_text and status_text in failed_statuses:
            runtime_ms = _extract_runtime_ms_from_response(response)
            threshold_ms = int(accept_failed_minutes * 60_000)
            if (
                accept_failed_minutes > 0
                and runtime_ms is not None
                and runtime_ms >= threshold_ms
            ):
                accepted_status = f"{status_text}_accepted_runtime"
                state.append_event(
                    f"{stage}_failed_status_accepted",
                    status=status_text,
                    accepted_status=accepted_status,
                    runtime_ms=runtime_ms,
                    accept_failed_if_runtime_minutes=accept_failed_minutes,
                )
                return response, accepted_status
            raise StageFailure(stage, f"{stage} reached failed status: {status_text}")

        elapsed = time.time() - started
        if elapsed > timeout:
            raise StageFailure(
                stage,
                f"{stage} polling timed out after {int(timeout)}s, last_status={status_text or 'unknown'}",
            )

        if status_text and status_text not in running_statuses:
            # Unknown status: keep waiting until timeout, but persist for diagnostics.
            state.append_event(
                f"{stage}_unknown_status",
                status=status_text,
                known_running=sorted(running_statuses),
                known_success=sorted(success_statuses),
                known_failed=sorted(failed_statuses),
            )

        time.sleep(interval)


def _ensure_phase(
    *,
    phase: str,
    state: RunStateStore,
    fn,
) -> Any:
    if state.phase_done(phase):
        state.append_event("phase_skipped", phase=phase, reason="already_success")
        return None
    state.update_phase(phase, "running")
    try:
        result = fn()
    except Exception:
        state.update_phase(phase, "failed")
        raise
    state.update_phase(phase, "success")
    return result


def _build_context(
    *,
    run_id: str,
    rollouts_path: Path | None,
    legacy_run: dict[str, Any] | None,
    mapped_run: dict[str, Any] | None,
    artifacts: dict[str, Any] | None,
    dataset_date: str,
) -> dict[str, Any]:
    merged_artifacts = artifacts or {}
    merged_legacy = legacy_run or {}
    merged_mapped = mapped_run or {}
    context = {
        "run_id": run_id,
        "timestamp": _slug_now(),
        "dataset_date": dataset_date,
        "rollouts_path": str(rollouts_path) if rollouts_path is not None else "",
        **merged_legacy,
        **merged_mapped,
        **merged_artifacts,
    }
    return context


def _int_or_default(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    raw = str(value).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _apply_train_runtime_defaults(
    *,
    context: dict[str, Any],
    train_cfg: dict[str, Any],
) -> None:
    defaults_cfg_raw = train_cfg.get("defaults")
    defaults_cfg = defaults_cfg_raw if isinstance(defaults_cfg_raw, dict) else {}

    instance_count = _int_or_default(
        context.get("train_instance_count"),
        _int_or_default(defaults_cfg.get("instance_count"), 8),
    )
    if instance_count <= 0:
        instance_count = 8

    shm_gi = _int_or_default(
        context.get("train_shm_gi"),
        _int_or_default(defaults_cfg.get("shm_gi"), 800),
    )
    if shm_gi <= 0:
        shm_gi = 800

    dataset_date = str(context.get("dataset_date") or "").strip()
    date_suffix = dataset_date[4:] if re.fullmatch(r"\d{8}", dataset_date) else dataset_date
    if not date_suffix:
        date_suffix = _slug_now()[4:8]

    model_name = str(
        context.get("model")
        or defaults_cfg.get("model_name")
        or "glm-4.6"
    ).strip()
    if not model_name:
        model_name = "glm-4.6"

    output_tag = str(
        context.get("train_output_tag")
        or defaults_cfg.get("output_tag")
        or f"{model_name}-pr-{date_suffix}"
    ).strip()
    if not output_tag:
        output_tag = f"{model_name}-pr-{date_suffix}"

    output_root = str(
        context.get("train_output_root")
        or defaults_cfg.get("output_root")
        or "/inspire/qb-ilm/project/qproject-fundationmodel/public/mhjiang/models"
    ).strip()
    if not output_root:
        output_root = "/inspire/qb-ilm/project/qproject-fundationmodel/public/mhjiang/models"

    output_dir = str(
        context.get("train_output_dir")
        or defaults_cfg.get("output_dir")
        or f"{output_root.rstrip('/')}/{output_tag}"
    ).strip()

    train_image_name = str(
        context.get("train_image_name")
        or defaults_cfg.get("image_name")
        or "docker.sii.shaipower.online/inspire-studio/slime:20250812-v2"
    ).strip()
    if not train_image_name:
        train_image_name = "docker.sii.shaipower.online/inspire-studio/slime:20250812-v2"

    train_image_type = str(
        context.get("train_image_type")
        or defaults_cfg.get("image_type")
        or "SOURCE_OFFICIAL"
    ).strip()
    if not train_image_type:
        train_image_type = "SOURCE_OFFICIAL"

    context["train_instance_count"] = instance_count
    context["train_shm_gi"] = shm_gi
    context["train_output_tag"] = output_tag
    context["train_output_root"] = output_root
    context["train_output_dir"] = output_dir
    context["train_image_name"] = train_image_name
    context["train_image_type"] = train_image_type
    context["train_total_gpu_cards"] = instance_count * 8


def _normalize_train_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "task_priority" in normalized:
        normalized["task_priority"] = _int_or_default(normalized.get("task_priority"), 10)
    normalized.setdefault("enable_notification", False)
    normalized.setdefault("enable_slow_detect", False)
    normalized.setdefault("enable_vccl", False)
    normalized.setdefault("enable_troubleshoot", False)
    if "dataset_info" not in normalized:
        normalized["dataset_info"] = []

    framework_cfg = normalized.get("framework_config")
    if isinstance(framework_cfg, list):
        updated: list[Any] = []
        for item in framework_cfg:
            if not isinstance(item, dict):
                updated.append(item)
                continue
            node = dict(item)
            node.pop("spec_id", None)
            if "instance_count" in node:
                node["instance_count"] = _int_or_default(node.get("instance_count"), 1)
            if "shm_gi" in node:
                node["shm_gi"] = _int_or_default(node.get("shm_gi"), 0)
            updated.append(node)
        normalized["framework_config"] = updated
    return normalized


def _resolve_context_template_keys(
    *,
    context: dict[str, Any],
    template_keys: list[str],
) -> None:
    def _normalize_shell_command(value: str) -> str:
        parts = [line.strip() for line in value.splitlines() if line.strip()]
        if not parts:
            return value.strip()
        return " ".join(parts)

    for key in template_keys:
        value = context.get(key)
        if not isinstance(value, str):
            continue
        if "{" not in value or "}" not in value:
            rendered = value
        else:
            rendered = _render_value(value, context)
        if key == "bash_command":
            rendered = _normalize_shell_command(rendered)
        context[key] = rendered


def _extract_hf_path_token_from_bash_command(command: str) -> str | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()

    candidates: list[str] = []
    for raw in tokens:
        token = raw.strip().rstrip(";,")
        if not token:
            continue
        if token in {"|", "||", "&&", ";", "&", ">", "1>", "2>", "2>&1", "&>"}:
            continue
        if token.startswith(">"):
            continue
        if token.startswith("-"):
            continue
        if "/iter_" not in token and not token.endswith("_hf"):
            continue
        candidates.append(token)

    if not candidates:
        return None

    for token in reversed(candidates):
        if re.fullmatch(r"iter_\d+_hf", Path(token).name):
            return token
    return candidates[-1]


def _normalize_ready_file_names(value: Any) -> list[str]:
    if isinstance(value, list):
        normalized = [str(item).strip() for item in value if str(item).strip()]
        if normalized:
            return normalized
    return ["config.json", "generation_config.json"]


def _extract_hf_iteration(name: str, match: re.Match[str]) -> int:
    if match.lastindex and match.lastindex >= 1:
        group = match.group(1)
        if group and str(group).isdigit():
            return int(group)
    fallback = re.search(r"\d+", name)
    if fallback:
        return int(fallback.group(0))
    return -1


def _scan_hf_directories(
    *,
    base_dir: Path,
    dir_name_pattern: re.Pattern[str],
    ready_file_names: list[str],
) -> tuple[list[tuple[int, Path]], list[tuple[int, Path]], dict[str, list[str]]]:
    candidates: list[tuple[int, Path]] = []
    ready: list[tuple[int, Path]] = []
    missing_by_dir: dict[str, list[str]] = {}

    if not base_dir.exists() or not base_dir.is_dir():
        return candidates, ready, missing_by_dir

    for child in base_dir.iterdir():
        if not child.is_dir():
            continue
        match = dir_name_pattern.fullmatch(child.name)
        if not match:
            continue
        iteration = _extract_hf_iteration(child.name, match)
        missing_files = [
            file_name for file_name in ready_file_names if not (child / file_name).is_file()
        ]
        candidates.append((iteration, child))
        if missing_files:
            missing_by_dir[str(child)] = missing_files
        else:
            ready.append((iteration, child))

    candidates.sort(key=lambda item: (item[0], item[1].name))
    ready.sort(key=lambda item: (item[0], item[1].name))
    return candidates, ready, missing_by_dir


def _wait_for_ready_hf_dir(
    *,
    base_dir: Path,
    hf_path_hint: Path,
    dir_name_regex: str,
    ready_file_names: list[str],
    poll_interval_seconds: int,
    timeout_seconds: int,
    state: RunStateStore,
) -> tuple[Path, int]:
    try:
        pattern = re.compile(dir_name_regex)
    except re.error as exc:
        raise ValueError(f"Invalid deploy.hf_wait.dir_name_regex: {dir_name_regex}") from exc

    stage = "deploy_hf_wait"
    state.append_event(
        "deploy_hf_wait_started",
        base_dir=str(base_dir),
        hf_path_hint=str(hf_path_hint),
        dir_name_regex=dir_name_regex,
        ready_file_names=ready_file_names,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    started_at = time.time()
    poll_index = 0

    while True:
        poll_index += 1
        candidates, ready, missing_by_dir = _scan_hf_directories(
            base_dir=base_dir,
            dir_name_pattern=pattern,
            ready_file_names=ready_file_names,
        )
        elapsed_seconds = int(time.time() - started_at)

        if ready:
            selected_iteration, selected_dir = ready[-1]
            state.append_event(
                "deploy_hf_wait_selected",
                poll_index=poll_index,
                base_dir=str(base_dir),
                selected_hf_dir=str(selected_dir),
                selected_iteration=selected_iteration,
                ready_count=len(ready),
                candidate_count=len(candidates),
                wait_seconds=elapsed_seconds,
            )
            return selected_dir, elapsed_seconds

        latest_candidate = str(candidates[-1][1]) if candidates else ""
        sample_missing: list[dict[str, Any]] = []
        for _, path in candidates[:5]:
            key = str(path)
            missing = missing_by_dir.get(key, [])
            if missing:
                sample_missing.append({"dir": key, "missing": missing})

        state.append_event(
            "deploy_hf_wait_poll",
            poll_index=poll_index,
            base_dir=str(base_dir),
            elapsed_seconds=elapsed_seconds,
            candidate_count=len(candidates),
            ready_count=len(ready),
            latest_candidate=latest_candidate,
            sample_missing=sample_missing,
        )

        if timeout_seconds > 0 and elapsed_seconds >= timeout_seconds:
            state.append_event(
                "deploy_hf_wait_timeout",
                base_dir=str(base_dir),
                elapsed_seconds=elapsed_seconds,
                timeout_seconds=timeout_seconds,
                candidate_count=len(candidates),
                ready_count=len(ready),
            )
            raise StageFailure(
                stage,
                f"Timeout waiting for ready HF directory under {base_dir} after {elapsed_seconds}s",
            )

        time.sleep(poll_interval_seconds)


def _rewrite_bash_command_hf_path(
    *,
    command: str,
    old_token: str,
    selected_hf_dir: Path,
) -> str:
    selected_str = str(selected_hf_dir)
    if old_token == selected_str:
        return command
    if old_token in command:
        return command.replace(old_token, selected_str, 1)
    return command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate qizhi train/deploy workflow based on legacy AutoQZ run config."
    )
    parser.add_argument(
        "--automation-config",
        type=Path,
        required=True,
        help="Skill automation YAML config path.",
    )
    parser.add_argument(
        "--legacy-run-config",
        type=Path,
        default=None,
        help="Legacy run.yaml path (list-format). Required unless --stop-after data_pipeline.",
    )
    parser.add_argument(
        "--parquet-path",
        type=Path,
        default=None,
        help="Optional existing training parquet. When provided, compose/data_pipeline are skipped.",
    )
    parser.add_argument(
        "--rollouts-path",
        type=Path,
        default=None,
        help="Optional composed rollout directory, passed to data pipeline as --rollouts-path.",
    )
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=None,
        help="Optional rollout registry SQLite path. Used when rollouts-path is not provided.",
    )
    parser.add_argument(
        "--compose-output-dir",
        type=Path,
        default=None,
        help="Optional compose output directory when registry-path is used.",
    )
    parser.add_argument(
        "--compose-chain-id",
        type=str,
        default="",
        help="Optional chain_id filter for compose stage.",
    )
    parser.add_argument(
        "--compose-exp-id",
        type=str,
        default="",
        help="Optional exp_id filter for compose stage.",
    )
    parser.add_argument(
        "--dataset-date",
        type=str,
        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
        help="Dataset date token in YYYYMMDD format (default: UTC today).",
    )
    parser.add_argument(
        "--stop-after",
        choices=["data_pipeline", "train_submit"],
        default="",
        help="Stop successfully after a specific phase.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default="",
        help="Optional explicit run id for new execution.",
    )
    parser.add_argument(
        "--resume-run-id",
        type=str,
        default="",
        help="Resume from an existing run id under skill runs/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    automation_config_path = args.automation_config.resolve()
    legacy_run_config_path = (
        args.legacy_run_config.resolve() if args.legacy_run_config else None
    )
    parquet_path = args.parquet_path.resolve() if args.parquet_path else None
    rollouts_path = args.rollouts_path.resolve() if args.rollouts_path else None
    registry_path = args.registry_path.resolve() if args.registry_path else None
    dataset_date = str(args.dataset_date or "").strip()
    if not re.fullmatch(r"\d{8}", dataset_date):
        raise ValueError(
            f"--dataset-date must be YYYYMMDD, got: {dataset_date!r}"
        )

    if not automation_config_path.exists():
        raise FileNotFoundError(f"automation config not found: {automation_config_path}")
    if args.stop_after != "data_pipeline" and legacy_run_config_path is None:
        raise ValueError(
            "--legacy-run-config is required unless --stop-after data_pipeline"
        )
    if legacy_run_config_path is not None and not legacy_run_config_path.exists():
        raise FileNotFoundError(f"legacy run config not found: {legacy_run_config_path}")
    if rollouts_path is not None and (not rollouts_path.exists() or not rollouts_path.is_dir()):
        raise FileNotFoundError(
            f"rollouts path must be an existing directory: {rollouts_path}"
        )
    if registry_path is not None and (not registry_path.exists() or not registry_path.is_file()):
        raise FileNotFoundError(
            f"registry path must be an existing file: {registry_path}"
        )
    if parquet_path is not None and (not parquet_path.exists() or not parquet_path.is_file()):
        raise FileNotFoundError(
            f"parquet path must be an existing file: {parquet_path}"
        )

    automation_config = _load_yaml_object(automation_config_path)

    run_id = args.resume_run_id.strip() or args.run_id.strip() or f"qz_{_slug_now()}"
    resume_mode = bool(args.resume_run_id.strip())
    state = RunStateStore(root_dir=RUNS_ROOT, run_id=run_id, resume=resume_mode)
    notifier = FeishuNotifier(automation_config)

    resumed_parquet_artifact = str(state.get_artifact("parquet_path") or "").strip()
    if parquet_path is None and resume_mode and resumed_parquet_artifact:
        parquet_path = Path(resumed_parquet_artifact).resolve()
        if not parquet_path.exists() or not parquet_path.is_file():
            raise FileNotFoundError(
                f"resumed parquet path must be an existing file: {parquet_path}"
            )
    if parquet_path is None and rollouts_path is None and registry_path is None:
        raise ValueError(
            "Either --parquet-path, --rollouts-path, or --registry-path must be provided"
        )

    try:
        state.append_event(
            "run_started",
            run_id=run_id,
            resume=resume_mode,
            automation_config=str(automation_config_path),
            legacy_run_config=str(legacy_run_config_path) if legacy_run_config_path else "",
            parquet_path=str(parquet_path) if parquet_path else "",
            rollouts_path=str(rollouts_path) if rollouts_path else "",
            registry_path=str(registry_path) if registry_path else "",
            stop_after=args.stop_after,
            dataset_date=dataset_date,
        )

        context = _build_context(
            run_id=run_id,
            rollouts_path=rollouts_path,
            legacy_run=None,
            mapped_run=None,
            artifacts=state.artifacts,
            dataset_date=dataset_date,
        )
        if parquet_path is not None:
            parquet_path = parquet_path.resolve()
            context["parquet_path"] = str(parquet_path)
            state.set_artifact("parquet_path", str(parquet_path))
            state.set_artifact("dataset_path", str(parquet_path.parent))
            state.set_artifact("dataset_date", dataset_date)
            state.append_event(
                "data_pipeline_skipped",
                reason="parquet_path_provided",
                parquet_path=str(parquet_path),
            )
        else:
            effective_rollouts_path: Path | None = rollouts_path
            if effective_rollouts_path is None:
                if registry_path is None:
                    raise StageFailure(
                        "compose_rollouts",
                        "registry_path is required when rollouts_path is not provided",
                    )

                compose_chain_id = args.compose_chain_id.strip() or None
                compose_exp_id = args.compose_exp_id.strip() or None
                compose_output_dir = (
                    args.compose_output_dir.resolve()
                    if args.compose_output_dir is not None
                    else None
                )

                def _compose_stage() -> Path:
                    return _run_compose_rollouts(
                        automation_config=automation_config,
                        registry_path=registry_path,
                        run_id=run_id,
                        context=context,
                        state=state,
                        compose_output_dir_override=compose_output_dir,
                        compose_chain_id=compose_chain_id,
                        compose_exp_id=compose_exp_id,
                    )

                compose_output = _ensure_phase(
                    phase="compose_rollouts",
                    state=state,
                    fn=_compose_stage,
                )
                if isinstance(compose_output, Path):
                    effective_rollouts_path = compose_output.resolve()
                else:
                    resumed_rollouts = str(state.get_artifact("rollouts_path") or "").strip()
                    if not resumed_rollouts:
                        raise StageFailure(
                            "compose_rollouts",
                            "Missing artifacts.rollouts_path for resumed compose run",
                        )
                    effective_rollouts_path = Path(resumed_rollouts).resolve()
            else:
                state.append_event(
                    "compose_rollouts_skipped",
                    reason="rollouts_path_provided",
                    rollouts_path=str(effective_rollouts_path),
                    registry_path=str(registry_path) if registry_path else "",
                )
                state.set_artifact("rollouts_path", str(effective_rollouts_path))
                context["rollouts_path"] = str(effective_rollouts_path)

            if not effective_rollouts_path.exists() or not effective_rollouts_path.is_dir():
                raise StageFailure(
                    "data_pipeline",
                    f"effective rollouts path must exist and be a directory: {effective_rollouts_path}",
                )
            context["rollouts_path"] = str(effective_rollouts_path)
            state.set_artifact("rollouts_path", str(effective_rollouts_path))

            def _data_pipeline_stage() -> None:
                next_parquet_path = _run_data_pipeline(
                    automation_config=automation_config,
                    rollouts_path=effective_rollouts_path,
                    context=context,
                    state=state,
                )
                context["parquet_path"] = str(next_parquet_path)

            _ensure_phase(phase="data_pipeline", state=state, fn=_data_pipeline_stage)

        if args.stop_after == "data_pipeline":
            state.finalize(status="success", error=None)
            state.append_event(
                "run_stopped_after",
                stop_after="data_pipeline",
                finished_at=_utc_now(),
            )
            notifier.notify(
                run_id=run_id,
                stage="data_pipeline",
                status="success",
                message="Qizhi automation stopped after data_pipeline",
                extras={
                    "parquet_path": state.get_artifact("parquet_path"),
                    "dataset_path": state.get_artifact("dataset_path"),
                },
            )
            print(f"[SUCCESS] run_id={run_id} (stopped_after=data_pipeline)")
            print(f"[STATE] {state.run_paths.state_path}")
            print(f"[ARTIFACTS] {state.run_paths.artifacts_path}")
            return 0

        if legacy_run_config_path is None:
            raise StageFailure(
                "train_submit",
                "legacy_run_config is required for train/deploy stages",
            )

        legacy_run = load_legacy_run_config(legacy_run_config_path)
        runtime_defaults_raw = automation_config.get("runtime_defaults")
        runtime_defaults = (
            runtime_defaults_raw if isinstance(runtime_defaults_raw, dict) else {}
        )
        qz_cfg = _resolve_qz_config(automation_config)

        legacy_cfg = _require_section(automation_config, "legacy")
        mapping_config_path = _resolve_path(
            str(legacy_cfg.get("mapping_config_path") or ""),
            base_dir=automation_config_path.parent,
        )
        mapping_tables = load_mapping_tables(mapping_config_path)
        mapping_tables = merge_mapping_overrides(
            mapping_tables,
            legacy_cfg.get("mapping_overrides"),
        )
        _apply_runtime_context_defaults(
            context=legacy_run,
            runtime_defaults=runtime_defaults,
            state=state,
        )

        if bool(qz_cfg.get("enabled", False)):
            if bool(qz_cfg.get("refresh_login_before_run", True)):
                login_result = _run_qz(
                    qz_cfg=qz_cfg,
                    qz_args=["login"],
                    state=state,
                    phase="qz_login_refresh",
                )
                if login_result.returncode != 0:
                    raise StageFailure(
                        "qz_login_refresh",
                        f"qz login failed: {_extract_qz_error_text(login_result)[-800:]}",
                    )
            ws_id, ws_name = _resolve_qz_workspace(
                qz_cfg=qz_cfg,
                legacy_run=legacy_run,
                state=state,
            )
            legacy_run["space_id"] = ws_id
            legacy_run["workspace_id"] = ws_id
            if ws_name:
                legacy_run["qz_workspace_name"] = ws_name

            required_nodes = _int_or_default(
                legacy_run.get("train_instance_count"),
                _int_or_default(
                    (_require_section(automation_config, "train").get("defaults") or {}).get("instance_count"),
                    8,
                ),
            )
            use_low_priority = False
            logic_group_table = mapping_tables.get("logic_compute_group")
            logic_group_id_to_key = {}
            if isinstance(logic_group_table, dict):
                logic_group_id_to_key = {
                    str(v): str(k) for k, v in logic_group_table.items()
                }
            candidates = _discover_qz_capacity_candidates(
                qz_cfg=qz_cfg,
                state=state,
                workspace_ids=[ws_id],
                required_nodes=required_nodes,
                use_low_priority=use_low_priority,
                logic_group_id_to_key=logic_group_id_to_key,
                type_preference=list(_normalize_qz_str_list(qz_cfg.get("type_preference"))),
                pool_allowlist=list(_normalize_qz_pool_allowlist(qz_cfg)),
            )
            _report_qz_capacity_candidates(
                state=state,
                required_nodes=required_nodes,
                candidates=candidates,
            )
            if not candidates:
                fallback_logic_group = str(
                    legacy_run.get("logic_compute_group")
                    or legacy_run.get("logic_compute_group_id")
                    or ""
                ).strip()
                fallback_room = str(legacy_run.get("room_id") or "").strip()
                if fallback_logic_group:
                    state.append_event(
                        "qz_capacity_scan_fallback_to_legacy",
                        required_nodes=required_nodes,
                        logic_compute_group=fallback_logic_group,
                        room_id=fallback_room,
                    )
                else:
                    raise StageFailure(
                        "qz_capacity_scan",
                        f"No capacity candidate found in 专项 workspace for required_nodes={required_nodes}",
                    )
            else:
                selected = candidates[0]
                selected_logic_group = str(selected.get("logic_compute_group") or "").strip()
                if not selected_logic_group:
                    raise StageFailure(
                        "qz_capacity_scan",
                        f"Selected capacity candidate missing logic_compute_group mapping: {selected}",
                    )
                legacy_run["logic_compute_group"] = selected_logic_group
                legacy_run["logic_compute_group_id"] = str(selected.get("logic_compute_group_id") or "")
                selected_room = str(selected.get("room_id") or "").strip()
                if selected_room:
                    legacy_run["room_id"] = selected_room
                qz_cfg["selected_pool"] = str(selected.get("pool_alias") or "")
                qz_cfg["selected_type"] = str(selected.get("type") or "")
                state.append_event(
                    "qz_capacity_candidate_selected",
                    required_nodes=required_nodes,
                    workspace_id=selected.get("workspace_id"),
                    workspace_name=selected.get("workspace_name"),
                    logic_compute_group=selected_logic_group,
                    logic_compute_group_id=selected.get("logic_compute_group_id"),
                    group_name=selected.get("group_name"),
                    pool_alias=selected.get("pool_alias"),
                    type=selected.get("type"),
                    room_id=selected.get("room_id"),
                    free_nodes=selected.get("free_nodes"),
                    raw_free_nodes=selected.get("raw_free_nodes"),
                    low_priority_nodes=selected.get("low_priority_nodes"),
                    tier=selected.get("tier"),
                )

        mapping_rules = list(legacy_cfg.get("mapping_rules") or DEFAULT_MAPPING_RULES)
        mapped_run = apply_mapping_rules(
            run_config=legacy_run,
            mapping_tables=mapping_tables,
            mapping_rules=mapping_rules,
            passthrough_if_id_like=bool(
                legacy_cfg.get("passthrough_if_id_like", True)
            ),
        )
        context.update(legacy_run)
        context.update(mapped_run)
        _apply_runtime_context_defaults(
            context=context,
            runtime_defaults=runtime_defaults,
            state=state,
        )

        if not bool(qz_cfg.get("enabled", False)):
            raise StageFailure(
                "qz_transport",
                "automation_config.qz.enabled (or legacy qzcli alias) must be true for train/deploy stages",
            )

        workspace_for_qz = str(
            context.get("workspace_id") or context.get("space_id") or ""
        ).strip()
        client = QzWorkflowClient(
            qz_cfg=qz_cfg,
            state=state,
            workspace_id=workspace_for_qz,
            pool_alias=str(qz_cfg.get("selected_pool") or ""),
            pool_type=str(qz_cfg.get("selected_type") or ""),
        )

        train_cfg = _require_section(automation_config, "train")
        deploy_cfg = _require_section(automation_config, "deploy")
        # Ensure train-derived runtime fields are always available, including resume flows
        # where train_submit phase might be skipped but deploy still depends on
        # placeholders like {train_output_dir}.
        _apply_train_runtime_defaults(context=context, train_cfg=train_cfg)

        def _train_submit_stage() -> None:
            _apply_train_runtime_defaults(context=context, train_cfg=train_cfg)
            workspace_for_qz = str(
                context.get("workspace_id") or context.get("space_id") or ""
            ).strip()
            _collect_qz_avail_snapshot(
                qz_cfg=qz_cfg,
                state=state,
                stage="train_submit_precheck",
                workspace=workspace_for_qz,
                required_nodes=_int_or_default(context.get("train_instance_count"), 1),
                use_low_priority=False,
            )
            payload_template = _require_section(train_cfg, "create_payload")
            payload = _normalize_train_payload(_render_value(payload_template, context))
            create_path = str(train_cfg.get("create_path") or "/api/v1/train_job/create")
            response = client.post(create_path, payload)
            job_id = extract_first(
                response,
                list(train_cfg.get("id_field_candidates") or DEFAULT_TRAIN_JOB_ID_CANDIDATES),
            )
            if not job_id:
                raise StageFailure(
                    "train_submit",
                    f"Unable to extract train job id from response: {json.dumps(response, ensure_ascii=False)[:1200]}",
                )
            state.append_event(
                "train_submit_payload_resolved",
                train_instance_count=context.get("train_instance_count"),
                train_shm_gi=context.get("train_shm_gi"),
                train_image_name=context.get("train_image_name"),
                train_image_type=context.get("train_image_type"),
                train_output_dir=context.get("train_output_dir"),
                train_output_tag=context.get("train_output_tag"),
                train_total_gpu_cards=context.get("train_total_gpu_cards"),
                workspace_id=context.get("workspace_id"),
                deploy_api_base=context.get("deploy_api_base"),
                experiment_api_base=context.get("experiment_api_base"),
            )
            context["train_job_id"] = str(job_id)
            state.set_artifact("train_job_id", str(job_id))
            state.append_event("train_submit_success", job_id=str(job_id))
            notifier.notify(
                run_id=run_id,
                stage="train_submit",
                status="success",
                message="Train job submitted",
                extras={"train_job_id": str(job_id)},
            )

        _ensure_phase(phase="train_submit", state=state, fn=_train_submit_stage)

        if args.stop_after == "train_submit":
            state.finalize(status="success", error=None)
            state.append_event(
                "run_stopped_after",
                stop_after="train_submit",
                finished_at=_utc_now(),
            )
            notifier.notify(
                run_id=run_id,
                stage="train_submit",
                status="success",
                message="Qizhi automation stopped after train_submit",
                extras={
                    "train_job_id": state.get_artifact("train_job_id"),
                    "parquet_path": state.get_artifact("parquet_path"),
                },
            )
            print(f"[SUCCESS] run_id={run_id} (stopped_after=train_submit)")
            print(f"[STATE] {state.run_paths.state_path}")
            print(f"[ARTIFACTS] {state.run_paths.artifacts_path}")
            return 0

        train_job_id = str(state.get_artifact("train_job_id") or context.get("train_job_id") or "")
        if not train_job_id:
            raise StageFailure("train_monitor", "train_job_id is missing before monitoring")
        context["train_job_id"] = train_job_id

        def _train_monitor_stage() -> None:
            detail_path = str(train_cfg.get("detail_path") or "/api/v1/train_job/detail")
            id_field = str(train_cfg.get("detail_id_field") or "job_id")
            polling_cfg = _require_section(train_cfg, "polling")
            workspace_for_qz = str(
                context.get("workspace_id") or context.get("space_id") or ""
            ).strip()
            required_nodes = _int_or_default(context.get("train_instance_count"), 1)
            response, status = _poll_until_terminal(
                client=client,
                detail_path=detail_path,
                id_field=id_field,
                resource_id=train_job_id,
                polling_cfg=polling_cfg,
                stage="train_monitor",
                state=state,
                on_poll=lambda poll_idx, _status, _resp: _maybe_collect_qz_monitor(
                    qz_cfg=qz_cfg,
                    state=state,
                    stage="train_monitor",
                    poll_index=poll_idx,
                    workspace=workspace_for_qz,
                    required_nodes=required_nodes,
                ),
            )
            state.set_artifact("train_final_status", status)
            state.set_artifact("train_detail_response", response)

        _ensure_phase(phase="train_monitor", state=state, fn=_train_monitor_stage)

        def _deploy_hf_wait_stage() -> None:
            hf_wait_cfg_raw = deploy_cfg.get("hf_wait")
            hf_wait_cfg = hf_wait_cfg_raw if isinstance(hf_wait_cfg_raw, dict) else {}
            if not bool(hf_wait_cfg.get("enabled", True)):
                state.append_event("deploy_hf_wait_skipped", reason="disabled")
                state.set_artifact(
                    "deploy_bash_command",
                    str(context.get("bash_command") or ""),
                )
                return

            _resolve_context_template_keys(
                context=context,
                template_keys=["bash_command"],
            )
            bash_command = str(context.get("bash_command") or "").strip()
            if not bash_command:
                raise StageFailure(
                    "deploy_hf_wait",
                    "bash_command is empty; unable to locate HF checkpoint path",
                )

            hf_token = _extract_hf_path_token_from_bash_command(bash_command)
            if not hf_token:
                raise StageFailure(
                    "deploy_hf_wait",
                    f"Unable to parse HF checkpoint path from bash_command: {bash_command}",
                )

            hf_path_hint = Path(hf_token).expanduser()
            if not hf_path_hint.is_absolute():
                hf_path_hint = (REPO_ROOT / hf_path_hint).resolve()

            dir_name_regex = str(hf_wait_cfg.get("dir_name_regex") or r"^iter_(\d+)_hf$")
            ready_file_names = _normalize_ready_file_names(
                hf_wait_cfg.get("ready_file_names")
            )
            poll_interval_seconds = max(
                1, _int_or_default(hf_wait_cfg.get("poll_interval_seconds"), 60)
            )
            timeout_seconds = max(
                0, _int_or_default(hf_wait_cfg.get("timeout_seconds"), 0)
            )
            selection_policy = str(
                hf_wait_cfg.get("selection_policy") or "latest_ready"
            ).strip().lower()
            if selection_policy != "latest_ready":
                raise StageFailure(
                    "deploy_hf_wait",
                    f"Unsupported deploy.hf_wait.selection_policy: {selection_policy}",
                )

            base_dir = hf_path_hint.parent
            try:
                compiled_pattern = re.compile(dir_name_regex)
            except re.error as exc:
                raise StageFailure(
                    "deploy_hf_wait",
                    f"Invalid deploy.hf_wait.dir_name_regex: {dir_name_regex}",
                ) from exc

            if not compiled_pattern.fullmatch(hf_path_hint.name):
                base_dir = hf_path_hint

            selected_hf_dir, wait_seconds = _wait_for_ready_hf_dir(
                base_dir=base_dir,
                hf_path_hint=hf_path_hint,
                dir_name_regex=dir_name_regex,
                ready_file_names=ready_file_names,
                poll_interval_seconds=poll_interval_seconds,
                timeout_seconds=timeout_seconds,
                state=state,
            )
            rewrite_bash = bool(
                hf_wait_cfg.get("rewrite_bash_command_with_selected_hf", True)
            )
            if rewrite_bash:
                bash_command = _rewrite_bash_command_hf_path(
                    command=bash_command,
                    old_token=hf_token,
                    selected_hf_dir=selected_hf_dir,
                )
                context["bash_command"] = bash_command

            context["hf_selected_dir"] = str(selected_hf_dir)
            context["hf_base_dir"] = str(base_dir)
            context["hf_selection_policy"] = selection_policy
            context["hf_wait_seconds"] = wait_seconds

            state.set_artifact("hf_selected_dir", str(selected_hf_dir))
            state.set_artifact("hf_base_dir", str(base_dir))
            state.set_artifact("hf_selection_policy", selection_policy)
            state.set_artifact("hf_wait_seconds", wait_seconds)
            state.set_artifact("deploy_bash_command", bash_command)

        _ensure_phase(phase="deploy_hf_wait", state=state, fn=_deploy_hf_wait_stage)

        resumed_hf_selected = str(state.get_artifact("hf_selected_dir") or "").strip()
        if resumed_hf_selected:
            context["hf_selected_dir"] = resumed_hf_selected
        resumed_hf_base = str(state.get_artifact("hf_base_dir") or "").strip()
        if resumed_hf_base:
            context["hf_base_dir"] = resumed_hf_base
        resumed_hf_policy = str(state.get_artifact("hf_selection_policy") or "").strip()
        if resumed_hf_policy:
            context["hf_selection_policy"] = resumed_hf_policy
        resumed_hf_wait_seconds = state.get_artifact("hf_wait_seconds")
        if resumed_hf_wait_seconds is not None:
            context["hf_wait_seconds"] = resumed_hf_wait_seconds
        resumed_bash_command = str(state.get_artifact("deploy_bash_command") or "").strip()
        if resumed_bash_command:
            context["bash_command"] = resumed_bash_command

        def _deploy_submit_stage() -> None:
            experiment_api_base = str(context.get("experiment_api_base") or "").strip()
            if not experiment_api_base:
                raise StageFailure(
                    "deploy_submit",
                    "experiment_api_base is empty. Please provide deploy_api_prefix and room_id (or explicit experiment_api_base).",
                )
            deploy_required_nodes = _int_or_default(
                context.get("num_nodes") or context.get("node_num_per_replica"),
                1,
            )
            workspace_for_qz = str(
                context.get("workspace_id") or context.get("space_id") or ""
            ).strip()
            _collect_qz_avail_snapshot(
                qz_cfg=qz_cfg,
                state=state,
                stage="deploy_submit_precheck",
                workspace=workspace_for_qz,
                required_nodes=deploy_required_nodes,
                use_low_priority=False,
            )
            _resolve_context_template_keys(
                context=context,
                template_keys=["bash_command"],
            )
            payload_template = _require_section(deploy_cfg, "create_payload")
            payload = _render_value(payload_template, context)
            create_path = str(
                deploy_cfg.get("create_path") or "/api/v1/inference_servings/create"
            )
            response = client.post(create_path, payload)
            serving_id = extract_first(
                response,
                list(deploy_cfg.get("id_field_candidates") or DEFAULT_SERVING_ID_CANDIDATES),
            )
            if not serving_id:
                raise StageFailure(
                    "deploy_submit",
                    "Unable to extract inference serving id from deploy response",
                )
            context["inference_serving_id"] = str(serving_id)
            state.set_artifact("inference_serving_id", str(serving_id))
            state.append_event(
                "deploy_submit_success",
                inference_serving_id=str(serving_id),
            )
            notifier.notify(
                run_id=run_id,
                stage="deploy_submit",
                status="success",
                message="Deploy job submitted",
                extras={"inference_serving_id": str(serving_id)},
            )

        _ensure_phase(phase="deploy_submit", state=state, fn=_deploy_submit_stage)

        serving_id = str(
            state.get_artifact("inference_serving_id")
            or context.get("inference_serving_id")
            or ""
        )
        if not serving_id:
            raise StageFailure(
                "deploy_monitor",
                "inference_serving_id is missing before monitoring",
            )
        context["inference_serving_id"] = serving_id

        def _deploy_monitor_stage() -> None:
            detail_path = str(
                deploy_cfg.get("detail_path") or "/api/v1/inference_servings/detail"
            )
            id_field = str(deploy_cfg.get("detail_id_field") or "inference_serving_id")
            polling_cfg = _require_section(deploy_cfg, "polling")
            workspace_for_qz = str(
                context.get("workspace_id") or context.get("space_id") or ""
            ).strip()
            deploy_required_nodes = _int_or_default(
                context.get("num_nodes") or context.get("node_num_per_replica"),
                1,
            )
            response, status = _poll_until_terminal(
                client=client,
                detail_path=detail_path,
                id_field=id_field,
                resource_id=serving_id,
                polling_cfg=polling_cfg,
                stage="deploy_monitor",
                state=state,
                on_poll=lambda poll_idx, _status, _resp: _maybe_collect_qz_monitor(
                    qz_cfg=qz_cfg,
                    state=state,
                    stage="deploy_monitor",
                    poll_index=poll_idx,
                    workspace=workspace_for_qz,
                    required_nodes=deploy_required_nodes,
                ),
            )
            endpoint = extract_first(
                response,
                list(
                    polling_cfg.get("endpoint_field_candidates")
                    or DEFAULT_ENDPOINT_CANDIDATES
                ),
            )
            endpoint_str = str(endpoint) if endpoint is not None else ""
            context["serving_endpoint"] = endpoint_str
            state.set_artifact("serving_endpoint", endpoint_str)
            state.set_artifact("deploy_final_status", status)
            state.set_artifact("deploy_detail_response", response)

        _ensure_phase(phase="deploy_monitor", state=state, fn=_deploy_monitor_stage)

        def _callback_stage() -> None:
            callback_cfg = _require_section(automation_config, "callback")
            command_template = str(callback_cfg.get("command") or "").strip()
            if not command_template:
                state.append_event("callback_skipped", reason="empty callback.command")
                return

            command = _render_value(command_template, context)
            shell = bool(callback_cfg.get("shell", True))
            cwd = _resolve_path(
                str(callback_cfg.get("working_dir") or str(REPO_ROOT)),
                base_dir=REPO_ROOT,
            )
            env = os.environ.copy()
            env["SERVING_ID"] = str(context.get("inference_serving_id") or "")
            env["SERVING_ENDPOINT"] = str(context.get("serving_endpoint") or "")
            env["DEPLOY_API_BASE"] = str(context.get("deploy_api_base") or "")
            env["EXPERIMENT_API_BASE"] = str(context.get("experiment_api_base") or "")

            state.append_event("callback_command", command=command, shell=shell, cwd=str(cwd))
            result = _run_subprocess(command, shell=shell, cwd=cwd, env=env)
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

            state.append_event(
                "callback_result",
                return_code=result.returncode,
                stdout_tail=result.stdout[-4000:],
                stderr_tail=result.stderr[-4000:],
            )
            state.set_artifact("callback_return_code", result.returncode)
            if result.returncode != 0:
                raise StageFailure(
                    "callback",
                    f"Callback command failed with exit code {result.returncode}",
                )

        _ensure_phase(phase="callback", state=state, fn=_callback_stage)

        state.finalize(status="success", error=None)
        state.append_event("run_succeeded", finished_at=_utc_now())
        notifier.notify(
            run_id=run_id,
            stage="all",
            status="success",
            message="Qizhi automation completed",
            extras={
                "train_job_id": state.get_artifact("train_job_id"),
                "inference_serving_id": state.get_artifact("inference_serving_id"),
                "serving_endpoint": state.get_artifact("serving_endpoint"),
            },
        )
        print(f"[SUCCESS] run_id={run_id}")
        print(f"[STATE] {state.run_paths.state_path}")
        print(f"[ARTIFACTS] {state.run_paths.artifacts_path}")
        return 0

    except (StageFailure, QizhiApiError, ValueError, FileNotFoundError) as exc:
        current_phase = str(state.state.get("current_phase") or "unknown")
        message = str(exc)
        state.append_event(
            "run_failed",
            stage=current_phase,
            error_type=type(exc).__name__,
            error=message,
        )
        state.finalize(status="failed", error=message)
        notifier.notify(
            run_id=run_id,
            stage=current_phase,
            status="failed",
            message=message,
            extras={
                "train_job_id": state.get_artifact("train_job_id"),
                "inference_serving_id": state.get_artifact("inference_serving_id"),
            },
        )
        print(f"[FAILED] stage={current_phase} error={message}", file=sys.stderr)
        print(f"[STATE] {state.run_paths.state_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
