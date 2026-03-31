#!/usr/bin/env python3
"""Expose export destination choices for selectors or chat fallbacks."""

from __future__ import annotations

import argparse
import json


ITEMS = [
    {
        "label": "上传到 GitHub",
        "description": "适合跨设备同步。需要仓库信息，后续可直接拉取导入。",
        "value": "github",
    },
    {
        "label": "导出为本地文件",
        "description": "把当前会话打包到本机，适合手动发送或自己留档。",
        "value": "local_bundle",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List export destinations.")
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
