"""Offline archive fixtures; no torch import and no pickle execution."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location("male_voice_assets", Path(__file__).resolve().parents[1] / "scripts/download_male_voices.py")
assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assets)
from speech_service import voice_assets as tensors

# Exact 165-byte descriptor observed in BOTH fixed official voice archives.
# This is test input, never loaded by pickle or torch.
DESCRIPTOR = (
    b"\x80\x02ctorch._utils\n_rebuild_tensor_v2\nq\x00((X\x07\x00\x00\x00storageq\x01"
    b"ctorch\nFloatStorage\nq\x02X\x01\x00\x00\x000q\x03X\x03\x00\x00\x00cpuq\x04"
    b"J\x00\xfe\x01\x00tq\x05QK\x00M\xfe\x01K\x01M\x00\x01\x87q\x06"
    b"M\x00\x01M\x00\x01K\x01\x87q\x07\x89ccollections\nOrderedDict\nq\x08)Rq\x09tq\x0aRq\x0b."
)


def archive_bytes(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def tensor_archive(*, descriptor=DESCRIPTOR, raw=None, byteorder=b"little", extra=None):
    raw = struct.pack("<f", 0.125) * (510 * 256) if raw is None else raw
    members = {"archive/data.pkl": descriptor, "archive/byteorder": byteorder,
               "archive/data/0": raw, "archive/version": b"3\n",
               "archive/.data/serialization_id": b"0" * 40}
    members.update(extra or {})
    return archive_bytes(members)


class ArchiveInspection(unittest.TestCase):
    def test_inspection_reports_instructions_without_executing_pickle(self):
        raw = archive_bytes({"archive/data.pkl": b"\x80\x02N.", "archive/data/0": b"1234"})
        report = assets.inspect_archive(raw)
        self.assertFalse(report["pickle_executed"])
        self.assertEqual([row["opcode"] for row in report["instructions"]], ["PROTO", "NONE", "STOP"])

    def test_forbidden_global_is_rejected_without_execution(self):
        raw = archive_bytes({"archive/data.pkl": b"\x80\x02cos\nsystem\n."})
        with self.assertRaisesRegex(ValueError, "forbidden global"):
            assets.inspect_archive(raw)

    def test_unsafe_or_multiple_archive_roots_are_rejected(self):
        for entries in ({"../data.pkl": b"N."}, {"a/data.pkl": b"N.", "b/data/0": b"1234"},
                        {"a//data.pkl": b"N."}, {"a/../../data.pkl": b"N."}):
            with self.subTest(entries=list(entries)), self.assertRaises(ValueError):
                assets.inspect_archive(archive_bytes(entries))

    def test_missing_or_oversized_pickle_is_rejected(self):
        for entries in ({"a/other": b"N."}, {"a/data.pkl": b"x" * (assets.MAX_PICKLE_BYTES + 1)}):
            with self.assertRaises(ValueError):
                assets.inspect_archive(archive_bytes(entries))

    def test_valid_existing_fixed_asset_is_reused_and_corruption_never_repaired(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            row = {"bytes": 4, "sha256": hashlib.sha256(b"good").hexdigest()}
            (root / "zm_yunxi.pt").write_bytes(b"good")
            with patch.dict(assets.ASSETS, {"zm_yunxi": row}), patch.object(assets.urllib.request, "urlopen") as network:
                self.assertEqual(assets.fetch_asset(root, "zm_yunxi", "https://huggingface.co").read_bytes(), b"good")
                network.assert_not_called()
                (root / "zm_yunxi.pt").write_bytes(b"evil")
                with self.assertRaisesRegex(ValueError, "existing voice differs"):
                    assets.fetch_asset(root, "zm_yunxi", "https://huggingface.co")
                network.assert_not_called()
                self.assertEqual((root / "zm_yunxi.pt").read_bytes(), b"evil")


class FixedTensorConversion(unittest.TestCase):
    def test_observed_descriptor_and_storage_are_copied_without_pickle_execution(self):
        self.assertEqual(len(DESCRIPTOR), 165)
        self.assertEqual(hashlib.sha256(DESCRIPTOR).hexdigest(), tensors.DESCRIPTOR_SHA256)
        raw = struct.pack("<f", 0.125) * (510 * 256)
        # The decoder has no pickle or torch loader to invoke.
        self.assertEqual(tensors.decode_voice_archive(tensor_archive(raw=raw)), raw)
        self.assertEqual(len(raw), 522240)

    def test_changed_global_shape_offset_and_trailing_pickle_are_rejected(self):
        changes = [DESCRIPTOR.replace(b"torch\n", b"posix\n"),
                   DESCRIPTOR[:105] + b"\xfd" + DESCRIPTOR[106:],
                   DESCRIPTOR[:103] + b"\x01" + DESCRIPTOR[104:], DESCRIPTOR + b"N."]
        for descriptor in changes:
            with self.subTest(sha=hashlib.sha256(descriptor).hexdigest()), self.assertRaises(ValueError):
                tensors.decode_voice_archive(tensor_archive(descriptor=descriptor))

    def test_closure_endianness_storage_length_and_nonfinite_values_are_rejected(self):
        bad_raw = struct.pack("<f", float("nan")) + b"\x00" * (522240 - 4)
        cases = [tensor_archive(extra={"archive/extra": b"unreviewed"}),
                 tensor_archive(byteorder=b"big___"), tensor_archive(raw=b"\x00" * 4),
                 tensor_archive(raw=bad_raw)]
        for value in cases:
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                tensors.decode_voice_archive(value)

    def test_pinned_pt_rederivation_rejects_corrupt_raw_even_if_receipt_is_also_changed(self):
        pt = tensor_archive()
        row = {"bytes": len(pt), "sha256": hashlib.sha256(pt).hexdigest()}
        with tempfile.TemporaryDirectory() as temp, patch.dict(tensors.ASSETS, {"zm_yunxi": row}):
            directory = Path(temp)
            (directory / "zm_yunxi.pt").write_bytes(pt)
            receipt = tensors.stage_voice(directory, "zm_yunxi")
            raw, found = tensors.load_verified_voice(directory, "zm_yunxi")
            self.assertEqual(found, receipt)
            self.assertEqual(receipt["shape"], [510, 1, 256])
            self.assertEqual(receipt["conversion_method"], "descriptor-hash-checked-no-pickle")
            self.assertFalse(receipt["pickle_executed"])
            corrupt = struct.pack("<f", 0.25) * (510 * 256)
            (directory / "zm_yunxi.bin").write_bytes(corrupt)
            altered = tensors.receipt_for("zm_yunxi", corrupt)
            (directory / "zm_yunxi.receipt.json").write_text(json.dumps(altered, sort_keys=True, indent=2) + "\n")
            with self.assertRaisesRegex(ValueError, "derived voice bytes differ"):
                tensors.load_verified_voice(directory, "zm_yunxi")
            # Source content is independently pinned, even if all three files
            # are changed consistently by a faulty/malicious local process.
            (directory / "zm_yunxi.pt").write_bytes(tensor_archive(raw=corrupt))
            with self.assertRaisesRegex(ValueError, "fixed official asset"):
                tensors.load_verified_voice(directory, "zm_yunxi")

    def test_altered_receipt_missing_raw_and_unknown_voice_are_rejected(self):
        pt = tensor_archive()
        row = {"bytes": len(pt), "sha256": hashlib.sha256(pt).hexdigest()}
        with tempfile.TemporaryDirectory() as temp, patch.dict(tensors.ASSETS, {"zm_yunxi": row}):
            directory = Path(temp)
            (directory / "zm_yunxi.pt").write_bytes(pt)
            tensors.stage_voice(directory, "zm_yunxi")
            receipt_file = directory / "zm_yunxi.receipt.json"
            original = receipt_file.read_bytes()
            receipt_file.write_bytes(original.replace(b"float32", b"float64"))
            with self.assertRaisesRegex(ValueError, "receipt differs"):
                tensors.load_verified_voice(directory, "zm_yunxi")
            receipt_file.write_bytes(original)
            (directory / "zm_yunxi.bin").unlink()
            with self.assertRaisesRegex(ValueError, "file is missing"):
                tensors.load_verified_voice(directory, "zm_yunxi")
            with patch.object(tensors, "_bounded_file") as read:
                for function in (tensors.load_verified_voice, tensors.stage_voice):
                    with self.assertRaisesRegex(ValueError, "unsupported voice"):
                        function(directory, "../unknown")
                read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
