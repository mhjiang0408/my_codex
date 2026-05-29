"""YAML/JSON template system with inheritance, interpolation, and overrides.

Templates are searched in ``templates/qzx/`` then ``templates/`` relative to
the repo root.  Each template can declare ``inherits: parent.yaml`` to compose
from a parent, and ``{placeholder}`` strings are replaced from a context dict.

CLI overrides use ``--set key=value`` with dotted paths (e.g. ``platform.gpus=8``).
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from qzx.context import default_repo_root

TEMPLATE_SUFFIXES = (".yaml", ".yml", ".json")
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def find_template_path(
    template: str,
    *,
    repo_root: Path | None = None,
    template_root: Path | None = None,
) -> Path:
    candidate = Path(template).expanduser()
    if candidate.is_file():
        return candidate.resolve()

    resolved_repo = Path(repo_root or default_repo_root()).resolve()
    search_roots = [
        Path(template_root).resolve() if template_root is not None else resolved_repo / "templates" / "qzx",
        resolved_repo / "templates",
    ]

    attempted: list[Path] = []
    for root in search_roots:
        if template.endswith(TEMPLATE_SUFFIXES):
            path = root / template
            attempted.append(path)
            if path.is_file():
                return path.resolve()
            continue

        for suffix in TEMPLATE_SUFFIXES:
            path = root / f"{template}{suffix}"
            attempted.append(path)
            if path.is_file():
                return path.resolve()

    attempted_text = ", ".join(str(path) for path in attempted)
    raise FileNotFoundError(f"template not found: {template} (checked: {attempted_text})")


def load_template(
    template: str,
    *,
    repo_root: Path | None = None,
    template_root: Path | None = None,
    overrides: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = find_template_path(template, repo_root=repo_root, template_root=template_root)
    return load_template_path(path, repo_root=repo_root, template_root=template_root, overrides=overrides, context=context)


def load_template_path(
    path: Path,
    *,
    repo_root: Path | None = None,
    template_root: Path | None = None,
    overrides: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    _seen: tuple[Path, ...] = (),
) -> dict[str, Any]:
    resolved_path = Path(path).resolve()
    if resolved_path in _seen:
        cycle = " -> ".join(str(item) for item in (*_seen, resolved_path))
        raise ValueError(f"template inheritance cycle detected: {cycle}")

    raw = _load_template_doc(resolved_path)
    inherits = raw.pop("inherits", None)
    merged: dict[str, Any] = {}
    if inherits:
        parent_path = _resolve_parent_template(
            inherits,
            current_path=resolved_path,
            repo_root=repo_root,
            template_root=template_root,
        )
        merged = load_template_path(
            parent_path,
            repo_root=repo_root,
            template_root=template_root,
            context=context,
            _seen=(*_seen, resolved_path),
        )

    merged = deep_merge(merged, raw)
    if overrides:
        for key, value in overrides.items():
            apply_override(merged, key, value)
    if context:
        merged = interpolate_template(merged, context)

    merged.setdefault("template", {})
    merged["template"]["path"] = str(resolved_path)
    merged["template"]["name"] = merged["template"].get("name") or resolved_path.stem
    return merged


def parse_template_overrides(items: list[str] | None) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for item in items or []:
        key, separator, raw_value = item.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"template override must use key=value syntax: {item}")
        overrides[key.strip()] = _parse_scalar(raw_value)
    return overrides


def interpolate_template(data: Any, context: dict[str, Any]) -> Any:
    if isinstance(data, dict):
        return {key: interpolate_template(value, context) for key, value in data.items()}
    if isinstance(data, list):
        return [interpolate_template(value, context) for value in data]
    if isinstance(data, str):
        return PLACEHOLDER_PATTERN.sub(lambda match: str(context.get(match.group(1), match.group(0))), data)
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def apply_override(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    cursor = data
    parts = [part for part in dotted_path.split(".") if part]
    if not parts:
        raise ValueError("override path cannot be empty")

    for part in parts[:-1]:
        existing = cursor.get(part)
        if existing is None:
            existing = {}
            cursor[part] = existing
        if not isinstance(existing, dict):
            raise ValueError(f"override path segment is not a mapping: {part}")
        cursor = existing
    cursor[parts[-1]] = value


def _resolve_parent_template(
    inherits: str,
    *,
    current_path: Path,
    repo_root: Path | None = None,
    template_root: Path | None = None,
) -> Path:
    candidate = (current_path.parent / inherits).resolve()
    if candidate.is_file():
        return candidate
    return find_template_path(inherits, repo_root=repo_root, template_root=template_root)


def _load_template_doc(path: Path) -> dict[str, Any]:
    text = path.read_text()
    if path.suffix == ".json":
        payload = json.loads(text)
    else:
        yaml = _load_yaml_module()
        payload = yaml.safe_load(text) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"template must decode to a mapping: {path}")
    return payload


def _load_yaml_module() -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load YAML qzx templates") from exc
    return yaml


def _parse_scalar(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    yaml = _load_yaml_module()
    return yaml.safe_load(raw)
