#!/usr/bin/env python3
"""Export Codex desktop sessions into a Git repo for cross-device continuity."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_SESSION_ROOT = Path.home() / ".codex" / "sessions"
SYNC_MODES = {
    "summary": {
        "write_summary": True,
        "write_context": False,
        "write_raw": False,
    },
    "continuation": {
        "write_summary": True,
        "write_context": True,
        "write_raw": False,
    },
    "archive": {
        "write_summary": True,
        "write_context": True,
        "write_raw": True,
    },
}
MODE_LABELS = {
    "summary": "快速发送",
    "continuation": "继续工作（推荐）",
    "archive": "完整迁移",
}
SECRET_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\b(?:access_token|refresh_token|id_token|api[_-]?key|bearer)\b", re.I),
    re.compile(r"\b[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
]


@dataclass
class SessionSummary:
    session_id: str
    source_file: Path
    timestamp: str
    cwd: str = ""
    source: str = ""
    originator: str = ""
    model_provider: str = ""
    cli_version: str = ""
    user_messages: list[str] = field(default_factory=list)
    assistant_finals: list[str] = field(default_factory=list)
    assistant_messages: list[str] = field(default_factory=list)
    tool_events: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync local Codex sessions into a Git repository."
    )
    parser.add_argument("--repo", required=True, help="Path to the target Git repository")
    parser.add_argument(
        "--session",
        action="append",
        default=[],
        help="Specific session JSONL file to export. Repeat to include more than one.",
    )
    parser.add_argument(
        "--session-root",
        default=str(DEFAULT_SESSION_ROOT),
        help="Root directory for local Codex sessions",
    )
    parser.add_argument(
        "--latest",
        type=int,
        default=1,
        help="Export the latest N sessions when --session is not supplied",
    )
    parser.add_argument(
        "--project",
        default="",
        help="Only export sessions whose cwd contains this text",
    )
    parser.add_argument(
        "--mode",
        choices=sorted(SYNC_MODES.keys()),
        default="continuation",
        help="Sync mode: summary, continuation, or archive",
    )
    parser.add_argument(
        "--copy-raw",
        action="store_true",
        help="Legacy flag. Equivalent to --mode archive",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push after committing",
    )
    parser.add_argument(
        "--message",
        default="",
        help="Custom git commit message",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Export files without creating a git commit",
    )
    return parser.parse_args()


def discover_latest_sessions(session_root: Path, limit: int) -> list[Path]:
    session_files = sorted(
        session_root.rglob("*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return session_files[:limit]


def clean_message(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if stripped.startswith("<environment_context>"):
        return ""
    if any(pattern.search(stripped) for pattern in SECRET_PATTERNS):
        return "[redacted sensitive text]"
    return stripped


def short_tool_label(payload: dict) -> str:
    payload_type = payload.get("type", "")
    if payload_type.endswith("_call"):
        action = payload.get("action", {})
        action_type = action.get("type")
        if isinstance(action_type, str) and action_type:
            return f"{payload_type}:{action_type}"
        return payload_type
    return ""


def parse_session_file(path: Path) -> SessionSummary:
    summary = SessionSummary(
        session_id=path.stem,
        source_file=path,
        timestamp=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
    )

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
                meta = payload
                summary.session_id = meta.get("id", summary.session_id)
                summary.timestamp = meta.get("timestamp", summary.timestamp)
                summary.cwd = meta.get("cwd", "")
                summary.source = meta.get("source", "")
                summary.originator = meta.get("originator", "")
                summary.model_provider = meta.get("model_provider", "")
                summary.cli_version = meta.get("cli_version", "")
                continue

            if record_type == "event_msg" and payload.get("type") == "user_message":
                message = clean_message(payload.get("message", ""))
                if message:
                    summary.user_messages.append(message)
                continue

            if record_type == "response_item" and payload.get("type") == "message":
                parts = payload.get("content", [])
                texts = [
                    part.get("text", "").strip()
                    for part in parts
                    if part.get("type") == "output_text" and part.get("text", "").strip()
                ]
                if payload.get("role") == "assistant" and texts:
                    joined = "\n".join(texts)
                    summary.assistant_messages.append(joined)
                    if payload.get("phase") == "final":
                        summary.assistant_finals.append(joined)
                continue

            if record_type == "response_item":
                label = short_tool_label(payload)
                if label:
                    summary.tool_events.append(label)

    return summary


def match_project(summary: SessionSummary, query: str) -> bool:
    if not query:
        return True
    lowered = query.casefold()
    return lowered in summary.cwd.casefold()


def format_bullets(items: Iterable[str]) -> str:
    values = [item.strip() for item in items if item and item.strip()]
    if not values:
        return "- None captured\n"
    return "".join(f"- {item.replace(chr(10), chr(10) + '  ')}\n" for item in values)


def build_markdown(summary: SessionSummary) -> str:
    tool_lines = sorted(set(summary.tool_events))
    first_user_message = summary.user_messages[0] if summary.user_messages else "unknown"
    return f"""# Codex Session Summary

- Session ID: `{summary.session_id}`
- Conversation Title: `{first_user_message}`
- First User Message: `{first_user_message}`
- Timestamp: `{summary.timestamp}`
- Source File: `{summary.source_file}`
- Working Directory: `{summary.cwd or "unknown"}`
- Originator: `{summary.originator or "unknown"}`
- Source: `{summary.source or "unknown"}`
- Model Provider: `{summary.model_provider or "unknown"}`
- CLI Version: `{summary.cli_version or "unknown"}`

## Recent User Requests

{format_bullets(summary.user_messages)}

## Assistant Final Answers

{format_bullets(summary.assistant_finals)}

## Notable Tool Events

{format_bullets(tool_lines)}
"""


def build_context_bundle(summary: SessionSummary) -> dict:
    return {
        "session_id": summary.session_id,
        "timestamp": summary.timestamp,
        "cwd": summary.cwd,
        "originator": summary.originator,
        "source": summary.source,
        "model_provider": summary.model_provider,
        "cli_version": summary.cli_version,
        "continuation_title": summary.user_messages[0] if summary.user_messages else summary.session_id,
        "continuation_goal": summary.user_messages[0] if summary.user_messages else "",
        "recent_user_messages": summary.user_messages[-5:],
        "recent_assistant_messages": summary.assistant_messages[-5:],
        "final_answers": summary.assistant_finals[-3:],
        "tool_events": sorted(set(summary.tool_events)),
    }


def build_artifact_manifest(summary: SessionSummary, mode: str) -> dict:
    return {
        "schema_version": 1,
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "session_id": summary.session_id,
        "timestamp": summary.timestamp,
        "cwd": summary.cwd,
        "conversation_title": summary.user_messages[0] if summary.user_messages else summary.session_id,
        "first_user_message": summary.user_messages[0] if summary.user_messages else "",
        "last_user_message": summary.user_messages[-1] if summary.user_messages else "",
        "project_name": Path(summary.cwd).name if summary.cwd else "",
    }


def normalize_mode(args: argparse.Namespace) -> str:
    if args.copy_raw:
        return "archive"
    return args.mode


def slug_date(timestamp: str) -> tuple[str, str, str]:
    normalized = timestamp.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    return dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")


def ensure_git_repo(repo: Path) -> None:
    if (repo / ".git").exists():
        return
    subprocess.run(["git", "init"], cwd=repo, check=True)


def git_has_changes(repo: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def git_identity_ready(repo: Path) -> bool:
    name = subprocess.run(
        ["git", "config", "user.name"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    email = subprocess.run(
        ["git", "config", "user.email"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    return bool(name.stdout.strip() and email.stdout.strip())


def export_session(summary: SessionSummary, repo: Path, mode: str) -> Path:
    year, month, day = slug_date(summary.timestamp)
    target_dir = repo / "sessions" / year / month / day / summary.session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    config = SYNC_MODES[mode]

    summary_path = target_dir / "summary.md"
    manifest_path = target_dir / "artifact.json"
    if config["write_summary"]:
        summary_path.write_text(build_markdown(summary), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(build_artifact_manifest(summary, mode), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if config["write_context"]:
        context_path = target_dir / "context.json"
        context_path.write_text(
            json.dumps(build_context_bundle(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if config["write_raw"]:
        shutil.copy2(summary.source_file, target_dir / "raw.jsonl")

    if config["write_summary"]:
        latest_path = repo / "latest.md"
        latest_path.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
    return summary_path


def commit_and_optionally_push(
    repo: Path,
    exported_ids: list[str],
    custom_message: str,
    push: bool,
    no_commit: bool,
) -> None:
    if no_commit:
        return

    if not git_identity_ready(repo):
        print(
            "[WARN] Git user.name/user.email are not configured in the target repo. "
            "Files were exported, but no commit was created."
        )
        return

    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    if not git_has_changes(repo):
        return

    message = custom_message.strip() or f"Sync Codex sessions: {', '.join(exported_ids)}"
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True)
    if push:
        subprocess.run(["git", "push"], cwd=repo, check=True)


def resolve_session_paths(args: argparse.Namespace) -> list[Path]:
    if args.session:
        return [Path(item).expanduser().resolve() for item in args.session]

    session_root = Path(args.session_root).expanduser().resolve()
    if not session_root.exists():
        raise FileNotFoundError(f"Session root not found: {session_root}")

    session_files = discover_latest_sessions(session_root, max(args.latest * 5, args.latest))
    if not session_files:
        raise FileNotFoundError(f"No session files found under: {session_root}")

    if not args.project:
        return session_files[: args.latest]

    matched: list[Path] = []
    for path in session_files:
        summary = parse_session_file(path)
        if match_project(summary, args.project):
            matched.append(path)
        if len(matched) >= args.latest:
            break

    if not matched:
        raise FileNotFoundError(
            f"No session files matched project filter '{args.project}' under: {session_root}"
        )
    return matched


def main() -> int:
    args = parse_args()
    mode = normalize_mode(args)
    repo = Path(args.repo).expanduser().resolve()
    repo.mkdir(parents=True, exist_ok=True)
    ensure_git_repo(repo)

    session_paths = resolve_session_paths(args)
    summaries = [parse_session_file(path) for path in session_paths]

    exported_paths = []
    for summary in summaries:
        exported_paths.append(export_session(summary, repo, mode))

    commit_and_optionally_push(
        repo=repo,
        exported_ids=[summary.session_id for summary in summaries],
        custom_message=args.message,
        push=args.push,
        no_commit=args.no_commit,
    )

    print(f"导出模式: {MODE_LABELS[mode]}")
    print("已导出:")
    for path in exported_paths:
        print(path)
    if mode == "summary":
        print("下一步: 这份内容适合当作摘要参考或轻量备份。")
    elif mode == "continuation":
        print("下一步: 这份内容适合在另一台设备作为续写上下文继续工作。")
    else:
        print("下一步: 这份内容既可续写，也可在另一台设备合并回本地会话。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] Command failed: {exc}", file=sys.stderr)
        raise SystemExit(exc.returncode)
    except Exception as exc:  # pragma: no cover
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
