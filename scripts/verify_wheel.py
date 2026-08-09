#!/usr/bin/env python3
"""Verify that a built Harness Maestro wheel contains every runtime resource."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath


PRIVATE_PATH_PATTERN = re.compile(
    rb"(?:/Users/[^/\x00\r\n]+/|/home/[^/\x00\r\n]+/|[A-Za-z]:\\Users\\[^\\\x00\r\n]+\\)"
)


def _runtime_resources(source_root: Path) -> set[str]:
    resource_root = source_root / "src" / "maestro" / "resources"
    return {
        f"maestro/resources/{item.relative_to(resource_root).as_posix()}"
        for item in resource_root.rglob("*")
        if item.is_file()
        and "__pycache__" not in item.parts
        and item.suffix in {
            ".json",
            ".md",
            ".py",
            ".html",
            ".css",
            ".js",
        }
    }


def verify_wheel(wheel: Path, source_root: Path) -> dict[str, object]:
    expected = _runtime_resources(source_root)
    if not expected:
        raise ValueError("source checkout has no runtime resources")

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        unsafe = sorted(
            name
            for name in names
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
        )
        missing = sorted(expected - names)
        entrypoint_names = sorted(
            name
            for name in names
            if name.endswith(".dist-info/entry_points.txt")
        )
        entrypoint_ok = len(entrypoint_names) == 1 and (
            "maestro = maestro.cli:main"
            in archive.read(entrypoint_names[0]).decode("utf-8")
        )
        private_path_entries = sorted(
            name
            for name in names
            if not name.endswith("/")
            and PRIVATE_PATH_PATTERN.search(archive.read(name))
        )

    return {
        "wheel": str(wheel.resolve()),
        "expected_runtime_resources": len(expected),
        "missing_runtime_resources": missing,
        "unsafe_archive_paths": unsafe,
        "entrypoint_ok": entrypoint_ok,
        "private_path_entries": private_path_entries,
        "status": (
            "PASS"
            if not missing
            and not unsafe
            and entrypoint_ok
            and not private_path_entries
            else "FAIL"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args(argv)

    try:
        report = verify_wheel(args.wheel, args.source_root.resolve())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
