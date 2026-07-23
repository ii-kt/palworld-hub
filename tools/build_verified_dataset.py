#!/usr/bin/env python3
"""Build the site data from the committed extraction of the fixed game build.

The raw rows in ``evidence/build-24181105.assets.json`` are the only
source used to select Pals and calculate children.  Pinned third-party files
are downloaded only after calculation and are treated as comparison oracles;
their integrity is checked, but their differences can neither change nor
invalidate the authoritative fixed-build result.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import audit_breeding_sources as auxiliary
import validate_exact_build_evidence as exact_build

ROOT = Path(__file__).resolve().parents[1]
PALWORLD = ROOT
RAW_ASSETS = PALWORLD / "evidence" / "build-24181105.assets.json"
NATIVE_EVIDENCE = PALWORLD / "evidence" / "build-24181105.native-breeding.json"
NATIVE_RUNTIME_EVIDENCE = PALWORLD / "audit" / "native-runtime-comparison.json"
RAW_EXTRACTOR_SOURCE = PALWORLD / "tools" / "RawPalDump.cs"
DATA_DIR = PALWORLD / "data"
AUDIT_DIR = PALWORLD / "audit"

GAME_VERSION = "v1.0.1.100619"
CLIENT_APP_ID = "1623730"
CLIENT_BUILD_ID = "24181527"
SERVER_APP_ID = "2394010"
SERVER_BUILD_ID = "24181105"
SERVER_DEPOT_ID = "2394012"
SERVER_DEPOT_MANIFEST_ID = "2167164727892555341"
DATASET_ID = "pw-1.0.1.100619-24181105-cad80fe15c38"
RAW_ASSETS_SHA256 = "e23a12ceffae5792b69c8faebe8ee3fbacbc09f0bd88572410d2b3b59aca1fe0"
NATIVE_EVIDENCE_SHA256 = "ac079224cbadb33886092145de2d4f5e2d6da6ccc5ba4cb0374f1e2f552e2651"
NATIVE_RUNTIME_EVIDENCE_SHA256 = "265bf315873f9d4f1e58ac8fec9544b912e7e6cea304cdc3b34cb1437be63bb1"
NATIVE_RUNTIME_EVIDENCE_DIGEST = "08d7850d2bb566a77cd8734c93b7ed8f31563c287850e41450de2328c89a36a6"
NATIVE_RUNTIME_WORKFLOW_RUN_ID = 30_018_308_091
NATIVE_RUNTIME_WORKFLOW_HEAD_SHA = "9c79baa3f1f3ddda60f20a79399a1d4c91fb5f14"
NATIVE_RUNTIME_ARTIFACT_ID = 8_568_465_293
NATIVE_RUNTIME_ARTIFACT_ZIP_SHA256 = "e3985f60f66b115d9cee71fe15adab71c54d6b277cf997329555f3fa9471e6a9"
SERVER_PAK_SHA256 = "cad80fe15c38d74a795779fbab31f04bc2c15c37fb8a2188e4d89f3800fb0e68"
SERVER_PAK_BYTES = 4_797_040_962
RAW_EXTRACTOR_REPOSITORY = "Awy64/palworld-atlas-data"
RAW_EXTRACTOR_COMMIT = "0385b3fd8bd757240d4a2c79615145122669abd5"
RAW_EXTRACTOR_SOURCE_SHA256 = "79d44cd07efcf767d5be0153763333249229e798c86444f21ca48d7826423eb8"
RELEASED_SOURCE_IDS_SHA256 = "09b6c2e7db674ac1f48ebf6561c2d7e7f1e2d0d94ffbe0d7dfee5ae4c348ad46"

PINNED_FILES = {
    "palcalcDb": {
        "repo": "tylercamp/palcalc",
        "commit": "b822c7fda4f019bd7c57f45437f14a74061a29bc",
        "path": "PalCalc.Model/db.json",
        "sha256": "803d891afdb18bd00e24332844a7276bbe5c0855170ef90ef142f2f4d7698ed1",
        "local": "/tmp/palcalc/PalCalc.Model/db.json",
    },
    "palcalcBreeding": {
        "repo": "tylercamp/palcalc",
        "commit": "b822c7fda4f019bd7c57f45437f14a74061a29bc",
        "path": "PalCalc.Model/breeding.json",
        "sha256": "1af1e4d6b461599ec3b80a2195002337ff484ed3c28ce57e27def96138262ec2",
        "local": "/tmp/palcalc/PalCalc.Model/breeding.json",
    },
    "palcalcPalsCsv": {
        "repo": "tylercamp/palcalc",
        "commit": "b822c7fda4f019bd7c57f45437f14a74061a29bc",
        "path": "PalCalc.GenDB/out-csv/pals.csv",
        "sha256": "01eb3aae31c82c9ed2160bb1d08ec5230516698f50a4025725e36cb5ded52561",
        "local": "/tmp/palcalc/PalCalc.GenDB/out-csv/pals.csv",
    },
    "palcalcCalculator": {
        "repo": "tylercamp/palcalc",
        "commit": "b822c7fda4f019bd7c57f45437f14a74061a29bc",
        "path": "PalCalc.GenDB/PalBreedingCalculator.cs",
        "sha256": "30f1cd4e787ca2c713075e4269ddf1b451a120eaaf347474eabb216f436fcab1",
        "local": "/tmp/palcalc/PalCalc.GenDB/PalBreedingCalculator.cs",
    },
    "palcalcReader": {
        "repo": "tylercamp/palcalc",
        "commit": "b822c7fda4f019bd7c57f45437f14a74061a29bc",
        "path": "PalCalc.GenDB/GameDataReaders/PalReader.cs",
        "sha256": "2002c8e10dd74eb37ec33a25ab98193b240e72cee1d6b5c05d950a484b3140fa",
        "local": "/tmp/palcalc/PalCalc.GenDB/GameDataReaders/PalReader.cs",
    },
    "palworldSaveTools": {
        "repo": "deafdudecomputers/PalworldSaveTools",
        "commit": "ec842cfb5aeca63b52c25e360228920b469bcb14",
        "path": "resources/game_data/breedingdata.json",
        "sha256": "07a137963d6d1113e142eab715140aa9fea5fe5e5a5d843ecb60bb982164f12c",
        "local": "/tmp/PalworldSaveTools/resources/game_data/breedingdata.json",
    },
    "paldeck": {
        "repo": "FearlessKenji/Paldeck",
        "commit": "48b43720607cd1140239cb8f3da7a92d7611390f",
        "path": "data/palBreeding.json",
        "sha256": "4cf5fb375771921b5a7b712fe88cc7f9e34674c4e4b54ce8d32c418f07e68c4a",
        "local": "/tmp/paldeck.breeding.json",
    },
}

EXPECTED_EXCLUSIONS = {
    "BOSS_VARIANT": 412,
    "DUPLICATE_PUBLIC_FORM_PARAMETER_ROW": 11,
    "PALDEX_NOT_RELEASED": 18,
    "PAL_CONFIGURATION_INCOMPLETE": 1,
    "PAL_ICON_MISSING": 23,
}

ELEMENTS = {
    "normal": "Neutral",
    "fire": "Fire",
    "water": "Water",
    "electricity": "Electric",
    "leaf": "Grass",
    "dark": "Dark",
    "dragon": "Dragon",
    "earth": "Ground",
    "ice": "Ice",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repository_text_bytes(path: Path) -> bytes:
    """Return the LF-canonical bytes stored by Git on every platform."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def stable_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded)


def validate_native_runtime_evidence(
    runtime_bytes: bytes,
    pals_bytes: bytes,
    breeding_bytes: bytes,
    released: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    require(
        sha256(runtime_bytes) == NATIVE_RUNTIME_EVIDENCE_SHA256,
        "Committed native runtime evidence file hash mismatch",
    )
    runtime = json.loads(runtime_bytes)
    require(runtime.get("schemaVersion") == 2, "Native runtime evidence schema mismatch")
    require(
        runtime.get("status") == "fixed-build-native-runtime-matched",
        "Native runtime evidence did not match",
    )
    claimed_digest = runtime.get("evidenceSha256")
    digest_payload = dict(runtime)
    digest_payload.pop("evidenceSha256", None)
    require(
        claimed_digest == NATIVE_RUNTIME_EVIDENCE_DIGEST
        and stable_digest(digest_payload) == claimed_digest,
        "Native runtime evidence self-digest mismatch",
    )
    require(runtime.get("target") == {
        "gameVersion": GAME_VERSION,
        "serverAppId": SERVER_APP_ID,
        "serverBuildId": SERVER_BUILD_ID,
        "serverDepotId": SERVER_DEPOT_ID,
        "serverDepotManifestId": SERVER_DEPOT_MANIFEST_ID,
        "serverExecutableBytes": 196_285_592,
        "serverExecutableSha256": "788649fa1592160faa7bcf07ccd16d474ebeaae954717bc32284b5a43028d8e7",
        "serverPakBytes": SERVER_PAK_BYTES,
        "serverPakSha256": SERVER_PAK_SHA256,
    }, "Native runtime target mismatch")

    invocation = runtime.get("invocation", {})
    require(
        invocation == {
            "nativeFunctionAddress": "0x71168c0",
            "managerHelperAddress": "0x76459e0",
            "method": "direct native function invocation in initialized fixed-build server",
            "parentOrdersPerGenderOrientation": 2,
            "genderOrientationsPerPair": 2,
            "nativeInvocationCount": 166_464,
            "harnessHelperScope": "data-table-manager lookup for two synthetic parent records only",
            "selectionOrRecipeLogicStubbed": False,
            "internetEgressBlocked": True,
        },
        "Native runtime invocation contract mismatch",
    )
    require(runtime.get("counts") == {
        "rawPalRows": 753,
        "releasedPals": 288,
        "uniqueCombinationRows": 258,
        "unorderedParentPairs": 41_616,
        "logicalResultRows": 41_617,
        "matchingLogicalResultRows": 41_617,
        "nativeInvocations": 166_464,
        "bossVariantMappings": 288,
    }, "Native runtime counts mismatch")

    expected_difference_keys = {
        "runtimeRowMetadata",
        "runtimeUniqueRows",
        "runtimeLogicalResults",
        "runtimeCalls",
        "parentOrder",
        "hiddenGender",
        "sameSpecies",
        "specialCombination",
        "normalSelection",
        "bossVariantMapping",
    }
    differences = runtime.get("differences", {})
    require(
        set(differences) == expected_difference_keys
        and all(value == 0 for value in differences.values()),
        "Native runtime differences are not all zero",
    )
    require(runtime.get("allDifferences") == {
        "rowMetadata": [],
        "uniqueRows": [],
        "logicalResults": [],
    }, "Native runtime difference details are not empty")
    require(runtime.get("gender") == {
        "maleRuntimeCode": 1,
        "femaleRuntimeCode": 2,
        "genderDependentPair": "catmage|foxmage",
    }, "Native runtime gender evidence mismatch")

    table_identity = runtime.get("runtimeTableIdentity", {})
    require(
        table_identity.get("rawTribeCount") == 333
        and table_identity.get("runtimeTribeCount") == 333
        and table_identity.get("rawToRuntimeAmbiguityCount") == 0
        and table_identity.get("runtimeToRawAmbiguityCount") == 0
        and table_identity.get("runtimeRowsSha256")
        == "8b699bc10bfb8de85e026850f074d46c0785843ea4a3b2aebba75dd7d2d6595f",
        "Native runtime table identity mismatch",
    )
    inputs = runtime.get("inputs", {})
    require(inputs.get("runtimeInput") == {
        "bytes": 518_868,
        "sha256": "e25e5bdd4ef66431263338e8509db8ccc4f969a13e7954185ea001921fccd57b",
        "rawPalRows": 753,
        "releasedPals": 288,
        "uniqueRows": 258,
        "pairs": 41_616,
        "logicalRows": 41_617,
        "specialPairs": 183,
        "tribes": 333,
    }, "Native runtime binary input evidence mismatch")
    require(
        inputs.get("rawAssetsSha256") == RAW_ASSETS_SHA256
        and inputs.get("palsSha256") == sha256(pals_bytes)
        and inputs.get("breedingSha256") == sha256(breeding_bytes)
        and inputs.get("staticNativeEvidenceSha256") == NATIVE_EVIDENCE_SHA256
        and inputs.get("runtimeProbeSourceSha256")
        == sha256(repository_text_bytes(PALWORLD / "tools" / "native_breeding_runtime_probe.c"))
        and inputs.get("offlineShimSourceSha256")
        == sha256(repository_text_bytes(PALWORLD / "tools" / "fixed_server_nonroot_shim.c")),
        "Native runtime source/input hash mismatch",
    )
    require(runtime.get("serverInitialization") == {
        "reportedGameVersion": GAME_VERSION,
        "reachedRunningState": True,
        "processExitCode": 143,
    }, "Native runtime server initialization mismatch")

    boss = runtime.get("bossAlphaPostProcessing", {})
    mappings = boss.get("mappings", [])
    require(
        boss.get("nativeFunctionAddress") == "0x7118c40"
        and boss.get("modeled") is True
        and boss.get("mappingCount") == 288
        and boss.get("mismatchCount") == 0
        and boss.get("speciesIdentityPreserved") is True
        and len(mappings) == len(released),
        "Native boss/Alpha species mapping evidence mismatch",
    )
    raw_by_source_id = {
        str(row["rowName"]): row
        for row in raw_rows
    }
    released_source_ids = {str(pal["sourceId"]) for pal in released}
    for mapping, pal in zip(mappings, released, strict=True):
        boss_source_id = mapping.get("bossSourceId")
        boss_row = raw_by_source_id.get(str(boss_source_id))
        require(
            mapping.get("palId") == pal["id"]
            and mapping.get("sourceId") == pal["sourceId"]
            and boss_row is not None
            and any(bool(boss_row[field]) for field in ("isBoss", "isRaidBoss", "isTowerBoss"))
            and str(boss_source_id) not in released_source_ids
            and enum_tail(boss_row["tribe"]) == pal["tribe"]
            and isinstance(mapping.get("baseTribeRuntimeId"), int)
            and mapping.get("baseTribeRuntimeId") == mapping.get("bossTribeRuntimeId")
            and mapping.get("valid") is True,
            f"Native boss/Alpha mapping drifted: {pal['id']}",
        )
    return runtime


def enum_tail(value: Any) -> str:
    return str(value or "").rsplit("::", 1)[-1]


def pal_id(value: Any) -> str:
    return str(value or "").strip().lower()


def pair_key(first: str, second: str) -> str:
    return "|".join(sorted((pal_id(first), pal_id(second))))


def pair_index(size: int, first: int, second: int) -> int:
    if first > second:
        first, second = second, first
    return first * size - first * (first - 1) // 2 + second - first


def gender(value: Any) -> str:
    result = enum_tail(value).upper()
    return "WILDCARD" if result in {"", "NONE", "ANY", "WILDCARD"} else result


def canonical_row(
    first: str,
    first_gender: str,
    second: str,
    second_gender: str,
    child: str,
) -> tuple[str, str, str, str, str]:
    left = (pal_id(first), gender(first_gender))
    right = (pal_id(second), gender(second_gender))
    if right[0] < left[0]:
        left, right = right, left
    return left[0], left[1], right[0], right[1], pal_id(child)


def fetch_pinned(label: str) -> tuple[bytes, dict[str, Any]]:
    spec = PINNED_FILES[label]
    local = Path(str(spec["local"]))
    data: bytes
    if local.is_file():
        candidate = local.read_bytes()
        if sha256(candidate) == spec["sha256"]:
            data = candidate
        else:
            data = b""
    else:
        data = b""
    if not data:
        url = f"https://raw.githubusercontent.com/{spec['repo']}/{spec['commit']}/{spec['path']}"
        request = urllib.request.Request(url, headers={"User-Agent": "palworld-hub-fixed-build-generator/6"})
        with urllib.request.urlopen(request, timeout=240) as response:
            data = response.read()
    actual = sha256(data)
    require(actual == spec["sha256"], f"Pinned file hash mismatch for {label}: {actual}")
    return data, {
        "repository": spec["repo"],
        "commit": spec["commit"],
        "path": spec["path"],
        "sha256": actual,
        "bytes": len(data),
    }


def exclusion_reason(row: dict[str, Any], icon_ids: set[str]) -> str | None:
    source = str(row["rowName"])
    lowered = source.lower()
    tribe = enum_tail(row["tribe"]).lower()
    if not row["isPal"]:
        return "NOT_A_PAL"
    if row["isBoss"] or row["isRaidBoss"] or row["isTowerBoss"]:
        return "BOSS_VARIANT"
    if lowered not in icon_ids and tribe not in icon_ids:
        return "PAL_ICON_MISSING"
    if int(row["zukanIndex"]) <= 0:
        return "PALDEX_NOT_RELEASED"
    if any(int(row[field]) <= 0 for field in ("rarity", "runSpeed", "walkSpeed", "combiRank")):
        return "PAL_CONFIGURATION_INCOMPLETE"
    return None


def public_form_key(row: dict[str, Any]) -> tuple[int, str, int]:
    """Return the fixed-asset form identity without classifying RowName text."""
    return int(row["zukanIndex"]), str(row["zukanIndexSuffix"] or ""), int(row["rarity"])


def display_name(row: dict[str, Any], names: dict[str, str]) -> str:
    override = str(row.get("overrideNameTextId") or "")
    key = f"PAL_NAME_{row['rowName']}" if override.lower() in {"", "none"} else override
    return str(names.get(key) or names.get(key.lower()) or "").strip()


def element_list(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("elementType1", "elementType2"):
        raw = enum_tail(row[field]).lower()
        if raw == "none":
            continue
        require(raw in ELEMENTS, f"Unknown element {row[field]} on {row['rowName']}")
        value = ELEMENTS[raw]
        if value not in values:
            values.append(value)
    return values


def special_matches(
    recipe: dict[str, Any],
    first: dict[str, Any],
    first_gender: str,
    second: dict[str, Any],
    second_gender: str,
) -> bool:
    def accepts(required: str, actual: str) -> bool:
        return required == "WILDCARD" or required == actual

    if recipe["parentA"] == first["id"] and recipe["parentB"] == second["id"]:
        return accepts(recipe["genderA"], first_gender) and accepts(recipe["genderB"], second_gender)
    if recipe["parentA"] == second["id"] and recipe["parentB"] == first["id"]:
        return accepts(recipe["genderA"], second_gender) and accepts(recipe["genderB"], first_gender)
    return False


def normal_child(parents: tuple[dict[str, Any], dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    first, second = parents
    target = (first["combiRank"] + second["combiRank"] + 1) // 2
    return min(candidates, key=lambda value: (
        abs(value["combiRank"] - target),
        -value["combiDuplicatePriority"],
        value["sourceOrder"],
    ))


def variant_tie_counterfactual_child(
    parents: tuple[dict[str, Any], dict[str, Any]], candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    first, second = parents
    target = (first["combiRank"] + second["combiRank"] + 1) // 2
    return min(candidates, key=lambda value: (
        abs(value["combiRank"] - target),
        -value["combiDuplicatePriority"],
        1 if value["variant"] else 0,
        value["sourceOrder"],
    ))


def rarity_counterfactual_child(
    parents: tuple[dict[str, Any], dict[str, Any]], candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    first, second = parents
    target = (first["combiRank"] + second["combiRank"] + 1) // 2
    parent_rarity = (first["rarity"] + second["rarity"]) / 2
    return min(candidates, key=lambda value: (
        abs(value["combiRank"] - target),
        abs(value["rarity"] - parent_rarity),
        value["rarity"],
        value["sourceOrder"],
    ))


def decode_compact(compact: dict[str, Any]) -> set[tuple[str, str, str, str, str]]:
    order = compact["palOrder"]
    size = len(order)
    override_by_index = {item["pairIndex"]: item for item in compact["genderOverrides"]}
    rows: set[tuple[str, str, str, str, str]] = set()
    cursor = 0
    for first in range(size):
        for second in range(first, size):
            require(cursor == pair_index(size, first, second), "Compact triangular index drift")
            override = override_by_index.get(cursor)
            if override:
                require(override["pair"] == [first, second], "Gender override pair drift")
                for row in override["rows"]:
                    rows.add(canonical_row(
                        order[row["parent1"]], row["parent1Gender"],
                        order[row["parent2"]], row["parent2Gender"],
                        order[row["child"]],
                    ))
            else:
                rows.add(canonical_row(
                    order[first], "WILDCARD", order[second], "WILDCARD", order[compact["children"][cursor]]
                ))
            cursor += 1
    require(cursor == len(compact["children"]), "Compact matrix length drift")
    return rows


def row_objects(rows: Iterable[tuple[str, str, str, str, str]]) -> list[dict[str, str]]:
    return [
        {"parent1": row[0], "parent1Gender": row[1], "parent2": row[2], "parent2Gender": row[3], "child": row[4]}
        for row in sorted(rows)
    ]


def compare_pair_map(authoritative: dict[str, set[str]], candidate: dict[str, set[str]]) -> dict[str, Any]:
    common = sorted(set(authoritative) & set(candidate))
    mismatches = [
        {"pair": key, "authoritative": sorted(authoritative[key]), "candidate": sorted(candidate[key])}
        for key in common if authoritative[key] != candidate[key]
    ]
    missing = sorted(set(authoritative) - set(candidate))
    extra = sorted(set(candidate) - set(authoritative))
    return {
        "authoritativePairCount": len(authoritative),
        "candidatePairCount": len(candidate),
        "commonPairCount": len(common),
        "matchingPairCount": len(common) - len(mismatches),
        "mismatchCount": len(mismatches),
        "missingPairCount": len(missing),
        "extraPairCount": len(extra),
        "mismatches": mismatches,
        "missingPairs": missing,
        "extraPairs": extra,
    }


def main() -> None:
    exact = exact_build.load_exact_build_evidence(write=True)
    raw_bytes = RAW_ASSETS.read_bytes()
    native_bytes = repository_text_bytes(NATIVE_EVIDENCE)
    runtime_bytes = repository_text_bytes(NATIVE_RUNTIME_EVIDENCE)
    require(sha256(raw_bytes) == RAW_ASSETS_SHA256, "Committed raw asset extraction hash mismatch")
    require(sha256(native_bytes) == NATIVE_EVIDENCE_SHA256, "Committed native breeding evidence hash mismatch")
    require(sha256(repository_text_bytes(RAW_EXTRACTOR_SOURCE)) == RAW_EXTRACTOR_SOURCE_SHA256,
            "Committed raw asset extractor extension hash mismatch")
    raw = json.loads(raw_bytes)
    native = json.loads(native_bytes)
    require(raw.get("schemaVersion") == 1 and raw.get("buildId") == SERVER_BUILD_ID, "Raw asset schema/build mismatch")
    require(len(raw.get("pals", [])) == 753, "Unexpected DT_PalMonsterParameter row count")
    require(len(raw.get("combinations", [])) == 258, "Unexpected DT_PalCombiUnique row count")
    require(raw.get("breedingItemEffectPath") ==
            "Pal/Content/Pal/DataAsset/MapObject/Breeding/DA_BreedingItemEffectData",
            "Breeding item effect asset path drifted")
    require(raw.get("breedingItemEffects") == [
        {"itemId": "Cake02", "talentBonusMin": 1, "talentBonusMax": 5,
         "mutationRateBonusPercent": 0, "combiRankBonus": 0, "breedCount": 1,
         "inheritAllActiveSkills": False, "passiveInheritCountOverride": 0},
        {"itemId": "Cake03", "talentBonusMin": 0, "talentBonusMax": 0,
         "mutationRateBonusPercent": 0, "combiRankBonus": 0, "breedCount": 2,
         "inheritAllActiveSkills": False, "passiveInheritCountOverride": 0},
        {"itemId": "Cake04", "talentBonusMin": 1, "talentBonusMax": 5,
         "mutationRateBonusPercent": 2, "combiRankBonus": 0, "breedCount": 1,
         "inheritAllActiveSkills": False, "passiveInheritCountOverride": 0},
        {"itemId": "Cake05", "talentBonusMin": 0, "talentBonusMax": 0,
         "mutationRateBonusPercent": 0, "combiRankBonus": 0, "breedCount": 1,
         "inheritAllActiveSkills": True, "passiveInheritCountOverride": 4},
    ], "Breeding item effect asset rows drifted")
    require(raw.get("pakFiles") == [{
        "file": "Pal-LinuxServer.pak", "bytes": SERVER_PAK_BYTES, "sha256": SERVER_PAK_SHA256
    }], "Exact server PAK evidence mismatch")
    require(native.get("schemaVersion") == 1, "Native breeding evidence schema mismatch")
    require(native.get("target", {}).get("serverBuildId") == SERVER_BUILD_ID,
            "Native breeding evidence build mismatch")
    require(native.get("conclusions") == {
        "sameSpeciesShortcut": False,
        "sameSpeciesResolution": "special combination first; otherwise normal candidate selection, including equal parents",
        "specialCombinationCheckedBeforeNormalSelection": True,
        "specialChildrenExcludedFromNormalCandidates": True,
        "ignoreCombiScope": "normal-child-candidate-only",
        "ignoreCombiParentExclusion": False,
        "normalTarget": "floor((parentA.CombiRank + parentB.CombiRank + 1) / 2)",
        "combiRankBonusClamp": "clamp(breedingItemEffect.CombiRankBonus, 0, 10)",
        "fixedBuildCombiRankBonusValues": [0],
        "firstTieBreaker": "higher CombiDuplicatePriority",
        "rarityUsedAsTieBreaker": False,
        "variantFlagUsedAsTieBreaker": False,
        "finalTieBreaker": "DT_PalMonsterParameter row enumeration order",
    }, "Native breeding conclusions drifted")

    references: dict[str, bytes] = {}
    reference_metadata: dict[str, Any] = {}
    for label in PINNED_FILES:
        references[label], reference_metadata[label] = fetch_pinned(label)

    calculator_source = references["palcalcCalculator"].decode("utf-8-sig")
    reader_source = references["palcalcReader"].decode("utf-8-sig")
    palcalc_semantics = {
        "sameSpeciesShortcut": "if (parent1.Pal == parent2.Pal)" in calculator_source,
        "specialCombinationLookup": "if (specialCombo.Any())" in calculator_source,
        "specialChildrenExcluded": (
            ".Where(p => !uniqueCombos.Any(c => p == c.Child))" in calculator_source
        ),
        "duplicatePriorityTieBreak": (
            "ThenByDescending(p => p.BreedingPowerPriority)" in calculator_source
        ),
        "duplicatePriorityAssetRead": "CombiDuplicatePriority" in reader_source,
    }

    icon_ids = {
        pal_id(item["id"])
        for item in raw["icons"]
        if "t_dummy_icon" not in str(item["path"]).lower()
    }
    exclusions: list[dict[str, str]] = []
    individually_eligible_rows: list[dict[str, Any]] = []
    for row in raw["pals"]:
        reason = exclusion_reason(row, icon_ids)
        if reason:
            exclusions.append({"id": pal_id(row["rowName"]), "sourceId": row["rowName"], "reason": reason})
        else:
            individually_eligible_rows.append(row)

    form_groups: dict[tuple[int, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in individually_eligible_rows:
        form_groups[public_form_key(row)].append(row)
    released_rows: list[dict[str, Any]] = []
    duplicate_form_group_count = 0
    duplicate_form_rows: list[dict[str, str]] = []
    for key, rows in form_groups.items():
        if len(rows) == 1:
            released_rows.append(rows[0])
            continue
        duplicate_form_group_count += 1
        exact_icon_rows = [row for row in rows if pal_id(row["rowName"]) in icon_ids]
        require(
            len(exact_icon_rows) == 1,
            f"Ambiguous fixed-asset form {key}: expected one exact character-icon row, got "
            f"{[row['rowName'] for row in exact_icon_rows]}",
        )
        released_rows.append(exact_icon_rows[0])
        for row in rows:
            if row is exact_icon_rows[0]:
                continue
            item = {
                "id": pal_id(row["rowName"]),
                "sourceId": str(row["rowName"]),
                "reason": "DUPLICATE_PUBLIC_FORM_PARAMETER_ROW",
            }
            exclusions.append(item)
            duplicate_form_rows.append(item)

    released_rows.sort(key=lambda row: int(row["sourceOrder"]))
    exclusions.sort(key=lambda item: next(
        int(row["sourceOrder"]) for row in raw["pals"] if row["rowName"] == item["sourceId"]
    ))
    exclusion_counts = dict(sorted(Counter(item["reason"] for item in exclusions).items()))
    require(exclusion_counts == EXPECTED_EXCLUSIONS, f"Released roster exclusion drift: {exclusion_counts}")
    require(len(released_rows) == 288, f"Unexpected released Pal count: {len(released_rows)}")
    fallback_icon_rows = [
        row for row in released_rows if pal_id(row["rowName"]) not in icon_ids
    ]
    require(
        duplicate_form_group_count == 9 and len(duplicate_form_rows) == 11,
        "Unexpected duplicate fixed-asset public-form resolution",
    )
    require(
        len(fallback_icon_rows) == 1
        and public_form_key(fallback_icon_rows[0]) not in {
            public_form_key(row)
            for row in released_rows
            if pal_id(row["rowName"]) in icon_ids
        },
        "Unexpected tribe-icon fallback public form",
    )

    japanese_names = {**raw["japaneseNames"], **{key.lower(): value for key, value in raw["japaneseNames"].items()}}
    english_names = {**raw["englishNames"], **{key.lower(): value for key, value in raw["englishNames"].items()}}
    source_rows: dict[str, dict[str, Any]] = {}
    released: list[dict[str, Any]] = []
    for row in released_rows:
        identifier = pal_id(row["rowName"])
        require(identifier not in source_rows, f"Duplicate released internal ID: {identifier}")
        name_key = str(row.get("overrideNameTextId") or "")
        if name_key.lower() in {"", "none"}:
            name_key = f"PAL_NAME_{row['rowName']}"
        suffix = str(row["zukanIndexSuffix"] or "")
        elements = element_list(row)
        english = display_name(row, english_names)
        japanese = display_name(row, japanese_names)
        require(english and japanese and elements, f"Released Pal metadata is incomplete: {row['rowName']}")
        work = {str(key).lower(): int(value) for key, value in row["workSuitability"].items() if int(value) > 0}
        model = {
            "id": identifier,
            "sourceId": row["rowName"],
            "tribe": enum_tail(row["tribe"]),
            "jp": japanese,
            "en": english,
            "nameTextId": name_key,
            "no": int(row["zukanIndex"]),
            "suffix": suffix,
            "displayNo": f"{int(row['zukanIndex'])}{suffix}",
            "variant": bool(suffix),
            "power": int(row["combiRank"]),
            "combiRank": int(row["combiRank"]),
            "combiDuplicatePriority": int(row["combiDuplicatePriority"]),
            "rarity": int(row["rarity"]),
            "ignoreCombi": bool(row["ignoreCombi"]),
            "isPal": bool(row["isPal"]),
            "isBoss": bool(row["isBoss"]),
            "isRaidBoss": bool(row["isRaidBoss"]),
            "isTowerBoss": bool(row["isTowerBoss"]),
            "sourceOrder": int(row["sourceOrder"]),
            "elements": elements,
            "work": work,
            "icon": "",
        }
        source_rows[identifier] = model
        released.append(model)

    released.sort(key=lambda value: (
        value["no"], value["suffix"], value["sourceOrder"], value["id"]
    ))
    order = [value["id"] for value in released]
    output_index = {identifier: index for index, identifier in enumerate(order)}
    released_ids = set(order)
    require(len(released_ids) == len(released), "Released ID duplication")
    released_source_ids_sha256 = stable_digest(
        sorted(value["sourceId"] for value in released)
    )
    require(
        released_source_ids_sha256 == RELEASED_SOURCE_IDS_SHA256,
        "Fixed-build released source-ID decision set drifted",
    )

    pals_by_tribe: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for value in released:
        pals_by_tribe[value["tribe"].lower()].append(value)
    unique_specials: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    raw_special_duplicates: list[dict[str, Any]] = []
    excluded_specials: list[dict[str, str]] = []
    for row in raw["combinations"]:
        parent_a = pals_by_tribe.get(enum_tail(row["parentTribeA"]).lower(), [])
        parent_b = pals_by_tribe.get(enum_tail(row["parentTribeB"]).lower(), [])
        child = source_rows.get(pal_id(row["childCharacterId"]))
        if not parent_a or not parent_b or child is None:
            excluded_specials.append({"sourceRow": row["rowName"], "reason": "SPECIAL_COMBINATION_NOT_RELEASED"})
            continue
        require(len(parent_a) == len(parent_b) == 1, f"Ambiguous special parent tribe: {row['rowName']}")
        recipe = {
            "sourceRow": row["rowName"],
            "parentA": parent_a[0]["id"],
            "genderA": gender(row["parentGenderA"]),
            "parentB": parent_b[0]["id"],
            "genderB": gender(row["parentGenderB"]),
            "child": child["id"],
        }
        signature = canonical_row(
            recipe["parentA"], recipe["genderA"], recipe["parentB"], recipe["genderB"], recipe["child"]
        )
        if signature in unique_specials:
            raw_special_duplicates.append({
                "duplicateSourceRow": row["rowName"],
                "keptSourceRow": unique_specials[signature]["sourceRow"],
                "signature": list(signature),
            })
        else:
            unique_specials[signature] = recipe
    specials = list(unique_specials.values())
    require(len(excluded_specials) == 73, f"Unexpected unreleased special row count: {len(excluded_specials)}")
    require(len(specials) == 184 and len(raw_special_duplicates) == 1,
            f"Unexpected valid/deduplicated special rows: {len(specials)}/{len(raw_special_duplicates)}")
    require(sum(item["parentA"] != item["parentB"] for item in specials) == 81,
            "Unexpected released non-self special recipe count")

    special_by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for recipe in specials:
        special_by_pair[pair_key(recipe["parentA"], recipe["parentB"])].append(recipe)
    all_unique_child_ids = {pal_id(row["childCharacterId"]) for row in raw["combinations"]}
    special_children = all_unique_child_ids & released_ids
    resolved_special_children = {recipe["child"] for recipe in specials}
    require(special_children == resolved_special_children,
            "An unreleased special recipe introduces a different released unique-only child")
    normal_candidates_with_ignore = [value for value in released if value["id"] not in special_children]
    normal_candidates = [value for value in normal_candidates_with_ignore if not value["ignoreCombi"]]
    require(len(special_children) == 103, f"Unexpected special-only child count: {len(special_children)}")
    require(len(normal_candidates) == 184, f"Normal child candidate pool drift: {len(normal_candidates)}")

    children: list[int] = []
    overrides: list[dict[str, Any]] = []
    authoritative_rows: set[tuple[str, str, str, str, str]] = set()
    recipe_types: dict[tuple[str, str, str, str, str], str] = {}
    formula_details: dict[str, dict[str, Any]] = {}
    for first_index, first in enumerate(released):
        for second_index in range(first_index, len(released)):
            second = released[second_index]
            matrix_index = len(children)
            require(matrix_index == pair_index(len(released), first_index, second_index), "Triangular index drift")
            outcomes: list[tuple[str, str, dict[str, Any], str]] = []
            pair_specials = special_by_pair.get(pair_key(first["id"], second["id"]), [])
            if pair_specials:
                for first_gender, second_gender in (("FEMALE", "MALE"), ("MALE", "FEMALE")):
                    matching = [
                        item for item in pair_specials
                        if special_matches(item, first, first_gender, second, second_gender)
                    ]
                    require(len(matching) == 1,
                            f"Special gender resolution conflict: {first['id']}:{first_gender}|{second['id']}:{second_gender}")
                    outcomes.append((first_gender, second_gender, source_rows[matching[0]["child"]], "special"))
                if len({(item[2]["id"], item[3]) for item in outcomes}) == 1:
                    outcomes = [("WILDCARD", "WILDCARD", outcomes[0][2], outcomes[0][3])]
            else:
                child = normal_child((first, second), normal_candidates)
                outcomes.append(("WILDCARD", "WILDCARD", child, "normal"))
                target = (first["combiRank"] + second["combiRank"] + 1) // 2
                formula_details[pair_key(first["id"], second["id"])] = {
                    "target": target,
                    "child": child["id"],
                    "distance": abs(child["combiRank"] - target),
                }
            children.append(output_index[outcomes[0][2]["id"]])
            if len(outcomes) > 1:
                override_rows = []
                for first_gender, second_gender, child, recipe_type in outcomes:
                    override_rows.append({
                        "parent1": first_index,
                        "parent1Gender": first_gender,
                        "parent2": second_index,
                        "parent2Gender": second_gender,
                        "child": output_index[child["id"]],
                    })
                    signature = canonical_row(first["id"], first_gender, second["id"], second_gender, child["id"])
                    require(signature not in authoritative_rows, f"Duplicate generated logical row: {signature}")
                    authoritative_rows.add(signature)
                    recipe_types[signature] = recipe_type
                overrides.append({"pairIndex": matrix_index, "pair": [first_index, second_index], "rows": override_rows})
            else:
                first_gender, second_gender, child, recipe_type = outcomes[0]
                signature = canonical_row(first["id"], first_gender, second["id"], second_gender, child["id"])
                require(signature not in authoritative_rows, f"Duplicate generated logical row: {signature}")
                authoritative_rows.add(signature)
                recipe_types[signature] = recipe_type

    expected_pairs = len(released) * (len(released) + 1) // 2
    require(expected_pairs == len(children) == 41_616, f"Pair count drift: {len(children)}")
    require(len(authoritative_rows) == 41_617, f"Logical row count drift: {len(authoritative_rows)}")
    require(len(overrides) == 1 and len(overrides[0]["rows"]) == 2, "Gender-dependent pair drift")
    override_pair = pair_key(order[overrides[0]["pair"][0]], order[overrides[0]["pair"][1]])
    require(override_pair == "catmage|foxmage", f"Unexpected gender-dependent pair: {override_pair}")
    zero_parent_candidate_child_ids = sorted(released_ids - {row[4] for row in authoritative_rows})
    require(zero_parent_candidate_child_ids == ["kingwhale", "plantslime_flower"],
            f"Reverse-index zero-candidate set drifted: {zero_parent_candidate_child_ids}")

    compact = {
        "schemaVersion": 3,
        "datasetId": DATASET_ID,
        "gameVersion": GAME_VERSION,
        "targetServerBuildId": SERVER_BUILD_ID,
        "palOrder": order,
        "children": children,
        "genderOverrides": overrides,
    }
    decoded_rows = decode_compact(compact)
    compact_missing = authoritative_rows - decoded_rows
    compact_extra = decoded_rows - authoritative_rows

    palcalc_breeding = json.loads(references["palcalcBreeding"])
    palcalc_rows: list[tuple[str, str, str, str, str]] = []
    palcalc_unreleased: list[dict[str, Any]] = []
    for row in palcalc_breeding["Breeding"]:
        signature = canonical_row(
            row["Parent1InternalName"], row["Parent1Gender"],
            row["Parent2InternalName"], row["Parent2Gender"], row["ChildInternalName"],
        )
        if signature[0] in released_ids and signature[2] in released_ids and signature[4] in released_ids:
            palcalc_rows.append(signature)
        else:
            palcalc_unreleased.append({
                "parent1": signature[0], "parent2": signature[2], "child": signature[4]
            })
    palcalc_duplicates = [
        {"signature": list(value), "count": count}
        for value, count in Counter(palcalc_rows).items() if count > 1
    ]
    palcalc_set = set(palcalc_rows)
    palcalc_missing_rows = authoritative_rows - palcalc_set
    palcalc_extra_rows = palcalc_set - authoritative_rows
    palcalc_db = json.loads(references["palcalcDb"])
    db_released = {
        pal_id(item["InternalName"]): item
        for item in palcalc_db["Pals"]
        if 0 < int(item["Id"]["PalDexNo"]) < 10_000
    }
    db_synthetic = sorted(
        {
            pal_id(item["InternalName"])
            for item in palcalc_db["Pals"]
            if int(item["Id"]["PalDexNo"]) >= 10_000
        }
    )
    db_released_ids = set(db_released)
    db_missing_released = sorted(released_ids - db_released_ids)
    db_extra_released = sorted(db_released_ids - released_ids)
    metadata_differences: list[dict[str, Any]] = []
    variant_model_differences: list[dict[str, Any]] = []
    for identifier in sorted(released_ids & db_released_ids):
        asset = source_rows[identifier]
        reference = db_released[identifier]
        comparisons = {
            "zukanIndex": (asset["no"], int(reference["Id"]["PalDexNo"])),
            "combiRank": (asset["combiRank"], int(reference["BreedingPower"])),
            "combiDuplicatePriority": (asset["combiDuplicatePriority"], int(reference["BreedingPowerPriority"])),
            "rarity": (asset["rarity"], int(reference["Rarity"])),
            "englishName": (asset["en"], str(reference["LocalizedNames"]["en"]).strip()),
            "japaneseName": (asset["jp"], str(reference["LocalizedNames"]["ja"]).strip()),
        }
        for field, (actual, expected) in comparisons.items():
            if actual != expected:
                metadata_differences.append({"pal": identifier, "field": field, "asset": actual, "reference": expected})
        reference_variant = bool(reference["Id"]["IsVariant"])
        if asset["variant"] != reference_variant:
            variant_model_differences.append({
                "pal": identifier,
                "assetZukanIndexSuffix": asset["suffix"],
                "assetVariant": asset["variant"],
                "referenceVariant": reference_variant,
            })
    native_raw_candidates = [
        {
            "id": pal_id(row["rowName"]),
            "combiRank": int(row["combiRank"]),
            "combiDuplicatePriority": int(row["combiDuplicatePriority"]),
            "sourceOrder": int(row["sourceOrder"]),
        }
        for row in raw["pals"]
        if not bool(row["isBoss"])
        and not bool(row["ignoreCombi"])
        and pal_id(row["rowName"]) not in all_unique_child_ids
    ]
    native_unpublished_candidates = sorted(
        value["id"] for value in native_raw_candidates if value["id"] not in released_ids
    )
    require(native_unpublished_candidates == ["quest_farmer03_pinkcat", "quest_farmer03_sheepball"],
            f"Native unpublished candidate set drifted: {native_unpublished_candidates}")
    native_candidate_differences: list[dict[str, Any]] = []
    rarity_differences: list[dict[str, Any]] = []
    ignore_differences: list[dict[str, Any]] = []
    variant_tie_differences: list[dict[str, Any]] = []
    for first_index, first in enumerate(released):
        for second in released[first_index:]:
            signature_key = pair_key(first["id"], second["id"])
            if signature_key in special_by_pair:
                continue
            actual = normal_child((first, second), normal_candidates)
            native_result = normal_child((first, second), native_raw_candidates)
            if native_result["id"] != actual["id"]:
                native_candidate_differences.append({
                    "pair": signature_key,
                    "releasedTableResult": actual["id"],
                    "fullNativeCandidatePoolResult": native_result["id"],
                })
            rarity_child = rarity_counterfactual_child((first, second), normal_candidates)
            if rarity_child["id"] != actual["id"]:
                rarity_differences.append({
                    "pair": signature_key,
                    "duplicatePriorityResult": actual["id"],
                    "rarityCounterfactualResult": rarity_child["id"],
                })
            ignore_child = normal_child((first, second), normal_candidates_with_ignore)
            if ignore_child["id"] != actual["id"]:
                ignore_differences.append({
                    "pair": signature_key,
                    "nativeIgnoreCombiExclusionResult": actual["id"],
                    "ignoreCombiIncludedResult": ignore_child["id"],
                })
            variant_child = variant_tie_counterfactual_child((first, second), normal_candidates)
            if variant_child["id"] != actual["id"]:
                variant_tie_differences.append({
                    "pair": signature_key,
                    "nativeRowOrderResult": actual["id"],
                    "variantFirstCounterfactualResult": variant_child["id"],
                })
    require(rarity_differences, "Rarity counterfactual unexpectedly has no distinguishing cases")

    authoritative_pair_map: dict[str, set[str]] = defaultdict(set)
    for row in authoritative_rows:
        authoritative_pair_map[pair_key(row[0], row[2])].add(row[4])
    site_pair_map: dict[str, set[str]] = defaultdict(set)
    for row in decoded_rows:
        site_pair_map[pair_key(row[0], row[2])].add(row[4])
    exact_pair_comparison = compare_pair_map(authoritative_pair_map, site_pair_map)
    pst = auxiliary.load_pst(references["palworldSaveTools"].decode("utf-8-sig"))
    paldeck = auxiliary.load_paldeck(references["paldeck"].decode("utf-8-sig"))
    pst_pairs = {
        key: {child for child in children if child in released_ids}
        for key, children in pst["pairs"].items()
        if all(parent in released_ids for parent in key.split("|"))
    }
    pst_pairs = {key: children for key, children in pst_pairs.items() if children}
    paldeck_pairs = {
        key: {child for child in children if child in released_ids}
        for key, children in paldeck["pairs"].items()
        if all(parent in released_ids for parent in key.split("|"))
    }
    paldeck_pairs = {key: children for key, children in paldeck_pairs.items() if children}
    auxiliary_comparisons = {
        "palCalc": {
            "role": "pinned-comparison-only",
            "releasedRosterCount": len(db_released),
            "releasedRosterMissing": db_missing_released,
            "releasedRosterExtra": db_extra_released,
            "logicalRowCount": len(palcalc_rows),
            "matchingLogicalRowCount": len(palcalc_set & authoritative_rows),
            "mismatchCount": len(palcalc_missing_rows) + len(palcalc_extra_rows),
            "missingRows": row_objects(palcalc_missing_rows),
            "extraRows": row_objects(palcalc_extra_rows),
            "duplicateRows": palcalc_duplicates,
            "unreleasedRowsExcludedFromComparison": palcalc_unreleased,
            "metadataDifferences": metadata_differences,
            "variantModelDifferences": variant_model_differences,
            "syntheticPalDexEntriesExcludedFromComparison": db_synthetic,
            "calculationSemanticsObserved": palcalc_semantics,
            "usedForAssetReleaseSelection": False,
        },
        "palworldSaveTools": {
            "role": "advisory-overlap-comparison-only",
            "releasedRosterCoverage": len(set(pst["pals"]) & released_ids),
            "missingReleasedPals": sorted(released_ids - set(pst["pals"])),
            **compare_pair_map(authoritative_pair_map, pst_pairs),
        },
        "paldeck": {
            "role": "advisory-overlap-comparison-only",
            "releasedRosterCoverage": len(set(paldeck["pals"]) & released_ids),
            "missingReleasedPals": sorted(released_ids - set(paldeck["pals"])),
            **compare_pair_map(authoritative_pair_map, paldeck_pairs),
        },
    }
    native_self_expected: dict[str, set[str]] = {}
    for pal in released:
        key = pair_key(pal["id"], pal["id"])
        pair_specials = special_by_pair.get(key, [])
        expected_children = {item["child"] for item in pair_specials}
        if not expected_children:
            expected_children = {normal_child((pal, pal), native_raw_candidates)["id"]}
        require(len(expected_children) == 1, f"Self-pair native result is ambiguous: {key}")
        native_self_expected[key] = expected_children
    same_species_mismatches = [
        {
            "pair": key,
            "nativeExpected": sorted(expected),
            "siteResults": sorted(site_pair_map.get(key, set())),
        }
        for key, expected in sorted(native_self_expected.items())
        if site_pair_map.get(key, set()) != expected
    ]
    same_species_identity_exceptions = [
        {
            "pair": pair_key(identifier, identifier),
            "parent": identifier,
            "nativeResult": next(iter(native_self_expected[pair_key(identifier, identifier)])),
        }
        for identifier in sorted(released_ids)
        if native_self_expected[pair_key(identifier, identifier)] != {identifier}
    ]
    require(same_species_identity_exceptions == [
        {"pair": "kingwhale|kingwhale", "parent": "kingwhale", "nativeResult": "domearmordragon"},
        {"pair": "plantslime_flower|plantslime_flower", "parent": "plantslime_flower", "nativeResult": "plantslime"},
    ], f"Native same-species identity exceptions drifted: {same_species_identity_exceptions}")
    gender_rows = [row for row in decoded_rows if row[1] != "WILDCARD" or row[3] != "WILDCARD"]
    gender_condition_mismatches: list[dict[str, Any]] = []
    expected_gender_rows = {
        canonical_row("catmage", "FEMALE", "foxmage", "MALE", "catmage_fire"),
        canonical_row("catmage", "MALE", "foxmage", "FEMALE", "foxmage_dark"),
    }
    if set(gender_rows) != expected_gender_rows:
        gender_condition_mismatches = row_objects(set(gender_rows) ^ expected_gender_rows)

    unreleased_contamination = sorted(
        {value for row in decoded_rows for value in (row[0], row[2], row[4]) if value not in released_ids}
    )
    missing_rows = authoritative_rows - decoded_rows
    extra_rows = decoded_rows - authoritative_rows
    exact_mismatch_count = len(missing_rows) + len(extra_rows)
    different_pair_keys = {
        item["pair"] for item in exact_pair_comparison["mismatches"]
    } | set(exact_pair_comparison["missingPairs"]) | set(exact_pair_comparison["extraPairs"])
    non_self_special_pairs = {
        pair_key(item["parentA"], item["parentB"])
        for item in specials if item["parentA"] != item["parentB"]
    }
    special_combination_mismatches = sorted(different_pair_keys & non_self_special_pairs)
    tie_break_mismatches = sorted(different_pair_keys - non_self_special_pairs)
    complete_failures = {
        "missingRows": row_objects(missing_rows),
        "extraRows": row_objects(extra_rows),
        "missingPairs": exact_pair_comparison["missingPairs"],
        "extraPairs": exact_pair_comparison["extraPairs"],
        "pairResultMismatches": exact_pair_comparison["mismatches"],
        "compactMissingRows": row_objects(compact_missing),
        "compactExtraRows": row_objects(compact_extra),
        "sameSpeciesMismatches": same_species_mismatches,
        "genderConditionMismatches": gender_condition_mismatches,
        "unreleasedPalIds": unreleased_contamination,
        "referenceDuplicates": [],
    }

    pals_payload = {
        "schemaVersion": 2,
        "datasetId": DATASET_ID,
        "gameVersion": GAME_VERSION,
        "targetServerBuildId": SERVER_BUILD_ID,
        "pals": released,
    }
    pals_bytes = (json.dumps(pals_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    breeding_bytes = (json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    generated_data_sha256 = stable_digest({"pals": released, "rows": row_objects(authoritative_rows)})
    native_runtime = validate_native_runtime_evidence(
        runtime_bytes, pals_bytes, breeding_bytes, released, raw["pals"]
    )

    ignore_true = sorted(value["id"] for value in released if value["ignoreCombi"])
    ignore_special = sorted(set(ignore_true) & special_children)
    ignore_non_special = sorted(set(ignore_true) - special_children)
    exact_comparison = {
        "schemaVersion": 1,
        "datasetId": DATASET_ID,
        "target": {
            "gameVersion": GAME_VERSION,
            "clientAppId": CLIENT_APP_ID,
            "clientBuildId": CLIENT_BUILD_ID,
            "serverAppId": SERVER_APP_ID,
            "serverBuildId": SERVER_BUILD_ID,
            "serverDepotId": SERVER_DEPOT_ID,
            "serverDepotManifestId": SERVER_DEPOT_MANIFEST_ID,
            "clientAppmanifestSha256": exact["sourceClient"]["appmanifestSha256"],
            "serverAppmanifestSha256": exact["targetServer"]["appmanifestSha256"],
            "serverPakSha256": SERVER_PAK_SHA256,
            "serverPakBytes": SERVER_PAK_BYTES,
            "mappingsUsmapSha256": exact["catalog"]["mappingsUsmapSha256"],
            "catalogContentHash": exact["catalog"]["contentHash"],
            "catalogPackageSha256": exact["catalog"]["packageSha256"],
            "acceptedCatalogExtractorCommit": exact["catalog"]["extractorCommit"],
            "rawAssetExtractorRepository": RAW_EXTRACTOR_REPOSITORY,
            "rawAssetExtractorCommit": RAW_EXTRACTOR_COMMIT,
            "rawAssetExtractorSourceSha256": RAW_EXTRACTOR_SOURCE_SHA256,
            "rawAssetExtractionSha256": RAW_ASSETS_SHA256,
            "nativeBreedingEvidenceSha256": NATIVE_EVIDENCE_SHA256,
            "nativeRuntimeEvidencePath": "audit/native-runtime-comparison.json",
            "nativeRuntimeEvidenceSha256": NATIVE_RUNTIME_EVIDENCE_SHA256,
            "nativeRuntimeEvidenceDigest": NATIVE_RUNTIME_EVIDENCE_DIGEST,
            "nativeRuntimeWorkflowRunId": NATIVE_RUNTIME_WORKFLOW_RUN_ID,
            "nativeRuntimeWorkflowHeadSha": NATIVE_RUNTIME_WORKFLOW_HEAD_SHA,
            "nativeRuntimeArtifactId": NATIVE_RUNTIME_ARTIFACT_ID,
            "nativeRuntimeArtifactZipSha256": NATIVE_RUNTIME_ARTIFACT_ZIP_SHA256,
            "serverExecutableSha256": native["executable"]["sha256"],
            "serverExecutableBytes": native["executable"]["bytes"],
            "serverExecutableElfBuildId": native["executable"]["elfBuildId"],
            "serverDepotManifestSha256": native["target"]["depotManifestSha256"],
        },
        "counts": {
            "rawPalRows": len(raw["pals"]),
            "releasedPals": len(released),
            "unorderedParentPairs": expected_pairs,
            "logicalResultRows": len(authoritative_rows),
            "matchingPairs": exact_pair_comparison["matchingPairCount"],
            "matchingLogicalRows": len(decoded_rows & authoritative_rows),
            "mismatches": exact_mismatch_count,
            "missingRows": len(missing_rows),
            "extraRows": len(extra_rows),
            "unreleasedPalContamination": len(unreleased_contamination),
            "genderConditionMismatches": len(gender_condition_mismatches),
            "sameSpeciesMismatches": len(same_species_mismatches),
            "specialCombinationMismatches": len(special_combination_mismatches),
            "tieBreakMismatches": len(tie_break_mismatches),
            "duplicates": 0,
            "zeroParentCandidateChildren": len(zero_parent_candidate_child_ids),
        },
        "rosterSelection": {
            "ruleSource": (
                "fixed-build DT_PalMonsterParameter and DT_PalCharacterIconDataTable fields only"
            ),
            "rowNamePatternInferenceUsed": False,
            "publicFormKeyFields": ["ZukanIndex", "ZukanIndexSuffix", "Rarity"],
            "duplicateFormResolution": (
                "within an identical public-form key, retain the single row with its own exact "
                "DT_PalCharacterIconDataTable ID; do not classify RowName prefixes or suffixes"
            ),
            "duplicateFormGroupCount": duplicate_form_group_count,
            "duplicateFormRowsExcludedCount": len(duplicate_form_rows),
            "tribeIconFallbackReleasedCount": len(fallback_icon_rows),
            "tribeIconFallbackReleasedSourceIds": sorted(
                str(row["rowName"]) for row in fallback_icon_rows
            ),
            "releasedSourceIdsSha256": released_source_ids_sha256,
            "exclusionCounts": exclusion_counts,
            "excluded": exclusions,
        },
        "specialCombinations": {
            "rawRows": len(raw["combinations"]),
            "releasedResolvedRowsBeforeDeduplication": len(specials) + len(raw_special_duplicates),
            "releasedUniqueRows": len(specials),
            "releasedNonSelfRows": sum(item["parentA"] != item["parentB"] for item in specials),
            "releasedSelfRows": sum(item["parentA"] == item["parentB"] for item in specials),
            "unreleasedRows": len(excluded_specials),
            "rawDuplicateRows": raw_special_duplicates,
            "excludedRows": excluded_specials,
            "genderDependentPair": override_pair,
        },
        "ignoreCombiAnalysis": {
            "releasedTrueCount": len(ignore_true),
            "releasedTrueIds": ignore_true,
            "alreadyExcludedAsSpecialChildrenCount": len(ignore_special),
            "alreadyExcludedAsSpecialChildren": ignore_special,
            "remainingIds": ignore_non_special,
            "normalChildPoolCounterfactualDifferenceCount": len(ignore_differences),
            "normalChildPoolCounterfactualDifferences": ignore_differences,
            "nativeRuntimeRoleDetermined": True,
            "nativeRuntimeRole": "excluded only from the normal child candidate pool; parent rank reads do not test the flag",
            "nativeEvidence": "evidence/build-24181105.native-breeding.json",
            "conclusionForThisDataset": (
                "The fixed-build executable checks IgnoreCombi while enumerating normal children and not while "
                "reading parent ranks. Including the flagged rows changes exactly KingWhale + KingWhale from "
                "DomeArmorDragon to KingWhale, so the native exclusion has one observable output in this build."
            ),
        },
        "nativeTieBreakAnalysis": {
            "evidence": "evidence/build-24181105.native-breeding.json",
            "normalTarget": native["conclusions"]["normalTarget"],
            "firstTieBreaker": native["conclusions"]["firstTieBreaker"],
            "finalTieBreaker": native["conclusions"]["finalTieBreaker"],
            "rarityUsed": native["conclusions"]["rarityUsedAsTieBreaker"],
            "variantFlagUsed": native["conclusions"]["variantFlagUsedAsTieBreaker"],
            "variantFirstCounterfactualDifferenceCount": len(variant_tie_differences),
            "variantFirstCounterfactualDifferences": variant_tie_differences,
        },
        "normalTargetAnalysis": {
            "baseFormula": native["conclusions"]["normalTarget"],
            "nativeItemEffectAdjustment": native["conclusions"]["combiRankBonusClamp"],
            "fixedBuildBreedingItemEffectPath": raw["breedingItemEffectPath"],
            "fixedBuildEffectEntryCount": len(raw["breedingItemEffects"]),
            "fixedBuildCombiRankBonusValues": sorted({
                int(item["combiRankBonus"]) for item in raw["breedingItemEffects"]
            }),
            "conclusion": (
                "The native function can add a clamped breeding-item CombiRankBonus, but every effect entry "
                "published in this fixed build has value 0. Therefore all fixed-build items use the base formula."
            ),
        },
        "nativeUnpublishedCandidateAnalysis": {
            "nativeCandidateFilter": "not IsBoss, not IgnoreCombi, not a DT_PalCombiUnique child",
            "fullCandidateCount": len(native_raw_candidates),
            "releasedCandidateCount": len(native_raw_candidates) - len(native_unpublished_candidates),
            "unpublishedCandidateCount": len(native_unpublished_candidates),
            "unpublishedCandidateIds": native_unpublished_candidates,
            "allNormalPairsCompared": sum(
                1 for first_index, first in enumerate(released)
                for second in released[first_index:]
                if pair_key(first["id"], second["id"]) not in special_by_pair
            ),
            "outputDifferenceCount": len(native_candidate_differences),
            "outputDifferences": native_candidate_differences,
            "conclusion": (
                "Two quest rows pass the native child filter, but both lose deterministic ties to their released "
                "base rows. They change zero public-parent results and are never emitted by the site."
            ),
        },
        "sameSpeciesNativeAnalysis": {
            "nativeTopLevelHasSameSpeciesShortcut": native["conclusions"]["sameSpeciesShortcut"],
            "nativeResolution": native["conclusions"]["sameSpeciesResolution"],
            "allReleasedSelfPairsCompared": len(native_self_expected),
            "identityResultCount": len(native_self_expected) - len(same_species_identity_exceptions),
            "identityExceptionCount": len(same_species_identity_exceptions),
            "identityExceptions": same_species_identity_exceptions,
            "siteMismatchCount": len(same_species_mismatches),
            "siteMismatches": same_species_mismatches,
            "nativeTopLevelFunctionInvokedForEveryPair": True,
            "conclusion": (
                "The fixed executable's complete top-level orchestration checks special combinations and then "
                "falls through to normal candidate selection without a parent-equality branch. Applying that "
                "control flow to all 288 self pairs yields 286 identity results and two asset-derived exceptions. "
                "All released parent pairs were also invoked directly in the fixed native function. "
                "The auxiliary same-species shortcut is therefore not treated as authoritative."
            ),
        },
        "reverseIndexAnalysis": {
            "releasedChildCount": len(released),
            "childrenWithAtLeastOneParentPair": len(released) - len(zero_parent_candidate_child_ids),
            "zeroParentCandidateChildCount": len(zero_parent_candidate_child_ids),
            "zeroParentCandidateChildIds": zero_parent_candidate_child_ids,
            "reason": (
                "These two forms are the native self-pair identity exceptions and no other released-parent "
                "pair resolves to them. Reverse lookup reports an empty candidate list instead of inventing an edge."
            ),
        },
        "rarityTieCounterevidence": {
            "counterfactual": "closest child rarity to the two-parent rarity average, then lower rarity",
            "differenceCountOnNormalNonSpecialPairs": len(rarity_differences),
            "differenceDigest": stable_digest(rarity_differences),
            "differences": rarity_differences,
        },
        "exactReferenceComparison": {
            "reference": (
                "logical rows regenerated directly from the fixed-build asset extraction using the committed "
                "native-static semantics; compared with the site's decoded compact table"
            ),
            "independentNativeOracle": False,
            "referenceLogicalRows": len(authoritative_rows),
            "siteLogicalRows": len(decoded_rows),
            "matchingLogicalRows": len(decoded_rows & authoritative_rows),
            "mismatchCount": exact_mismatch_count,
            "pairComparison": exact_pair_comparison,
            "specialCombinationMismatchPairs": special_combination_mismatches,
            "tieBreakMismatchPairs": tie_break_mismatches,
            **complete_failures,
        },
        "nativeRuntimeComparison": {
            "evidencePath": "audit/native-runtime-comparison.json",
            "evidenceFileSha256": NATIVE_RUNTIME_EVIDENCE_SHA256,
            "evidenceDigest": NATIVE_RUNTIME_EVIDENCE_DIGEST,
            "workflowRunId": NATIVE_RUNTIME_WORKFLOW_RUN_ID,
            "workflowHeadSha": NATIVE_RUNTIME_WORKFLOW_HEAD_SHA,
            "artifactId": NATIVE_RUNTIME_ARTIFACT_ID,
            "artifactZipSha256": NATIVE_RUNTIME_ARTIFACT_ZIP_SHA256,
            "scope": (
                "fixed native breeding function with exact extracted asset tables injected by "
                "the audit harness"
            ),
            "instrumentedLookupPoints": [
                "raw DT FindRow at 0x713d270",
                "unique-combination DT FindRow at 0x7118880",
                "DT row-key generation at 0xa2f9f40",
                "manager FindRow at 0x713a280",
                "manager helper at 0x76459e0",
            ],
            "livePakDataTablesReadDirectly": False,
            "selectionOrRecipeLogicStubbed": native_runtime["invocation"][
                "selectionOrRecipeLogicStubbed"
            ],
            "unorderedParentPairs": native_runtime["counts"]["unorderedParentPairs"],
            "logicalResultRows": native_runtime["counts"]["logicalResultRows"],
            "matchingLogicalResultRows": native_runtime["counts"]["matchingLogicalResultRows"],
            "nativeInvocationCount": native_runtime["counts"]["nativeInvocations"],
            "differenceCount": sum(native_runtime["differences"].values()),
            "differences": native_runtime["differences"],
            "allDifferences": native_runtime["allDifferences"],
            "runtimeTableIdentity": native_runtime["runtimeTableIdentity"],
            "serverInitialization": native_runtime["serverInitialization"],
            "bossAlphaSpeciesMapping": {
                "mappingCount": native_runtime["bossAlphaPostProcessing"]["mappingCount"],
                "mismatchCount": native_runtime["bossAlphaPostProcessing"]["mismatchCount"],
                "speciesIdentityPreserved": native_runtime["bossAlphaPostProcessing"][
                    "speciesIdentityPreserved"
                ],
            },
        },
        "auxiliaryImplementations": auxiliary_comparisons,
        "referenceFiles": reference_metadata,
        "generated": {
            "palsJsonSha256": sha256(pals_bytes),
            "breedingJsonSha256": sha256(breeding_bytes),
            "logicalRowsSha256": stable_digest(row_objects(authoritative_rows)),
            "datasetSha256": generated_data_sha256,
        },
        "runtimeVerification": {
            "resultScope": "base-released-form-id",
            "nativeBreedingStaticAnalysis": True,
            "nativeBreedingFunctionExhaustive": True,
            "nativeBreedingFunctionInvocationCount": native_runtime["counts"]["nativeInvocations"],
            "nativeRuntimeMismatchCount": sum(native_runtime["differences"].values()),
            "fixedExtractedAssetTablesInjected": True,
            "livePakDataTablesReadDirectly": False,
            "inGameHatchExhaustive": False,
            "bossAlphaSpeciesMappingVerified": True,
            "bossAlphaAndIndividualStatePostProcessingModeled": False,
        },
    }

    verification = {
        "schemaVersion": 8,
        "appDataSchemaVersion": 2,
        "datasetId": DATASET_ID,
        "status": "fixed-build-native-runtime-matched",
        "gameVersion": GAME_VERSION,
        "sourceClientAppId": CLIENT_APP_ID,
        "sourceClientBuildId": CLIENT_BUILD_ID,
        "targetServerAppId": SERVER_APP_ID,
        "targetServerBuildId": SERVER_BUILD_ID,
        "targetServerDepotManifestId": SERVER_DEPOT_MANIFEST_ID,
        "serverPakSha256": SERVER_PAK_SHA256,
        "mappingsUsmapSha256": exact["catalog"]["mappingsUsmapSha256"],
        "catalogContentHash": exact["catalog"]["contentHash"],
        "rawAssetExtractionSha256": RAW_ASSETS_SHA256,
        "nativeBreedingEvidenceSha256": NATIVE_EVIDENCE_SHA256,
        "nativeRuntimeEvidenceSha256": NATIVE_RUNTIME_EVIDENCE_SHA256,
        "nativeRuntimeEvidenceDigest": NATIVE_RUNTIME_EVIDENCE_DIGEST,
        "serverExecutableSha256": native["executable"]["sha256"],
        "breedingItemEffectDataPath": raw["breedingItemEffectPath"],
        "breedingItemCombiRankBonusValues": sorted({
            int(item["combiRankBonus"]) for item in raw["breedingItemEffects"]
        }),
        "palCount": len(released),
        "unorderedPairCount": expected_pairs,
        "compactChildCount": len(children),
        "resultRowCount": len(authoritative_rows),
        "matchingResultRowCount": len(decoded_rows & authoritative_rows),
        "mismatchCount": exact_mismatch_count,
        "missingPairCount": exact_pair_comparison["missingPairCount"],
        "extraPairCount": exact_pair_comparison["extraPairCount"],
        "unreleasedPalContaminationCount": len(unreleased_contamination),
        "duplicateCount": 0,
        "zeroParentCandidateChildIds": zero_parent_candidate_child_ids,
        "genderDependentPairs": [override_pair],
        "exactGameAssetExtractionEvidence": True,
        "nativeBreedingStaticAnalysisEvidence": True,
        "nativeBreedingFunctionExhaustiveVerification": True,
        "nativeBreedingFunctionInvocationCount": native_runtime["counts"]["nativeInvocations"],
        "nativeRuntimeMismatchCount": sum(native_runtime["differences"].values()),
        "nativeRuntimeFixedExtractedAssetTablesInjected": True,
        "nativeRuntimeLivePakDataTablesReadDirectly": False,
        "gameRuntimeHatchExhaustiveVerification": False,
        "resultScope": "base-released-form-id",
        "bossAlphaSpeciesMappingVerified": True,
        "bossAlphaAndIndividualStatePostProcessingModeled": False,
        "currentBuildEndpoint": "https://api.steamcmd.net/v1/info/2394010",
        "palDataSha256": sha256(pals_bytes),
        "breedingDataSha256": sha256(breeding_bytes),
        "generatedDataSha256": generated_data_sha256,
    }

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "pals.verified.json").write_bytes(pals_bytes)
    (DATA_DIR / "breeding.verified.json").write_bytes(breeding_bytes)
    (DATA_DIR / "verification.json").write_bytes(
        (json.dumps(verification, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    (AUDIT_DIR / "exact-comparison.json").write_bytes(
        (json.dumps(exact_comparison, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )

    failed = any((
        exact_mismatch_count,
        compact_missing,
        compact_extra,
        same_species_mismatches,
        gender_condition_mismatches,
        unreleased_contamination,
        native_candidate_differences,
        variant_tie_differences,
        exact_pair_comparison["mismatches"],
        exact_pair_comparison["missingPairs"],
        exact_pair_comparison["extraPairs"],
    ))
    require(not failed, "Exact-build comparison failed; see audit/exact-comparison.json")
    print(json.dumps({
        "datasetId": DATASET_ID,
        "pals": len(released),
        "pairs": expected_pairs,
        "logicalRows": len(authoritative_rows),
        "nativeInvocations": native_runtime["counts"]["nativeInvocations"],
        "mismatches": exact_mismatch_count,
        "datasetSha256": generated_data_sha256,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
