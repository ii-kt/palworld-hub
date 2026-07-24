#!/usr/bin/env python3
"""Fail closed if private game inputs or build outputs could reach GitHub Pages."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {
    ".acf",
    ".dll",
    ".dylib",
    ".exe",
    ".pak",
    ".pdb",
    ".so",
    ".ucas",
    ".usmap",
    ".utoc",
}
FORBIDDEN_PATH_PARTS = {
    "depotcache",
    "steamapps",
}
FORBIDDEN_BUILD_PATHS = {
    ("tools", "pal-icon-extractor", "bin"),
    ("tools", "pal-icon-extractor", "obj"),
}
MAX_FILE_BYTES = 10 * 1024 * 1024
STEAM_MANIFEST = re.compile(r"appmanifest_[0-9]+[.]acf", re.IGNORECASE)


def repository_files():
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    for raw_relative in sorted(result.stdout.split(b"\0")):
        if raw_relative:
            yield ROOT / raw_relative.decode("utf-8")


def violations():
    for path in repository_files():
        relative = path.relative_to(ROOT)
        lower_parts = tuple(part.lower() for part in relative.parts)
        if not path.exists() and not path.is_symlink():
            yield f"tracked file is missing from the checkout: {relative.as_posix()}"
            continue
        if path.is_symlink():
            yield f"symbolic link is not allowed in the Pages artifact: {relative.as_posix()}"
            continue
        if any(part in FORBIDDEN_PATH_PARTS for part in lower_parts):
            yield f"Steam/depot directory is forbidden: {relative.as_posix()}"
        if any(
            lower_parts[: len(prefix)] == prefix
            for prefix in FORBIDDEN_BUILD_PATHS
        ):
            yield f"compiled extractor output is forbidden: {relative.as_posix()}"
        suffix = path.suffix.lower()
        if suffix in FORBIDDEN_SUFFIXES or STEAM_MANIFEST.fullmatch(path.name):
            yield f"fixed-game input or compiled binary is forbidden: {relative.as_posix()}"
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            yield (
                f"file exceeds the {MAX_FILE_BYTES}-byte publication limit: "
                f"{relative.as_posix()} ({size} bytes)"
            )


def main():
    problems = list(violations())
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    print("Repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
