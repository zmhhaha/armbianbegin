"""Mixed routing tests use fake frontends, with no model or native imports."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


SPEC = importlib.util.spec_from_file_location(
    "speech_pronunciation", Path(__file__).resolve().parents[1] / "speech_service/pronunciation.py")
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class MixedPronunciation(unittest.TestCase):
    def setUp(self):
        self.normalized = []
        self.chinese_calls = []
        self.english_calls = []
        self.loaded = 0
        self.delegated = []

    def normalize(self, text):
        self.normalized.append(text)
        # Approximate only these explicit test fixtures. No dependency/model
        # behavior is claimed from this deterministic fake.
        return text.replace("2026年10月30日", "二零二六年十月三十日").replace("1.0", "一点零").replace("，", ", ").replace("。", ". ").strip()

    def chinese(self, fragment):
        self.chinese_calls.append(fragment)
        self.assertFalse(policy.LATIN_WORD.search(fragment))
        return fragment.replace("你好", "nihao").replace("世界", "shijie")

    def english(self, word):
        self.english_calls.append(word)
        return "<" + word + ">"

    def components(self):
        self.loaded += 1
        return self.normalize, self.chinese, self.english

    def official(self, route):
        self.delegated.append(route)
        return lambda text: route + ":" + text

    def factory(self, components=None):
        return policy.make_mixed_chinese_g2p_factory(
            self.official, components_factory=components or self.components)

    def test_only_z_is_overridden_and_components_are_lazy(self):
        factory = self.factory()
        self.assertEqual(self.loaded, 0)
        for route in ("a", "b", "j", "h", "unknown"):
            self.assertEqual(factory(route)("raw"), route + ":raw")
        self.assertEqual(self.delegated, ["a", "b", "j", "h", "unknown"])
        self.assertEqual(self.loaded, 0)
        factory("z")
        self.assertEqual(self.loaded, 1)

    def test_six_terms_use_explicit_initialisms_and_keep_cordis_as_a_word(self):
        result = self.factory()("z")("DSH、Cordis、SDK、ACP、PTY 和 LSP。")
        self.assertEqual(self.english_calls, ["D S H", "Cordis", "S D K", "A C P", "P T Y", "L S P"])
        self.assertEqual(result, "<D S H>、<Cordis>、<S D K>、<A C P>、<P T Y> 和 <L S P>. ".strip())

    def test_normalizes_whole_date_and_decimal_once_preserving_boundaries(self):
        text = "你好  SDK，2026年10月30日，1.0倍。"
        result = self.factory()("z")(text)
        self.assertEqual(self.normalized, [text])
        self.assertEqual(self.english_calls, ["S D K"])
        self.assertEqual(self.chinese_calls, ["你好  ", ", 二零二六年十月三十日, 一点零倍."])
        self.assertEqual(result, "nihao  <S D K>, 二零二六年十月三十日, 一点零倍.")

    def test_chinese_and_english_output_are_never_reprocessed_as_source(self):
        english_calls, chinese_calls = [], []

        def chinese(fragment):
            chinese_calls.append(fragment)
            return "ChinesePhonemes"

        def english(word):
            english_calls.append(word)
            return "IˈdiH"

        fn = self.factory(lambda: (lambda text: text, chinese, english))("z")
        self.assertEqual(fn("你好SDK世界"), "ChinesePhonemesIˈdiHChinesePhonemes")
        self.assertEqual(chinese_calls, ["你好", "世界"])
        self.assertEqual(english_calls, ["S D K"])

    def test_internal_apostrophes_hyphens_and_separate_spaces_remain(self):
        result = self.factory()("z")("don't  DeepSeek-Harness / SDK!")
        self.assertEqual(self.english_calls, ["don't", "DeepSeek-Harness", "S D K"])
        self.assertEqual(result, "<don't>  <DeepSeek-Harness> / <S D K>!")

    def test_spelling_policy_is_limited_to_two_or_more_uppercase_ascii_letters(self):
        self.factory()("z")("A API Api api iPhone AC")
        self.assertEqual(self.english_calls, ["A", "A P I", "Api", "api", "iPhone", "A C"])

    def test_unknown_english_empty_and_partial_unresolved_tokens_fail(self):
        for value in ("", "  ", None, ("d", [SimpleNamespace(phonemes=None)])):
            with self.subTest(value=value):
                fn = self.factory(lambda: (lambda text: text, self.chinese, lambda word: value))("z")
                with self.assertRaises((ValueError, TypeError)):
                    fn("SDK")

    def test_valid_misaki_tuple_and_unknown_symbols_are_preserved_for_official_gate(self):
        fn = self.factory(lambda: (lambda text: text, self.chinese,
                                   lambda word: ("dˈiΩ", [SimpleNamespace(phonemes="dˈiΩ")])))("z")
        # Policy does not delete unsupported phonemes to make _ids accept them.
        self.assertEqual(fn("SDK🙂"), "dˈiΩ🙂")
        self.assertEqual(self.chinese_calls, ["🙂"])

    def test_pure_chinese_uses_legacy_after_one_full_normalization(self):
        result = self.factory()("z")("你好，世界。")
        self.assertEqual(result, "nihao, shijie.")
        self.assertEqual(self.chinese_calls, ["你好, 世界."])
        self.assertEqual(self.english_calls, [])

    def test_missing_or_empty_chinese_output_and_invalid_input_fail(self):
        fn = self.factory(lambda: (lambda text: text, lambda fragment: "", self.english))("z")
        with self.assertRaisesRegex(ValueError, "legacy Chinese"):
            fn("你好SDK")
        for text in ("", " \n", None, 1):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "text must be non-empty"):
                fn(text)


if __name__ == "__main__":
    unittest.main()
