#!/usr/bin/env python3
"""State persistence helpers for qizhi automation skill."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


@dataclass
class RunPaths:
    run_dir: Path
    state_path: Path
    events_path: Path
    artifacts_path: Path


class RunStateStore:
    """Persist run state/events/artifacts with simple resume support."""

    def __init__(
        self,
        *,
        root_dir: Path,
        run_id: str,
        resume: bool,
    ) -> None:
        self.run_paths = RunPaths(
            run_dir=root_dir / run_id,
            state_path=root_dir / run_id / "state.json",
            events_path=root_dir / run_id / "events.jsonl",
            artifacts_path=root_dir / run_id / "artifacts.json",
        )
        self.run_paths.run_dir.mkdir(parents=True, exist_ok=True)

        if resume and self.run_paths.state_path.exists():
            self.state = self._load_json(self.run_paths.state_path)
        else:
            self.state = {
                "run_id": run_id,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "status": "running",
                "current_phase": "init",
                "phase_status": {},
                "last_error": None,
            }
            self._save_state()

        if resume and self.run_paths.artifacts_path.exists():
            loaded_artifacts = self._load_json(self.run_paths.artifacts_path)
            self.artifacts: dict[str, Any] = dict(loaded_artifacts)
        else:
            self.artifacts = {}
            self._save_artifacts()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object in {path}")
        return data

    def _save_state(self) -> None:
        self.state["updated_at"] = _utc_now()
        _atomic_write_json(self.run_paths.state_path, self.state)

    def _save_artifacts(self) -> None:
        _atomic_write_json(self.run_paths.artifacts_path, self.artifacts)

    def append_event(self, event: str, **payload: Any) -> None:
        record = {
            "ts": _utc_now(),
            "event": event,
            **payload,
        }
        with self.run_paths.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def update_phase(self, phase: str, status: str) -> None:
        phase_status = self.state.setdefault("phase_status", {})
        if not isinstance(phase_status, dict):
            phase_status = {}
            self.state["phase_status"] = phase_status
        phase_status[phase] = status
        self.state["current_phase"] = phase
        self._save_state()

    def phase_done(self, phase: str) -> bool:
        phase_status = self.state.get("phase_status")
        if not isinstance(phase_status, dict):
            return False
        return str(phase_status.get(phase) or "") == "success"

    def set_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value
        self._save_artifacts()

    def get_artifact(self, key: str, default: Any = None) -> Any:
        return self.artifacts.get(key, default)

    def finalize(self, *, status: str, error: str | None = None) -> None:
        self.state["status"] = status
        self.state["last_error"] = error
        self._save_state()
