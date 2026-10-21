#!/usr/bin/env python3
"""Create or verify a byte-preserving inventory of study data (standard library only)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "DATA_MANIFEST.csv"
FIELDS = ("path", "category", "size_bytes", "sha256")


def data_paths() -> list[Path]:
    paths = [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.relative_to(ROOT).parts
        and path.suffix.lower() == ".csv"
        and path != MANIFEST
    ]
    if (ROOT / "magictap.txt").is_file():
        paths.append(ROOT / "magictap.txt")
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def inventory() -> list[dict[str, str]]:
    rows = []
    for path in data_paths():
        relative = path.relative_to(ROOT)
        first = relative.parts[0]
        category = (
            "raw" if first.isdecimal()
            else "legacy" if first == "旧版"
            else "analysis_output" if first == "analysis_outputs"
            else "supporting_record"
        )
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        rows.append({
            "path": relative.as_posix(),
            "category": category,
            "size_bytes": str(path.stat().st_size),
            "sha256": digest.hexdigest(),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate the manifest after intentional data changes")
    args = parser.parse_args()
    actual = inventory()
    if args.write:
        with MANIFEST.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(actual)
        print(f"Wrote {len(actual)} records to {MANIFEST.name}")
    else:
        if not MANIFEST.is_file():
            print(f"Missing {MANIFEST.name}", file=sys.stderr)
            return 1
        with MANIFEST.open(encoding="utf-8", newline="") as source:
            expected = list(csv.DictReader(source))
        by_path = {row["path"]: row for row in actual}
        expected_paths = {row["path"] for row in expected}
        errors = []
        if len(expected_paths) != len(expected):
            errors.append("Duplicate paths in manifest")
        for row in expected:
            found = by_path.get(row["path"])
            if found is None:
                errors.append(f"Missing: {row['path']}")
            elif found != row:
                errors.append(f"Changed: {row['path']}")
        for path in sorted(set(by_path) - expected_paths):
            errors.append(f"Not inventoried: {path}")
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print(f"Verified all {len(actual)} records: paths, byte counts and SHA-256 match.")
    counts = Counter(row["category"] for row in actual)
    print(", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
