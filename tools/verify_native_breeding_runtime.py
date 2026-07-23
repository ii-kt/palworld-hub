#!/usr/bin/env python3
"""Invoke the fixed server build's native breeding function exhaustively.

The server, PAK, mappings, or compiled probes are never committed. This tool
accepts an exact Steam depot root, verifies its hashes, builds two small audit
shared objects in a temporary directory, starts the server with all Internet
egress denied by the preload shim, and compares the real Build 24181105
breeding function with every verified public parent pair in both parent orders
and both meaningful gender orientations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PALWORLD = ROOT
RAW_ASSETS = PALWORLD / "evidence" / "build-24181105.assets.json"
NATIVE_STATIC = PALWORLD / "evidence" / "build-24181105.native-breeding.json"
PALS = PALWORLD / "data" / "pals.verified.json"
BREEDING = PALWORLD / "data" / "breeding.verified.json"
PROBE_SOURCE = PALWORLD / "tools" / "native_breeding_runtime_probe.c"
OFFLINE_SHIM_SOURCE = PALWORLD / "tools" / "fixed_server_nonroot_shim.c"
DEFAULT_OUTPUT = PALWORLD / "audit" / "native-runtime-comparison.json"

EXPECTED_SERVER_BUILD = "24181105"
EXPECTED_BINARY_BYTES = 196_285_592
EXPECTED_BINARY_SHA256 = "788649fa1592160faa7bcf07ccd16d474ebeaae954717bc32284b5a43028d8e7"
EXPECTED_PAK_BYTES = 4_797_040_962
EXPECTED_PAK_SHA256 = "cad80fe15c38d74a795779fbab31f04bc2c15c37fb8a2188e4d89f3800fb0e68"
EXPECTED_DEPOT_MANIFEST = "2167164727892555341"

HEADER = struct.Struct("<8s10I")
RAW_RECORD = struct.Struct("<iiiiBBH")
RELEASED_RECORD = struct.Struct("<HHi")
UNIQUE_RECORD = struct.Struct("<HHHBB")
PAIR_RECORD = struct.Struct("<HHHHBB2x")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


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


def gender_code(value: Any) -> int:
    value = enum_tail(value).upper()
    mapping = {"": 0, "NONE": 0, "MALE": 1, "FEMALE": 2}
    require(value in mapping, f"Unsupported gender in fixed assets: {value}")
    return mapping[value]


def fixed_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    raw = json.loads(RAW_ASSETS.read_text(encoding="utf-8"))
    pals = json.loads(PALS.read_text(encoding="utf-8"))
    breeding = json.loads(BREEDING.read_text(encoding="utf-8"))
    require(raw["buildId"] == EXPECTED_SERVER_BUILD, "Raw asset Build ID mismatch")
    require(pals["targetServerBuildId"] == EXPECTED_SERVER_BUILD, "Pal data Build ID mismatch")
    require(breeding["targetServerBuildId"] == EXPECTED_SERVER_BUILD, "Breeding data Build ID mismatch")
    require(len(raw["pals"]) == 753, "Raw pal row count mismatch")
    require(len(raw["combinations"]) == 258, "Raw unique-combination count mismatch")
    require(len(pals["pals"]) == 288, "Released pal count mismatch")
    require(len(breeding["children"]) == 41_616, "Compact pair count mismatch")
    return raw, pals, breeding


def build_runtime_input(path: Path) -> dict[str, Any]:
    raw, pals_document, breeding = fixed_inputs()
    raw_rows = raw["pals"]
    released = pals_document["pals"]
    raw_by_id = {pal_id(row["rowName"]): row for row in raw_rows}
    require(len(raw_by_id) == len(raw_rows), "Raw pal row IDs are not unique")
    raw_by_tribe: dict[str, list[dict[str, Any]]] = {}
    for row in raw_rows:
        raw_by_tribe.setdefault(enum_tail(row["tribe"]).lower(), []).append(row)
    tribe_ids = {tribe: index + 1 for index, tribe in enumerate(raw_by_tribe)}
    require(len(tribe_ids) <= 65_535, "Fixed-build tribe count exceeds audit encoding")

    released_by_tribe: dict[str, list[dict[str, Any]]] = {}
    for pal in released:
        key = str(pal["tribe"]).lower()
        released_by_tribe.setdefault(key, []).append(pal)
    released_index = {pal["id"]: index for index, pal in enumerate(released)}
    require(breeding["palOrder"] == [pal["id"] for pal in released], "Released order drift")

    special_pairs: set[str] = set()
    for row in raw["combinations"]:
        parent_a = released_by_tribe.get(enum_tail(row["parentTribeA"]).lower(), [])
        parent_b = released_by_tribe.get(enum_tail(row["parentTribeB"]).lower(), [])
        child = raw_by_id.get(pal_id(row["childCharacterId"]))
        if parent_a and parent_b and child is not None and pal_id(child["rowName"]) in released_index:
            require(len(parent_a) == len(parent_b) == 1,
                    f"Released special parent tribe is ambiguous: {row['rowName']}")
            special_pairs.add(pair_key(parent_a[0]["id"], parent_b[0]["id"]))

    payload = bytearray()
    logical_count = len(breeding["children"]) + sum(
        len(item["rows"]) - 1 for item in breeding["genderOverrides"]
    )
    payload.extend(HEADER.pack(
        b"PWNRT01\0", 1, len(raw_rows), len(released), len(raw["combinations"]),
        len(breeding["children"]), logical_count,
        RAW_RECORD.size, RELEASED_RECORD.size, UNIQUE_RECORD.size, PAIR_RECORD.size,
    ))
    for source_order, row in enumerate(raw_rows):
        require(row["sourceOrder"] == source_order, "Raw source order is not contiguous")
        payload.extend(RAW_RECORD.pack(
            source_order, int(row["combiRank"]), int(row["combiDuplicatePriority"]),
            int(row["zukanIndex"]), int(bool(row["isBoss"])), int(bool(row["ignoreCombi"])),
            tribe_ids[enum_tail(row["tribe"]).lower()],
        ))
    for pal in released:
        payload.extend(RELEASED_RECORD.pack(
            int(pal["sourceOrder"]), 0, int(pal["combiRank"]),
        ))
    for source_order, row in enumerate(raw["combinations"]):
        require(row["sourceOrder"] == source_order, "Unique source order is not contiguous")
        parent_a_rows = raw_by_tribe.get(enum_tail(row["parentTribeA"]).lower(), [])
        parent_b_rows = raw_by_tribe.get(enum_tail(row["parentTribeB"]).lower(), [])
        child = raw_by_id.get(pal_id(row["childCharacterId"]))
        require(parent_a_rows and parent_b_rows and child is not None,
                f"Unique row cannot be resolved: {row['rowName']}")
        payload.extend(UNIQUE_RECORD.pack(
            int(parent_a_rows[0]["sourceOrder"]), int(parent_b_rows[0]["sourceOrder"]),
            int(child["sourceOrder"]), gender_code(row["parentGenderA"]),
            gender_code(row["parentGenderB"]),
        ))

    override_by_index = {item["pairIndex"]: item for item in breeding["genderOverrides"]}
    packed_pair_count = 0
    for first in range(len(released)):
        for second in range(first, len(released)):
            index = pair_index(len(released), first, second)
            require(index == packed_pair_count, "Pair packing index drift")
            default_child = int(breeding["children"][index])
            female_male_child = default_child
            male_female_child = default_child
            gender_dependent = 0
            override = override_by_index.get(index)
            if override is not None:
                for row in override["rows"]:
                    orientation = (row["parent1Gender"], row["parent2Gender"])
                    if orientation == ("FEMALE", "MALE"):
                        female_male_child = int(row["child"])
                    elif orientation == ("MALE", "FEMALE"):
                        male_female_child = int(row["child"])
                    else:
                        raise RuntimeError(f"Unexpected override orientation: {orientation}")
                gender_dependent = int(female_male_child != male_female_child)
            recipe_type = 2 if pair_key(released[first]["id"], released[second]["id"]) in special_pairs else 1
            payload.extend(PAIR_RECORD.pack(
                first, second, female_male_child, male_female_child,
                gender_dependent, recipe_type,
            ))
            packed_pair_count += 1

    expected_size = HEADER.size + len(raw_rows) * RAW_RECORD.size + len(released) * RELEASED_RECORD.size + \
        len(raw["combinations"]) * UNIQUE_RECORD.size + len(breeding["children"]) * PAIR_RECORD.size
    require(len(payload) == expected_size, "Runtime input size mismatch")
    require(logical_count == 41_617, "Logical row count mismatch")
    path.write_bytes(payload)
    return {
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "rawPalRows": len(raw_rows),
        "releasedPals": len(released),
        "uniqueRows": len(raw["combinations"]),
        "pairs": len(breeding["children"]),
        "logicalRows": logical_count,
        "specialPairs": len(special_pairs),
        "tribes": len(tribe_ids),
    }


def compile_shared(source: Path, output: Path, *extra: str) -> None:
    command = [
        "gcc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
        str(source), *extra, "-o", str(output),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def verify_server_root(server_root: Path) -> tuple[Path, Path]:
    binary = server_root / "Pal" / "Binaries" / "Linux" / "PalServer-Linux-Shipping"
    pak = server_root / "Pal" / "Content" / "Paks" / "Pal-LinuxServer.pak"
    require(binary.is_file(), f"Server executable is missing: {binary}")
    require(pak.is_file(), f"Server PAK is missing: {pak}")
    require(binary.stat().st_size == EXPECTED_BINARY_BYTES, "Server executable size mismatch")
    require(pak.stat().st_size == EXPECTED_PAK_BYTES, "Server PAK size mismatch")
    require(sha256_file(binary) == EXPECTED_BINARY_SHA256, "Server executable hash mismatch")
    require(sha256_file(pak) == EXPECTED_PAK_SHA256, "Server PAK hash mismatch")
    static = json.loads(NATIVE_STATIC.read_text(encoding="utf-8"))
    require(static["target"]["serverBuildId"] == EXPECTED_SERVER_BUILD, "Native static Build ID mismatch")
    require(static["target"]["serverDepotManifestId"] == EXPECTED_DEPOT_MANIFEST,
            "Native static depot manifest mismatch")
    require(static["executable"]["sha256"] == EXPECTED_BINARY_SHA256,
            "Native static executable hash mismatch")
    return binary, pak


def validate_runtime_rows(runtime: dict[str, Any], raw: dict[str, Any]) -> dict[str, int]:
    rows = runtime["runtimeRows"]
    require(len(rows) == len(raw["pals"]), "Runtime row evidence count mismatch")
    raw_tribe_to_runtime: dict[str, set[int]] = {}
    runtime_tribe_to_raw: dict[int, set[str]] = {}
    for source_order, (runtime_row, raw_row) in enumerate(zip(rows, raw["pals"], strict=True)):
        require(runtime_row["sourceOrder"] == source_order, "Runtime row order mismatch")
        require(runtime_row["combiRank"] == raw_row["combiRank"], "Runtime rank mismatch")
        require(runtime_row["combiDuplicatePriority"] == raw_row["combiDuplicatePriority"],
                "Runtime duplicate priority mismatch")
        require(runtime_row["isBoss"] is bool(raw_row["isBoss"]), "Runtime boss flag mismatch")
        require(runtime_row["ignoreCombi"] is bool(raw_row["ignoreCombi"]), "Runtime ignore flag mismatch")
        raw_tribe = enum_tail(raw_row["tribe"]).lower()
        runtime_tribe = int(runtime_row["tribeId"])
        raw_tribe_to_runtime.setdefault(raw_tribe, set()).add(runtime_tribe)
        runtime_tribe_to_raw.setdefault(runtime_tribe, set()).add(raw_tribe)
    ambiguous_raw = sum(len(values) != 1 for values in raw_tribe_to_runtime.values())
    ambiguous_runtime = sum(len(values) != 1 for values in runtime_tribe_to_raw.values())
    require(ambiguous_raw == 0, "One raw tribe maps to multiple runtime tribe IDs")
    require(ambiguous_runtime == 0, "One runtime tribe ID maps to multiple raw tribes")
    return {
        "rawTribeCount": len(raw_tribe_to_runtime),
        "runtimeTribeCount": len(runtime_tribe_to_raw),
        "rawToRuntimeAmbiguityCount": ambiguous_raw,
        "runtimeToRawAmbiguityCount": ambiguous_runtime,
    }


def run_runtime(server_root: Path, timeout: int) -> dict[str, Any]:
    binary, pak = verify_server_root(server_root)
    raw, pals, breeding = fixed_inputs()
    with tempfile.TemporaryDirectory(prefix="palworld-native-runtime-") as temporary:
        temp = Path(temporary)
        runtime_input = temp / "runtime-input.bin"
        runtime_output = temp / "runtime-output.json"
        probe = temp / "native-breeding-runtime-probe.so"
        shim = temp / "fixed-server-offline-shim.so"
        home = temp / "home"
        home.mkdir()
        input_evidence = build_runtime_input(runtime_input)
        compile_shared(PROBE_SOURCE, probe, "-pthread")
        compile_shared(OFFLINE_SHIM_SOURCE, shim, "-Wno-pedantic", "-ldl")

        environment = os.environ.copy()
        for key in (
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
            "BUNDLE_HTTP_PROXY", "BUNDLE_HTTPS_PROXY", "DOCKER_HTTP_PROXY", "DOCKER_HTTPS_PROXY",
        ):
            environment.pop(key, None)
        environment.update({
            "HOME": str(home),
            "LD_PRELOAD": f"{shim}:{probe}",
            "PAL_NATIVE_AUDIT_INPUT": str(runtime_input),
            "PAL_NATIVE_AUDIT_OUTPUT": str(runtime_output),
        })
        command = [str(binary), "Pal", "-NoSteam", "-NoEOS", "-log"]
        process = subprocess.Popen(
            command, cwd=server_root, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                stdout, _ = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, _ = process.communicate()
            raise RuntimeError(f"Native runtime audit timed out after {timeout}s")
        server_log = stdout.decode("utf-8", errors="replace").replace("\x00", "")
        require(runtime_output.is_file(),
                f"Native runtime audit produced no result (exit {process.returncode}):\n{server_log[-4000:]}")
        runtime = json.loads(runtime_output.read_text(encoding="utf-8"))
        require(runtime["status"] == "fixed-build-native-runtime-matched",
                f"Native runtime mismatch: {json.dumps(runtime, ensure_ascii=False)[:4000]}")
        require("Game version is v1.0.1.100619" in server_log, "Server did not report the fixed game version")
        require("Running Palworld dedicated server" in server_log, "Server did not finish initialization")
        require(runtime["nativeInvocationCount"] == 41_616 * 4, "Native invocation count mismatch")
        require(runtime["runtimeLogicalResultMismatchCount"] == 0, "Native logical result mismatch")
        require(runtime["runtimeCallMismatchCount"] == 0, "Native call mismatch")
        require(runtime["parentOrderMismatchCount"] == 0, "Native parent order mismatch")
        require(runtime["hiddenGenderMismatchCount"] == 0, "Native hidden gender mismatch")
        require(runtime["runtimeUniqueRowMismatchCount"] == 0, "Native unique row mismatch")
        require(runtime["bossVariantMappingMismatchCount"] == 0, "Boss variant mapping mismatch")
        tribe_evidence = validate_runtime_rows(runtime, raw)

        runtime_rows = runtime.pop("runtimeRows")
        boss_mappings = runtime.pop("bossVariantMappings")
        released_rows = pals["pals"]
        raw_rows = raw["pals"]
        enriched_boss = []
        for mapping in boss_mappings:
            pal = released_rows[mapping["releasedIndex"]]
            boss_source = mapping["bossSourceOrder"]
            enriched_boss.append({
                "palId": pal["id"],
                "sourceId": pal["sourceId"],
                "bossSourceId": None if boss_source < 0 else raw_rows[boss_source]["rowName"],
                "baseTribeRuntimeId": mapping["sourceTribeId"],
                "bossTribeRuntimeId": mapping["bossTribeId"],
                "valid": mapping["valid"],
            })

        evidence = {
            "schemaVersion": 2,
            "status": runtime["status"],
            "target": {
                "gameVersion": "v1.0.1.100619",
                "serverAppId": "2394010",
                "serverBuildId": EXPECTED_SERVER_BUILD,
                "serverDepotId": "2394012",
                "serverDepotManifestId": EXPECTED_DEPOT_MANIFEST,
                "serverExecutableBytes": binary.stat().st_size,
                "serverExecutableSha256": EXPECTED_BINARY_SHA256,
                "serverPakBytes": pak.stat().st_size,
                "serverPakSha256": EXPECTED_PAK_SHA256,
            },
            "invocation": {
                "nativeFunctionAddress": runtime["nativeFunctionAddress"],
                "managerHelperAddress": runtime["managerHelperAddress"],
                "method": "direct native function invocation in initialized fixed-build server",
                "parentOrdersPerGenderOrientation": 2,
                "genderOrientationsPerPair": 2,
                "nativeInvocationCount": runtime["nativeInvocationCount"],
                "harnessHelperScope": "data-table-manager lookup for two synthetic parent records only",
                "selectionOrRecipeLogicStubbed": False,
                "internetEgressBlocked": True,
            },
            "counts": {
                "rawPalRows": runtime["rawPalRowCount"],
                "releasedPals": runtime["releasedPalCount"],
                "uniqueCombinationRows": runtime["uniqueCombinationRowCount"],
                "unorderedParentPairs": runtime["unorderedPairCount"],
                "logicalResultRows": runtime["logicalResultRowCount"],
                "matchingLogicalResultRows": runtime["logicalResultRowCount"] - runtime["runtimeLogicalResultMismatchCount"],
                "nativeInvocations": runtime["nativeInvocationCount"],
                "bossVariantMappings": runtime["bossVariantMappingCount"],
            },
            "differences": {
                "runtimeRowMetadata": runtime["runtimeRowMetadataMismatchCount"],
                "runtimeUniqueRows": runtime["runtimeUniqueRowMismatchCount"],
                "runtimeLogicalResults": runtime["runtimeLogicalResultMismatchCount"],
                "runtimeCalls": runtime["runtimeCallMismatchCount"],
                "parentOrder": runtime["parentOrderMismatchCount"],
                "hiddenGender": runtime["hiddenGenderMismatchCount"],
                "sameSpecies": runtime["sameSpeciesMismatchCount"],
                "specialCombination": runtime["specialCombinationMismatchCount"],
                "normalSelection": runtime["normalSelectionMismatchCount"],
                "bossVariantMapping": runtime["bossVariantMappingMismatchCount"],
            },
            "gender": {
                "maleRuntimeCode": runtime["maleRuntimeCode"],
                "femaleRuntimeCode": runtime["femaleRuntimeCode"],
                "genderDependentPair": "catmage|foxmage",
            },
            "runtimeTableIdentity": {
                **tribe_evidence,
                "runtimeRowsSha256": sha256_bytes(canonical_bytes(runtime_rows)),
            },
            "bossAlphaPostProcessing": {
                "nativeFunctionAddress": "0x7118c40",
                "modeled": True,
                "mappingCount": runtime["bossVariantMappingCount"],
                "mismatchCount": runtime["bossVariantMappingMismatchCount"],
                "speciesIdentityPreserved": True,
                "mappings": enriched_boss,
            },
            "allDifferences": {
                "rowMetadata": runtime["rowMetadataMismatches"],
                "uniqueRows": runtime["uniqueRowMismatches"],
                "logicalResults": runtime["logicalResultMismatches"],
            },
            "inputs": {
                "runtimeInput": input_evidence,
                "rawAssetsSha256": sha256_file(RAW_ASSETS),
                "palsSha256": sha256_file(PALS),
                "breedingSha256": sha256_file(BREEDING),
                "staticNativeEvidenceSha256": sha256_file(NATIVE_STATIC),
                "runtimeProbeSourceSha256": sha256_file(PROBE_SOURCE),
                "offlineShimSourceSha256": sha256_file(OFFLINE_SHIM_SOURCE),
            },
            "serverInitialization": {
                "reportedGameVersion": "v1.0.1.100619",
                "reachedRunningState": True,
                "processExitCode": process.returncode,
            },
        }
        evidence["evidenceSha256"] = sha256_bytes(canonical_bytes(evidence))
        return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("server_root", type=Path,
                        help="Exact depot 2394012 manifest 2167164727892555341 root")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--check", action="store_true",
                        help="Compare with the committed runtime evidence instead of rewriting it")
    args = parser.parse_args()
    evidence = run_runtime(args.server_root.resolve(), args.timeout)
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        require(args.output.is_file(), f"Committed runtime evidence is missing: {args.output}")
        require(args.output.read_text(encoding="utf-8") == rendered,
                "Committed native runtime evidence drifted")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rendered.encode("utf-8"))
    print(json.dumps({
        "status": evidence["status"],
        "serverBuildId": evidence["target"]["serverBuildId"],
        "releasedPals": evidence["counts"]["releasedPals"],
        "unorderedParentPairs": evidence["counts"]["unorderedParentPairs"],
        "logicalResultRows": evidence["counts"]["logicalResultRows"],
        "nativeInvocations": evidence["counts"]["nativeInvocations"],
        "differences": evidence["differences"],
        "evidenceSha256": evidence["evidenceSha256"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
