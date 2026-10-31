"""Explicit mixed-English routing for the pinned Kokoro v1.0 Chinese frontend.

Misaki 0.9.4 ZHG2P(version=None) copies non-Han text through unchanged and does
not invoke en_callable. Keep its Chinese/number normalization, but phonemize
each Latin word/acronym with the installed English frontend. This policy does
not expand abbreviations or approve pronunciation quality. The official
Kokoro frontend remains responsible for strict vocabulary validation.
"""
from __future__ import annotations

from importlib import metadata
import re
from typing import Callable

POLICY_ID = "kokoro-v10-zh-legacy-explicit-english-v1"
ACRONYM_POLICY = "ascii-uppercase-2plus-spell-letters"
LATIN_WORD = re.compile(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*")


def _load_components():
    """Load installed frontends only; never download a missing spaCy model."""
    if metadata.version("misaki") != "0.9.4":
        raise RuntimeError("this pronunciation policy requires misaki 0.9.4")
    import spacy
    if not spacy.util.is_package("en_core_web_sm"):
        raise RuntimeError("install the reviewed en_core_web_sm package before enabling this policy")
    import cn2an
    from misaki import en, zh
    from misaki.espeak import EspeakFallback

    chinese = zh.ZHG2P(version=None, unk="")
    if chinese.frontend is not None:
        raise RuntimeError("expected the pinned legacy Chinese frontend")
    english = en.G2P(trf=False, british=False,
                     fallback=EspeakFallback(british=False), unk="")

    def normalize(text):
        # Apply the original Chinese policy to the complete raw input once;
        # normalizing fragments could change date/number interpretation and
        # strip the spaces at every English/Chinese boundary.
        return zh.ZHG2P.map_punctuation(cn2an.transform(text, "an2cn"))

    return normalize, chinese.legacy_call, english


def _english_phonemes(value) -> str:
    if isinstance(value, tuple) and len(value) == 2:
        phonemes, tokens = value
        # Misaki can replace unresolved tokens with unk="". Catch that before
        # an otherwise nonempty word/compound silently loses a component.
        if tokens is not None:
            for token in tokens:
                if getattr(token, "phonemes", None) is None:
                    raise ValueError("English frontend left an unresolved token")
    else:
        phonemes = value
    if not isinstance(phonemes, str):
        raise TypeError("English frontend must return a phoneme string")
    if not phonemes.strip():
        raise ValueError("English frontend returned empty phonemes")
    return phonemes


def make_mixed_chinese_g2p_factory(
    official_factory: Callable[[str], Callable[[str], str]],
    *,
    components_factory: Callable | None = None,
) -> Callable[[str], Callable[[str], str]]:
    """Wrap frontend.g2p_factory; override only its normalized ``z`` route.

    ``components_factory`` is an offline-test seam returning three callables:
    normalize(raw)->str, legacy_chinese(non_latin_fragment)->str, and
    english(latin_word)->str or (str, Misaki tokens). Production uses only the
    fixed, installed Misaki frontends. Construct this wrapper once and assign
    it to ``frontend.g2p_factory``; the official frontend caches it per route.
    """
    if not callable(official_factory):
        raise TypeError("official_factory must be callable")
    load = components_factory or _load_components

    def factory(route: str) -> Callable[[str], str]:
        if route != "z":
            return official_factory(route)
        normalize, chinese, english = load()
        if not all(callable(function) for function in (normalize, chinese, english)):
            raise TypeError("frontend components must be callable")

        def call(text: str) -> str:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("text must be non-empty")
            normalized = normalize(text)
            if not isinstance(normalized, str) or not normalized.strip():
                raise ValueError("Chinese normalization returned empty or invalid text")
            parts, end = [], 0
            for match in LATIN_WORD.finditer(normalized):
                if match.start() > end:
                    fragment = normalized[end:match.start()]
                    value = chinese(fragment)
                    if not isinstance(value, str) or (fragment.strip() and not value.strip()):
                        raise ValueError("legacy Chinese frontend returned empty or invalid phonemes")
                    parts.append(value)
                # Phonemize source text exactly once. Never feed generated
                # English phonemes back into the Chinese normalizer/splitter.
                word = match.group()
                # Capitalized words remain words. Multi-letter all-uppercase
                # ASCII tokens have an explicit initialism policy, avoiding
                # backend guesses such as ACP -> "ackp" or PTY -> "tie".
                spoken = " ".join(word) if (len(word) >= 2 and word.isascii()
                                              and word.isalpha() and word.isupper()) else word
                parts.append(_english_phonemes(english(spoken)))
                end = match.end()
            if end < len(normalized):
                fragment = normalized[end:]
                value = chinese(fragment)
                if not isinstance(value, str) or (fragment.strip() and not value.strip()):
                    raise ValueError("legacy Chinese frontend returned empty or invalid phonemes")
                parts.append(value)
            return "".join(parts)

        return call

    return factory
