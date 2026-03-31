#!/usr/bin/env python3
"""Import a local Codex session zip bundle."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import zipfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a local Codex session bundle.")
    parser.add_argument("--bundle", required=True, help="Path to the exported zip bundle")
    parser.add_argument(
        "--import-script",
        default=str(Path(__file__).with_name("import_codex_sessions.py")),
        help="Path to import_codex_sessions.py",
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = Path(args.bundle).expanduser().resolve()
    if not bundle.exists():
        raise SystemExit(f"Bundle not found: {bundle}")

    with tempfile.TemporaryDirectory(prefix="codex-session-import-") as temp_dir:
        temp_path = Path(temp_dir)
        with zipfile.ZipFile(bundle, "r") as archive:
            archive.extractall(temp_path)
        subprocess.run(
            [
                "python3",
                args.import_script,
                "--repo",
                str(temp_path),
                "--target-session-root",
                args.target_session_root,
                "--target-context-root",
                args.target_context_root,
            ],
            check=True,
        )
    print(f"已从本地文件恢复: {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
