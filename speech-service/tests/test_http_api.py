"""Protocol and real socket tests; no model imports, downloads or paid APIs."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from speech_service import SpeechApplication, SpeechSettings


def wav_bytes(frames=2400, rate=24000, channels=1, level=1000):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(struct.pack("<h", level) * frames * channels)
    return output.getvalue()


def payload(**changes):
    value = {"model": "fixture-model", "voice": "fixture-voice", "input": "测试旁白。",
             "speed": 1.0, "response_format": "wav"}
    value.update(changes)
    return json.dumps(value, ensure_ascii=True).encode("utf-8")


def settings(**changes):
    return SpeechSettings(model="fixture-model", voice="fixture-voice", token="fixture-secret", **changes)


class Backend:
    def __init__(self, *, block=False, result=None, failure=None, preload_failure=False):
        self.started = threading.Event()
        self.release = threading.Event()
        if not block:
            self.release.set()
        self.result = wav_bytes() if result is None else result
        self.failure, self.preload_failure = failure, preload_failure
        self.calls = []
        self.running, self.peak = 0, 0
        self.cleaned = False
        self._lock = threading.Lock()

    def preload(self):
        if self.preload_failure:
            raise RuntimeError("private initialization path and fixture-secret")

    def synthesize(self, text, *, voice, speed):
        with self._lock:
            self.calls.append((text, voice, speed))
            self.running += 1
            self.peak = max(self.peak, self.running)
        self.started.set()
        try:
            if not self.release.wait(5):
                raise RuntimeError("test failed to release native backend")
            if self.failure:
                raise self.failure
            return self.result
        finally:
            with self._lock:
                self.running -= 1

    def cleanup(self):
        if self.running:
            raise RuntimeError("cleanup overlapped native inference")
        self.cleaned = True


class AsgiHarness:
    def __init__(self, app):
        self.app = app
        self.lifespan_in, self.lifespan_out = asyncio.Queue(), asyncio.Queue()
        self.lifecycle = None

    async def start(self):
        self.lifecycle = asyncio.create_task(self.app({"type": "lifespan"}, self.lifespan_in.get, self.lifespan_out.put))
        await self.lifespan_in.put({"type": "lifespan.startup"})
        return await asyncio.wait_for(self.lifespan_out.get(), 2)

    async def close(self):
        if self.lifecycle is not None and not self.lifecycle.done():
            await self.lifespan_in.put({"type": "lifespan.shutdown"})
            message = await asyncio.wait_for(self.lifespan_out.get(), 2)
            if message["type"] != "lifespan.shutdown.complete":
                raise AssertionError(message)
        if self.lifecycle:
            await asyncio.wait_for(self.lifecycle, 2)

    async def request(self, body=None, *, path="/v1/audio/speech", method="POST", headers=None, incoming=None):
        body = payload() if body is None else body
        if headers is None:
            headers = [(b"authorization", b"Bearer fixture-secret"), (b"content-type", b"application/json")]
        queue = incoming or asyncio.Queue()
        if incoming is None:
            await queue.put({"type": "http.request", "body": body, "more_body": False})
        messages = []

        async def send(message):
            messages.append(message)

        await self.app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                        "method": method, "scheme": "http", "path": path,
                        "raw_path": path.encode(), "query_string": b"", "headers": headers,
                        "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 80)}, queue.get, send)
        if not messages:
            return None
        return messages[0]["status"], dict(messages[0]["headers"]), b"".join(m.get("body", b"") for m in messages[1:])


class ConfigurationTests(unittest.TestCase):
    def test_token_file_is_required_bounded_and_never_in_repr_or_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            credential = Path(temp) / "private-token"
            credential.write_text("fixture-secret\n", encoding="ascii")
            env = {"SPEECH_MODEL": "fixture-model", "SPEECH_VOICE": "fixture-voice", "TOKEN_FILE": str(credential)}
            configured = SpeechSettings.from_env(env)
            self.assertEqual(configured.token, "fixture-secret")
            self.assertNotIn("fixture-secret", repr(configured))
            for value in (b"", b"x" * 4097, b"\xff", b"bad\x00token"):
                credential.write_bytes(value)
                with self.assertRaises(ValueError) as raised:
                    SpeechSettings.from_env(env)
                self.assertNotIn(str(credential), str(raised.exception))
                self.assertNotIn("bad", str(raised.exception))
            with self.assertRaises(ValueError):
                SpeechSettings.from_env({"SPEECH_TOKEN": "inline-secret"})

    def test_configuration_limits_are_strict_and_finite(self):
        for changes in ({"synthesis_timeout": float("nan")}, {"max_text_characters": True},
                        {"min_speed": 0}, {"max_speed": 10**400}, {"max_request_bytes": 10**9}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(settings(), **changes)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = Backend()
        self.app = SpeechApplication(self.backend, settings())
        self.harness = AsgiHarness(self.app)
        self.assertEqual((await self.harness.start())["type"], "lifespan.startup.complete")

    async def asyncTearDown(self):
        self.backend.release.set()
        await self.harness.close()

    async def test_complete_wav_and_fixed_backend_arguments(self):
        status, headers, data = await self.harness.request(payload(speed=1.25))
        self.assertEqual(status, 200)
        self.assertEqual(headers[b"content-type"], b"audio/wav")
        self.assertEqual(int(headers[b"content-length"]), len(data))
        self.assertNotIn(b"content-encoding", headers)
        self.assertEqual(data, wav_bytes())
        self.assertEqual(self.backend.calls, [("测试旁白。", "fixture-voice", 1.25)])

    async def test_health_is_minimal_and_does_not_need_credentials(self):
        for path in ("/health/live", "/health/ready"):
            status, _, data = await self.harness.request(path=path, method="GET", headers=[])
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data), {"status": "ok"})
        self.assertEqual(self.backend.calls, [])

    async def test_unstarted_service_is_live_but_not_ready(self):
        app = SpeechApplication(Backend(), settings())
        harness = AsgiHarness(app)
        try:
            self.assertEqual((await harness.request(path="/health/live", method="GET", headers=[]))[0], 200)
            self.assertEqual((await harness.request(path="/health/ready", method="GET", headers=[]))[0], 503)
            self.assertEqual((await harness.request())[0], 503)
        finally:
            app._executor.shutdown(wait=True)

    async def test_authentication_precedes_body_read_and_is_sanitized(self):
        for values in ([], [(b"authorization", b"Bearer wrong-private-token")],
                       [(b"authorization", b"Bearer fixture-secret")] * 2):
            status, _, data = await self.harness.request(headers=values, incoming=asyncio.Queue())
            self.assertEqual(status, 401)
            self.assertEqual(json.loads(data)["error"]["code"], "speech_unauthorized")
            self.assertNotIn(b"private-token", data)
            self.assertNotIn(b"fixture-secret", data)
        self.assertEqual(self.backend.calls, [])

    async def test_invalid_json_input_and_operator_selection_never_run_backend(self):
        cases = [b"{", b'{"model":"a","model":"b"}', b"[]", payload(model="other-model"),
                 payload(voice="other-voice"), payload(input=""), payload(input=" \n "),
                 payload(input="\x00private"), payload(input="\ud800"), payload(speed=True),
                 payload(speed=float("nan")), payload(speed=10**400), payload(response_format="mp3"),
                 payload(upstream_url="http://private"), payload(input="汉" * 2001)]
        for raw in cases:
            with self.subTest(raw=raw[:80]):
                status, _, _ = await self.harness.request(raw)
                self.assertIn(status, {400, 422})
        self.assertEqual(self.backend.calls, [])

    async def test_body_limit_is_checked_before_buffering_or_next_chunk(self):
        queue = asyncio.Queue()
        await queue.put({"type": "http.request", "body": b"x" * (64 * 1024 + 1), "more_body": True})
        status, _, _ = await asyncio.wait_for(self.harness.request(incoming=queue), 1)
        self.assertEqual(status, 413)
        headers = [(b"authorization", b"Bearer fixture-secret"), (b"content-type", b"application/json"),
                   (b"content-length", b"999999")]
        self.assertEqual((await self.harness.request(headers=headers, incoming=asyncio.Queue()))[0], 413)
        self.assertEqual(self.backend.calls, [])

    async def test_partial_length_and_encoded_request_are_rejected(self):
        common = [(b"authorization", b"Bearer fixture-secret"), (b"content-type", b"application/json")]
        self.assertEqual((await self.harness.request(headers=common + [(b"content-length", b"1")]))[0], 400)
        self.assertEqual((await self.harness.request(headers=common + [(b"content-encoding", b"gzip")]))[0], 415)
        self.assertEqual(self.backend.calls, [])

    async def test_body_deadline_does_not_admit_native_work(self):
        self.app.settings = replace(self.app.settings, body_timeout=0.02)
        self.assertEqual((await self.harness.request(incoming=asyncio.Queue()))[0], 408)
        self.assertEqual(self.backend.calls, [])

    async def test_backend_failure_is_sanitized_and_slot_recovers(self):
        self.backend.failure = RuntimeError("/private/path fixture-secret document text")
        status, _, data = await self.harness.request()
        self.assertEqual(status, 503)
        self.assertNotIn(b"private", data)
        self.assertNotIn(b"fixture-secret", data)
        self.backend.failure = None
        self.assertEqual((await self.harness.request())[0], 200)
        self.assertEqual(len(self.backend.calls), 2)

    async def test_invalid_or_incomplete_audio_is_never_published(self):
        original = wav_bytes()
        placeholder = original[:4] + b"\xff" * 4 + original[8:]
        corrupt_format = bytearray(original)
        corrupt_format[28:32] = struct.pack("<I", 1)
        for raw in (b"private json", original[:-1], placeholder, bytes(corrupt_format), wav_bytes(frames=0), wav_bytes(level=0),
                    wav_bytes(rate=1000), wav_bytes(channels=3)):
            self.backend.result = raw
            with self.subTest(size=len(raw)):
                status, headers, data = await self.harness.request()
                self.assertEqual(status, 502)
                self.assertEqual(headers[b"content-type"], b"application/json")
                self.assertEqual(json.loads(data)["error"]["code"], "speech_invalid_audio")

    async def test_measured_duration_and_actual_bytes_are_bounded(self):
        self.app.settings = replace(self.app.settings, max_audio_seconds=0.05)
        self.assertEqual((await self.harness.request())[0], 502)
        self.app.settings = replace(self.app.settings, max_audio_seconds=300, max_audio_bytes=100)
        self.assertEqual((await self.harness.request())[0], 502)

    async def test_startup_failure_is_generic_and_cleans_partial_backend(self):
        backend = Backend(preload_failure=True)
        harness = AsgiHarness(SpeechApplication(backend, settings()))
        message = await harness.start()
        self.assertEqual(message["type"], "lifespan.startup.failed")
        self.assertNotIn("private", message["message"])
        self.assertNotIn("fixture-secret", message["message"])
        self.assertTrue(backend.cleaned)
        await harness.close()


class InflightTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = Backend(block=True)
        self.app = SpeechApplication(self.backend, settings(synthesis_timeout=0.1))
        self.harness = AsgiHarness(self.app)
        await self.harness.start()

    async def asyncTearDown(self):
        self.backend.release.set()
        await self.harness.close()

    async def wait_started(self):
        self.assertTrue(await asyncio.to_thread(self.backend.started.wait, 2))

    async def finish_native(self):
        self.backend.release.set()
        # Native completion is independent of the HTTP task under test.
        await asyncio.shield(asyncio.wrap_future(self.app._active))

    async def assert_busy(self):
        status, headers, data = await self.harness.request()
        self.assertEqual(status, 429)
        self.assertEqual(headers[b"retry-after"], b"1")
        self.assertEqual(json.loads(data)["error"]["code"], "speech_busy")
        self.assertEqual(len(self.backend.calls), 1)
        self.assertEqual(self.backend.peak, 1)

    async def test_http_deadline_does_not_cancel_or_release_native_work(self):
        first = asyncio.create_task(self.harness.request())
        await self.wait_started()
        await self.assert_busy()
        self.assertEqual((await first)[0], 504)
        await self.assert_busy()
        await self.finish_native()
        self.assertEqual((await self.harness.request())[0], 200)
        self.assertEqual(len(self.backend.calls), 2)
        self.assertEqual(self.backend.peak, 1)

    async def test_asgi_task_cancellation_keeps_slot_until_native_done(self):
        first = asyncio.create_task(self.harness.request())
        await self.wait_started()
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        await self.assert_busy()
        await self.finish_native()
        self.assertEqual((await self.harness.request())[0], 200)
        self.assertEqual(self.backend.peak, 1)

    async def test_socket_disconnect_keeps_slot_and_sends_no_response(self):
        incoming = asyncio.Queue()
        await incoming.put({"type": "http.request", "body": payload(), "more_body": False})
        first = asyncio.create_task(self.harness.request(incoming=incoming))
        await self.wait_started()
        await incoming.put({"type": "http.disconnect"})
        self.assertIsNone(await first)
        await self.assert_busy()
        await self.finish_native()
        self.assertEqual((await self.harness.request())[0], 200)

    async def test_shutdown_waits_for_native_before_cleanup(self):
        first = asyncio.create_task(self.harness.request())
        await self.wait_started()
        self.assertEqual((await first)[0], 504)
        close = asyncio.create_task(self.harness.close())
        for _ in range(10):
            await asyncio.sleep(0)
            if (await self.harness.request(path="/health/ready", method="GET", headers=[]))[0] == 503:
                break
        self.assertFalse(self.backend.cleaned)
        self.assertFalse(close.done())
        self.assertEqual((await self.harness.request())[0], 503)
        await self.finish_native()
        await close
        self.assertTrue(self.backend.cleaned)


@unittest.skipUnless(importlib.util.find_spec("uvicorn"), "uvicorn is not installed")
class RealHttpTests(unittest.TestCase):
    @contextmanager
    def server(self, backend):
        import uvicorn

        app = SpeechApplication(backend, settings(synthesis_timeout=2))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(16)
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, workers=1,
                                               lifespan="on", ws="none", access_log=False, log_level="critical"))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        try:
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(server.started, "test HTTP server did not start")
            yield f"http://127.0.0.1:{port}"
        finally:
            backend.release.set()
            server.should_exit = True
            thread.join(5)
            sock.close()
            self.assertFalse(thread.is_alive(), "test HTTP server did not stop")

    def request(self, base, timeout=1):
        request = urllib.request.Request(base + "/v1/audio/speech", data=payload(), headers={
            "Authorization": "Bearer fixture-secret", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.headers, error.read()

    def test_real_http_client_timeout_does_not_allow_overlapping_synthesis(self):
        backend = Backend(block=True)
        with self.server(backend) as base:
            with self.assertRaises((TimeoutError, urllib.error.URLError)):
                self.request(base, timeout=0.05)
            self.assertTrue(backend.started.wait(1))
            self.assertEqual(self.request(base)[0], 429)
            self.assertEqual(len(backend.calls), 1)
            backend.release.set()
            deadline = time.monotonic() + 2
            while True:
                status, headers, data = self.request(base)
                if status != 429 or time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
            self.assertEqual(status, 200)
            self.assertEqual(data, wav_bytes())
            self.assertEqual(int(headers["Content-Length"]), len(data))
            self.assertEqual(backend.peak, 1)
            self.assertEqual(len(backend.calls), 2)
        self.assertTrue(backend.cleaned)

    def test_real_http_digital_silence_is_rejected_before_publication(self):
        backend = Backend(result=wav_bytes(level=0))
        with self.server(backend) as base:
            status, headers, data = self.request(base)
            self.assertEqual(status, 502)
            self.assertEqual(headers["Content-Type"], "application/json")
            self.assertEqual(json.loads(data)["error"]["code"], "speech_invalid_audio")
            backend.result = wav_bytes()
            self.assertEqual(self.request(base)[0], 200)
            self.assertEqual(len(backend.calls), 2)
            self.assertEqual(backend.peak, 1)


if __name__ == "__main__":
    unittest.main()
