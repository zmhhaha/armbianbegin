#!/usr/bin/env python3
"""Offline CPU reference for Matcha-Icefall-ZH-EN + original Vocos ONNX.

No download, server, NPU access, or installation is performed by this script.
Dependency: sherpa-onnx (and its numpy dependency); WAV uses the stdlib.

Example:
  python matcha-cpu-baseline.py \
    --acoustic models/matcha-icefall-zh-en/model-steps-3.onnx \
    --vocoder models/vocos-16khz-univ.onnx \
    --text '你好，欢迎使用视频工作台。' --output out/matcha-cpu.wav

Uses sherpa's native lexicon/FST frontend, not rkvoice-stream's custom frontend.
Thus it is a complete CPU reference, not a controlled same-frontend NPU A/B.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
import wave


def rss() -> dict[str, int | None]:
    current = None
    try:
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                current = int(line.split()[1]) * 1024
                break
    except (OSError, ValueError):
        pass
    peak = None
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak = int(value if sys.platform == 'darwin' else value * 1024)
    except (ImportError, OSError, ValueError):
        pass
    return {'rss_bytes': current, 'process_peak_rss_bytes': peak}


def model_identity(path: Path) -> dict[str, str | int]:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size,
            'sha256': digest.hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--acoustic', required=True, type=Path)
    parser.add_argument('--vocoder', required=True, type=Path)
    parser.add_argument('--tokens', type=Path)
    parser.add_argument('--lexicon', action='append', type=Path,
                        help='Repeat for Chinese and English lexicons; default acoustic-dir/lexicon.txt')
    parser.add_argument('--rule', action='append', type=Path,
                        help='Repeat for FSTs; default phone/date/number-zh.fst in acoustic-dir')
    parser.add_argument('--no-rules', action='store_true',
                        help='Explicitly disable text normalization; recorded in the result')
    parser.add_argument('--data-dir', type=Path,
                        help='Optional espeak-ng-data for legacy sherpa; current v2 ignores this')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--text')
    source.add_argument('--text-file', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path,
                        help='Default output path with suffix .json')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--speed', type=float, default=1.0)
    parser.add_argument('--noise-scale', type=float, default=0.667,
                        help='Match rkvoice-stream default; sherpa upstream example defaults to 1.0')
    parser.add_argument('--warmup', type=int, default=0)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    if args.threads < 1 or args.speed <= 0 or args.warmup < 0 or args.repeats < 1:
        parser.error('threads/repeats/speed must be positive; warmup must be nonnegative')
    if args.noise_scale < 0:
        parser.error('noise-scale must be nonnegative')
    if args.no_rules and args.rule:
        parser.error('--no-rules and --rule are mutually exclusive')

    text = args.text if args.text is not None else args.text_file.read_text(encoding='utf-8')
    text = text.strip()
    if not text:
        parser.error('text must not be empty')
    base = args.acoustic.parent
    tokens = args.tokens or base / 'tokens.txt'
    lexicons = args.lexicon or [base / 'lexicon.txt']
    rules = [] if args.no_rules else args.rule or [
        base / 'phone-zh.fst', base / 'date-zh.fst', base / 'number-zh.fst']
    required = [args.acoustic, args.vocoder, tokens, *lexicons, *rules]
    for path in required:
        if not path.is_file():
            parser.error(f'required file missing: {path}')
        if ',' in str(path):
            parser.error(f'comma in path is unsupported by sherpa list fields: {path}')

    identities = [model_identity(path) for path in required]
    before_import = time.perf_counter()
    import numpy as np
    import sherpa_onnx
    import_seconds = time.perf_counter() - before_import
    try:
        package_version = importlib.metadata.version('sherpa-onnx')
    except importlib.metadata.PackageNotFoundError:
        package_version = getattr(sherpa_onnx, '__version__', 'unknown')

    matcha_fields = dict(acoustic_model=str(args.acoustic), vocoder=str(args.vocoder),
                         tokens=str(tokens), lexicon=','.join(map(str, lexicons)),
                         noise_scale=args.noise_scale, length_scale=1.0)
    if args.data_dir:
        matcha_fields['data_dir'] = str(args.data_dir)
    start = time.perf_counter()
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            matcha=sherpa_onnx.OfflineTtsMatchaModelConfig(**matcha_fields),
            num_threads=args.threads, provider='cpu', debug=args.debug),
        rule_fsts=','.join(map(str, rules)))
    if hasattr(config, 'validate') and not config.validate():
        raise RuntimeError('sherpa rejected the Matcha/Vocos configuration')
    tts = sherpa_onnx.OfflineTts(config)
    load_seconds = time.perf_counter() - start
    after_load_memory = rss()

    # v2 uses GenerationConfig; older sherpa releases use sid/speed keywords.
    if hasattr(sherpa_onnx, 'GenerationConfig'):
        generation = sherpa_onnx.GenerationConfig()
        generation.sid = 0
        generation.speed = args.speed
        generate = lambda: tts.generate(text, generation)
        generation_api = 'GenerationConfig'
    else:
        generate = lambda: tts.generate(text, sid=0, speed=args.speed)
        generation_api = 'sid/speed keywords'

    warmup_runs = []
    for _ in range(args.warmup):
        start = time.perf_counter()
        result = generate()
        warmup_runs.append({'inference_seconds': time.perf_counter() - start,
                            'frames': len(result.samples), 'sample_rate': result.sample_rate})

    records = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for index in range(args.repeats):
        start = time.perf_counter()
        audio = generate()
        elapsed = time.perf_counter() - start
        samples = np.asarray(audio.samples, dtype=np.float32)
        sample_rate = int(audio.sample_rate)
        if samples.ndim != 1 or len(samples) == 0 or sample_rate <= 0:
            raise RuntimeError('invalid or empty mono audio returned by sherpa')
        if not np.isfinite(samples).all():
            raise RuntimeError('nonfinite audio samples returned by sherpa')
        path = args.output if args.repeats == 1 else args.output.with_name(
            f'{args.output.stem}-{index + 1:02d}{args.output.suffix or ".wav"}')
        # Identical PCM conversion for each repetition, no per-clip gain change.
        pcm = np.rint(np.clip(samples, -1.0, 1.0) * 32767.0).astype('<i2')
        with wave.open(str(path), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(sample_rate)
            stream.writeframes(pcm.tobytes())
        duration = len(samples) / sample_rate
        record = {'index': index + 1, 'output': str(path.resolve()),
                  'inference_seconds': elapsed, 'duration_seconds': duration,
                  'rtf': elapsed / duration, 'sample_rate': sample_rate,
                  'frames': len(samples), 'peak_amplitude': float(np.max(np.abs(samples))),
                  'clipped_sample_fraction': float(np.mean(np.abs(samples) > 1.0)),
                  **rss()}
        records.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    report = {'backend': 'sherpa-onnx Matcha + Vocos, CPU provider',
              'sherpa_onnx_version': package_version, 'python': platform.python_version(),
              'machine': platform.machine(), 'platform': platform.platform(),
              'pid': os.getpid(), 'threads': args.threads, 'speed': args.speed,
              'noise_scale': args.noise_scale, 'text': text,
              'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
              'import_seconds': import_seconds, 'load_seconds': load_seconds,
              'after_load_memory': after_load_memory, 'generation_api': generation_api,
              'models_and_frontend': identities, 'text_rules_enabled': bool(rules),
              'frontend_note': 'Native sherpa lexicon/FST frontend; differs from rkvoice custom frontend.',
              'warmup_runs': warmup_runs, 'runs': records}
    report_path = args.report or args.output.with_suffix('.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Report: {report_path.resolve()}')


if __name__ == '__main__':
    main()
