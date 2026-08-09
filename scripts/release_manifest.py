#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) in sys.path:
    sys.path.remove(str(SRC))
sys.path.insert(0, str(SRC))

from maestro import __version__
from maestro.release import (
    build_release_manifest,
    load_source_release_manifest,
    release_manifest_path,
)
from maestro.util import atomic_write, canonical_json, pretty_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify the content-addressed release manifest."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--write", action="store_true")
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--tag-ref")
    args = parser.parse_args(argv)

    source_root = args.source_root.expanduser().resolve()
    expected = build_release_manifest(source_root)
    path = release_manifest_path(source_root)
    if args.tag_ref is not None and args.tag_ref != f"v{__version__}":
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": (
                        f"tag {args.tag_ref!r} does not match "
                        f"framework version v{__version__}"
                    ),
                },
                sort_keys=True,
            )
        )
        return 1

    if args.write:
        atomic_write(path, pretty_json(expected).encode("utf-8"))
        print(
            json.dumps(
                {
                    "status": "WRITTEN",
                    "path": str(path),
                    "release_id": expected["release_id"],
                },
                sort_keys=True,
            )
        )
        return 0

    try:
        actual = load_source_release_manifest(source_root)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    if canonical_json(actual) != canonical_json(expected):
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": "release manifest is stale",
                    "path": str(path),
                    "expected_release_id": expected["release_id"],
                    "actual_release_id": actual.get("release_id"),
                },
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "path": str(path),
                "release_id": actual["release_id"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
