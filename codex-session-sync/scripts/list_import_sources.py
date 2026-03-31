#!/usr/bin/env python3
"""Expose import source choices for selectors or chat fallbacks."""

from __future__ import annotations

import argparse
import json


ITEMS = [
    {
        "label": "从 GitHub 导入",
        "description": "从同步仓库拉取会话，再恢复到本机。",
        "value": "github",
    },
    {
        "label": "从本地文件导入",
        "description": "从之前导出的 zip 包或目录恢复。",
        "value": "local_bundle",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List import sources.")
    parser.add_argument("--selector-json", action="store_true", help="Emit selector-friendly JSON")
    parser.add_argument("--json", action="store_true", help="Emit plain JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.selector_json:
        print(json.dumps({"items": ITEMS}, ensure_ascii=False, indent=2))
        return 0
    if args.json:
        print(json.dumps(ITEMS, ensure_ascii=False, indent=2))
        return 0
    for index, item in enumerate(ITEMS, start=1):
        print(f"[{index}] {item['label']}")
        print(f"    {item['description']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
