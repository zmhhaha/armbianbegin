"""Small offline fixtures for revalidation; no network or model runtime imports."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source = load_script("prepare_source")
matcha = load_script("download_matcha")


def tar_bytes(files, mode):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode=mode) as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


class SourceIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "vendor" / ("rkvoice-stream-" + source.REVISION)
        self.receipt = self.root / ".state/source.json"
        prefix = "rkvoice-stream-" + source.REVISION + "/"
        self.archive = tar_bytes({prefix + "pyproject.toml": b"[project]\nname='fixture'\n",
                                 prefix + "rkvoice_stream/engine/tts.py": b"original source\n"}, "w:gz")
        self.addCleanup(patch.stopall)
        patch.object(source, "ARCHIVE_SHA256", hashlib.sha256(self.archive).hexdigest()).start()
        self.download = patch.object(source, "download_archive", return_value=self.archive).start()
        source.prepare(self.root)

    def legacy_receipt(self):
        data = json.loads(self.receipt.read_text())
        data.pop("inventory")
        data.pop("schema_version")
        self.receipt.write_text(json.dumps(data), encoding="utf-8")

    def test_rerun_checks_source_and_accepts_generated_build_and_bytecode(self):
        for name in ("build/lib/generated.py", "fixture.egg-info/PKG-INFO",
                     "rkvoice_stream/engine/__pycache__/tts.cpython-310.pyc"):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"generated, not source")
        self.download.reset_mock()
        data = source.prepare(self.root)
        self.download.assert_not_called()
        self.assertIn("rkvoice_stream/engine/tts.py", data["inventory"])

    def test_existing_inventory_rejects_missing_or_changed_source_without_repair(self):
        target = self.source / "rkvoice_stream/engine/tts.py"
        original_receipt = self.receipt.read_bytes()
        target.write_bytes(b"damaged source\n")
        with self.assertRaisesRegex(RuntimeError, "checksum/size mismatch"):
            source.prepare(self.root)
        self.assertEqual(target.read_bytes(), b"damaged source\n")
        target.unlink()
        with self.assertRaisesRegex(RuntimeError, "missing or linked"):
            source.prepare(self.root)
        self.assertFalse(target.exists())
        self.assertEqual(self.receipt.read_bytes(), original_receipt)

    def test_legacy_migration_uses_archive_and_rejects_corruption(self):
        self.legacy_receipt()
        self.download.reset_mock()
        data = source.prepare(self.root)
        self.download.assert_called_once_with()
        self.assertEqual(data["schema_version"], 2)
        self.legacy_receipt()
        original_receipt = self.receipt.read_bytes()
        (self.source / "rkvoice_stream/engine/tts.py").write_bytes(b"damaged source\n")
        with self.assertRaisesRegex(RuntimeError, "checksum/size mismatch"):
            source.prepare(self.root)
        self.assertEqual(self.receipt.read_bytes(), original_receipt)

    def test_additional_source_in_trusted_package_is_rejected(self):
        (self.source / "rkvoice_stream/extra.py").write_bytes(b"unexpected code\n")
        with self.assertRaisesRegex(RuntimeError, "unexpected file"):
            source.prepare(self.root)


class MatchaIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = {"matcha-icefall-zh-en/model-steps-3.onnx": b"acoustic fixture",
                      "matcha-icefall-zh-en/tokens.txt": b"tokens fixture",
                      "matcha-icefall-zh-en/lexicon.txt": b"lexicon fixture",
                      "matcha-icefall-zh-en/number-zh.fst": b"FST fixture"}
        raw = tar_bytes(self.files, "w:bz2")
        self.archive = self.root / "fixture.tar.bz2"
        self.archive.write_bytes(raw)
        self.addCleanup(patch.stopall)
        patch.object(matcha, "ARTIFACTS", [(self.archive.name, "unused", len(raw),
                     hashlib.sha256(raw).hexdigest())]).start()
        patch.object(matcha, "ACOUSTIC_SHA256", hashlib.sha256(
            self.files["matcha-icefall-zh-en/model-steps-3.onnx"]).hexdigest()).start()
        matcha.extract_frontend(self.archive, self.root)
        self.marker = self.root / ".frontend-verified.json"

    def legacy_marker(self):
        data = json.loads(self.marker.read_text())
        self.marker.write_text(json.dumps({"archive_sha256": data["archive_sha256"],
                                          "bytes": data["bytes"]}), encoding="utf-8")

    def test_legacy_marker_upgrades_only_after_actual_tar_comparison(self):
        self.legacy_marker()
        matcha.extract_frontend(self.archive, self.root)
        data = json.loads(self.marker.read_text())
        self.assertEqual(set(data["inventory"]), set(self.files))
        self.assertEqual(data["schema_version"], 2)

    def test_legacy_and_current_markers_reject_missing_or_corrupted_model_and_fst(self):
        for legacy in (False, True):
            for name in ("model-steps-3.onnx", "tokens.txt", "number-zh.fst"):
                for damage in ("missing", "changed"):
                    with self.subTest(legacy=legacy, name=name, damage=damage):
                        if legacy:
                            self.legacy_marker()
                        target = self.root / "matcha-icefall-zh-en" / name
                        expected = self.files["matcha-icefall-zh-en/" + name]
                        if damage == "missing":
                            target.unlink()
                        else:
                            target.write_bytes(b"x" * len(expected))
                        old_marker = self.marker.read_bytes()
                        with self.assertRaisesRegex(RuntimeError, "missing|checksum/size mismatch"):
                            matcha.extract_frontend(self.archive, self.root)
                        self.assertEqual(self.marker.read_bytes(), old_marker)
                        self.assertEqual(target.exists(), damage == "changed")
                        if target.exists():
                            self.assertEqual(target.read_bytes(), b"x" * len(expected))
                        target.write_bytes(expected)
                        # Restore a verified current marker before the next case.
                        matcha.extract_frontend(self.archive, self.root)

    def test_corrupt_existing_download_fails_without_network_or_replacement(self):
        target = self.root / "vocos.onnx"
        target.write_bytes(b"corrupt")
        with patch.object(matcha.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(RuntimeError, "existing artifact checksum/size mismatch"):
                matcha.fetch(target, "unused", 4, hashlib.sha256(b"good").hexdigest())
            network.assert_not_called()
        self.assertEqual(target.read_bytes(), b"corrupt")

    def test_429_keeps_partial_untrusted_and_explicit_rerun_can_download(self):
        target = self.root / "vocos.onnx"
        partial = self.root / "vocos.onnx.part"
        partial.write_bytes(b"untrusted partial")
        error = urllib.error.HTTPError("https://fixture.invalid", 429, "limited", {}, None)
        with patch.object(matcha.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                matcha.fetch(target, "https://fixture.invalid", 4, hashlib.sha256(b"good").hexdigest())
        self.assertFalse(target.exists())
        with patch.object(matcha.urllib.request, "urlopen", return_value=io.BytesIO(b"good")), redirect_stdout(io.StringIO()):
            matcha.fetch(target, "https://fixture.invalid", 4, hashlib.sha256(b"good").hexdigest())
        self.assertEqual(target.read_bytes(), b"good")
        self.assertFalse(partial.exists())


if __name__ == "__main__":
    unittest.main()
