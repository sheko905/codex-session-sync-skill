#!/usr/bin/env python3
"""Export selected Codex sessions into a local zip bundle."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a local Codex session export bundle.")
    parser.add_argument("--out-dir", required=True, help="Directory where the zip bundle should be written")
    parser.add_argument(
        "--sync-script",
        default=str(Path(__file__).with_name("sync_codex_sessions.py")),
        help="Path to sync_codex_sessions.py",
    )
    parser.add_argument("--mode", default="continuation", choices=["summary", "continuation", "archive"])
    parser.add_argument("--session", action="append", default=[])
    parser.add_argument("--project", default="")
    parser.add_argument("--latest", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_root = out_dir / f"codex-session-export-{timestamp}"
    bundle_root.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3",
        args.sync_script,
        "--repo",
        str(bundle_root),
        "--mode",
        args.mode,
        "--latest",
        str(args.latest),
        "--no-commit",
    ]
    for session in args.session:
        cmd.extend(["--session", session])
    if args.project:
        cmd.extend(["--project", args.project])

    subprocess.run(cmd, check=True)
    archive_path = shutil.make_archive(str(bundle_root), "zip", root_dir=bundle_root)
    print("本地导出已完成")
    print(f"bundle: {archive_path}")
    print(f"folder: {bundle_root}")
    print("下一步: 你可以直接发送这个 zip 包，或在另一台设备用本地导入功能恢复。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
