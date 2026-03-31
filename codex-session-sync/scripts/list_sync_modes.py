#!/usr/bin/env python3
"""Expose user-facing sync modes for selectors or chat fallbacks."""

from __future__ import annotations

import argparse
import json


MODES = [
    {
        "label": "快速发送",
        "description": "最轻量，适合低风险备份或快速分享。",
        "value": "summary",
    },
    {
        "label": "继续工作（推荐）",
        "description": "最适合换设备继续工作，会保留更强的续写上下文。",
        "value": "continuation",
    },
    {
        "label": "完整迁移",
        "description": "最完整，可尝试恢复到本地会话，但隐私风险更高。",
        "value": "archive",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List user-facing Codex sync modes.")
    parser.add_argument("--selector-json", action="store_true", help="Emit selector-friendly JSON")
    parser.add_argument("--json", action="store_true", help="Emit plain JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.selector_json:
        print(json.dumps({"items": MODES}, ensure_ascii=False, indent=2))
        return 0
    if args.json:
        print(json.dumps(MODES, ensure_ascii=False, indent=2))
        return 0

    for index, mode in enumerate(MODES, start=1):
        print(f"[{index}] {mode['label']}")
        print(f"    {mode['description']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
