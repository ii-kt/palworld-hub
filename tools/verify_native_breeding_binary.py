#!/usr/bin/env python3
"""Verify the committed native-breeding evidence against an exact server ELF.

The executable is deliberately not committed. Pass the binary from Steam depot
2394012 manifest 2167164727892555341 to reproduce every byte and region hash in
``evidence/build-24181105.native-breeding.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "build-24181105.native-breeding.json"
RAW_ASSETS = ROOT / "evidence" / "build-24181105.assets.json"


def integer(value: str) -> int:
    return int(value, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify(binary: Path, evidence: dict[str, Any]) -> None:
    executable = evidence["executable"]
    require(binary.stat().st_size == executable["bytes"], "Server executable size mismatch")
    require(sha256(binary) == executable["sha256"], "Server executable SHA-256 mismatch")
    with binary.open("rb") as stream:
        require(stream.read(4) == b"\x7fELF", "Input is not an ELF executable")
        for region in evidence["verifiedRegions"]:
            stream.seek(integer(region["fileOffset"]))
            data = stream.read(region["bytes"])
            require(hashlib.sha256(data).hexdigest() == region["sha256"],
                    f"Native region mismatch: {region['name']}")
        for field in evidence["reflectedFields"]:
            expected = bytes.fromhex(field["descriptorBytes"])
            stream.seek(integer(field["descriptorFileOffset"]))
            require(stream.read(len(expected)) == expected, f"Reflected field mismatch: {field['name']}")
        for instruction in evidence["instructionEvidence"]:
            expected = bytes.fromhex(instruction["bytes"])
            stream.seek(integer(instruction["fileOffset"]))
            require(stream.read(len(expected)) == expected,
                    f"Instruction evidence mismatch: {instruction['name']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path, help="PalServer-Linux-Shipping from the fixed depot manifest")
    args = parser.parse_args()
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(evidence.get("schemaVersion") == 1, "Native evidence schema mismatch")
    corroboration = evidence["assetCorroboration"]
    require(sha256(RAW_ASSETS) == corroboration["rawEvidenceSha256"],
            "Raw asset corroboration hash mismatch")
    raw = json.loads(RAW_ASSETS.read_text(encoding="utf-8"))
    require(raw["breedingItemEffectPath"] == corroboration["breedingItemEffectPackage"],
            "Breeding item effect package mismatch")
    require(len(raw["breedingItemEffects"]) == corroboration["effectEntryCount"],
            "Breeding item effect entry count mismatch")
    require(sorted({int(item["combiRankBonus"]) for item in raw["breedingItemEffects"]}) ==
            corroboration["combiRankBonusValues"], "Breeding item CombiRankBonus values mismatch")
    verify(args.binary, evidence)
    print(json.dumps({
        "serverBuildId": evidence["target"]["serverBuildId"],
        "executableSha256": evidence["executable"]["sha256"],
        "verifiedRegions": len(evidence["verifiedRegions"]),
        "reflectedFields": len(evidence["reflectedFields"]),
        "instructionExcerpts": len(evidence["instructionEvidence"]),
        "breedingItemEffects": len(raw["breedingItemEffects"]),
        "combiRankBonusValues": corroboration["combiRankBonusValues"],
    }, indent=2))


if __name__ == "__main__":
    main()
