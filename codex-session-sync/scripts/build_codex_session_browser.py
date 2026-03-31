#!/usr/bin/env python3
"""Generate a static HTML browser for local Codex sessions."""

from __future__ import annotations

import argparse
import html
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
class SessionCard:
    session_id: str
    timestamp: str
    cwd: str
    project_label: str
    source_file: str
    user_count: int
    assistant_final_count: int
    tool_labels: list[str]
    recent_user_messages: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a static Codex session browser.")
    parser.add_argument(
        "--session-root",
        default=str(DEFAULT_SESSION_ROOT),
        help="Root directory for local Codex sessions",
    )
    parser.add_argument("--out", required=True, help="Output HTML file path")
    parser.add_argument(
        "--latest",
        type=int,
        default=30,
        help="Include the latest N sessions",
    )
    return parser.parse_args()


def clean_message(text: str) -> str:
    value = text.strip()
    if not value or value.startswith("<environment_context>"):
        return ""
    if any(pattern.search(value) for pattern in SECRET_PATTERNS):
        return "[redacted sensitive text]"
    return value


def short_tool_label(payload: dict) -> str:
    payload_type = payload.get("type", "")
    if payload_type.endswith("_call"):
        action = payload.get("action", {})
        action_type = action.get("type")
        if isinstance(action_type, str) and action_type:
            return f"{payload_type}:{action_type}"
        return payload_type
    return ""


def project_label_from_cwd(cwd: str) -> str:
    if not cwd:
        return "Unknown Project"
    return Path(cwd).name or cwd


def discover_latest_sessions(session_root: Path, limit: int) -> list[Path]:
    return sorted(
        session_root.rglob("*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]


def parse_session(path: Path) -> SessionCard:
    session_id = path.stem
    timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    cwd = ""
    user_messages: list[str] = []
    assistant_final_count = 0
    tool_labels: set[str] = set()

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
            elif record_type == "response_item" and payload.get("type") == "message":
                if payload.get("role") == "assistant" and payload.get("phase") == "final":
                    assistant_final_count += 1
            elif record_type == "response_item":
                label = short_tool_label(payload)
                if label:
                    tool_labels.add(label)

    return SessionCard(
        session_id=session_id,
        timestamp=timestamp,
        cwd=cwd,
        project_label=project_label_from_cwd(cwd),
        source_file=str(path),
        user_count=len(user_messages),
        assistant_final_count=assistant_final_count,
        tool_labels=sorted(tool_labels),
        recent_user_messages=user_messages[-3:],
    )


def iso_to_localish(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).strftime("%Y-%m-%d %H:%M")


def render_cards(cards: list[SessionCard]) -> str:
    rendered = []
    for card in cards:
        recent = "".join(
            f"<li>{html.escape(message)}</li>" for message in card.recent_user_messages
        ) or "<li>No recent user message preview</li>"
        tools = ", ".join(card.tool_labels) if card.tool_labels else "No tool traces"
        sync_command = (
            "python3 skills/codex-session-sync/scripts/sync_codex_sessions.py "
            f"--repo /path/to/private-repo --session {html.escape(card.source_file)}"
        )
        rendered.append(
            f"""
            <article class="card" data-project="{html.escape(card.project_label.lower())}">
              <div class="card-top">
                <div>
                  <p class="eyebrow">{html.escape(iso_to_localish(card.timestamp))}</p>
                  <h2>{html.escape(card.project_label)}</h2>
                </div>
                <span class="pill">{html.escape(card.session_id[:8])}</span>
              </div>
              <p class="path">{html.escape(card.cwd or 'Unknown working directory')}</p>
              <div class="stats">
                <span>{card.user_count} user messages</span>
                <span>{card.assistant_final_count} final answers</span>
              </div>
              <p class="tools">{html.escape(tools)}</p>
              <h3>Recent prompts</h3>
              <ul>{recent}</ul>
              <details>
                <summary>How to sync this session</summary>
                <p>Use summary-only first unless you need the raw archive.</p>
                <pre>{sync_command}</pre>
                <p class="path">Source file: {html.escape(card.source_file)}</p>
              </details>
            </article>
            """
        )
    return "\n".join(rendered)


def build_html(cards: list[SessionCard]) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex Session Browser</title>
  <style>
    :root {{
      --bg: #f6f2e8;
      --panel: rgba(255,255,255,0.8);
      --ink: #18230f;
      --muted: #5a6750;
      --accent: #2f6f4f;
      --line: rgba(24,35,15,0.12);
      --shadow: 0 18px 40px rgba(24,35,15,0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-rounded, "SF Pro Rounded", "Hiragino Sans GB", "PingFang SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(47,111,79,0.16), transparent 26rem),
        linear-gradient(180deg, #fbf8f0 0%, var(--bg) 100%);
    }}
    .shell {{
      max-width: 1160px;
      margin: 0 auto;
      padding: 32px 20px 60px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(255,255,255,0.82), rgba(241,232,211,0.92));
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 28px;
      margin-bottom: 22px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(32px, 5vw, 56px);
      line-height: 0.95;
      letter-spacing: -0.04em;
    }}
    .sub {{
      margin: 0;
      max-width: 58rem;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.5;
    }}
    .controls {{
      margin-top: 18px;
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }}
    input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px 16px;
      font-size: 15px;
      background: rgba(255,255,255,0.92);
    }}
    .hint {{
      color: var(--muted);
      font-size: 13px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 18px;
    }}
    .card {{
      background: var(--panel);
      backdrop-filter: blur(10px);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 20px;
    }}
    .card-top {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }}
    .eyebrow {{
      margin: 0 0 6px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }}
    h2 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.05;
    }}
    .pill {{
      border: 1px solid rgba(47,111,79,0.18);
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(47,111,79,0.08);
      color: var(--accent);
      font-size: 12px;
      white-space: nowrap;
    }}
    .path, .tools {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
      word-break: break-word;
    }}
    .stats {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin: 14px 0;
    }}
    .stats span {{
      border-radius: 999px;
      padding: 7px 10px;
      background: rgba(24,35,15,0.05);
      font-size: 13px;
    }}
    h3 {{
      margin: 18px 0 8px;
      font-size: 15px;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
      color: var(--ink);
    }}
    details {{
      margin-top: 16px;
      border-top: 1px solid var(--line);
      padding-top: 14px;
    }}
    summary {{
      cursor: pointer;
      color: var(--accent);
      font-weight: 600;
    }}
    pre {{
      margin: 12px 0;
      padding: 14px;
      overflow: auto;
      border-radius: 16px;
      background: #18230f;
      color: #f7f4ea;
      font-size: 13px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .footer {{
      margin-top: 20px;
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 640px) {{
      .shell {{ padding: 20px 14px 42px; }}
      .hero {{ padding: 20px; border-radius: 22px; }}
      .card {{ border-radius: 20px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>Codex Session Browser</h1>
      <p class="sub">A visual index of recent local Codex sessions. Filter by project name, skim the latest prompts, then copy the sync command for the one you want to carry to another device.</p>
      <div class="controls">
        <input id="projectFilter" type="text" placeholder="Filter by project name, for example AI 小工具">
        <p class="hint">Generated at {html.escape(generated_at)}. Summary-only sync is the safest default.</p>
      </div>
    </section>
    <section class="grid" id="cardGrid">
      {render_cards(cards)}
    </section>
    <p class="footer">Tip: keep code changes in your normal project repo, and use this browser for session continuity notes.</p>
  </main>
  <script>
    const filter = document.getElementById('projectFilter');
    const cards = Array.from(document.querySelectorAll('.card'));
    filter.addEventListener('input', () => {{
      const query = filter.value.trim().toLowerCase();
      cards.forEach(card => {{
        const project = card.dataset.project || '';
        card.style.display = !query || project.includes(query) ? '' : 'none';
      }});
    }});
  </script>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    session_root = Path(args.session_root).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cards = [parse_session(path) for path in discover_latest_sessions(session_root, args.latest)]
    out_path.write_text(build_html(cards), encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
