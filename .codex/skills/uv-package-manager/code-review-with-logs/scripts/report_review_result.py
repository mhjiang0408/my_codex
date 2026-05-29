#!/usr/bin/env python3
"""Send the final review result from the outer workflow and persist the attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

try:
    from review_session import resolve_session_paths
except ModuleNotFoundError:
    import importlib.util

    _SESSION_PATH = Path(__file__).with_name("review_session.py")
    _SESSION_SPEC = importlib.util.spec_from_file_location("review_session", _SESSION_PATH)
    assert _SESSION_SPEC is not None
    assert _SESSION_SPEC.loader is not None
    _SESSION_MODULE = importlib.util.module_from_spec(_SESSION_SPEC)
    _SESSION_SPEC.loader.exec_module(_SESSION_MODULE)
    resolve_session_paths = _SESSION_MODULE.resolve_session_paths


DEFAULT_FEISHU_CHAT_ID = "oc_28abbb3d6e900a7084967e947da391fe"
TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def compute_validation_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_json_object(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json_object(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_chat_id(cli_value: str | None) -> str | None:
    value = (cli_value or "").strip()
    if value:
        return value
    for env_key in ("CODE_REVIEW_FEISHU_CHAT_ID", "FEISHU_CHAT_ID"):
        env_value = os.getenv(env_key, "").strip()
        if env_value:
            return env_value
    return DEFAULT_FEISHU_CHAT_ID


def result_reporting_enabled() -> bool:
    value = os.getenv("CODE_REVIEW_FEISHU_RESULT_ENABLED", "").strip().lower()
    if not value:
        return True
    return value not in {"0", "false", "no", "off"}


def _extract_flag_value(args: list[Any], *flags: str) -> str | None:
    for index, item in enumerate(args):
        if item not in flags:
            continue
        if index + 1 >= len(args):
            return None
        value = args[index + 1]
        if isinstance(value, str):
            return value.strip() or None
    return None


def resolve_app_credentials(workspace: Path) -> tuple[str | None, str | None, str | None]:
    env_app_id = os.getenv("FEISHU_APP_ID", "").strip()
    env_app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if env_app_id and env_app_secret:
        return env_app_id, env_app_secret, "env"

    config_path = workspace / ".codex" / "config.toml"
    if not config_path.is_file():
        return None, None, None

    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None, None

    feishu_cfg = ((config.get("mcp_servers") or {}).get("feishu") or {})
    args = feishu_cfg.get("args") or []
    if not isinstance(args, list):
        return None, None, None

    app_id = _extract_flag_value(args, "-a", "--app-id")
    app_secret = _extract_flag_value(args, "-s", "--app-secret")
    if app_id and app_secret:
        return app_id, app_secret, "workspace_config"
    return None, None, None


def parse_stop_reason(summary_text: str) -> str | None:
    match = re.search(r"^- Stop Reason:\s*(.+?)\s*$", summary_text, flags=re.MULTILINE)
    if not match:
        return None
    reason = match.group(1).strip()
    return reason or None


def summarize_findings(findings: list[dict[str, Any]], limit: int = 3) -> list[str]:
    lines: list[str] = []
    for finding in findings[:limit]:
        severity = str(finding.get("severity") or "P2").strip()
        title = str(finding.get("title") or "Untitled finding").strip()
        location = ""
        file_path = str(finding.get("file") or "").strip()
        line = finding.get("line")
        if file_path:
            location = file_path
            if isinstance(line, int):
                location = f"{location}:{line}"
        elif isinstance(line, int):
            location = f"line {line}"
        if location:
            lines.append(f"- [{severity}] {title} ({location})")
        else:
            lines.append(f"- [{severity}] {title}")
    return lines


def _step_status(step: dict[str, Any] | None, key: str) -> str | None:
    if not isinstance(step, dict):
        return None
    value = step.get(key)
    if isinstance(value, dict):
        status = value.get("status")
        if isinstance(status, str) and status.strip():
            return status.strip()
    return None


def _phase_level_status(step: dict[str, Any] | None) -> str | None:
    if not isinstance(step, dict):
        return None
    status = step.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    return None


def build_card_content(
    *,
    review_id: str,
    root_review_id: str | None,
    summary_text: str,
    validation_payload: dict[str, Any],
    session_dir: Path,
    review_target_sha: str | None,
) -> dict[str, Any]:
    requirement = validation_payload.get("requirement_fulfillment") or {}
    steps = validation_payload.get("steps") or {}
    benchmark = validation_payload.get("benchmark_validation") or {}
    status = str(validation_payload.get("status") or "UNKNOWN").upper()
    feedback = str(validation_payload.get("feedback") or "").strip()
    deliverables_status = (
        _step_status(requirement, "deliverables")
        or _phase_level_status(steps.get("deliverable_review"))
        or "UNKNOWN"
    )
    functional_tests_status = (
        _step_status(requirement, "functional_tests")
        or _phase_level_status(steps.get("functional_tests"))
        or "UNKNOWN"
    )
    stop_reason = parse_stop_reason(summary_text) or feedback or "Review completed."

    lines = [
        f"状态：{status}",
        f"Review ID：{review_id}",
        f"Target SHA：{review_target_sha[:12] if review_target_sha else 'n/a'}",
        f"Deliverables：{deliverables_status}",
        f"Tests：{functional_tests_status}",
        f"Benchmark：{benchmark.get('status', 'NOT_REQUESTED')}",
        f"反馈：{feedback or stop_reason}",
        f"Session：{session_dir}",
    ]
    if root_review_id and root_review_id != review_id:
        lines.insert(2, f"Root Review ID：{root_review_id}")

    findings_lines: list[str] = []
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(lines),
            },
        }
    ]
    if findings_lines:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "Findings:\n" + "\n".join(findings_lines),
                },
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"代码审查结果：{review_id}",
            }
        },
        "elements": elements,
    }


def build_text_content(
    *,
    review_id: str,
    root_review_id: str | None,
    summary_text: str,
    validation_payload: dict[str, Any],
    session_dir: Path,
    review_target_sha: str | None,
) -> str:
    card = build_card_content(
        review_id=review_id,
        root_review_id=root_review_id,
        summary_text=summary_text,
        validation_payload=validation_payload,
        session_dir=session_dir,
        review_target_sha=review_target_sha,
    )
    header = (((card.get("header") or {}).get("title") or {}).get("content") or "代码审查结果")
    lines = [header]
    for element in card.get("elements") or []:
        if not isinstance(element, dict):
            continue
        text = ((element.get("text") or {}).get("content") or "").strip()
        if text:
            lines.append(text)
    return "\n\n".join(lines)


def fetch_tenant_token(app_id: str, app_secret: str) -> str:
    response = requests.post(
        TOKEN_URL,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", 0)) != 0:
        raise RuntimeError(f"Feishu token fetch failed: code={payload.get('code')}")
    token = payload.get("tenant_access_token")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("Feishu token fetch returned empty token")
    return token.strip()


def send_interactive_card(chat_id: str, app_id: str, app_secret: str, content: dict[str, Any]) -> str | None:
    token = fetch_tenant_token(app_id, app_secret)
    response = requests.post(
        MESSAGE_URL,
        params={"receive_id_type": "chat_id"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(content, ensure_ascii=False),
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", 0)) != 0:
        raise RuntimeError(f"Feishu send failed: code={payload.get('code')}")
    data = payload.get("data")
    if isinstance(data, dict):
        message_id = data.get("message_id")
        if isinstance(message_id, str) and message_id.strip():
            return message_id.strip()
    message_id = payload.get("message_id")
    if isinstance(message_id, str) and message_id.strip():
        return message_id.strip()
    return None


def send_text_message(chat_id: str, app_id: str, app_secret: str, text: str) -> str | None:
    token = fetch_tenant_token(app_id, app_secret)
    response = requests.post(
        MESSAGE_URL,
        params={"receive_id_type": "chat_id"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", 0)) != 0:
        raise RuntimeError(f"Feishu send failed: code={payload.get('code')}")
    data = payload.get("data")
    if isinstance(data, dict):
        message_id = data.get("message_id")
        if isinstance(message_id, str) and message_id.strip():
            return message_id.strip()
    message_id = payload.get("message_id")
    if isinstance(message_id, str) and message_id.strip():
        return message_id.strip()
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report the final code-review result from the outer workflow.")
    parser.add_argument("--workspace", required=True, help="Workspace root")
    parser.add_argument("--review-id", required=True, help="Review session identifier")
    parser.add_argument("--summary", required=True, help="Session review_summary.md path")
    parser.add_argument("--validation-json", required=True, help="Session validation_results.json path")
    parser.add_argument("--output-json", default=None, help="Session-scoped result report artifact path")
    parser.add_argument("--chat-id", default=None, help="Optional Feishu chat_id override")
    parser.add_argument("--root-review-id", default=None, help="Optional root review identifier for retargeted sessions")
    parser.add_argument("--review-target-sha", default=None, help="Optional review target SHA override")
    parser.add_argument("--flow-exit-code", type=int, default=None, help="Original run_review_flow.sh exit code")
    parser.add_argument("--exit-code", type=int, default=None, help="Alias for --flow-exit-code")
    parser.add_argument("--skip-reason", default=None, help="Write a skipped report artifact without sending")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    session_paths = resolve_session_paths(
        workspace,
        review_id=args.review_id,
    )
    output_json = Path(args.output_json).resolve() if args.output_json else Path(session_paths["result_report_json"])
    summary_path = Path(args.summary).resolve()
    validation_path = Path(args.validation_json).resolve()
    session_dir = Path(session_paths["session_dir"])

    summary_text = summary_path.read_text(encoding="utf-8") if summary_path.is_file() else ""
    validation_payload = load_json_object(validation_path)
    validation_fingerprint = compute_validation_fingerprint(validation_payload) if validation_payload else None
    existing_payload = load_json_object(output_json)
    if (
        existing_payload.get("delivery_status") == "sent"
        and validation_fingerprint
        and existing_payload.get("validation_fingerprint") == validation_fingerprint
    ):
        print(json.dumps(existing_payload, ensure_ascii=False))
        return 0

    payload: dict[str, Any] = {
        "generated_at": utc_now(),
        "workspace": workspace.as_posix(),
        "review_id": str(session_paths["review_id"]),
        "session_dir": session_dir.as_posix(),
        "summary": summary_path.as_posix(),
        "validation_json": validation_path.as_posix(),
        "root_review_id": (args.root_review_id or "").strip() or None,
        "flow_exit_code": args.flow_exit_code if args.flow_exit_code is not None else args.exit_code,
        "validation_fingerprint": validation_fingerprint,
        "status": str(validation_payload.get("status") or "UNKNOWN").upper(),
        "feedback": str(validation_payload.get("feedback") or "").strip(),
        "stop_reason": parse_stop_reason(summary_text),
        "review_target_sha": (
            str(args.review_target_sha or "").strip()
            or None
        ),
        "delivery_status": "skipped",
        "delivery_reason": None,
        "chat_id": resolve_chat_id(args.chat_id),
        "message_id": None,
        "auth_source": None,
        "message_mode": None,
    }

    if (args.skip_reason or "").strip():
        payload["delivery_reason"] = (args.skip_reason or "").strip()
        write_json_object(output_json, payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if not result_reporting_enabled():
        payload["delivery_reason"] = "result_reporting_disabled"
        write_json_object(output_json, payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    app_id, app_secret, auth_source = resolve_app_credentials(workspace)
    payload["auth_source"] = auth_source
    if not payload["chat_id"]:
        payload["delivery_reason"] = "missing_chat_id"
        write_json_object(output_json, payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if not app_id or not app_secret:
        payload["delivery_reason"] = "missing_feishu_credentials"
        write_json_object(output_json, payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    card_content = build_card_content(
        review_id=str(session_paths["review_id"]),
        root_review_id=(args.root_review_id or "").strip() or None,
        summary_text=summary_text,
        validation_payload=validation_payload,
        session_dir=session_dir,
        review_target_sha=str(payload["review_target_sha"] or "").strip() or None,
    )

    try:
        message_id = send_interactive_card(
            str(payload["chat_id"]),
            app_id,
            app_secret,
            card_content,
        )
    except Exception as exc:  # noqa: BLE001
        interactive_error = str(exc)
        try:
            message_id = send_text_message(
                str(payload["chat_id"]),
                app_id,
                app_secret,
                build_text_content(
                    review_id=str(session_paths["review_id"]),
                    root_review_id=(args.root_review_id or "").strip() or None,
                    summary_text=summary_text,
                    validation_payload=validation_payload,
                    session_dir=session_dir,
                    review_target_sha=str(payload["review_target_sha"] or "").strip() or None,
                ),
            )
        except Exception as fallback_exc:  # noqa: BLE001
            payload["delivery_status"] = "failed"
            payload["delivery_reason"] = f"interactive={interactive_error}; text_fallback={fallback_exc}"
            write_json_object(output_json, payload)
            print(json.dumps(payload, ensure_ascii=False))
            return 1
        payload["delivery_status"] = "sent"
        payload["delivery_reason"] = f"interactive_failed:{interactive_error}"
        payload["message_mode"] = "text_fallback"
        payload["message_id"] = message_id
        write_json_object(output_json, payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    payload["delivery_status"] = "sent"
    payload["message_id"] = message_id
    payload["message_mode"] = "interactive"
    write_json_object(output_json, payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
