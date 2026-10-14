#!/usr/bin/env python3
"""Clone the user's exact source revision, or verify the supplied source snapshot.

No unpinned `git pull`, no automatic overwrite, and no app.py execution.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((ROOT / "config/sources.lock.json").read_text())["colombiacongestionV2"]
    source = ROOT / "external/colombiacongestionV2"
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", str(source)], check=True)
        subprocess.run(
            ["git", "-C", str(source), "remote", "add", "origin", lock["url"]], check=True
        )
        subprocess.run(
            ["git", "-C", str(source), "fetch", "--depth", "1", "origin", lock["commit"]],
            check=True,
        )
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", "FETCH_HEAD"], check=True)
    for relative, expected in lock["files"].items():
        path = source / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(
                f"Source verification failed for {relative}. Refusing to overwrite changes. "
                "Move aside the source folder and rerun, or explicitly review a new pin."
            )
    print(f"Verified {len(lock['files'])} source files at {lock['commit']}")


if __name__ == "__main__":
    main()
