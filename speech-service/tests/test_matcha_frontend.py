"""Frontend coverage tests use no models, native runtimes, downloads or NumPy."""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "audit_matcha_frontend", Path(__file__).resolve().parents[1] / "scripts/audit_matcha_frontend.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class FrontendCoverage(unittest.TestCase):
    def setUp(self):
        self.lexicon = {"你好": ["ni2", "hao3"], "世界": ["shi4", "jie4"]}
        self.tokens = {" ": 1, "ni2": 2, "hao3": 3, "shi4": 4, "jie4": 5,
                       "d": 6, "i": 7, "s": 8, "e": 9, "h": 10, ",": 11, ".": 12}
        self.calls = []

    def chinese(self, text):
        matched, _ = audit.lexicon_coverage(text, self.lexicon, 0)
        return [token for row in matched for token in row["lexicon_tokens"]]

    def english(self, text):
        self.calls.append(text)
        return {"tokens": ["d", "i"], "ipa": "dˈi", "route": "espeak_en_us"}

    def run_audit(self, text, english=None):
        return audit.audit_text(text, self.lexicon, self.tokens, self.chinese, english or self.english)

    def test_covers_terms_keeps_actual_ipa_and_boundaries_without_claiming_quality(self):
        result = self.run_audit("你好 DSH、Cordis、SDK、ACP、PTY 和 LSP。")
        self.assertFalse(result["coverage_passed"])  # 和 is deliberately absent from fixture lexicon.
        self.assertFalse(result["quality_validated"])
        for term in audit.TERMS:
            row = result["terms"][term][0]
            self.assertEqual(row["ipa"], "dˈi")
            self.assertEqual(row["token_ids"], [6, 7])
            self.assertEqual(row["route"], "espeak_en_us")
        # Latin followed by a rendered comma gets the model word-boundary token.
        first_term = result["token_ids"].index(6)
        self.assertEqual(result["token_ids"][first_term:first_term + 4], [6, 7, 1, 11])

    def test_unknown_chinese_is_not_masked_by_surrounding_known_text(self):
        result = self.run_audit("你好龘世界")
        self.assertEqual(result["errors"], [{"code": "unknown_chinese_character", "start": 2,
                                            "end": 3, "text": "龘"}])
        self.assertEqual(result["token_ids"], [2, 3, 4, 5])
        self.assertEqual(result["status"], "unknown_coverage")

    def test_longest_match_uses_four_character_limit(self):
        matched, unknown = audit.lexicon_coverage("一二三四五", {"一二三四五": ["x"],
                                                   "一二三四": ["a"], "五": ["b"]}, 5)
        self.assertEqual([row["text"] for row in matched], ["一二三四", "五"])
        self.assertEqual([row["start"] for row in matched], [5, 9])
        self.assertEqual(unknown, [])

    def test_empty_english_and_unknown_ipa_are_errors(self):
        empty = self.run_audit("SDK", lambda _: {"tokens": [], "ipa": "", "route": "espeak_en_us"})
        self.assertEqual(empty["errors"][0]["code"], "empty_phonemization")
        unknown = self.run_audit("Cordis", lambda _: {"tokens": ["d", "Ω"], "ipa": "dΩ", "route": "espeak_en_us"})
        self.assertEqual(unknown["errors"][0]["tokens"], ["Ω"])
        self.assertEqual(unknown["items"][0]["unknown_tokens"], ["Ω"])
        self.assertEqual(unknown["token_ids"], [6])

    def test_digits_are_observed_individually_and_date_decimal_risks_remain(self):
        result = self.run_audit("2026年10月30日，1.0倍，8。")
        self.assertEqual(self.calls, list("20261030108"))
        self.assertEqual([row["text"] for row in result["risks"]], ["2026年10月30日", "1.0", "8"])
        self.assertTrue(all(row["code"] == "number_or_date_has_no_chinese_normalization" for row in result["risks"]))
        # Full digit token coverage does not approve their pronunciation.
        simple = self.run_audit("8")
        self.assertTrue(simple["coverage_passed"])
        self.assertEqual(simple["status"], "needs_pronunciation_review")

    def test_punctuation_policy_and_whitespace_are_explicit_and_not_phonemized(self):
        result = self.run_audit("你好 （世界）！ \n")
        self.assertEqual(self.calls, ["！"])  # Unknown punctuation is sent to English, as upstream does.
        self.assertEqual(sum(row["route"] == "explicit_punctuation_drop" for row in result["items"]), 2)
        self.assertEqual(result["items"][-1]["route"], "ignored_whitespace")

    def test_exception_and_empty_text_cannot_succeed(self):
        def broken(_):
            raise ValueError("fixture")
        result = self.run_audit("SDK", broken)
        self.assertEqual(result["errors"][0]["code"], "frontend_exception")
        self.assertEqual(result["errors"][0]["exception_type"], "ValueError")
        self.assertFalse(result["coverage_passed"])
        self.assertFalse(self.run_audit(" \n")["coverage_passed"])

    def test_npu_import_guard_blocks_native_runtime_and_restores_import_stack(self):
        previous = list(sys.meta_path)
        with audit.no_npu_imports():
            with self.assertRaisesRegex(RuntimeError, "forbidden NPU import"):
                importlib.import_module("rknnlite.api")
        self.assertEqual(sys.meta_path, previous)
        with patch.dict(sys.modules, {"rknn": object()}):
            with self.assertRaisesRegex(RuntimeError, "fresh process"):
                with audit.no_npu_imports():
                    pass

    def test_inventory_identity_rejects_corrupted_source_without_importing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "source.py"
            target.write_bytes(b"original\n")
            expected = {"bytes": 9, "sha256": hashlib.sha256(b"original\n").hexdigest()}
            self.assertEqual(audit.require_identity(target, expected)["sha256"], expected["sha256"])
            target.write_bytes(b"modified\n")
            with self.assertRaisesRegex(RuntimeError, "verified inventory"):
                audit.require_identity(target, expected)

    def test_cli_writes_failure_evidence_and_returns_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "text.txt"
            source.write_text("SDK", encoding="utf-8")
            output = root / "out/audit.json"
            argv = ["audit_matcha_frontend.py", "--root", str(root), "--text-file", str(source), "--output", str(output)]
            with patch.object(sys, "argv", argv), patch.object(audit, "audit_installed", side_effect=RuntimeError("fixture failure")):
                self.assertEqual(audit.main(), 2)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "audit_failed")
            self.assertFalse(result["audio_generated"])
            self.assertIn("fixture failure", result["errors"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
