#!/usr/bin/env python3
"""Validate a rebuilt code-review-with-logs report and prepare Feishu delivery."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "Field",
    "Why it matters",
    "Objective",
    "Permission boundary",
    "Plan changes",
    "command trace",
    "Diff summary",
    "Tests and evals",
    "Cost and retries",
    "Rollback path",
    "reliable check",
}

DEFAULT_CHAT_ID = "oc_28abbb3d6e900a7084967e947da391fe"


def validate_report_payload(payload: dict[str, Any]) -> tuple[bool, str | None]:
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return False, "review_report.json is missing object field: fields"
    missing = sorted(REQUIRED_FIELDS.difference(fields))
    if missing:
        return False, "review_report.json missing fields: " + ", ".join(missing)
    legacy_field = "Why it matters（影响了哪些模块）"
    if legacy_field in fields:
        return (
            False,
            "review_report.json uses legacy misleading field name: "
            f"{legacy_field}; use Why it matters and put impacted modules in Field",
        )
    return True, None


def build_feishu_document_title(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "UNKNOWN").upper()
    review_id = str(payload.get("review_id") or "unknown-review")
    return f"代码审查报告 [{status}] {review_id}"


def build_feishu_document_markdown(payload: dict[str, Any], summary_text: str) -> str:
    reliable = _reliable_payload(payload)
    if not reliable:
        return summary_text
    replacement = _render_reliable_check_markdown(reliable)
    return _replace_markdown_section(summary_text, "reliable check", replacement)


def build_feishu_message_text(
    payload: dict[str, Any],
    *,
    summary_text: str | None = None,
    doc_url: str | None = None,
    attachment_name: str | None = None,
) -> str:
    status = str(payload.get("status") or "UNKNOWN").upper()
    review_id = str(payload.get("review_id") or "unknown-review")
    objective = _clip_inline(_field_text(payload, "Objective", fallback="未提供目标"), limit=140)
    tests_status = _tests_status(payload)
    reliable_status = _reliable_status(payload)
    lines = [
        f"审查结果：{_status_text_zh(status)}",
        f"审查编号：{review_id}",
        f"目标：{objective}",
        f"完成情况：{_task_completion_status_text(status)}",
        "任务摘要：",
        _message_task_summary(payload, summary_text=summary_text),
        f"验证：测试{tests_status}；可靠检查{reliable_status}",
    ]
    conclusion = _short_conclusion(payload)
    if conclusion:
        lines.append(f"结论：{conclusion}")
    if doc_url:
        lines.append(f"完整报告：{doc_url}")
    elif attachment_name:
        lines.append(f"完整报告：已随消息发送 Markdown 文件附件 `{attachment_name}`")
    else:
        lines.append("完整报告：查看随消息发送的 Markdown 文件附件")
    return "\n".join(lines)


def build_delivery_payload(
    payload: dict[str, Any],
    summary_text: str,
    *,
    doc_url: str | None = None,
    attachment_path: Path | None = None,
) -> dict[str, Any]:
    attachment_name = attachment_path.name if attachment_path else None
    return {
        "review_id": payload.get("review_id"),
        "status": payload.get("status"),
        "document_title": build_feishu_document_title(payload),
        "document_markdown": build_feishu_document_markdown(payload, summary_text),
        "message_text": build_feishu_message_text(
            payload,
            summary_text=summary_text,
            doc_url=doc_url,
            attachment_name=attachment_name,
        ),
        "doc_url": doc_url,
        "attachment_path": attachment_path.as_posix() if attachment_path else None,
        "attachment_name": attachment_name,
    }


def _field_text(payload: dict[str, Any], field: str, *, fallback: str) -> str:
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return fallback
    value = fields.get(field)
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    return json.dumps(value, ensure_ascii=False)


def _tests_status(payload: dict[str, Any]) -> str:
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    tests = fields.get("Tests and evals") if isinstance(fields, dict) else None
    if isinstance(tests, dict):
        status = str(tests.get("status") or "UNKNOWN").upper()
        command_count = tests.get("command_count")
        if command_count is not None:
            return f"{_status_text_zh(status)}（{command_count} 条命令）"
        return _status_text_zh(status)
    return "状态未知"


def _reliable_status(payload: dict[str, Any]) -> str:
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    reliable = fields.get("reliable check") if isinstance(fields, dict) else None
    if isinstance(reliable, dict):
        return _status_text_zh(str(reliable.get("status") or "UNKNOWN").upper())
    return "状态未知"


def _status_text_zh(status: str) -> str:
    return {
        "PASS": "通过",
        "FAIL": "失败",
        "BLOCKED": "阻塞",
        "NOT_APPLICABLE": "不适用",
    }.get(status, "状态未知")


def _short_conclusion(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "UNKNOWN").upper()
    if status == "PASS":
        return "任务级测试和可靠性检查均通过。"
    if status == "FAIL":
        return "存在失败项，请先查看完整报告中的 Tests and evals / reliable check。"
    if status == "BLOCKED":
        return "证据或环境不足，完整报告中列出了阻塞项。"
    return ""


def _task_completion_status_text(status: str) -> str:
    if status == "PASS":
        return "任务已完成"
    if status == "FAIL":
        return "任务未完成"
    if status == "BLOCKED":
        return "任务收口被阻塞"
    return "任务状态不适用"


def _message_task_summary(payload: dict[str, Any], *, summary_text: str | None = None) -> str:
    if summary_text:
        section = _extract_markdown_section(summary_text, "Task completion summary")
        if section:
            return section
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    return _message_work_summary(fields)


def _extract_markdown_section(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^## |\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(markdown)
    if not match:
        return ""
    return match.group("body").strip()


def _message_work_summary(fields: dict[str, Any]) -> str:
    field_text = str(fields.get("Field") or "")
    impacted = _extract_bullet_items(field_text)
    if impacted:
        return "涉及 " + "、".join(f"`{item}`" for item in impacted[:4])
    diff = fields.get("Diff summary")
    if isinstance(diff, dict):
        requested = diff.get("changed_paths_requested")
        if isinstance(requested, list) and requested:
            return "涉及 " + "、".join(f"`{str(item)}`" for item in requested[:4])
        stat = str(diff.get("git_diff_stat") or "").strip()
        if stat:
            return _clip_inline("变更：" + " ".join(stat.split()), limit=120)
    return "未能从报告中定位具体变更路径"


def _extract_bullet_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        item = stripped[2:].strip().strip("`")
        if item:
            items.append(item)
    return items


def _message_tests_summary(value: Any) -> str:
    if not isinstance(value, dict):
        return "测试状态未知"
    status = _status_text_zh(str(value.get("status") or "UNKNOWN").upper())
    command_count = value.get("command_count")
    if command_count is None:
        return f"测试{status}"
    return f"测试{status}（{command_count} 条命令）"


def _message_reliable_summary(value: Any) -> str:
    if not isinstance(value, dict):
        return "状态未知"
    return _status_text_zh(str(value.get("status") or "UNKNOWN").upper())


def _clip_inline(value: str, *, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "..."


def _run_lark_cli(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _doc_create_commands(title: str, markdown_path: str) -> list[list[str]]:
    return [
        [
            "lark-cli",
            "docs",
            "+create",
            "--api-version",
            "v2",
            "--as",
            "bot",
            "--title",
            title,
            "--content",
            f"@{markdown_path}",
            "--doc-format",
            "markdown",
        ],
        [
            "lark-cli",
            "docs",
            "+create",
            "--api-version",
            "v1",
            "--as",
            "bot",
            "--title",
            title,
            "--markdown",
            f"@{markdown_path}",
        ],
    ]


def create_feishu_document(title: str, markdown: str) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".md",
            prefix=".codex_review_",
            dir=Path.cwd(),
            delete=False,
        ) as handle:
            handle.write(markdown)
            handle.flush()
            temp_path = Path(handle.name)
        markdown_path = f"./{temp_path.name}"
        for command in _doc_create_commands(title, markdown_path):
            proc = _run_lark_cli(command)
            output = _command_output(proc)
            attempts.append(
                {
                    "api_version": _arg_value(command, "--api-version"),
                    "exit_code": proc.returncode,
                    "output": output,
                }
            )
            if proc.returncode != 0:
                continue
            payload = _json_object(proc.stdout)
            if payload is None:
                continue
            doc_url = _find_nested_string(payload, ("doc_url", "document_url", "url"))
            doc_id = _find_nested_string(
                payload, ("doc_id", "document_id", "file_token", "obj_token", "token")
            )
            if doc_url:
                return {
                    "status": "PASS",
                    "doc_url": doc_url,
                    "doc_id": doc_id,
                    "output": proc.stdout.strip(),
                    "attempts": attempts,
                }
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return {
        "status": "FAIL",
        "doc_url": None,
        "doc_id": None,
        "output": attempts[-1]["output"] if attempts else "",
        "attempts": attempts,
    }


def grant_feishu_chat_document_access(doc_id: str | None, chat_id: str) -> dict[str, Any]:
    if not doc_id:
        return {
            "status": "SKIPPED",
            "reason": "document token is missing; cannot grant chat view access",
        }
    attempts: list[dict[str, Any]] = []
    data = {
        "member_type": "openchat",
        "member_id": chat_id,
        "perm": "view",
        "type": "chat",
    }
    for token_type in ("docx", "doc"):
        proc = _run_lark_cli(
            [
                "lark-cli",
                "drive",
                "permission.members",
                "create",
                "--as",
                "bot",
                "--params",
                json.dumps({"token": doc_id, "type": token_type}, ensure_ascii=False),
                "--data",
                json.dumps(data, ensure_ascii=False),
            ]
        )
        attempts.append(
            {
                "token_type": token_type,
                "exit_code": proc.returncode,
                "output": _command_output(proc),
            }
        )
        if proc.returncode == 0:
            return {
                "status": "PASS",
                "doc_id": doc_id,
                "chat_id": chat_id,
                "token_type": token_type,
                "output": proc.stdout.strip(),
                "attempts": attempts,
            }
    return {
        "status": "FAIL",
        "doc_id": doc_id,
        "chat_id": chat_id,
        "output": attempts[-1]["output"] if attempts else "",
        "attempts": attempts,
    }


def send_feishu_message(chat_id: str, text: str) -> tuple[str | None, str]:
    proc = _run_lark_cli(
        ["lark-cli", "im", "+messages-send", "--as", "bot", "--chat-id", chat_id, "--text", text]
    )
    if proc.returncode != 0:
        return None, proc.stderr.strip() or proc.stdout.strip()
    payload = _json_object(proc.stdout)
    if payload is None:
        return None, proc.stdout.strip()
    message_id = _find_nested_string(payload, ("message_id",))
    if message_id:
        return message_id, proc.stdout.strip()
    return None, proc.stdout.strip()


def send_feishu_file(chat_id: str, file_path: Path) -> tuple[str | None, str]:
    proc = _run_lark_cli(
        [
            "lark-cli",
            "im",
            "+messages-send",
            "--as",
            "bot",
            "--chat-id",
            chat_id,
            "--file",
            _lark_file_arg(file_path),
        ]
    )
    if proc.returncode != 0:
        return None, proc.stderr.strip() or proc.stdout.strip()
    payload = _json_object(proc.stdout)
    if payload is None:
        return None, proc.stdout.strip()
    message_id = _find_nested_string(payload, ("message_id",))
    if message_id:
        return message_id, proc.stdout.strip()
    return None, proc.stdout.strip()


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _find_nested_string(value: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for child in value.values():
            found = _find_nested_string(child, keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_nested_string(child, keys)
            if found:
                return found
    return None


def _token_from_doc_url(doc_url: str | None) -> str | None:
    if not doc_url:
        return None
    match = re.search(r"/(docx|doc)/([A-Za-z0-9]+)", doc_url)
    if match:
        return match.group(2)
    return None


def _arg_value(command: list[str], flag: str) -> str | None:
    try:
        return command[command.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _command_output(proc: subprocess.CompletedProcess[str]) -> str:
    return proc.stderr.strip() or proc.stdout.strip()


def _reliable_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return None
    reliable = fields.get("reliable check")
    return reliable if isinstance(reliable, dict) else None


def _replace_markdown_section(markdown: str, heading: str, body: str) -> str:
    replacement = f"## {heading}\n{body.strip()}\n"
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$\n.*?(?=^## |\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    if pattern.search(markdown):
        return pattern.sub(replacement, markdown).rstrip() + "\n"
    suffix = "" if markdown.endswith("\n") else "\n"
    return markdown + suffix + "\n" + replacement


def _render_reliable_check_markdown(reliable: dict[str, Any]) -> str:
    reviewer_markdown = reliable.get("reviewer_markdown")
    if isinstance(reviewer_markdown, str) and reviewer_markdown.strip():
        return reviewer_markdown.strip()

    status = str(reliable.get("status") or "UNKNOWN").upper()
    lines = [f"状态：{_status_text_zh(status)}"]

    checks = reliable.get("checks")
    if isinstance(checks, list) and checks:
        lines.append("")
        lines.append("检查项：")
        for item in checks:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            display_name = str(
                item.get("display_name")
                or _reliable_check_display_name(name)
                or name
                or "未命名检查"
            )
            check_status = str(item.get("status") or "UNKNOWN").upper()
            status_text = str(item.get("status_text") or _status_text_zh(check_status))
            lines.append(f"- {display_name}：{status_text}")
            details = item.get("details")
            if isinstance(details, str) and details.strip():
                lines.append(f"  - 说明：{details.strip()}")
            evidence = item.get("evidence")
            if isinstance(evidence, list):
                for evidence_item in evidence:
                    text = str(evidence_item).strip()
                    if text:
                        lines.append(f"  - 证据：{text}")

    context_files = reliable.get("context_files")
    if isinstance(context_files, list) and context_files:
        lines.append("")
        lines.append("上下文文件：")
        for item in context_files:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            label = str(
                item.get("label_zh")
                or _context_file_label_zh(str(item.get("label") or ""))
                or item.get("label")
                or "上下文"
            )
            status = str(item.get("status") or "UNKNOWN").lower()
            status_text = str(item.get("status_text") or _context_file_status_zh(status))
            if path:
                lines.append(f"- {label}：{status_text}，已读取 {path}")
            else:
                lines.append(f"- {label}：{status_text}")
    return "\n".join(lines)


def _reliable_check_display_name(name: str) -> str:
    return {
        "codex_record_presence": "会话记录完整性",
        "codex_idea_presence": "科研记录适用性",
        "command_and_plan_alignment": "命令与计划一致性",
        "diff_scope_alignment": "Diff 范围一致性",
        "runtime_evidence": "运行产物证据",
    }.get(name, name)


def _context_file_label_zh(label: str) -> str:
    return {
        "task_plan": "任务计划",
        "progress": "进度记录",
        "findings": "发现记录",
        "idea_plan": "科研计划",
        "idea_progress": "科研进度",
        "idea_findings": "科研发现",
    }.get(label, label)


def _context_file_status_zh(status: str) -> str:
    return {
        "present": "存在",
        "missing_required": "缺失",
        "missing_optional": "不适用",
    }.get(status, status)


def _lark_file_arg(file_path: Path) -> str:
    try:
        return file_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return file_path.as_posix()


def _write_normalized_attachment(summary_path: Path, markdown: str) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix=".codex_review_attachment_", dir=Path.cwd()))
    normalized_path = temp_dir / summary_path.name
    normalized_path.write_text(markdown, encoding="utf-8")
    return normalized_path


def _cleanup_normalized_attachment(path: Path) -> None:
    parent = path.parent
    path.unlink(missing_ok=True)
    try:
        parent.rmdir()
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or print a code-review-with-logs report JSON."
    )
    parser.add_argument("report_json", help="Path to .codex/reviews/<review_id>/review_report.json")
    parser.add_argument("--print-summary", action="store_true", help="Print a one-line summary.")
    parser.add_argument("--summary-md", default=None, help="Path to review_summary.md.")
    parser.add_argument(
        "--prepare-feishu-delivery",
        action="store_true",
        help="Build Feishu document markdown and concise message payload.",
    )
    parser.add_argument(
        "--doc-url",
        default=None,
        help="Existing Feishu document URL for message rendering.",
    )
    parser.add_argument(
        "--send-feishu",
        action="store_true",
        help="Send concise Feishu text and attach review_summary.md as a Markdown file.",
    )
    parser.add_argument(
        "--send-feishu-doc",
        action="store_true",
        help="Legacy mode: create a Feishu doc and send a concise message with the doc link.",
    )
    parser.add_argument("--chat-id", default=DEFAULT_CHAT_ID, help="Feishu chat id.")
    args = parser.parse_args(argv)

    path = Path(args.report_json)
    payload = json.loads(path.read_text(encoding="utf-8"))
    valid, error = validate_report_payload(payload)
    if not valid:
        sys.stderr.write(str(error) + "\n")
        return 1
    if args.print_summary:
        print(
            f"{payload.get('status', 'UNKNOWN')} "
            f"review_id={payload.get('review_id', 'n/a')} "
            f"session_id={payload.get('session_id', 'n/a')}"
        )
    if args.prepare_feishu_delivery or args.send_feishu or args.send_feishu_doc:
        summary_path = (
            Path(args.summary_md) if args.summary_md else path.with_name("review_summary.md")
        )
        summary_text = summary_path.read_text(encoding="utf-8")
        delivery_payload = build_delivery_payload(
            payload,
            summary_text,
            doc_url=args.doc_url,
            attachment_path=summary_path,
        )
        if args.prepare_feishu_delivery and not (args.send_feishu or args.send_feishu_doc):
            print(json.dumps(delivery_payload, ensure_ascii=False, indent=2))
            return 0
        if args.send_feishu:
            message_id, message_output = send_feishu_message(
                args.chat_id,
                str(delivery_payload["message_text"]),
            )
            delivery_payload["message_id"] = message_id
            delivery_payload["message_send_output"] = message_output
            if not message_id:
                delivery_payload["delivery_status"] = "message_failed"
                print(json.dumps(delivery_payload, ensure_ascii=False, indent=2))
                return 1
            normalized_attachment = _write_normalized_attachment(
                summary_path, str(delivery_payload["document_markdown"])
            )
            try:
                attachment_id, attachment_output = send_feishu_file(
                    args.chat_id, normalized_attachment
                )
            finally:
                _cleanup_normalized_attachment(normalized_attachment)
            delivery_payload["attachment_message_id"] = attachment_id
            delivery_payload["attachment_send_output"] = attachment_output
            delivery_payload["delivery_status"] = "sent" if attachment_id else "attachment_failed"
            print(json.dumps(delivery_payload, ensure_ascii=False, indent=2))
            return 0 if attachment_id else 1
        document_result = create_feishu_document(
            str(delivery_payload["document_title"]),
            str(delivery_payload["document_markdown"]),
        )
        doc_url = document_result.get("doc_url")
        delivery_payload["doc_url"] = doc_url
        delivery_payload["document_create"] = document_result
        delivery_payload["message_text"] = build_feishu_message_text(
            payload,
            summary_text=summary_text,
            doc_url=doc_url,
        )
        if not doc_url:
            print(json.dumps(delivery_payload, ensure_ascii=False, indent=2))
            return 1
        doc_token = _find_nested_string(document_result, ("doc_id", "document_id", "file_token"))
        if not doc_token:
            doc_token = _token_from_doc_url(doc_url)
        permission_result = grant_feishu_chat_document_access(doc_token, args.chat_id)
        delivery_payload["permission_grant"] = permission_result
        if permission_result.get("status") != "PASS":
            delivery_payload["message_text"] = (
                str(delivery_payload["message_text"])
                + "\n权限：自动授权未确认，请检查文档访问权限。"
            )
        message_id, message_output = send_feishu_message(
            args.chat_id,
            str(delivery_payload["message_text"]),
        )
        delivery_payload["message_id"] = message_id
        delivery_payload["message_send_output"] = message_output
        if message_id:
            delivery_payload["delivery_status"] = (
                "sent"
                if permission_result.get("status") == "PASS"
                else "sent_permission_unconfirmed"
            )
        else:
            delivery_payload["delivery_status"] = "message_failed"
        print(json.dumps(delivery_payload, ensure_ascii=False, indent=2))
        return 0 if message_id else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
