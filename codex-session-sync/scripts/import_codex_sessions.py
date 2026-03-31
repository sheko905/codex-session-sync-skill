#!/usr/bin/env python3
"""Import synced Codex session artifacts from a repo back onto a machine."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

MODE_LABELS = {
    "summary": "已恢复为摘要参考",
    "continuation": "已恢复为续写上下文",
    "archive": "已恢复为本地会话并保留续写上下文",
}
MATCH_LABELS = {
    "exact_session_id": "已精确匹配到本地同一会话",
    "title_project_time": "已匹配到本地相近对话",
    "none": "未找到可安全自动合并的本地对话",
}


@dataclass
class LocalSessionCandidate:
    session_id: str
    path: Path
    timestamp: str
    cwd: str
    first_user_message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import synced Codex session artifacts.")
    parser.add_argument("--repo", required=True, help="Path to the synced session repository")
    parser.add_argument(
        "--session-id",
        action="append",
        default=[],
        help="Only import the given session id. Repeat for more.",
    )
    parser.add_argument(
        "--target-session-root",
        default=str(Path.home() / ".codex" / "sessions"),
        help="Where raw imported sessions should be merged",
    )
    parser.add_argument(
        "--target-context-root",
        default=str(Path.home() / ".codex" / "imported-session-context"),
        help="Where continuation bundles should be restored",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable results",
    )
    return parser.parse_args()


def find_session_dirs(repo: Path) -> list[Path]:
    return sorted(path for path in repo.glob("sessions/*/*/*/*") if path.is_dir())


def matches_session(path: Path, session_ids: list[str]) -> bool:
    if not session_ids:
        return True
    return path.name in session_ids


def extract_first_user_message(summary_file: Path) -> str:
    if not summary_file.exists():
        return ""
    for line in summary_file.read_text(encoding="utf-8").splitlines():
        prefix = "- First User Message: `"
        if line.startswith(prefix) and line.endswith("`"):
            return line[len(prefix) : -1]
    return ""


def read_artifact_manifest(session_dir: Path) -> dict:
    artifact_file = session_dir / "artifact.json"
    if not artifact_file.exists():
        return {}
    return json.loads(artifact_file.read_text(encoding="utf-8"))


def parse_local_session(path: Path) -> LocalSessionCandidate | None:
    session_id = path.stem
    timestamp = ""
    cwd = ""
    first_user_message = ""
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
                message = payload.get("message", "").strip()
                if message and not message.startswith("<environment_context>"):
                    first_user_message = message
                    break
    if not timestamp:
        return None
    return LocalSessionCandidate(
        session_id=session_id,
        path=path,
        timestamp=timestamp,
        cwd=cwd,
        first_user_message=first_user_message,
    )


def normalize_iso(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def find_local_match(
    session_root: Path,
    session_id: str,
    first_user_message: str,
    cwd: str,
    timestamp: str,
) -> tuple[str, LocalSessionCandidate | None]:
    candidates = sorted(session_root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:200]
    parsed = [item for item in (parse_local_session(path) for path in candidates) if item]

    for item in parsed:
        if item.session_id == session_id:
            return "exact_session_id", item

    imported_time = normalize_iso(timestamp)
    if not imported_time:
        return "none", None

    scored: list[tuple[timedelta, LocalSessionCandidate]] = []
    for item in parsed:
        if not item.first_user_message or not first_user_message:
            continue
        if item.first_user_message != first_user_message:
            continue
        if cwd and item.cwd and item.cwd != cwd:
            continue
        local_time = normalize_iso(item.timestamp)
        if not local_time:
            continue
        delta = abs(imported_time - local_time)
        if delta <= timedelta(days=7):
            scored.append((delta, item))

    if scored:
        scored.sort(key=lambda pair: pair[0])
        return "title_project_time", scored[0][1]
    return "none", None


def import_one(session_dir: Path, session_root: Path, context_root: Path) -> dict:
    session_id = session_dir.name
    raw_file = session_dir / "raw.jsonl"
    context_file = session_dir / "context.json"
    summary_file = session_dir / "summary.md"
    manifest = read_artifact_manifest(session_dir)
    conversation_title = manifest.get("conversation_title") or extract_first_user_message(summary_file)
    first_user_message = manifest.get("first_user_message") or conversation_title
    cwd = manifest.get("cwd", "")
    timestamp = manifest.get("timestamp", "")
    match_type, matched_local = find_local_match(
        session_root=session_root,
        session_id=session_id,
        first_user_message=first_user_message,
        cwd=cwd,
        timestamp=timestamp,
    )

    result = {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "merged_raw": False,
        "restored_context": False,
        "restored_summary": False,
        "detected_mode": "summary",
        "conversation_title": conversation_title,
        "merge_match_type": match_type,
        "matched_local_session_id": matched_local.session_id if matched_local else "",
        "notes": [],
    }

    result["notes"].append(MATCH_LABELS[match_type])

    if raw_file.exists():
        result["detected_mode"] = "archive"
        if match_type == "exact_session_id" and matched_local:
            result["merged_raw"] = True
            result["raw_target"] = str(matched_local.path)
            result["notes"].append("identical session already exists locally, raw merge skipped as duplicate")
        else:
            year = session_dir.parents[2].name
            month = session_dir.parents[1].name
            day = session_dir.parents[0].name
            target_dir = session_root / year / month / day
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / f"imported-{session_id}.jsonl"
            shutil.copy2(raw_file, target_file)
            result["merged_raw"] = True
            result["raw_target"] = str(target_file)
            result["notes"].append("raw session merged into local Codex session root")
    else:
        result["notes"].append("raw session file missing, native merge skipped")

    if context_file.exists() or summary_file.exists():
        target_dir = context_root / session_id
        target_dir.mkdir(parents=True, exist_ok=True)
        if context_file.exists():
            shutil.copy2(context_file, target_dir / "context.json")
            if result["detected_mode"] != "archive":
                result["detected_mode"] = "continuation"
        if summary_file.exists():
            shutil.copy2(summary_file, target_dir / "summary.md")
            result["restored_summary"] = True
        result["restored_context"] = True
        result["context_target"] = str(target_dir)
        if context_file.exists():
            result["notes"].append("continuation bundle restored for resume")
        else:
            result["notes"].append("summary restored, but richer continuation context was not included")

    return result


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).expanduser().resolve()
    session_root = Path(args.target_session_root).expanduser().resolve()
    context_root = Path(args.target_context_root).expanduser().resolve()

    results = [
        import_one(path, session_root, context_root)
        for path in find_session_dirs(repo)
        if matches_session(path, args.session_id)
    ]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    for item in results:
        print(item["session_id"])
        if item.get("conversation_title"):
            print(f"  - title: {item['conversation_title']}")
        print(f"  - {MODE_LABELS.get(item['detected_mode'], '已恢复')}")
        for note in item["notes"]:
            print(f"  - {note}")
        if "raw_target" in item:
            print(f"  - raw target: {item['raw_target']}")
        if item.get("matched_local_session_id"):
            print(f"  - matched local session: {item['matched_local_session_id']}")
        if "context_target" in item:
            print(f"  - context target: {item['context_target']}")
            if item["detected_mode"] != "archive":
                print("  - next step: open this context folder and continue from summary.md plus context.json")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
