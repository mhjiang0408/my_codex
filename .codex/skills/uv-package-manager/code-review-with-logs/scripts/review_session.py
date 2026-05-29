#!/usr/bin/env python3
"""Review session path helpers for code-review-with-logs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SESSION_ROOT_RELATIVE = Path(".codex") / "reviews"
LATEST_INDEX_NAME = "latest.json"
SESSION_ARTIFACTS = {
    "summary": "review_summary.md",
    "run_log": "review_run.log",
    "validation_json": "validation_results.json",
    "result_report_json": "review_result_report.json",
    "test_results_json": "test_results.json",
    "benchmark_results_json": "benchmark_results.json",
    "repro_steps": "repro_steps.md",
    "repro_results_json": "repro_results.json",
    "session_metadata": "session.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitize_review_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = cleaned.strip(".-")
    return cleaned or "review"


def generate_review_id(review_target_sha: str | None = None) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = sanitize_review_id((review_target_sha or "head")[:12].lower())
    return f"{timestamp}-{suffix}"


def reviews_root(workspace: Path) -> Path:
    return (workspace / SESSION_ROOT_RELATIVE).resolve()


def session_dir_for_review_id(workspace: Path, review_id: str) -> Path:
    return (reviews_root(workspace) / sanitize_review_id(review_id)).resolve()


def infer_review_id_from_path(path: Path | None, workspace: Path) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    root = reviews_root(workspace)
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return None
    parts = relative.parts
    if not parts:
        return None
    review_id = parts[0]
    if review_id == LATEST_INDEX_NAME:
        return None
    return review_id


def resolve_review_id(
    workspace: Path,
    *,
    review_id: str | None = None,
    artifact_path: Path | None = None,
    fallback_review_target_sha: str | None = None,
) -> str:
    inferred = review_id or infer_review_id_from_path(artifact_path, workspace)
    if inferred:
        return sanitize_review_id(inferred)
    return generate_review_id(fallback_review_target_sha)


def resolve_session_paths(
    workspace: Path,
    *,
    review_id: str | None = None,
    artifact_path: Path | None = None,
    fallback_review_target_sha: str | None = None,
) -> dict[str, Path | str]:
    session_review_id = resolve_review_id(
        workspace,
        review_id=review_id,
        artifact_path=artifact_path,
        fallback_review_target_sha=fallback_review_target_sha,
    )
    session_dir = session_dir_for_review_id(workspace, session_review_id)
    paths: dict[str, Path | str] = {
        "review_id": session_review_id,
        "session_dir": session_dir,
        "reviews_root": reviews_root(workspace),
        "latest_index": (reviews_root(workspace) / LATEST_INDEX_NAME).resolve(),
    }
    for key, filename in SESSION_ARTIFACTS.items():
        paths[key] = (session_dir / filename).resolve()
    return paths


def write_latest_index(workspace: Path, payload: dict[str, Any]) -> Path:
    latest_index = (reviews_root(workspace) / LATEST_INDEX_NAME).resolve()
    latest_index.parent.mkdir(parents=True, exist_ok=True)
    latest_index.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return latest_index
