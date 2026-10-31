"""Audit the pinned Matcha text frontend without loading a model or NPU runtime.

This is coverage evidence, never speech-quality approval. The CLI exits 2 for
unknown input/token coverage or unresolved number/date pronunciation risks and
keeps its JSON report. It does not rewrite narration or generate a dictionary.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib
import importlib.abc
import importlib.util
import json
import logging
from pathlib import Path
import re
import sys

REVISION = "f2c2d730403e1d4c732add799f0414da34695043"
ARCHIVE_SHA256 = "52aee0cb7f1bf25a04ad01ee906f27b7b665df22b2d266cfea97a7e43460718c"
FRONTEND_ARCHIVE_SHA256 = "271b804af570400d3bcdcb53bf6e53cc9f75180ee763b9f13eb5eaf2b0d086ef"
BACKEND_PATH = "rkvoice_stream/backends/tts/matcha.py"
NPU_ROOTS = {"rknn", "rknnlite", "rkllm"}
TERMS = ("DSH", "Cordis", "SDK", "ACP", "PTY", "LSP")
ITEM_RE = re.compile(r"[一-鿿]+|[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ'\-]*|\s+|.")
WORD_RE = re.compile(r"[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ'\-]*")
NUMERIC_RE = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日|\d+(?:\.\d+)?")
PUNCT_NORMALIZE = {"：": ",", ":": ",", "，": ",", "、": ",", "。": ".",
                   "！": "!", "？": "?", "；": ";"}
PUNCT_DROP = frozenset("-'（）《》")


def identity(path: Path) -> dict:
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def require_identity(path: Path, expected: dict) -> dict:
    found = identity(path)
    if found["bytes"] != expected.get("bytes") or found["sha256"] != expected.get("sha256"):
        raise RuntimeError("file differs from verified inventory: " + str(path))
    return found


class _NoNpuImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in NPU_ROOTS:
            raise RuntimeError("frontend audit attempted a forbidden NPU import: " + fullname)
        return None


@contextmanager
def no_npu_imports():
    if any(name.split(".")[0] in NPU_ROOTS for name in sys.modules):
        raise RuntimeError("frontend audit requires a fresh process without NPU imports")
    guard = _NoNpuImports()
    sys.meta_path.insert(0, guard)
    try:
        yield
    finally:
        sys.meta_path.remove(guard)


def lexicon_coverage(raw: str, lexicon: dict, offset: int) -> tuple[list, list]:
    """Follow the pinned frontend's longest-match, at-most-four-character lookup."""
    matched, unknown = [], []
    index = 0
    while index < len(raw):
        for length in range(min(4, len(raw) - index), 0, -1):
            word = raw[index:index + length]
            if word in lexicon:
                matched.append({"start": offset + index, "end": offset + index + length,
                                "text": word, "lexicon_tokens": list(lexicon[word])})
                index += length
                break
        else:
            unknown.append({"code": "unknown_chinese_character", "start": offset + index,
                            "end": offset + index + 1, "text": raw[index]})
            index += 1
    return matched, unknown


def audit_text(text: str, lexicon: dict, tokens: dict, chinese_tokens, english_tokens) -> dict:
    """Pure audit with injected frontend callbacks; no I/O or model imports.

    english_tokens returns {tokens: [...], ipa: str|None, route: str}. Positions
    are zero-based Python Unicode code points, with exclusive ends.
    """
    rows, errors, emitted = [], [], []
    if not text.strip():
        errors.append({"code": "empty_text"})
    for match in ITEM_RE.finditer(text):
        raw, start, end = match.group(), match.start(), match.end()
        row = {"text": raw, "start": start, "end": end}
        if raw.isspace():
            row.update(kind="whitespace", route="ignored_whitespace", tokens=[], token_ids=[])
            rows.append(row)
            continue
        is_word = bool(WORD_RE.fullmatch(raw))
        try:
            if "一" <= raw[0] <= "鿿":
                row.update(kind="chinese", route="lexicon_with_tone_sandhi")
                row["lexicon_matches"], unknown = lexicon_coverage(raw, lexicon, start)
                errors.extend(unknown)
                row["unknown_characters"] = unknown
                strings = list(chinese_tokens(raw))
            elif is_word:
                row.update(kind="latin", **english_tokens(raw))
                strings = list(row["tokens"])
            else:
                ch = PUNCT_NORMALIZE.get(raw, raw)
                if ch in PUNCT_DROP:
                    row.update(kind="punctuation", route="explicit_punctuation_drop", tokens=[], token_ids=[])
                    rows.append(row)
                    continue
                if not ch.isalnum() and ch in tokens:
                    row.update(kind="punctuation", route="normalized_punctuation")
                    strings = [ch]
                else:
                    row.update(kind="digit" if raw.isdigit() else "symbol", **english_tokens(raw))
                    strings = list(row["tokens"])
            if not strings:
                errors.append({"code": "empty_phonemization", "start": start, "end": end, "text": raw})
            missing = [value for value in strings if value not in tokens]
            if missing:
                errors.append({"code": "unknown_phoneme_tokens", "start": start, "end": end,
                               "text": raw, "tokens": missing})
            row.update(tokens=strings, unknown_tokens=missing,
                       token_ids=[tokens[value] for value in strings if value in tokens])
        except Exception as exc:
            errors.append({"code": "frontend_exception", "start": start, "end": end,
                           "text": raw, "exception_type": type(exc).__name__})
            row.update(tokens=[], token_ids=[])
        rows.append(row)
        emitted.append((is_word, row["tokens"], row["token_ids"]))
    ids = []
    for index, (is_word, strings, item_ids) in enumerate(emitted):
        ids.extend(item_ids)
        if is_word and strings and " " in tokens and index + 1 < len(emitted) and emitted[index + 1][1]:
            ids.append(tokens[" "])
    risks = [{"code": "number_or_date_has_no_chinese_normalization", "start": match.start(),
              "end": match.end(), "text": match.group(),
              "detail": "Digits are routed individually through the English frontend; no date/number FST is applied."}
             for match in NUMERIC_RE.finditer(text)]
    return {"scope": "frontend_coverage_only", "audio_generated": False, "quality_validated": False,
            "text": text, "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "position_units": "zero_based_unicode_code_points_end_exclusive", "items": rows,
            "terms": {term: [row for row in rows if row["text"] == term] for term in TERMS},
            "token_ids": ids, "errors": errors, "risks": risks,
            "coverage_passed": not errors,
            "status": "unknown_coverage" if errors else "needs_pronunciation_review" if risks else "coverage_only"}


def load_frontend(root: Path):
    receipt_path = root / ".state/source.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (receipt.get("schema_version") != 2 or receipt.get("revision") != REVISION
            or receipt.get("archive_sha256") != ARCHIVE_SHA256):
        raise RuntimeError("run the updated prepare_source.py first; a pinned inventory receipt is required")
    expected = receipt.get("inventory", {}).get(BACKEND_PATH)
    if not expected:
        raise RuntimeError("verified source receipt lacks the Matcha frontend")
    vendor = root / "vendor" / ("rkvoice-stream-" + REVISION) / BACKEND_PATH
    vendor_identity = require_identity(vendor, expected)
    spec = importlib.util.find_spec("rkvoice_stream.backends.tts.matcha")
    if spec is None or not spec.origin:
        raise RuntimeError("the pinned rkvoice-stream package is not installed in this interpreter")
    backend_identity = require_identity(Path(spec.origin), expected)
    backend = importlib.import_module("rkvoice_stream.backends.tts.matcha")
    model_root = root / "models/matcha"
    model_receipt_path = model_root / ".frontend-verified.json"
    model_receipt = json.loads(model_receipt_path.read_text(encoding="utf-8"))
    if (model_receipt.get("schema_version") != 2
            or model_receipt.get("archive_sha256") != FRONTEND_ARCHIVE_SHA256):
        raise RuntimeError("run the updated download_matcha.py first; frontend inventory is required")
    frontend = model_root / "matcha-icefall-zh-en"
    file_identities = {}
    for name in ("lexicon.txt", "tokens.txt"):
        expected_file = model_receipt.get("inventory", {}).get("matcha-icefall-zh-en/" + name)
        if not expected_file:
            raise RuntimeError("verified model inventory lacks " + name)
        file_identities[name] = require_identity(frontend / name, expected_file)
    # Constructor and frontend methods do not call load(), preload(), inference(),
    # or import rknnlite. The process-level import guard enforces this boundary.
    engine = backend.RKNNMatchaVocoder("", "", str(frontend / "lexicon.txt"),
                                      str(frontend / "tokens.txt"), str(frontend / "espeak-ng-data"))
    engine._lexicon = {}
    for line in (frontend / "lexicon.txt").read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            engine._lexicon[parts[0]] = parts[1:]
    engine._token_to_id = backend.parse_tokens_file(str(frontend / "tokens.txt"))
    return backend, engine, {"source_revision": REVISION, "source_receipt": identity(receipt_path),
                             "backend_source": backend_identity, "vendor_source": vendor_identity,
                             "frontend_receipt": identity(model_receipt_path), **file_identities}


def audit_installed(root: Path, text: str) -> dict:
    warnings = []

    class Capture(logging.Handler):
        def emit(self, record):
            warnings.append(record.getMessage())

    with no_npu_imports():
        backend, engine, identities = load_frontend(root)
        logger = logging.getLogger(backend.__name__)
        capture = Capture(logging.WARNING)
        logger.addHandler(capture)
        try:
            capi = backend._EspeakPhonemizer.get(engine.data_dir)
            original_ipa, ipa_cache = engine._espeak_ipa, {}

            def cached_ipa(word):
                if word not in ipa_cache:
                    ipa_cache[word] = original_ipa(word)
                return ipa_cache[word]

            engine._espeak_ipa = cached_ipa

            def english(word):
                strings = engine._phonemize_english(word)
                return {"tokens": list(strings), "ipa": ipa_cache.get(word),
                        "route": "direct_model_token" if word in engine._token_to_id else "espeak_en_us"}

            result = audit_text(text, engine._lexicon, engine._token_to_id,
                                engine._chinese_token_strings, english)
            actual_ids = list(engine.text_to_tokens(text))
            result["matches_actual_frontend_tokens"] = actual_ids == result["token_ids"]
            if not result["matches_actual_frontend_tokens"]:
                result["errors"].append({"code": "audit_and_backend_tokenization_differ"})
                result.update(coverage_passed=False, status="unknown_coverage")
            result.update(identities=identities, backend_warnings=warnings,
                          espeak_c_api={"available": capi is not None,
                                        "fallback_policy": "Backend may fall back to CLI on C API call error; warnings are retained."},
                          npu_modules_loaded=[name for name in sys.modules if name.split(".")[0] in NPU_ROOTS])
        finally:
            logger.removeHandler(capture)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--text-file", type=Path, help="Default: root/samples/benchmark-zh.txt")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    source = args.text_file or root / "samples/benchmark-zh.txt"
    try:
        raw = source.read_bytes()
        if len(raw) > 65536:
            raise RuntimeError("text exceeds the 64KiB audit budget")
        result = audit_installed(root, raw.decode("utf-8").strip())
        result["text_file"] = identity(source)
    except Exception as exc:
        result = {"scope": "frontend_coverage_only", "status": "audit_failed", "coverage_passed": False,
                  "audio_generated": False, "quality_validated": False, "risks": [],
                  "errors": [{"code": "audit_exception", "exception_type": type(exc).__name__, "detail": str(exc)}]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output.resolve()), "status": result["status"],
                      "errors": len(result["errors"]), "risks": len(result["risks"])}, ensure_ascii=False))
    return 2 if result["errors"] or result["risks"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
