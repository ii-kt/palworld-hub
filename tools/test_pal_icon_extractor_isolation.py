#!/usr/bin/env python3
"""Exercise the extractor's fail-closed container checks without game files."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "tools" / "pal-icon-extractor" / "PalIconExtractor.csproj"
PALS = ROOT / "data" / "pals.verified.json"
ASSETS = ROOT / "evidence" / "build-24181105.assets.json"


def dotnet_command():
    configured = os.environ.get("DOTNET_HOST_PATH")
    if configured:
        return configured
    discovered = shutil.which("dotnet")
    if discovered:
        return discovered
    raise RuntimeError("dotnet was not found")


def run_with_containers(container_names):
    with tempfile.TemporaryDirectory(prefix="pal-icon-isolation-") as temporary:
        base = Path(temporary)
        pak_root = base / "pak"
        pak_root.mkdir()
        for name in container_names:
            (pak_root / name).touch()
        mappings = base / "Mappings.usmap"
        mappings.touch()
        oodle = base / "oodle-data-shared.dll"
        oodle.touch()
        command = [
            dotnet_command(),
            "run",
            "--project",
            str(PROJECT),
            "--configuration",
            "Release",
            "--no-build",
            "--",
            str(pak_root),
            str(PALS),
            str(ASSETS),
            str(base / "icons"),
            str(base / "manifest.json"),
            str(mappings),
            str(ROOT / "tools" / "pal-icon-extractor" / "Program.cs"),
            str(ROOT / "tools" / "pal-icon-extractor" / "packages.lock.json"),
            str(oodle),
        ]
        return subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )


def require_failure(container_names, expected):
    result = run_with_containers(container_names)
    combined = result.stdout + result.stderr
    if result.returncode == 0:
        raise AssertionError(f"extractor unexpectedly accepted {container_names}")
    if expected not in combined:
        raise AssertionError(
            f"expected {expected!r} for {container_names}, got:\n{combined}"
        )


def main():
    require_failure(
        ["Pal-Windows.pak", "mod.pak"],
        "must be isolated and contain exactly one regular file",
    )
    require_failure(
        ["Pal-Windows.pak", "Override.uproject", "T_SheepBall.uasset"],
        "must be isolated and contain exactly one regular file",
    )
    require_failure(
        ["Other-Windows.pak"],
        "The only allowed container is the fixed Pal-Windows.pak",
    )
    require_failure(
        ["Pal-Windows.pak"],
        "Fixed client PAK size mismatch",
    )
    print("Pal icon extractor isolation checks passed (4/4).")


if __name__ == "__main__":
    main()
