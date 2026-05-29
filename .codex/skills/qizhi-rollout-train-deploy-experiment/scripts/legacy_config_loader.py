#!/usr/bin/env python3
"""Load AutoQZ legacy configs and map semantic values to API-ready IDs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


_ID_LIKE_PATTERNS = (
    re.compile(r"^[a-z]+-[a-f0-9\-]{6,}$", re.IGNORECASE),
    re.compile(r"^[a-z0-9]+m[a-z0-9]+g[a-z0-9]+t$", re.IGNORECASE),
)


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _require_single_key_dict(item: Any, *, context: str) -> tuple[str, Any]:
    if not isinstance(item, dict) or len(item) != 1:
        raise ValueError(f"{context} expects single-key dict entries: {item!r}")
    key = next(iter(item.keys()))
    return str(key), item[key]


def load_legacy_run_config(path: Path) -> dict[str, Any]:
    raw = load_yaml(path)
    if not isinstance(raw, list):
        raise ValueError(
            f"Legacy run config must be list format (- key: value). path={path}"
        )
    output: dict[str, Any] = {}
    for item in raw:
        key, value = _require_single_key_dict(item, context="legacy run config")
        output[key] = value
    return output


def load_mapping_tables(path: Path) -> dict[str, dict[str, str]]:
    raw = load_yaml(path)
    if not isinstance(raw, list):
        raise ValueError(f"Mapping config must be list format. path={path}")

    tables: dict[str, dict[str, str]] = {}
    for item in raw:
        table_key, table_value = _require_single_key_dict(
            item, context="mapping config"
        )
        if not isinstance(table_value, list):
            raise ValueError(
                f"Mapping table '{table_key}' must be list of single-key dicts"
            )
        parsed_table: dict[str, str] = {}
        for pair in table_value:
            source, target = _require_single_key_dict(
                pair, context=f"mapping config table '{table_key}'"
            )
            parsed_table[str(source)] = str(target)
        tables[table_key] = parsed_table
    return tables


def merge_mapping_overrides(
    base: dict[str, dict[str, str]],
    overrides: dict[str, Any] | None,
) -> dict[str, dict[str, str]]:
    merged = {key: dict(value) for key, value in base.items()}
    if not overrides:
        return merged

    for table_key, table_value in overrides.items():
        if not isinstance(table_value, dict):
            raise ValueError(
                f"mapping_overrides.{table_key} must be dict[str, str], got {type(table_value).__name__}"
            )
        target_table = merged.setdefault(str(table_key), {})
        for source, target in table_value.items():
            target_table[str(source)] = str(target)
    return merged


def _is_id_like(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False
    for pattern in _ID_LIKE_PATTERNS:
        if pattern.match(lowered):
            return True
    return False


def _normalize_rules(raw_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, rule in enumerate(raw_rules, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"mapping_rules[{index}] must be an object")
        source_key = str(rule.get("source_key") or "").strip()
        target_key = str(rule.get("target_key") or source_key).strip()
        map_key = str(rule.get("map_key") or source_key).strip()
        required = bool(rule.get("required", True))
        if not source_key:
            raise ValueError(f"mapping_rules[{index}] missing source_key")
        if not target_key:
            raise ValueError(f"mapping_rules[{index}] missing target_key")
        if not map_key:
            raise ValueError(f"mapping_rules[{index}] missing map_key")
        normalized.append(
            {
                "source_key": source_key,
                "target_key": target_key,
                "map_key": map_key,
                "required": required,
            }
        )
    return normalized


def apply_mapping_rules(
    *,
    run_config: dict[str, Any],
    mapping_tables: dict[str, dict[str, str]],
    mapping_rules: list[dict[str, Any]],
    passthrough_if_id_like: bool,
) -> dict[str, Any]:
    resolved = dict(run_config)
    rules = _normalize_rules(mapping_rules)
    errors: list[str] = []

    for rule in rules:
        source_key = rule["source_key"]
        target_key = rule["target_key"]
        map_key = rule["map_key"]
        required = bool(rule["required"])

        if source_key not in run_config:
            if required:
                errors.append(f"Missing required source key: {source_key}")
            continue

        raw_value = run_config.get(source_key)
        if raw_value is None:
            if required:
                errors.append(f"source key {source_key} is null")
            continue

        source_value = str(raw_value)
        table = mapping_tables.get(map_key)
        if table is None:
            if passthrough_if_id_like and _is_id_like(source_value):
                resolved[target_key] = source_value
                continue
            if required:
                errors.append(
                    f"Mapping table '{map_key}' not found for source key '{source_key}'"
                )
            continue

        mapped = table.get(source_value)
        if mapped is not None:
            resolved[target_key] = mapped
            continue

        if passthrough_if_id_like and _is_id_like(source_value):
            resolved[target_key] = source_value
            continue

        if required:
            errors.append(
                f"No mapping found: table={map_key}, value={source_value}, source_key={source_key}"
            )

    if errors:
        raise ValueError("; ".join(errors))
    return resolved
