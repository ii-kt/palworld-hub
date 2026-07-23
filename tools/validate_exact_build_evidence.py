#!/usr/bin/env python3
"""Validate the immutable evidence bundle for Palworld build 24181105.

The repository cited here is corroborating evidence, not the calculator's data
source.  Calculator rows are rebuilt from the committed raw-table extraction in
``evidence``.  Every remote file is pinned by commit and SHA-256 so a
future branch update cannot silently change what was accepted.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit" / "exact-build-evidence.json"
NATIVE_EVIDENCE = ROOT / "evidence" / "build-24181105.native-breeding.json"
NATIVE_EVIDENCE_SHA256 = "2bab43353a81a08bb438686b728055f1a79cb4884b8b1aeaded08ff90e0f38f3"

REPOSITORY = "MetalLee/PalHatchHelper"
COMMIT = "b41dbd54f371502b7d24bdc368420248a418f437"
FILES = {
    "acceptance": {
        "path": "docs/reviews/phase-4-full-catalog-acceptance.md",
        "sha256": "b7298d5e41ae2f8c611afa84da3e0b9f38b6d983310f88489611c3b50ac55ade",
    },
    "extractor": {
        "path": "tools/palworld-catalog-extractor/src/PalworldCatalogExtractor/Readers/ConfirmedCatalogReaders.cs",
        "sha256": "8ddacf0e27eb5fcf2f8bf5ebbd0aba0882dbe92feae22cf1b709c33c4f25a53e",
    },
    "acceptanceTest": {
        "path": "apps/agent/tests/game_catalog/test_real_catalog_acceptance.py",
        "sha256": "f7d16d178ac6c2bde4ebc0ed99480f30328979bd32b024e38f04c070c26d8beb",
    },
}
EXPECTED = {
    "gameVersion": "v1.0.1.100619",
    "sourceClientAppId": "1623730",
    "sourceClientBuildId": "24181527",
    "sourceClientAppmanifestSha256": "e0751824680f7de12cf79ee77ec888b8d2cdba9f682d7667c0562bb05f6450c6",
    "targetServerAppId": "2394010",
    "targetServerBuildId": "24181105",
    "targetServerAppmanifestSha256": "98ef29829ebfde6d71528f5a83883e6bfda96fa77ce363e52630205353c1a189",
    "packageSha256": "8c36cb60e4f78c3e4c7681cde602539b4b85f160d26392ed0144f728c6f191a9",
    "contentHash": "872e4a79af5b5043ee97d9a4287a41bba407afc96ff3b0a6de56fff827d334b3",
    "sourcePackageManifestSha256": "ed7d9aefb8cae7f4e29810bc7bcd5155f0dec147ac25527eb24a10a30f6b182a",
    "mappingsUsmapSha256": "561ef13c8ee3cf785e4de8aa5bc9b3ad1646e416d895f1d1166fa27ebdfd26b0",
    "extractorCommit": "705f9144a0f1c8891a3129e7db1db597ab97a109",
    "palCalcCommit": "b822c7fda4f019bd7c57f45437f14a74061a29bc",
    "palCount": 288,
    "recipeCount": 41617,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(path: str, expected_hash: str) -> tuple[str, dict[str, Any]]:
    url = f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{path}"
    request = urllib.request.Request(url, headers={"User-Agent": "palworld-hub-exact-build-audit/5"})
    with urllib.request.urlopen(request, timeout=180) as response:
        data = response.read()
    actual_hash = sha256(data)
    require(actual_hash == expected_hash, f"Pinned evidence hash mismatch: {path}: {actual_hash}")
    return data.decode("utf-8-sig"), {
        "path": path,
        "url": url,
        "bytes": len(data),
        "sha256": actual_hash,
    }


def contains_all(text: str, values: dict[str, str], label: str) -> None:
    for key, value in values.items():
        require(value in text, f"{label} is missing pinned {key}: {value}")


def load_exact_build_evidence(*, write: bool = True) -> dict[str, Any]:
    texts: dict[str, str] = {}
    metadata: dict[str, Any] = {}
    for label, spec in FILES.items():
        texts[label], metadata[label] = fetch(spec["path"], spec["sha256"])

    acceptance = texts["acceptance"]
    extractor = texts["extractor"]
    acceptance_test = texts["acceptanceTest"]
    native_bytes = NATIVE_EVIDENCE.read_bytes()
    require(sha256(native_bytes) == NATIVE_EVIDENCE_SHA256, "Native breeding evidence hash mismatch")
    native = json.loads(native_bytes)
    require(native.get("schemaVersion") == 1, "Native breeding evidence schema mismatch")
    require(native.get("target", {}).get("serverBuildId") == EXPECTED["targetServerBuildId"],
            "Native breeding evidence build mismatch")
    require(native.get("conclusions", {}).get("ignoreCombiScope") == "normal-child-candidate-only",
            "Native IgnoreCombi conclusion drifted")
    require(native.get("conclusions", {}).get("sameSpeciesShortcut") is False,
            "Native same-species control-flow conclusion drifted")
    require(native.get("conclusions", {}).get("fixedBuildCombiRankBonusValues") == [0],
            "Native/fixed-asset CombiRankBonus conclusion drifted")
    require(native.get("conclusions", {}).get("firstTieBreaker") == "higher CombiDuplicatePriority",
            "Native tie-break conclusion drifted")
    require(native.get("conclusions", {}).get("rarityUsedAsTieBreaker") is False,
            "Native rarity conclusion drifted")

    contains_all(acceptance, {
        "game version": EXPECTED["gameVersion"],
        "client app ID": EXPECTED["sourceClientAppId"],
        "client build ID": EXPECTED["sourceClientBuildId"],
        "client appmanifest": EXPECTED["sourceClientAppmanifestSha256"],
        "server app ID": EXPECTED["targetServerAppId"],
        "server build ID": EXPECTED["targetServerBuildId"],
        "server appmanifest": EXPECTED["targetServerAppmanifestSha256"],
        "package hash": EXPECTED["packageSha256"],
        "content hash": EXPECTED["contentHash"],
        "source package manifest": EXPECTED["sourcePackageManifestSha256"],
        "Mappings.usmap": EXPECTED["mappingsUsmapSha256"],
        "extractor commit": EXPECTED["extractorCommit"],
        "PalCalc commit": EXPECTED["palCalcCommit"],
    }, "Acceptance record")
    require(re.search(r"\| pals\s*\|\s*288\s*\|\s*288\s*\|", acceptance) is not None,
            "Acceptance record does not prove 288 imported Pals")
    require(re.search(r"\| breeding_recipes\s*\|\s*41617\s*\|\s*41617\s*\|", acceptance) is not None,
            "Acceptance record does not prove 41,617 imported recipe rows")
    require("unresolved 0" in acceptance and "missing localization 0" in acceptance,
            "Acceptance record has unresolved catalog facts")
    require("SPECIAL_COMBINATION_NOT_RELEASED`     |       73" in acceptance,
            "Special-combination exclusion count drifted")

    auxiliary_extractor_semantics = {
        "releasedPalFilter": 'if (Integer(row, "ZukanIndex") <= 0) return "PALDEX_NOT_RELEASED";',
        "sameSpeciesFirst": "if (StringComparer.Ordinal.Equals(parentA.StableId, parentB.StableId))",
        "specialBeforeNormal": "var pairCombinations = combinations.Where(value => value.HasParents(parentA, parentB)).ToArray();",
        "specialChildrenExcluded": "var normalCandidates = pals.Where(value => !specialChildren.Contains(value.StableId)).ToArray();",
        "targetPowerFormula": "Math.Floor((parentA.BreedingPower + parentB.BreedingPower + 1) / 2.0f)",
        "duplicatePriorityTie": ".ThenByDescending(value => value.BreedingPriority)",
        "variantTie": ".ThenBy(value => value.IsVariant ? 1 : 0)",
        "sourceOrderTie": ".ThenBy(value => value.SourceOrder)",
        "bothGenderOrientations": 'var orientations = new[] { (A: "female", B: "male"), (A: "male", B: "female") };',
    }
    semantics = {name: fragment in extractor for name, fragment in auxiliary_extractor_semantics.items()}
    require(all(semantics.values()), "Pinned auxiliary extractor breeding semantics drifted")
    require('var suffix = Text(row.Value, "ZukanIndexSuffix");' in extractor,
            "Pinned extractor no longer reads ZukanIndexSuffix")
    require('var priority = Integer(row.Value, "CombiDuplicatePriority");' in extractor,
            "Pinned extractor no longer reads CombiDuplicatePriority")

    contains_all(acceptance_test, {
        "content hash": EXPECTED["contentHash"],
        "server build": EXPECTED["targetServerBuildId"],
        "Mappings hash": EXPECTED["mappingsUsmapSha256"],
        "pal count": '"pals": 288',
        "recipe count": '"breeding_recipes": 41617',
    }, "Acceptance test")

    evidence = {
        "schemaVersion": 3,
        "status": "fixed-build-evidence-validated",
        "repository": REPOSITORY,
        "commit": COMMIT,
        "files": metadata,
        "sourceClient": {
            "appId": EXPECTED["sourceClientAppId"],
            "buildId": EXPECTED["sourceClientBuildId"],
            "gameVersion": EXPECTED["gameVersion"],
            "appmanifestSha256": EXPECTED["sourceClientAppmanifestSha256"],
        },
        "targetServer": {
            "appId": EXPECTED["targetServerAppId"],
            "buildId": EXPECTED["targetServerBuildId"],
            "gameVersion": EXPECTED["gameVersion"],
            "appmanifestSha256": EXPECTED["targetServerAppmanifestSha256"],
        },
        "catalog": {
            "packageSha256": EXPECTED["packageSha256"],
            "contentHash": EXPECTED["contentHash"],
            "sourcePackageManifestSha256": EXPECTED["sourcePackageManifestSha256"],
            "mappingsUsmapSha256": EXPECTED["mappingsUsmapSha256"],
            "extractorCommit": EXPECTED["extractorCommit"],
            "palCalcReferenceCommit": EXPECTED["palCalcCommit"],
        },
        "counts": {"pals": EXPECTED["palCount"], "breedingRecipes": EXPECTED["recipeCount"]},
        "auxiliaryExtractorSemantics": semantics,
        "nativeStaticAnalysis": {
            "evidencePath": "evidence/build-24181105.native-breeding.json",
            "evidenceSha256": NATIVE_EVIDENCE_SHA256,
            "serverExecutableSha256": native["executable"]["sha256"],
            "serverExecutableBytes": native["executable"]["bytes"],
            "serverExecutableElfBuildId": native["executable"]["elfBuildId"],
            "verifiedRegionCount": len(native["verifiedRegions"]),
            "reflectedFieldCount": len(native["reflectedFields"]),
            "conclusions": native["conclusions"],
        },
        "runtimeHatchExhaustive": False,
    }
    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return evidence


if __name__ == "__main__":
    print(json.dumps(load_exact_build_evidence(), ensure_ascii=False, indent=2))
