"""One local Chinese synthesis; run inside the isolated worker environment."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import sys
import time
import wave

MANIFEST_SHA256 = '83733c717e0ce5b76ac1295e4827cf3ad2e111955259e9d670897e100fabeb6e'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, help='Pinned rkvoice-stream checkout, if not installed as a package')
    ap.add_argument('--bundle', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--text', default='这是视频工作台。我们正在测试本地语音合成服务，检查中文发音是否清晰自然。')
    ap.add_argument('--speed', type=float, default=1.0)
    ap.add_argument('--require-npu', action='store_true')
    args = ap.parse_args()
    if args.source:
        sys.path.insert(0, str(args.source.resolve()))
    from rkvoice_stream.backends.tts.kokoro_convonly import KokoroConvOnlyBackend, KokoroConvOnlyConfig

    backend = KokoroConvOnlyBackend(KokoroConvOnlyConfig('rk3588', args.bundle.resolve(), MANIFEST_SHA256, intra=4, inter=1))
    started = time.perf_counter()
    try:
        backend.preload()
        preload_s = time.perf_counter() - started
        print(json.dumps({'stage': 'preloaded', 'elapsed_s': preload_s, 'runtime': backend.runtime_info()}, ensure_ascii=False), flush=True)
        wav_bytes, metadata = backend.synthesize(args.text, language='zh', voice='zf_xiaobei', speed=args.speed)
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wav:
            frames = wav.getnframes()
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000) or frames < 1:
                raise ValueError('unexpected WAV parameters')
            if len(wav.readframes(frames + 1)) != frames * 2:
                raise ValueError('truncated WAV')
            duration = frames / wav.getframerate()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(wav_bytes)
        report = {'source_sha': 'f2c2d730403e1d4c732add799f0414da34695043', 'preload_s': preload_s,
                  'wall_s_including_preload': time.perf_counter() - started, 'text': args.text,
                  'audio_s_measured': duration, 'wav_sha256': hashlib.sha256(wav_bytes).hexdigest(),
                  'runtime': backend.runtime_info(), 'metadata': metadata}
        args.out.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'stage': 'synthesized', 'wav': str(args.out), 'audio_s': duration, 'engine': metadata.get('engine'), 'fallback': metadata.get('fallback'), 'full_rtf': metadata.get('full_rtf')}, ensure_ascii=False), flush=True)
        if args.require_npu and (metadata.get('engine') != 'npu' or metadata.get('fallback')):
            raise RuntimeError('audio was generated but the selected route used CPU fallback; this is not NPU acceptance')
    finally:
        backend.cleanup()


if __name__ == '__main__':
    main()
