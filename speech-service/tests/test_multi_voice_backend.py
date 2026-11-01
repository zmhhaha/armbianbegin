"""One model, immutable per-request styles, and no voice leakage across callers."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from speech_service.rkvoice_backend import RkvoiceKokoroBackend,VOICE,VOICE_NAMES,MALE_VOICES,FEMALE_VOICES
from speech_service import voice_assets

VOICES=tuple(VOICE_NAMES)
LEVELS={voice:index+1 for index,voice in enumerate(VOICES)}


def verified_fixture(directory,voice):
    raw=struct.pack('<f',LEVELS[voice])*(510*256)
    return raw,dict(voice_id=voice,raw_sha256=hashlib.sha256(raw).hexdigest())


class Upstream:
    instances=[]

    def __init__(self,config):
        self.config=SimpleNamespace(platform='rk3588')
        self.frontend=SimpleNamespace(_official_g2p=lambda route:lambda text:text,
                                     _voice_cache={'z':'old-default-style'})
        self.calls=[]
        self.preloads=0
        self.cleanups=0
        self.started=threading.Event()
        self.second_started=threading.Event()
        self.release=threading.Event();self.release.set()
        self.fail=False
        self.wrong_metadata=None
        self.instances.append(self)

    def preload(self):
        self.preloads+=1

    def is_ready(self):
        return True

    @staticmethod
    def _request(text,speaker_id,speed,pitch_shift,kwargs):
        if speaker_id!=0 or pitch_shift not in (None,0) or kwargs.get('voice')!=VOICE:
            raise ValueError('upstream request rejected')
        return 'zh','z',VOICE,speed,()

    def synthesize(self,text,**kwargs):
        _,_,voice,speed,_=self._request(text,0,kwargs['speed'],None,kwargs)
        # The actual style is read before all simulated duration/stem work,
        # exactly where the pinned frontend.prepare reads it.
        style=self.frontend._voice('z',len(text))
        self.calls.append((voice,speed,float(style[0,0])))
        self.started.set()
        if len(self.calls)>1:
            self.second_started.set()
        if not self.release.wait(3):
            raise RuntimeError('fixture native work not released')
        if self.fail:
            raise RuntimeError('simulated failure after style binding')
        pieces=[(0,1),(1,len(text))] if len(text)>1 else [(0,1)]
        segments=[dict(engine='npu',fallback=False,finite=True,cancelled=False,
                       source_start=start,source_end=end,sentence_text=text[start:end],voice=voice)
                  for start,end in pieces]
        metadata=dict(engine='npu',fallback=False,source_start=0,source_end=len(text),
                      voice=voice,segments=segments,full_source_sha256='unchanged-source')
        if self.wrong_metadata=='top':
            metadata['voice']='zm_yunxi' if voice!='zm_yunxi' else 'zm_yunjian'
        if self.wrong_metadata=='segment':
            segments[-1]['voice']='wrong-voice'
        return voice.encode(),metadata

    def cleanup(self):
        self.cleanups+=1


@contextmanager
def adapter(*,loader=verified_fixture,voices=VOICES,voice='zm_yunjian'):
    with tempfile.TemporaryDirectory() as temporary:
        directory=Path(temporary)
        source=directory/'reviewed.py';source.write_bytes(b'pinned multi-voice fixture')
        module=SimpleNamespace(__file__=str(source),KokoroConvOnlyBackend=Upstream,
                               KokoroConvOnlyConfig=lambda *args,**kwargs:args)
        backend=RkvoiceKokoroBackend(directory,voice=voice,voices=voices,voice_directory=directory)
        with patch('speech_service.rkvoice_backend.BACKEND_SHA256',hashlib.sha256(source.read_bytes()).hexdigest()), \
             patch('speech_service.rkvoice_backend.importlib.import_module',return_value=module), \
             patch.object(voice_assets,'load_verified_voice',side_effect=loader):
            try:
                yield backend
            finally:
                backend.cleanup()


class MultiVoiceTests(unittest.TestCase):
    def test_one_model_and_all_request_styles_are_bound_before_frontend_work(self):
        before=len(Upstream.instances)
        with adapter() as backend:
            with self.assertRaises(RuntimeError):
                backend.voice_catalog()
            backend.preload();upstream=backend._backend
            self.assertEqual(len(Upstream.instances)-before,1)
            self.assertEqual([item['id'] for item in backend.voice_catalog()],list(VOICES))
            self.assertEqual([item['id'] for item in backend.voice_catalog() if item['default']],['zm_yunjian'])
            self.assertEqual({item['id'] for item in backend.voice_catalog() if item['gender']=='female'},FEMALE_VOICES)
            self.assertEqual({item['id'] for item in backend.voice_catalog() if item['gender']=='male'},MALE_VOICES)
            self.assertEqual({item['id']:item['name'] for item in backend.voice_catalog()},VOICE_NAMES)
            for voice in (*VOICES,'zm_yunjian'):
                self.assertEqual(backend.synthesize('测试',voice=voice,speed=1.0),voice.encode())
                self.assertEqual(upstream.calls[-1],(voice,1.0,LEVELS[voice]))
                self.assertEqual(backend.last_metadata['full_source_sha256'],'unchanged-source')
                self.assertTrue(all(s['voice']==voice for s in backend.last_metadata['segments']))
                self.assertIsNone(backend._active_voice)
            self.assertEqual(upstream.preloads,1)
            self.assertEqual(upstream.frontend._voice_cache,{'z':'old-default-style'})
            self.assertTrue(all(not table.flags.writeable for table in backend._voice_tables.values()))
            with self.assertRaises(ValueError):
                upstream.frontend._voice('z',2)
            with self.assertRaises(RuntimeError):
                backend.synthesize('测试',voice='not-enabled',speed=1.0)
            self.assertEqual(len(upstream.calls),len(VOICES)+1)

    def test_configured_xiaobei_singleton_uses_pinned_asset_instead_of_legacy_bundle_style(self):
        with adapter(voices=('zf_xiaobei',),voice='zf_xiaobei') as backend:
            backend.preload()
            self.assertEqual(set(backend.voice_receipts),{'zf_xiaobei'})
            self.assertEqual(backend.synthesize('测试',voice='zf_xiaobei',speed=1.0),b'zf_xiaobei')
            self.assertEqual(backend._backend.calls,[('zf_xiaobei',1.0,LEVELS['zf_xiaobei'])])
            self.assertEqual(backend.voice_catalog(),[dict(id='zf_xiaobei',name='晓贝',language='zh-CN',
                                                         gender='female',default=True)])

    def test_native_failure_or_wrong_segment_voice_cannot_leave_a_selected_style(self):
        with adapter() as backend:
            backend.preload();upstream=backend._backend
            upstream.fail=True
            with self.assertRaises(RuntimeError):
                backend.synthesize('测试',voice='zm_yunxia',speed=1.0)
            self.assertIsNone(backend._active_voice)
            self.assertIsNone(backend.last_metadata)
            upstream.fail=False
            for wrong in ('top','segment'):
                upstream.wrong_metadata=wrong
                with self.assertRaisesRegex(RuntimeError,'voice binding|segment execution'):
                    backend.synthesize('测试',voice='zm_yunyang',speed=1.0)
                self.assertIsNone(backend._active_voice)
                self.assertIsNone(backend.last_metadata)
            upstream.wrong_metadata=None
            self.assertEqual(backend.synthesize('测试',voice='zm_yunxi',speed=1.0),b'zm_yunxi')
            self.assertEqual(upstream.calls[-1][2],LEVELS['zm_yunxi'])

    def test_parallel_callers_cannot_swap_style_or_cleanup_during_inference(self):
        with adapter() as backend:
            backend.preload();upstream=backend._backend;upstream.release.clear()
            results,errors=[],[]
            second_calling=threading.Event()
            def call(voice):
                try:
                    if voice=='zf_xiaoyi':second_calling.set()
                    results.append((voice,backend.synthesize('测试',voice=voice,speed=1.0)))
                except BaseException as error:
                    errors.append(error)
            first=threading.Thread(target=call,args=('zm_yunxi',))
            second=threading.Thread(target=call,args=('zf_xiaoyi',))
            first.start()
            self.assertTrue(upstream.started.wait(1))
            second.start();self.assertTrue(second_calling.wait(1))
            try:
                self.assertFalse(upstream.second_started.wait(.05))
                self.assertEqual(backend._active_voice,'zm_yunxi')
                self.assertEqual(upstream.calls,[('zm_yunxi',1.0,LEVELS['zm_yunxi'])])
                with self.assertRaises(ValueError):
                    upstream.frontend._voice('z',2)
                with self.assertRaises(ValueError):
                    upstream._request('测试',0,1.0,None,{'voice':'zm_yunxi'})
            finally:
                upstream.release.set()
                first.join(2);second.join(2)
            self.assertFalse(first.is_alive() or second.is_alive())
            self.assertEqual(errors,[])
            self.assertEqual(dict(results),{'zm_yunxi':b'zm_yunxi','zf_xiaoyi':b'zf_xiaoyi'})
            self.assertIsNone(backend._active_voice)
            self.assertEqual(upstream.preloads,1)
            # An independent cleanup caller also waits for the complete call.
            upstream.started.clear();upstream.release.clear()
            worker=threading.Thread(target=call,args=('zm_yunxi',));worker.start()
            self.assertTrue(upstream.started.wait(1))
            cleaned=threading.Event()
            cleanup=threading.Thread(target=lambda:(backend.cleanup(),cleaned.set()));cleanup.start()
            try:
                self.assertFalse(cleaned.wait(.05))
                self.assertEqual(upstream.cleanups,0)
            finally:
                upstream.release.set();worker.join(2);cleanup.join(2)
            self.assertTrue(cleaned.is_set())
            self.assertIsNone(backend._backend)
            with self.assertRaises(RuntimeError):backend.voice_catalog()

    def test_missing_any_enabled_voice_fails_the_entire_initialization(self):
        def broken(directory,voice):
            if voice=='zf_xiaoni':raise ValueError('missing pinned secondary voice')
            return verified_fixture(directory,voice)
        with adapter(loader=broken) as backend:
            with self.assertRaises(ValueError):backend.preload()
            with self.assertRaises(RuntimeError):backend.voice_catalog()
            for voice in VOICES:
                with self.assertRaises(RuntimeError):backend.synthesize('测试',voice=voice,speed=1.0)
            self.assertIsNone(backend._backend)
            self.assertEqual(dict(backend._voice_tables),{})

    def test_explicit_voice_configuration_is_bounded_and_requires_the_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            env=dict(SPEECH_BACKEND='kokoro_convonly',SPEECH_VOICE='zm_yunjian',
                     SPEECH_VOICE_ROOT=temporary,KOKORO_CONVONLY_ROOT=temporary)
            self.assertEqual(RkvoiceKokoroBackend.from_env(env)._voices,('zm_yunjian',))
            self.assertEqual(RkvoiceKokoroBackend.from_env({**env,'SPEECH_VOICES':','.join(VOICES)})._voices,VOICES)
            for voice in FEMALE_VOICES:
                selected=RkvoiceKokoroBackend.from_env({**env,'SPEECH_VOICE':voice})
                self.assertEqual(selected._voices,(voice,))
                self.assertEqual(selected._voice_directory,Path(temporary))
            for value in ('','zm_yunxi','zm_yunjian,zm_yunjian','zm_yunjian,',
                          'zm_yunjian,zf_unknown','zm_yunjian,../unknown'):
                with self.subTest(value=value),self.assertRaises(ValueError):
                    RkvoiceKokoroBackend.from_env({**env,'SPEECH_VOICES':value})


if __name__=='__main__':unittest.main()
