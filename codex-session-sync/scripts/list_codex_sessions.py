#!/usr/bin/env python3
"""List recent Codex sessions in a compact, user-facing format."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_SESSION_ROOT = Path.home() / ".codex" / "sessions"
SECRET_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\b(?:access_token|refresh_token|id_token|api[_-]?key|bearer)\b", re.I),
    re.compile(r"\b[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
]


@dataclass
class SessionItem:
    session_id: str
    timestamp: str
    cwd: str
    project: str
    title: str
    source_file: str
    first_user_message: str
    recent_user_message: str
    user_count: int
    has_redacted_preview: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List recent local Codex sessions.")
    parser.add_argument(
        "--session-root",
        default=str(DEFAULT_SESSION_ROOT),
        help="Root directory for local Codex sessions",
    )
    parser.add_argument("--latest", type=int, default=8, help="Number of sessions to inspect")
    parser.add_argument(
        "--project",
        default="",
        help="Only include sessions whose cwd contains this text",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of readable text",
    )
    parser.add_argument(
        "--selector-json",
        action="store_true",
        help="Emit selector-friendly JSON with label/description/value fields",
    )
    return parser.parse_args()


def discover_latest_sessions(session_root: Path, limit: int) -> list[Path]:
    return sorted(
        session_root.rglob("*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]


def clean_message(text: str) -> str:
    value = text.strip()
    if not value or value.startswith("<environment_context>"):
        return ""
    value = " ".join(value.split())
    if any(pattern.search(value) for pattern in SECRET_PATTERNS):
        return "[redacted sensitive text]"
    if len(value) > 140:
        return value[:137] + "..."
    return value


def choose_title(user_messages: list[str], project: str) -> str:
    for message in user_messages:
        if message and message != "[redacted sensitive text]":
            return message
    if user_messages:
        return user_messages[0]
    return f"{project} session"


def human_time_label(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


def parse_session(path: Path) -> SessionItem:
    session_id = path.stem
    timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    cwd = ""
    user_messages: list[str] = []

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            record_type = record.get("type")
            payload = record.get("payload", {})

            if record_type == "session_meta":
                session_id = payload.get("id", session_id)
                timestamp = payload.get("timestamp", timestamp)
                cwd = payload.get("cwd", cwd)
            elif record_type == "event_msg" and payload.get("type") == "user_message":
                message = clean_message(payload.get("message", ""))
                if message:
                    user_messages.append(message)

    project = Path(cwd).name if cwd else "Unknown Project"
    preview = user_messages[-1] if user_messages else ""
    title = choose_title(user_messages, project)
    return SessionItem(
        session_id=session_id,
        timestamp=timestamp,
        cwd=cwd,
        project=project,
        title=title,
        source_file=str(path),
        first_user_message=user_messages[0] if user_messages else "",
        recent_user_message=preview,
        user_count=len(user_messages),
        has_redacted_preview=(preview == "[redacted sensitive text]"),
    )


def match_project(item: SessionItem, query: str) -> bool:
    if not query:
        return True
    lowered = query.casefold()
    return lowered in item.cwd.casefold()


def main() -> int:
    args = parse_args()
    session_root = Path(args.session_root).expanduser().resolve()
    items = [
        parse_session(path)
        for path in discover_latest_sessions(session_root, max(args.latest * 3, args.latest))
    ]
    items = [item for item in items if match_project(item, args.project)][: args.latest]

    if args.selector_json:
        print(
            json.dumps(
                {
                    "items": [
                        {
                            "label": item.title,
                            "description": (
                                f"{human_time_label(item.timestamp)} · {item.project}"
                                + (
                                    " · latest hidden for privacy"
                                    if item.has_redacted_preview
                                    else (
                                        f" · {item.recent_user_message}"
                                        if item.recent_user_message and item.recent_user_message != item.title
                                        else ""
                                    )
                                )
                            ),
                            "value": item.session_id,
                            "group": item.project,
                            "session_id": item.session_id,
                            "project": item.project,
                            "timestamp": item.timestamp,
                            "source_file": item.source_file,
                            "cwd": item.cwd,
                            "title": item.title,
                            "recent_user_message": item.recent_user_message,
                            "has_redacted_preview": item.has_redacted_preview,
                        }
                        for item in items
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "session_id": item.session_id,
                        "timestamp": item.timestamp,
                        "project": item.project,
                        "cwd": item.cwd,
                        "source_file": item.source_file,
                        "recent_user_message": item.recent_user_message,
                        "user_count": item.user_count,
                        "title": item.title,
                        "has_redacted_preview": item.has_redacted_preview,
                    }
                    for item in items
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for index, item in enumerate(items, start=1):
        print(f"[{index}] {item.title}")
        print(f"    time: {human_time_label(item.timestamp)}")
        print(f"    project: {item.project}")
        if item.recent_user_message and item.recent_user_message != item.title:
            label = "latest message"
            if item.has_redacted_preview:
                print(f"    {label}: hidden for privacy")
            else:
                print(f"    {label}: {item.recent_user_message}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
