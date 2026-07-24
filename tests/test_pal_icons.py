import hashlib
import json
import re
import struct
import unittest
import zlib
from collections import defaultdict
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PALS_PATH = ROOT / "data" / "pals.verified.json"
RAW_ASSETS_PATH = ROOT / "evidence" / "build-24181105.assets.json"
ICON_MANIFEST_PATH = ROOT / "evidence" / "build-24181527.pal-icons.json"
LOCAL_ICON = re.compile(r"assets/pal-icons/[a-z0-9_]+[.]png")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SHA256 = re.compile(r"[0-9a-f]{64}")


def paeth_predictor(left, above, upper_left):
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def png_rgba_and_validate(path):
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise AssertionError(f"not a PNG: {path}")

    cursor = len(PNG_SIGNATURE)
    dimensions = None
    idat_payloads = []
    saw_idat = False
    saw_iend = False
    while cursor < len(data):
        if cursor + 12 > len(data):
            raise AssertionError(f"truncated PNG chunk: {path}")
        length = struct.unpack(">I", data[cursor:cursor + 4])[0]
        chunk_type = data[cursor + 4:cursor + 8]
        chunk_end = cursor + 12 + length
        if chunk_end > len(data):
            raise AssertionError(f"truncated PNG payload: {path}")
        payload = data[cursor + 8:cursor + 8 + length]
        expected_crc = struct.unpack(">I", data[cursor + 8 + length:chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(payload, actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise AssertionError(f"invalid PNG CRC: {path}")
        if chunk_type == b"IHDR":
            if dimensions is not None or length != 13:
                raise AssertionError(f"invalid PNG IHDR: {path}")
            width, height, bit_depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if width <= 0 or height <= 0:
                raise AssertionError(f"invalid PNG dimensions: {path}")
            if (bit_depth, color_type, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                raise AssertionError(f"expected non-interlaced RGBA8 PNG: {path}")
            dimensions = (width, height)
        elif chunk_type == b"IDAT":
            saw_idat = True
            idat_payloads.append(payload)
        elif chunk_type == b"IEND":
            if length != 0:
                raise AssertionError(f"invalid PNG IEND: {path}")
            saw_iend = True
            cursor = chunk_end
            break
        cursor = chunk_end

    if dimensions is None or not saw_idat or not saw_iend or cursor != len(data):
        raise AssertionError(f"incomplete PNG: {path}")

    width, height = dimensions
    bytes_per_pixel = 4
    row_bytes = width * bytes_per_pixel
    filtered = zlib.decompress(b"".join(idat_payloads))
    if len(filtered) != height * (row_bytes + 1):
        raise AssertionError(f"unexpected decompressed PNG size: {path}")

    rgba = bytearray()
    previous = bytearray(row_bytes)
    for row_index in range(height):
        offset = row_index * (row_bytes + 1)
        filter_type = filtered[offset]
        encoded = filtered[offset + 1:offset + 1 + row_bytes]
        if filter_type not in range(5):
            raise AssertionError(f"unknown PNG filter {filter_type}: {path}")
        decoded = bytearray(row_bytes)
        for index, value in enumerate(encoded):
            left = decoded[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            else:
                predictor = paeth_predictor(left, above, upper_left)
            decoded[index] = (value + predictor) & 0xFF
        rgba.extend(decoded)
        previous = decoded
    return dimensions, bytes(rgba)


class PalIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(PALS_PATH.read_text(encoding="utf-8"))
        cls.pals = cls.payload["pals"]
        cls.raw_assets = json.loads(RAW_ASSETS_PATH.read_text(encoding="utf-8"))
        cls.manifest = json.loads(ICON_MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.raw_icons = {
            row["id"].lower(): row
            for row in cls.raw_assets["icons"]
            if "t_dummy_icon" not in row["path"].lower()
        }
        cls.manifest_icons = {
            row["iconId"]: row for row in cls.manifest["icons"]
        }

    def test_01_every_released_pal_has_a_strict_local_png_path(self):
        self.assertEqual(len(self.pals), 288)
        for pal in self.pals:
            icon = pal.get("icon")
            self.assertIsInstance(icon, str, pal["id"])
            self.assertRegex(icon, rf"\A{LOCAL_ICON.pattern}\Z", pal["id"])
            self.assertNotIn("://", icon)
            self.assertNotIn("..", PurePosixPath(icon).parts)
            self.assertFalse(PurePosixPath(icon).is_absolute())

    def test_02_manifest_is_pinned_to_the_fixed_client_and_icon_table(self):
        manifest = self.manifest
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["gameVersion"], "v1.0.1.100619")
        self.assertEqual(manifest["sourceClient"], {
            "appId": "1623730",
            "buildId": "24181527",
            "depotId": "1623731",
            "depotManifestId": "2714631871676494093",
            "pakFile": "Pal-Windows.pak",
            "pakBytes": 40_526_106_335,
            "pakSha256": "fe2d7b8548d5be0649b6bb3e49aadc79529c2e7d138baaacece3a3563a864227",
        })
        self.assertEqual(manifest["sourceMapping"], {
            "iconTable": "Pal/Content/Pal/DataTable/Character/DT_PalCharacterIconDataTable",
            "evidencePath": "evidence/build-24181105.assets.json",
            "evidenceSha256": "e23a12ceffae5792b69c8faebe8ee3fbacbc09f0bd88572410d2b3b59aca1fe0",
            "catalogMappingsSha256": "561ef13c8ee3cf785e4de8aa5bc9b3ad1646e416d895f1d1166fa27ebdfd26b0",
            "parserMappings": "PalworldModding/UsefulFiles@42cf396e714c166f17950a9c964583e0cadf2a15",
            "parserMappingsSha256": "241c45de9d5b55b246cd4b39d62b9209faf7758ce0637e1f7a545aa0f75f71f0",
        })
        self.assertEqual(manifest["extractor"], {
            "tableExtractor": "Awy64/palworld-atlas-data@0385b3fd8bd757240d4a2c79615145122669abd5",
            "textureDecoder": "FabianFG/CUE4Parse@ecad882a3049df6f27e0c5c3a3531346305c010b",
            "cue4ParseVersion": "1.2.2.202607",
        })
        self.assertEqual(manifest["counts"], {
            "palForms": 288,
            "uniqueIcons": 287,
            "sharedIcons": 1,
        })
        self.assertEqual(len(manifest["icons"]), 287)
        self.assertEqual(len(self.manifest_icons), 287)

    def test_03_every_mapping_is_the_exact_fixed_table_soft_object_path(self):
        expected_users = defaultdict(set)
        for pal in self.pals:
            source_id = pal["sourceId"].lower()
            tribe = pal["tribe"].lower()
            icon_row = self.raw_icons.get(source_id) or self.raw_icons.get(tribe)
            self.assertIsNotNone(icon_row, pal["id"])
            icon_id = icon_row["id"].lower()
            expected_path = f"assets/pal-icons/{icon_id}.png"
            self.assertEqual(pal["icon"], expected_path, pal["id"])

            record = self.manifest_icons[icon_id]
            self.assertEqual(record["sourceTableId"], icon_row["id"])
            self.assertEqual(record["objectPath"], icon_row["path"])
            self.assertEqual(record["outputPath"], expected_path)
            self.assertIn(pal["id"], record["palIds"])
            expected_users[icon_id].add(pal["id"])

        for icon_id, record in self.manifest_icons.items():
            self.assertEqual(set(record["palIds"]), expected_users[icon_id])
        fallbacks = {
            pal_id
            for record in self.manifest_icons.values()
            for pal_id in record["tribeFallbackPalIds"]
        }
        self.assertEqual(fallbacks, {"plantslime_flower"})

    def test_04_every_referenced_icon_matches_its_png_manifest(self):
        checked = {}
        for pal in self.pals:
            relative = PurePosixPath(pal["icon"])
            path = ROOT.joinpath(*relative.parts).resolve()
            self.assertTrue(path.is_relative_to(ROOT), pal["id"])
            self.assertTrue(path.is_file(), pal["id"])
            if path not in checked:
                data = path.read_bytes()
                dimensions, rgba = png_rgba_and_validate(path)
                record = self.manifest_icons[path.stem]
                self.assertEqual(dimensions, (record["width"], record["height"]))
                self.assertEqual(len(data), record["pngBytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), record["pngSha256"])
                self.assertEqual(len(rgba), record["decodedPixelBytes"])
                self.assertEqual(
                    hashlib.sha256(rgba).hexdigest(),
                    record["decodedPixelSha256"],
                )
                self.assertRegex(record["pngSha256"], rf"\A{SHA256.pattern}\Z")
                self.assertRegex(record["decodedPixelSha256"], rf"\A{SHA256.pattern}\Z")
                self.assertEqual(record["pixelFormat"], "PF_R8G8B8A8")
                self.assertEqual(
                    record["decodedPixelBytes"],
                    record["width"] * record["height"] * 4,
                )
                checked[path] = dimensions
        self.assertEqual(len(checked), 287)
        self.assertEqual(
            {path.relative_to(ROOT).as_posix() for path in checked},
            {record["outputPath"] for record in self.manifest_icons.values()},
        )
        icon_dir = ROOT / "assets" / "pal-icons"
        self.assertEqual(
            {path.relative_to(ROOT).as_posix() for path in icon_dir.glob("*.png")},
            {record["outputPath"] for record in self.manifest_icons.values()},
        )

    def test_05_only_the_fixed_asset_table_fallback_shares_an_icon(self):
        users = defaultdict(set)
        for pal in self.pals:
            users[pal["icon"]].add(pal["id"])
        shared = {icon: pal_ids for icon, pal_ids in users.items() if len(pal_ids) > 1}
        self.assertEqual(shared, {
            "assets/pal-icons/plantslime.png": {"plantslime", "plantslime_flower"},
        })
        shared_records = [
            record for record in self.manifest_icons.values() if record["shared"]
        ]
        self.assertEqual(len(shared_records), 1)
        self.assertEqual(shared_records[0]["iconId"], "plantslime")

    def test_06_extracted_pixel_payloads_are_unique_and_expected_sizes(self):
        pixel_hashes = [
            record["decodedPixelSha256"]
            for record in self.manifest_icons.values()
        ]
        png_hashes = [record["pngSha256"] for record in self.manifest_icons.values()]
        self.assertEqual(len(set(pixel_hashes)), 287)
        self.assertEqual(len(set(png_hashes)), 287)
        dimensions = defaultdict(list)
        for record in self.manifest_icons.values():
            dimensions[(record["width"], record["height"])].append(record["iconId"])
        self.assertEqual(len(dimensions[(128, 128)]), 286)
        self.assertEqual(dimensions[(512, 512)], ["snowtigerbeastman"])
        self.assertEqual(set(dimensions), {(128, 128), (512, 512)})


if __name__ == "__main__":
    unittest.main(verbosity=2)
