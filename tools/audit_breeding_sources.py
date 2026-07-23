#!/usr/bin/env python3
"""Parse and audit pinned auxiliary Palworld breeding implementations.

Auxiliary projects are comparison inputs only. This module deliberately does
not resolve their latest branches, vote on a released roster, or emit a
consensus table. ``build_verified_dataset.py`` pins every compared file by
commit and SHA-256, and records the complete comparison against the table
regenerated from the fixed-build asset extraction.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXACT_COMPARISON = ROOT / "audit" / "exact-comparison.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canon(value: Any) -> str:
    return str(value or "").strip().lower()


def pkey(first: Any, second: Any) -> str:
    return "|".join(sorted((canon(first), canon(second))))


def add(table: dict[str, set[str]], first: Any, second: Any, child: Any) -> None:
    parent_a, parent_b, child_id = canon(first), canon(second), canon(child)
    if parent_a and parent_b and child_id:
        table.setdefault(pkey(parent_a, parent_b), set()).add(child_id)


def child_map(raw: dict[str, Any], field: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for child, rows in raw.get(field, {}).items():
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict):
                add(result, row.get("parent_a"), row.get("parent_b"), child)
    return result


def load_pst(text: str) -> dict[str, Any]:
    """Decode a pinned PalworldSaveTools breedingdata.json snapshot."""
    raw = json.loads(text)
    pals = {
        canon(key): {
            "name": value.get("name"),
            "rank": int(value.get("combi_rank") or 0),
            "rarity": int(value.get("rarity") or 0),
            "ignoreCombi": bool(value.get("ignore_combi")),
        }
        for key, value in raw.get("pal_info", {}).items()
        if isinstance(value, dict)
    }
    formula = child_map(raw, "child_to_parents_formula")
    ignore_formula = child_map(raw, "child_to_parents_ignore")
    unique_reverse = child_map(raw, "child_to_parents_unique")
    unique_direct: dict[str, set[str]] = {}
    for row in raw.get("unique_combos", []):
        if isinstance(row, dict):
            add(unique_direct, row.get("parent_a"), row.get("parent_b"), row.get("child"))

    # Reconstruct this implementation's effective forward result. It is
    # measured, never used to select a Pal or child in the site dataset.
    resolved = {key: set(children) for key, children in formula.items()}
    for key, children in ignore_formula.items():
        resolved[key] = set(children)
    for key, children in unique_direct.items():
        resolved[key] = set(children)
    for pal_id in pals:
        resolved[pkey(pal_id, pal_id)] = {pal_id}

    return {
        "pals": pals,
        "pairs": resolved,
        "formula": formula,
        "ignoreFormula": ignore_formula,
        "unique": unique_direct,
        "uniqueReverse": unique_reverse,
    }


def load_paldeck(text: str) -> dict[str, Any]:
    """Decode a pinned Paldeck/PalDB breeding snapshot."""
    raw = json.loads(text)
    entries = list(raw.get("Pals", [])) + list(raw.get("SourceOnlyPals", []))
    name_to_id: dict[str, str] = {}
    pals: dict[str, dict[str, Any]] = {}
    for entry in entries:
        pal_id = canon(entry.get("breedingId"))
        name = str(entry.get("name") or "").strip()
        if pal_id and name:
            name_to_id[canon(name)] = pal_id
            pals[pal_id] = {
                "name": name,
                "dex": entry.get("number"),
                "rank": entry.get("breedingRank"),
                "canBeParent": bool(entry.get("canBeParent")),
                "canBeChild": bool(entry.get("canBeChild")),
                "canBeStandardChild": bool(entry.get("canBeStandardChild")),
            }
    pairs: dict[str, set[str]] = {}
    unknown: list[list[Any]] = []
    for row in raw.get("PairResults", []):
        if isinstance(row, list) and len(row) >= 3:
            names = row[:3]
        elif isinstance(row, dict):
            names = [row.get("parentA"), row.get("parentB"), row.get("child")]
        else:
            continue
        identifiers = [name_to_id.get(canon(name), "") for name in names]
        if all(identifiers):
            add(pairs, *identifiers)
        else:
            unknown.append(names)
    return {
        "pals": pals,
        "pairs": pairs,
        "unknown": unknown,
        "metadata": raw.get("PairResultsMetadata", {}),
        "rowCount": len(raw.get("PairResults", [])),
    }


def main() -> None:
    audit = json.loads(EXACT_COMPARISON.read_text(encoding="utf-8"))
    auxiliary = audit.get("auxiliaryImplementations", {})
    require(set(auxiliary) == {"palCalc", "palworldSaveTools", "paldeck"},
            "The three pinned auxiliary comparisons are incomplete")
    require(auxiliary["palCalc"].get("role") == "pinned-comparison-only",
            "PalCalc must remain comparison-only")
    require(auxiliary["palCalc"].get("usedForAssetReleaseSelection") is False,
            "An auxiliary roster must not select released Pals")
    for source in ("palworldSaveTools", "paldeck"):
        require(auxiliary[source].get("role") == "advisory-overlap-comparison-only",
                f"{source} must remain advisory comparison-only")

    summary = {
        "policy": "fixed-build assets are authoritative; no voting or consensus table",
        "palCalc": {
            "roster": auxiliary["palCalc"]["releasedRosterCount"],
            "logicalRows": auxiliary["palCalc"]["logicalRowCount"],
            "mismatches": auxiliary["palCalc"]["mismatchCount"],
        },
        "palworldSaveTools": {
            "rosterCoverage": auxiliary["palworldSaveTools"]["releasedRosterCoverage"],
            "matchingPairs": auxiliary["palworldSaveTools"]["matchingPairCount"],
            "mismatches": auxiliary["palworldSaveTools"]["mismatchCount"],
            "missingPairs": auxiliary["palworldSaveTools"]["missingPairCount"],
        },
        "paldeck": {
            "rosterCoverage": auxiliary["paldeck"]["releasedRosterCoverage"],
            "matchingPairs": auxiliary["paldeck"]["matchingPairCount"],
            "mismatches": auxiliary["paldeck"]["mismatchCount"],
            "missingPairs": auxiliary["paldeck"]["missingPairCount"],
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
