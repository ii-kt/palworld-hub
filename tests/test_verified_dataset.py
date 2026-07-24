#!/usr/bin/env python3
"""Independent invariants for every fixed-build Palworld breeding pair."""
from __future__ import annotations

import hashlib
import json
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PALWORLD = ROOT
DATASET_ID = "pw-1.0.1.100619-24181105-cad80fe15c38"


def load(path: str):
    return json.loads((PALWORLD / path).read_text(encoding="utf-8"))


def repository_text_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def stable_digest(value) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def tail(value):
    return str(value).rsplit("::", 1)[-1]


def pid(value):
    return str(value).strip().lower()


def pkey(first, second):
    return "|".join(sorted((pid(first), pid(second))))


def gender(value):
    value = tail(value).upper()
    return "WILDCARD" if value in {"", "NONE", "ANY", "WILDCARD"} else value


def canonical(first, first_gender, second, second_gender, child):
    left, right = (pid(first), gender(first_gender)), (pid(second), gender(second_gender))
    if right[0] < left[0]:
        left, right = right, left
    return left[0], left[1], right[0], right[1], pid(child)


def triangle(size, first, second):
    if first > second:
        first, second = second, first
    return first * size - first * (first - 1) // 2 + second - first


class VerifiedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pals_payload = load("data/pals.verified.json")
        cls.compact = load("data/breeding.verified.json")
        cls.verification = load("data/verification.json")
        cls.audit = load("audit/exact-comparison.json")
        cls.native_path = PALWORLD / "evidence/build-24181105.native-breeding.json"
        cls.native = json.loads(cls.native_path.read_text(encoding="utf-8"))
        cls.runtime_path = PALWORLD / "audit/native-runtime-comparison.json"
        cls.runtime = json.loads(cls.runtime_path.read_text(encoding="utf-8"))
        cls.raw_path = PALWORLD / "evidence/build-24181105.assets.json"
        cls.raw = json.loads(cls.raw_path.read_text(encoding="utf-8"))
        cls.pals = cls.pals_payload["pals"]
        cls.order = cls.compact["palOrder"]
        cls.by_id = {pal["id"]: pal for pal in cls.pals}
        cls.index = {pal_id: index for index, pal_id in enumerate(cls.order)}
        cls.override_by_index = {item["pairIndex"]: item for item in cls.compact["genderOverrides"]}
        cls.rows = []
        cls.pairs = defaultdict(list)
        cursor = 0
        for first in range(len(cls.order)):
            for second in range(first, len(cls.order)):
                override = cls.override_by_index.get(cursor)
                if override:
                    values = [canonical(
                        cls.order[row["parent1"]], row["parent1Gender"],
                        cls.order[row["parent2"]], row["parent2Gender"],
                        cls.order[row["child"]],
                    ) for row in override["rows"]]
                else:
                    values = [canonical(
                        cls.order[first], "WILDCARD", cls.order[second], "WILDCARD",
                        cls.order[cls.compact["children"][cursor]],
                    )]
                cls.rows.extend(values)
                cls.pairs[pkey(cls.order[first], cls.order[second])].extend(values)
                cursor += 1
        cls.row_set = set(cls.rows)
        cls.reverse = defaultdict(list)
        cls.by_parent = defaultdict(lambda: defaultdict(list))
        for row in cls.rows:
            cls.reverse[row[4]].append(row)
            cls.by_parent[row[0]][row[2]].append(row)
            if row[0] != row[2]:
                cls.by_parent[row[2]][row[0]].append(row)

        icons = {pid(item["id"]) for item in cls.raw["icons"] if "t_dummy_icon" not in item["path"].lower()}

        def excluded(row):
            source, tribe = row["rowName"].lower(), tail(row["tribe"]).lower()
            if not row["isPal"]:
                return "NOT_A_PAL"
            if row["isBoss"] or row["isRaidBoss"] or row["isTowerBoss"]:
                return "BOSS_VARIANT"
            if source not in icons and tribe not in icons:
                return "PAL_ICON_MISSING"
            if row["zukanIndex"] <= 0:
                return "PALDEX_NOT_RELEASED"
            if min(row["rarity"], row["runSpeed"], row["walkSpeed"], row["combiRank"]) <= 0:
                return "PAL_CONFIGURATION_INCOMPLETE"
            return None

        cls.raw_exclusions = {}
        individually_eligible = []
        for row in cls.raw["pals"]:
            reason = excluded(row)
            if reason:
                cls.raw_exclusions[pid(row["rowName"])] = reason
            else:
                individually_eligible.append(row)
        form_groups = defaultdict(list)
        for row in individually_eligible:
            form_groups[(row["zukanIndex"], row["zukanIndexSuffix"], row["rarity"])].append(row)
        cls.raw_released = []
        cls.duplicate_form_groups = []
        for key, rows in form_groups.items():
            if len(rows) == 1:
                cls.raw_released.append(rows[0])
                continue
            exact_icon_rows = [row for row in rows if pid(row["rowName"]) in icons]
            if len(exact_icon_rows) != 1:
                raise AssertionError(f"ambiguous form {key}: {exact_icon_rows}")
            cls.raw_released.append(exact_icon_rows[0])
            cls.duplicate_form_groups.append(rows)
            for row in rows:
                if row is not exact_icon_rows[0]:
                    cls.raw_exclusions[pid(row["rowName"])] = "DUPLICATE_PUBLIC_FORM_PARAMETER_ROW"
        cls.raw_released.sort(key=lambda row: row["sourceOrder"])
        cls.raw_by_id = {pid(row["rowName"]): row for row in cls.raw_released}
        tribes = defaultdict(list)
        for row in cls.raw_released:
            tribes[tail(row["tribe"]).lower()].append(row)
        cls.specials = []
        cls.unreleased_specials = []
        seen = set()
        for row in cls.raw["combinations"]:
            first = tribes.get(tail(row["parentTribeA"]).lower(), [])
            second = tribes.get(tail(row["parentTribeB"]).lower(), [])
            child = cls.raw_by_id.get(pid(row["childCharacterId"]))
            if len(first) != 1 or len(second) != 1 or not child:
                cls.unreleased_specials.append(row)
                continue
            signature = canonical(
                first[0]["rowName"], row["parentGenderA"],
                second[0]["rowName"], row["parentGenderB"], child["rowName"],
            )
            if signature not in seen:
                seen.add(signature)
                cls.specials.append(signature)
        cls.special_pairs = {pkey(row[0], row[2]) for row in cls.specials}
        cls.all_unique_child_ids = {pid(row["childCharacterId"]) for row in cls.raw["combinations"]}
        cls.special_children = cls.all_unique_child_ids & set(cls.order)
        cls.normal_candidates = [
            cls.by_id[pid(row["rowName"])] for row in cls.raw_released
            if pid(row["rowName"]) not in cls.special_children and not row["ignoreCombi"]
        ]
        cls.native_raw_candidates = [
            {
                "id": pid(row["rowName"]),
                "combiRank": int(row["combiRank"]),
                "combiDuplicatePriority": int(row["combiDuplicatePriority"]),
                "sourceOrder": int(row["sourceOrder"]),
            }
            for row in cls.raw["pals"]
            if not row["isBoss"] and not row["ignoreCombi"]
            and pid(row["rowName"]) not in cls.all_unique_child_ids
        ]

    def test_01_all_schema_and_dataset_versions_match(self):
        self.assertEqual(self.pals_payload["schemaVersion"], 2)
        self.assertEqual(self.compact["schemaVersion"], 3)
        self.assertEqual(self.verification["schemaVersion"], 8)
        self.assertEqual({self.pals_payload["datasetId"], self.compact["datasetId"], self.verification["datasetId"]}, {DATASET_ID})

    def test_02_fixed_build_and_raw_input_hashes(self):
        self.assertEqual(self.raw["buildId"], "24181105")
        self.assertEqual(hashlib.sha256(self.raw_path.read_bytes()).hexdigest(), "e23a12ceffae5792b69c8faebe8ee3fbacbc09f0bd88572410d2b3b59aca1fe0")
        self.assertEqual(self.raw["pakFiles"], [{"file": "Pal-LinuxServer.pak", "bytes": 4797040962, "sha256": "cad80fe15c38d74a795779fbab31f04bc2c15c37fb8a2188e4d89f3800fb0e68"}])
        self.assertEqual(self.verification["targetServerDepotManifestId"], "2167164727892555341")
        self.assertEqual(self.verification["mappingsUsmapSha256"],
                         "561ef13c8ee3cf785e4de8aa5bc9b3ad1646e416d895f1d1166fa27ebdfd26b0")
        self.assertEqual(self.verification["catalogContentHash"],
                         "872e4a79af5b5043ee97d9a4287a41bba407afc96ff3b0a6de56fff827d334b3")
        self.assertEqual(self.raw["breedingItemEffectPath"],
                         "Pal/Content/Pal/DataAsset/MapObject/Breeding/DA_BreedingItemEffectData")
        self.assertEqual({item["combiRankBonus"] for item in self.raw["breedingItemEffects"]}, {0})
        self.assertEqual([item["itemId"] for item in self.raw["breedingItemEffects"]],
                         ["Cake02", "Cake03", "Cake04", "Cake05"])

    def test_03_asset_release_filter_selects_exactly_288(self):
        self.assertEqual(len(self.raw_released), 288)
        self.assertEqual({pid(row["rowName"]) for row in self.raw_released}, set(self.order))
        self.assertEqual(
            stable_digest(sorted(row["rowName"] for row in self.raw_released)),
            "09b6c2e7db674ac1f48ebf6561c2d7e7f1e2d0d94ffbe0d7dfee5ae4c348ad46",
        )
        self.assertEqual(
            self.audit["rosterSelection"]["releasedSourceIdsSha256"],
            "09b6c2e7db674ac1f48ebf6561c2d7e7f1e2d0d94ffbe0d7dfee5ae4c348ad46",
        )

    def test_04_release_exclusion_reasons_and_counts(self):
        self.assertEqual(
            self.audit["rosterSelection"]["publicFormKeyFields"],
            ["ZukanIndex", "ZukanIndexSuffix", "Rarity"],
        )
        self.assertEqual(Counter(self.raw_exclusions.values()), Counter({
            "BOSS_VARIANT": 412, "PAL_ICON_MISSING": 23, "PALDEX_NOT_RELEASED": 18,
            "DUPLICATE_PUBLIC_FORM_PARAMETER_ROW": 11,
            "PAL_CONFIGURATION_INCOMPLETE": 1,
        }))
        self.assertEqual(len(self.duplicate_form_groups), 9)
        self.assertEqual(self.audit["rosterSelection"]["duplicateFormGroupCount"], 9)
        self.assertEqual(self.audit["rosterSelection"]["duplicateFormRowsExcludedCount"], 11)
        self.assertEqual(self.audit["rosterSelection"]["tribeIconFallbackReleasedCount"], 1)
        self.assertEqual(
            self.audit["rosterSelection"]["tribeIconFallbackReleasedSourceIds"],
            ["PlantSlime_Flower"],
        )
        self.assertFalse(self.audit["rosterSelection"]["rowNamePatternInferenceUsed"])
        self.assertNotIn("worldtreedragon", self.order)
        self.assertIn("plantslime_flower", self.order)

    def test_05_all_288_metadata_rows_are_valid(self):
        self.assertEqual(len(self.by_id), 288)
        for pal in self.pals:
            self.assertTrue(pal["id"] and pal["sourceId"] and pal["jp"] and pal["en"])
            self.assertGreater(pal["no"], 0)
            self.assertGreater(pal["power"], 0)
            self.assertGreater(pal["rarity"], 0)
            self.assertTrue(pal["elements"])
            self.assertEqual(pal["variant"], bool(pal["suffix"]))
            self.assertTrue(pal["isPal"])
            self.assertFalse(pal["isBoss"] or pal["isRaidBoss"] or pal["isTowerBoss"])

    def test_06_every_unordered_parent_pair_exists_once(self):
        self.assertEqual(len(self.pairs), 41616)
        expected = {pkey(self.order[i], self.order[j]) for i in range(288) for j in range(i, 288)}
        self.assertEqual(set(self.pairs), expected)

    def test_07_compact_triangular_index_matches_every_pair(self):
        cursor = 0
        for first in range(288):
            for second in range(first, 288):
                self.assertEqual(cursor, triangle(288, first, second))
                cursor += 1
        self.assertEqual(cursor, len(self.compact["children"]))

    def test_08_all_parent_and_child_ids_are_released(self):
        released = set(self.order)
        self.assertFalse({value for row in self.rows for value in (row[0], row[2], row[4])} - released)

    def test_09_logical_rows_are_complete_and_unique(self):
        self.assertEqual(len(self.rows), 41617)
        self.assertEqual(len(self.row_set), 41617)

    def test_10_same_species_uses_native_special_then_normal_control_flow(self):
        identity_exceptions = {}
        for pal_id in self.order:
            key = pkey(pal_id, pal_id)
            if key in self.special_pairs:
                expected = pal_id
            else:
                pal = self.by_id[pal_id]
                expected = min(self.native_raw_candidates, key=lambda candidate: (
                    abs(candidate["combiRank"] - pal["combiRank"]),
                    -candidate["combiDuplicatePriority"], candidate["sourceOrder"],
                ))["id"]
            self.assertEqual(self.pairs[key], [canonical(pal_id, "WILDCARD", pal_id, "WILDCARD", expected)])
            if expected != pal_id:
                identity_exceptions[key] = expected
        self.assertEqual(identity_exceptions, {
            "kingwhale|kingwhale": "domearmordragon",
            "plantslime_flower|plantslime_flower": "plantslime",
        })

    def test_11_special_rows_are_asset_resolved_and_deduplicated(self):
        self.assertEqual(len(self.raw["combinations"]), 258)
        self.assertEqual(len(self.unreleased_specials), 73)
        self.assertEqual(len(self.specials), 184)
        self.assertEqual(sum(row[0] != row[2] for row in self.specials), 81)

    def test_12_special_combinations_precede_normal_formula(self):
        for special in self.specials:
            if special[0] == special[2]:
                self.assertEqual(self.pairs[pkey(special[0], special[2])][0][4], special[0])
                continue
            actual = self.pairs[pkey(special[0], special[2])]
            matching = [row for row in actual if row[4] == special[4]]
            self.assertTrue(matching, special)

    def test_13_gender_dependent_pair_has_both_exact_orientations(self):
        self.assertEqual(set(self.pairs["catmage|foxmage"]), {
            canonical("catmage", "FEMALE", "foxmage", "MALE", "catmage_fire"),
            canonical("catmage", "MALE", "foxmage", "FEMALE", "foxmage_dark"),
        })

    def test_14_every_normal_pair_matches_formula_and_all_ties(self):
        for key, values in self.pairs.items():
            first_id, second_id = key.split("|")
            if key in self.special_pairs:
                continue
            first, second = self.by_id[first_id], self.by_id[second_id]
            target = (first["combiRank"] + second["combiRank"] + 1) // 2
            expected = min(self.normal_candidates, key=lambda pal: (
                abs(pal["combiRank"] - target), -pal["combiDuplicatePriority"],
                pal["sourceOrder"],
            ))["id"]
            self.assertEqual(values, [canonical(first_id, "WILDCARD", second_id, "WILDCARD", expected)])

    def test_15_special_children_never_enter_normal_candidate_pool(self):
        self.assertEqual(len(self.special_children), 103)
        self.assertFalse(self.special_children & {pal["id"] for pal in self.normal_candidates})

    def test_16_parent_order_is_invariant_for_all_pairs(self):
        def resolve(first, second):
            first_index, second_index = self.index[first], self.index[second]
            pair_position = triangle(len(self.order), first_index, second_index)
            override = self.override_by_index.get(pair_position)
            if not override:
                return {(self.order[self.compact["children"][pair_position]], "WILDCARD", "WILDCARD")}
            resolved = set()
            for row in override["rows"]:
                if first_index <= second_index:
                    first_gender, second_gender = row["parent1Gender"], row["parent2Gender"]
                else:
                    first_gender, second_gender = row["parent2Gender"], row["parent1Gender"]
                resolved.add((self.order[row["child"]], first_gender, second_gender))
            return resolved

        for first in self.order:
            for second in self.order:
                forward = resolve(first, second)
                reverse = resolve(second, first)
                self.assertEqual(
                    {(child, first_gender, second_gender)
                     for child, first_gender, second_gender in forward},
                    {(child, second_gender, first_gender)
                     for child, first_gender, second_gender in reverse},
                    (first, second),
                )

    def test_17_exact_reference_comparison_has_no_differences(self):
        comparison = self.audit["exactReferenceComparison"]
        self.assertEqual(comparison["matchingLogicalRows"], 41617)
        self.assertEqual(comparison["mismatchCount"], 0)
        for field in ("missingRows", "extraRows", "missingPairs", "extraPairs", "pairResultMismatches", "compactMissingRows", "compactExtraRows", "sameSpeciesMismatches", "genderConditionMismatches", "unreleasedPalIds", "referenceDuplicates"):
            self.assertEqual(comparison[field], [], field)

    def test_18_rarity_tie_claim_has_thousands_of_counterexamples(self):
        counter = self.audit["rarityTieCounterevidence"]
        self.assertEqual(counter["differenceCountOnNormalNonSpecialPairs"], len(counter["differences"]))
        self.assertGreater(counter["differenceCountOnNormalNonSpecialPairs"], 6000)

    def test_19_ignore_combi_native_scope_has_the_expected_self_pair_effect(self):
        analysis = self.audit["ignoreCombiAnalysis"]
        self.assertEqual(analysis["releasedTrueCount"], 27)
        self.assertEqual(analysis["alreadyExcludedAsSpecialChildrenCount"], 26)
        self.assertEqual(analysis["remainingIds"], ["kingwhale"])
        self.assertEqual(analysis["normalChildPoolCounterfactualDifferenceCount"], 1)
        self.assertEqual(analysis["normalChildPoolCounterfactualDifferences"], [{
            "pair": "kingwhale|kingwhale",
            "nativeIgnoreCombiExclusionResult": "domearmordragon",
            "ignoreCombiIncludedResult": "kingwhale",
        }])
        self.assertTrue(analysis["nativeRuntimeRoleDetermined"])
        self.assertEqual(analysis["nativeRuntimeRole"],
                         "excluded only from the normal child candidate pool; parent rank reads do not test the flag")
        self.assertNotIn("kingwhale", {pal["id"] for pal in self.normal_candidates})

    def test_20_reverse_index_roundtrips_every_logical_row(self):
        self.assertEqual(set(self.order) - set(self.reverse), {"kingwhale", "plantslime_flower"})
        self.assertEqual(self.verification["zeroParentCandidateChildIds"],
                         ["kingwhale", "plantslime_flower"])
        for child, rows in self.reverse.items():
            for row in rows:
                self.assertIn(row, self.pairs[pkey(row[0], row[2])])
                self.assertEqual(row[4], child)

    def test_21_reverse_index_has_no_duplicate_parent_conditions(self):
        for child, rows in self.reverse.items():
            signatures = {(row[0], row[1], row[2], row[3]) for row in rows}
            self.assertEqual(len(signatures), len(rows), child)

    def test_22_every_single_parent_has_288_unique_partner_groups(self):
        for parent in self.order:
            self.assertEqual(set(self.by_parent[parent]), set(self.order))
            self.assertEqual(len(self.by_parent[parent]), 288)

    def test_23_single_parent_groups_preserve_every_gender_result(self):
        for parent, partners in self.by_parent.items():
            for partner, rows in partners.items():
                self.assertEqual(rows, self.pairs[pkey(parent, partner)])
        self.assertEqual(len(self.by_parent["catmage"]["foxmage"]), 2)

    def test_24_four_generation_ancestor_tree_edges_are_valid_and_cycle_safe(self):
        direct_edges = 0
        for child in self.order:
            for edge in self.reverse[child]:
                self.assertIn(edge, self.row_set)
                self.assertEqual(edge[4], child)
                direct_edges += 1
        self.assertEqual(direct_edges, 41617)

        def visit(pal_id, depth, ancestors):
            if pal_id in ancestors or depth >= 4:
                return depth
            candidates = sorted(
                self.reverse[pal_id],
                key=lambda row: (int(row[0] == pal_id or row[2] == pal_id), self.index[row[0]], self.index[row[2]], row[1], row[3]),
            )
            if not candidates:
                self.assertIn(pal_id, {"kingwhale", "plantslime_flower"})
                return depth
            edge = candidates[0]
            self.assertIn(edge, self.row_set)
            next_ancestors = ancestors | {pal_id}
            return max(visit(edge[0], depth + 1, next_ancestors), visit(edge[2], depth + 1, next_ancestors))

        for pal_id in self.order:
            self.assertLessEqual(visit(pal_id, 0, set()), 4)

    def test_25_four_generation_descendant_tree_edges_are_valid_and_cycle_safe(self):
        direct_edges = 0
        for parent in self.order:
            for rows in self.by_parent[parent].values():
                for edge in rows:
                    self.assertIn(edge, self.row_set)
                    self.assertIn(parent, (edge[0], edge[2]))
                    direct_edges += 1
        self.assertEqual(direct_edges, 82946)

        def visit(pal_id, depth, ancestors):
            if pal_id in ancestors or depth >= 4:
                return depth
            edges = []
            for rows in self.by_parent[pal_id].values():
                edges.extend(rows)
            edges.sort(key=lambda row: (int(row[4] == pal_id), self.index[row[4]], self.index[row[0] if row[2] == pal_id else row[2]], row[1], row[3]))
            self.assertTrue(edges)
            edge = edges[0]
            self.assertIn(edge, self.row_set)
            return visit(edge[4], depth + 1, ancestors | {pal_id})

        for pal_id in self.order:
            self.assertLessEqual(visit(pal_id, 0, set()), 4)

    def test_26_native_binary_evidence_is_fixed_to_the_target_build(self):
        self.assertEqual(hashlib.sha256(repository_text_bytes(self.native_path)).hexdigest(),
                         "ac079224cbadb33886092145de2d4f5e2d6da6ccc5ba4cb0374f1e2f552e2651")
        self.assertEqual(self.native["target"]["serverBuildId"], "24181105")
        self.assertEqual(self.native["executable"]["sha256"],
                         "788649fa1592160faa7bcf07ccd16d474ebeaae954717bc32284b5a43028d8e7")
        self.assertEqual(len(self.native["verifiedRegions"]), 3)
        self.assertEqual(len(self.native["reflectedFields"]), 4)
        self.assertEqual(len(self.native["instructionEvidence"]), 6)

    def test_27_native_semantics_drive_ignore_and_tie_break_rules(self):
        conclusions = self.native["conclusions"]
        self.assertFalse(conclusions["sameSpeciesShortcut"])
        self.assertEqual(conclusions["ignoreCombiScope"], "normal-child-candidate-only")
        self.assertFalse(conclusions["ignoreCombiParentExclusion"])
        self.assertEqual(conclusions["normalTarget"],
                         "floor((parentA.CombiRank + parentB.CombiRank + 1) / 2)")
        self.assertEqual(conclusions["fixedBuildCombiRankBonusValues"], [0])
        self.assertEqual(self.audit["normalTargetAnalysis"]["fixedBuildCombiRankBonusValues"], [0])
        self.assertEqual(conclusions["firstTieBreaker"], "higher CombiDuplicatePriority")
        self.assertFalse(conclusions["rarityUsedAsTieBreaker"])
        self.assertFalse(conclusions["variantFlagUsedAsTieBreaker"])
        self.assertEqual(self.audit["nativeTieBreakAnalysis"]["variantFirstCounterfactualDifferenceCount"], 0)

    def test_28_unpublished_native_candidates_never_change_or_enter_public_results(self):
        released = set(self.order)
        unpublished = sorted(value["id"] for value in self.native_raw_candidates if value["id"] not in released)
        self.assertEqual(len(self.native_raw_candidates), 186)
        self.assertEqual(unpublished, ["quest_farmer03_pinkcat", "quest_farmer03_sheepball"])
        analysis = self.audit["nativeUnpublishedCandidateAnalysis"]
        self.assertEqual(analysis["allNormalPairsCompared"], 41433)
        self.assertEqual(analysis["outputDifferenceCount"], 0)
        self.assertEqual(analysis["outputDifferences"], [])
        for key, values in self.pairs.items():
            first_id, second_id = key.split("|")
            if key in self.special_pairs:
                continue
            first, second = self.by_id[first_id], self.by_id[second_id]
            target = (first["combiRank"] + second["combiRank"] + 1) // 2
            expected = min(self.native_raw_candidates, key=lambda pal: (
                abs(pal["combiRank"] - target), -pal["combiDuplicatePriority"], pal["sourceOrder"],
            ))["id"]
            self.assertIn(expected, released)
            self.assertEqual(values[0][4], expected)

    def test_29_auxiliary_projects_are_comparison_only_without_voting(self):
        auxiliary = self.audit["auxiliaryImplementations"]
        self.assertEqual(set(auxiliary), {"palCalc", "palworldSaveTools", "paldeck"})
        self.assertEqual(auxiliary["palCalc"]["role"], "pinned-comparison-only")
        self.assertFalse(auxiliary["palCalc"]["usedForAssetReleaseSelection"])
        self.assertEqual(auxiliary["palCalc"]["matchingLogicalRowCount"], 41615)
        self.assertEqual(auxiliary["palCalc"]["mismatchCount"], 4)
        self.assertEqual(auxiliary["palCalc"]["releasedRosterMissing"], [])
        self.assertEqual(auxiliary["palCalc"]["releasedRosterExtra"], [])
        self.assertEqual(auxiliary["palCalc"]["metadataDifferences"], [])
        self.assertEqual(auxiliary["palworldSaveTools"]["role"], "advisory-overlap-comparison-only")
        self.assertEqual(auxiliary["palworldSaveTools"]["mismatchCount"], 1)
        self.assertEqual(auxiliary["paldeck"]["role"], "advisory-overlap-comparison-only")
        self.assertEqual(auxiliary["paldeck"]["mismatchCount"], 2)

    def test_30_native_self_pair_control_flow_overrides_auxiliary_shortcut(self):
        analysis = self.audit["sameSpeciesNativeAnalysis"]
        self.assertFalse(analysis["nativeTopLevelHasSameSpeciesShortcut"])
        self.assertTrue(analysis["nativeTopLevelFunctionInvokedForEveryPair"])
        self.assertEqual(analysis["allReleasedSelfPairsCompared"], 288)
        self.assertEqual(analysis["identityResultCount"], 286)
        self.assertEqual(analysis["identityExceptionCount"], 2)
        self.assertEqual(analysis["siteMismatchCount"], 0)
        self.assertEqual(analysis["identityExceptions"], [
            {
                "pair": "kingwhale|kingwhale",
                "parent": "kingwhale",
                "nativeResult": "domearmordragon",
            },
            {
                "pair": "plantslime_flower|plantslime_flower",
                "parent": "plantslime_flower",
                "nativeResult": "plantslime",
            },
        ])

    def test_31_browser_manifest_pins_exact_generated_files_and_dataset(self):
        pal_bytes = repository_text_bytes(PALWORLD / "data/pals.verified.json")
        breeding_bytes = repository_text_bytes(PALWORLD / "data/breeding.verified.json")
        self.assertEqual(hashlib.sha256(pal_bytes).hexdigest(), self.verification["palDataSha256"])
        self.assertEqual(hashlib.sha256(breeding_bytes).hexdigest(), self.verification["breedingDataSha256"])
        self.assertEqual(self.verification["generatedDataSha256"],
                         self.audit["generated"]["datasetSha256"])
        self.assertEqual(self.verification["resultScope"], "base-released-form-id")
        self.assertTrue(self.verification["nativeBreedingFunctionExhaustiveVerification"])
        self.assertEqual(self.verification["nativeBreedingFunctionInvocationCount"], 166464)
        self.assertEqual(self.verification["nativeRuntimeMismatchCount"], 0)
        self.assertTrue(self.verification["nativeRuntimeFixedExtractedAssetTablesInjected"])
        self.assertFalse(self.verification["nativeRuntimeLivePakDataTablesReadDirectly"])
        self.assertFalse(self.verification["gameRuntimeHatchExhaustiveVerification"])
        self.assertTrue(self.verification["bossAlphaSpeciesMappingVerified"])
        self.assertFalse(self.verification["bossAlphaAndIndividualStatePostProcessingModeled"])
        self.assertEqual(self.audit["runtimeVerification"]["resultScope"], "base-released-form-id")
        self.assertTrue(self.audit["runtimeVerification"]["nativeBreedingFunctionExhaustive"])
        self.assertEqual(self.audit["runtimeVerification"]
                         ["nativeBreedingFunctionInvocationCount"], 166464)
        self.assertEqual(self.audit["runtimeVerification"]["nativeRuntimeMismatchCount"], 0)
        self.assertFalse(self.audit["runtimeVerification"]
                         ["bossAlphaAndIndividualStatePostProcessingModeled"])

    def test_32_native_runtime_evidence_matches_every_fixed_build_result(self):
        self.assertEqual(
            hashlib.sha256(repository_text_bytes(self.runtime_path)).hexdigest(),
            "265bf315873f9d4f1e58ac8fec9544b912e7e6cea304cdc3b34cb1437be63bb1",
        )
        digest_payload = dict(self.runtime)
        claimed_digest = digest_payload.pop("evidenceSha256")
        self.assertEqual(
            claimed_digest,
            "08d7850d2bb566a77cd8734c93b7ed8f31563c287850e41450de2328c89a36a6",
        )
        self.assertEqual(stable_digest(digest_payload), claimed_digest)
        self.assertEqual(self.runtime["schemaVersion"], 2)
        self.assertEqual(self.runtime["status"], "fixed-build-native-runtime-matched")
        self.assertEqual(self.runtime["target"], {
            "gameVersion": "v1.0.1.100619",
            "serverAppId": "2394010",
            "serverBuildId": "24181105",
            "serverDepotId": "2394012",
            "serverDepotManifestId": "2167164727892555341",
            "serverExecutableBytes": 196285592,
            "serverExecutableSha256":
                "788649fa1592160faa7bcf07ccd16d474ebeaae954717bc32284b5a43028d8e7",
            "serverPakBytes": 4797040962,
            "serverPakSha256":
                "cad80fe15c38d74a795779fbab31f04bc2c15c37fb8a2188e4d89f3800fb0e68",
        })
        self.assertEqual(self.runtime["counts"], {
            "rawPalRows": 753,
            "releasedPals": 288,
            "uniqueCombinationRows": 258,
            "unorderedParentPairs": 41616,
            "logicalResultRows": 41617,
            "matchingLogicalResultRows": 41617,
            "nativeInvocations": 166464,
            "bossVariantMappings": 288,
        })
        self.assertEqual(set(self.runtime["differences"]), {
            "runtimeRowMetadata", "runtimeUniqueRows", "runtimeLogicalResults",
            "runtimeCalls", "parentOrder", "hiddenGender", "sameSpecies",
            "specialCombination", "normalSelection", "bossVariantMapping",
        })
        self.assertEqual(set(self.runtime["differences"].values()), {0})
        self.assertEqual(self.runtime["allDifferences"], {
            "rowMetadata": [], "uniqueRows": [], "logicalResults": [],
        })
        self.assertEqual(
            self.runtime["runtimeTableIdentity"]["runtimeRowsSha256"],
            "8b699bc10bfb8de85e026850f074d46c0785843ea4a3b2aebba75dd7d2d6595f",
        )
        invocation = self.runtime["invocation"]
        self.assertEqual(invocation["nativeFunctionAddress"], "0x71168c0")
        self.assertEqual(invocation["parentOrdersPerGenderOrientation"], 2)
        self.assertEqual(invocation["genderOrientationsPerPair"], 2)
        self.assertEqual(invocation["nativeInvocationCount"], 166464)
        self.assertFalse(invocation["selectionOrRecipeLogicStubbed"])
        self.assertTrue(invocation["internetEgressBlocked"])
        inputs = self.runtime["inputs"]
        self.assertEqual(inputs["rawAssetsSha256"],
                         hashlib.sha256(self.raw_path.read_bytes()).hexdigest())
        runtime_pals_payload = {
            **self.pals_payload,
            "pals": [{**pal, "icon": ""} for pal in self.pals],
        }
        runtime_pals_bytes = (
            json.dumps(runtime_pals_payload, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self.assertEqual(inputs["palsSha256"],
                         hashlib.sha256(runtime_pals_bytes).hexdigest())
        self.assertEqual(inputs["breedingSha256"],
                         hashlib.sha256(repository_text_bytes(
                             PALWORLD / "data/breeding.verified.json")).hexdigest())
        self.assertEqual(inputs["staticNativeEvidenceSha256"],
                         hashlib.sha256(repository_text_bytes(self.native_path)).hexdigest())
        self.assertEqual(inputs["runtimeProbeSourceSha256"],
                         hashlib.sha256(repository_text_bytes(
                             PALWORLD / "tools/native_breeding_runtime_probe.c")).hexdigest())
        self.assertEqual(inputs["offlineShimSourceSha256"],
                         hashlib.sha256(repository_text_bytes(
                             PALWORLD / "tools/fixed_server_nonroot_shim.c")).hexdigest())
        self.assertEqual(self.runtime["serverInitialization"], {
            "reportedGameVersion": "v1.0.1.100619",
            "reachedRunningState": True,
            "processExitCode": 143,
        })
        boss = self.runtime["bossAlphaPostProcessing"]
        self.assertEqual(boss["mappingCount"], len(self.pals))
        self.assertEqual(boss["mismatchCount"], 0)
        self.assertTrue(boss["speciesIdentityPreserved"])
        raw_by_source = {row["rowName"]: row for row in self.raw["pals"]}
        released_source_ids = {pal["sourceId"] for pal in self.pals}
        for mapping, pal in zip(boss["mappings"], self.pals, strict=True):
            self.assertEqual(mapping["palId"], pal["id"])
            self.assertEqual(mapping["sourceId"], pal["sourceId"])
            self.assertIn(mapping["bossSourceId"], raw_by_source)
            self.assertTrue(any(
                raw_by_source[mapping["bossSourceId"]][field]
                for field in ("isBoss", "isRaidBoss", "isTowerBoss")
            ))
            self.assertNotIn(mapping["bossSourceId"], released_source_ids)
            self.assertEqual(
                tail(raw_by_source[mapping["bossSourceId"]]["tribe"]),
                pal["tribe"],
            )
            self.assertIsInstance(mapping["baseTribeRuntimeId"], int)
            self.assertEqual(
                mapping["baseTribeRuntimeId"],
                mapping["bossTribeRuntimeId"],
            )
            self.assertTrue(mapping["valid"])
        runtime_audit = self.audit["nativeRuntimeComparison"]
        self.assertEqual(runtime_audit["nativeInvocationCount"], 166464)
        self.assertEqual(runtime_audit["matchingLogicalResultRows"], 41617)
        self.assertEqual(runtime_audit["differenceCount"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
