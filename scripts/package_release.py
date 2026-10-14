#!/usr/bin/env python3
"""Build a local ZIP delivery without credentials, Git internals or environments.

Including the original source/data is an explicit choice. Review the separate
licenses before PUBLIC redistribution; this command does not publish anything.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".snakemake",
    ".cache",
    "node_modules",
    "build",
    "dist",
    ".ipynb_checkpoints",
}
EXCLUDE_NAMES = {
    ".env",
    ".cdsapirc",
    "secrets.toml",
    ".netrc",
    ".git-credentials",
    "RELEASE_MANIFEST.json",
}


def include(path: Path, args):
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIRS or part.endswith(".egg-info") for part in relative.parts):
        return False
    if path.name in EXCLUDE_NAMES or path.suffix in {".pyc", ".log", ".zip"}:
        return False
    if relative.parts[:2] == ("external", "colombiacongestionV2") and not args.include_source:
        return False
    if not args.include_example_data and (
        relative.parts[0] in {"resources", "results"}
        or relative.parts[:2] in {("data", "raw"), ("data", "processed")}
    ):
        return False
    if (
        relative.parts[:2] == ("data", "user")
        and path.name != "README.md"
        and not path.name.endswith(".example.csv")
    ):
        return False
    if relative.parts[0] == "cutouts" and path.suffix == ".nc":
        return False
    return path.is_file() and not path.is_symlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-source", action="store_true")
    parser.add_argument("--include-example-data", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT.parent / "pypsa-col-v0.1.0.zip")
    args = parser.parse_args()
    files = []
    for folder, directories, names in os.walk(ROOT):
        directories[:] = sorted(
            d for d in directories if d not in EXCLUDE_DIRS and not d.endswith(".egg-info")
        )
        for name in names:
            path = Path(folder) / name
            if include(path, args):
                files.append(path)
    files.sort()
    try:
        code_commit = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        code_commit = None
    manifest = {
        "version": "0.1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_code_commit": code_commit,
        "remote_publication": False,
        "source_included": args.include_source,
        "example_data_included": args.include_example_data,
        "rights_notice": "New code MIT; original source and all datasets retain separate terms. See THIRD_PARTY_NOTICES.md.",
        "files": [
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in files
        ],
    }
    manifest_path = ROOT / "RELEASE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for path in [*files, manifest_path]:
            archive.write(path, arcname=str(Path("pypsa-col") / path.relative_to(ROOT)))
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(".zip.sha256").write_text(f"{digest}  {args.output.name}\n")
    print(
        f"Created {args.output}: {len(files) + 1} files, {args.output.stat().st_size / 1024**2:.2f} MiB"
    )
    print(f"SHA-256 {digest}")


if __name__ == "__main__":
    main()
