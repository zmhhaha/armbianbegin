"""Small ASGI protocol with a native synthesis task that owns its busy slot.

Run one instance in one server process/worker. Native inference is not assumed
to be cancellable. HTTP cancellation, timeout and disconnect stop collection;
only the native task's finally block releases admission for another synthesis.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hmac
import io
import json
import math
import struct
import threading
from time import monotonic
from typing import Protocol
import wave

from .settings import SpeechSettings


class SpeechBackend(Protocol):
    def preload(self) -> None: ...
    def synthesize(self, text: str, *, voice: str, speed: float) -> bytes: ...
    def cleanup(self) -> None: ...


class _InvalidAudio(Exception):
    pass


class _BackendFailed(Exception):
    pass


class _RequestFailed(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


_MESSAGES = {
    "speech_unauthorized": "Speech authorization failed",
    "speech_unavailable": "Speech service is unavailable",
    "speech_busy": "Speech service is busy",
    "speech_timeout": "Speech generation timed out",
    "speech_body_timeout": "Speech request timed out",
    "speech_request_too_large": "Speech request is too large",
    "speech_invalid_request": "Invalid speech request",
    "speech_invalid_input": "Invalid speech input",
    "speech_unsupported_media": "Unsupported speech request media",
    "speech_invalid_audio": "Speech backend returned invalid audio",
    "speech_backend_failed": "Speech generation failed",
    "not_found": "Not found",
    "method_not_allowed": "Method not allowed",
}


def _complete_pcm16(data, settings):
    """Validate all RIFF boundaries and actual PCM frames before publication."""
    if type(data) is not bytes or not 44 <= len(data) <= settings.max_audio_bytes:
        raise _InvalidAudio()
    try:
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE" or struct.unpack_from("<I", data, 4)[0] + 8 != len(data):
            raise ValueError()
        position, fmt, data_size, data_start = 12, None, None, None
        while position < len(data):
            if position + 8 > len(data):
                raise ValueError()
            name = data[position:position + 4]
            size = struct.unpack_from("<I", data, position + 4)[0]
            start, end = position + 8, position + 8 + size
            if end + (size & 1) > len(data):
                raise ValueError()
            if name == b"fmt ":
                if fmt is not None or data_size is not None or size < 16:
                    raise ValueError()
                fmt = struct.unpack_from("<HHIIHH", data, start)
            elif name == b"data":
                if fmt is None or data_size is not None:
                    raise ValueError()
                data_size, data_start = size, start
            position = end + (size & 1)
        if fmt is None or data_size is None or data_size <= 0:
            raise ValueError()
        encoding, channels, rate, byte_rate, block_align, bits = fmt
        if (encoding != 1 or channels not in {1, 2} or not 8000 <= rate <= 96000
                or bits != 16 or block_align != channels * 2 or byte_rate != rate * block_align
                or data_size % block_align):
            raise ValueError()
        frames = data_size // block_align
        if not 0 < frames / rate <= settings.max_audio_seconds:
            raise ValueError()
        # Signed PCM16 digital silence consists entirely of zero bytes. Check
        # the data chunk itself without copying another full audio buffer.
        if not any(memoryview(data)[data_start:data_start + data_size]):
            raise ValueError()
        with wave.open(io.BytesIO(data), "rb") as audio:
            if (audio.getparams()[:4] != (channels, 2, rate, frames)
                    or audio.getcomptype() != "NONE"
                    or len(audio.readframes(frames + 1)) != data_size):
                raise ValueError()
    except (ValueError, OSError, EOFError, wave.Error, struct.error, OverflowError):
        raise _InvalidAudio() from None
    return data


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError()
        result[name] = value
    return result


def _reject_constant(value):
    raise ValueError()


class SpeechApplication:
    def __init__(self, backend: SpeechBackend, settings: SpeechSettings):
        if not isinstance(settings, SpeechSettings):
            raise TypeError("SpeechSettings is required")
        self.settings = settings
        self._backend = backend
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="speech-native")
        self._state_lock = threading.Lock()
        self._ready = False
        self._closing = False
        self._busy = False
        self._active = None

    def _preload(self):
        try:
            self._backend.preload()
        except Exception:
            try:
                self._backend.cleanup()
            except Exception:
                pass
            raise _BackendFailed() from None

    async def _lifespan(self, receive, send):
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    await asyncio.shield(asyncio.wrap_future(self._executor.submit(self._preload)))
                except Exception:
                    self._executor.shutdown(wait=False, cancel_futures=True)
                    await send({"type": "lifespan.startup.failed", "message": "Speech backend initialization failed"})
                    return
                with self._state_lock:
                    self._ready = True
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                with self._state_lock:
                    self._closing, self._ready = True, False
                # The same executor serializes cleanup after any ongoing native
                # task. Shutdown waits honestly; a supervisor may terminate a
                # stuck process, but this app does not claim the native work died.
                try:
                    await asyncio.shield(asyncio.wrap_future(self._executor.submit(self._backend.cleanup)))
                except Exception:
                    self._executor.shutdown(wait=False, cancel_futures=False)
                    await send({"type": "lifespan.shutdown.failed", "message": "Speech backend cleanup failed"})
                    return
                self._executor.shutdown(wait=False, cancel_futures=False)
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] != "http":
            raise RuntimeError("Only HTTP and lifespan scopes are supported")
        try:
            await self._http(scope, receive, send)
        except _RequestFailed as error:
            headers = [(b"retry-after", b"1")] if error.status == 429 else []
            if error.status == 401:
                headers.append((b"www-authenticate", b"Bearer"))
            if error.status == 405:
                allowed = b"GET" if scope.get("path", "").startswith("/health/") else b"POST"
                headers.append((b"allow", allowed))
            await self._json(send, error.status, {"error": {"code": error.code, "message": _MESSAGES[error.code]}}, headers)
        except OSError:
            # ASGI servers may raise on a response to an already disconnected
            # socket. No cancellation or release of native work happens here.
            return

    async def _json(self, send, status, value, extra_headers=()):
        body = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        await self._respond(send, status, body, b"application/json", extra_headers)

    async def _respond(self, send, status, body, content_type, extra_headers=()):
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", content_type), (b"content-length", str(len(body)).encode("ascii")),
            (b"cache-control", b"no-store"), *extra_headers,
        ]})
        await send({"type": "http.response.body", "body": body})

    def _authorized(self, headers):
        auth = [value for name, value in headers if name.lower() == b"authorization"]
        if len(auth) != 1 or not 8 <= len(auth[0]) <= 4103 or auth[0][:7].lower() != b"bearer ":
            return False
        return hmac.compare_digest(auth[0][7:], self.settings.token.encode("ascii"))

    async def _body(self, headers, receive):
        def one(name):
            values = [value for key, value in headers if key.lower() == name]
            if len(values) > 1:
                raise _RequestFailed(400, "speech_invalid_request")
            return values[0] if values else None

        media, encoding, length = one(b"content-type"), one(b"content-encoding"), one(b"content-length")
        if media is None or media.split(b";", 1)[0].strip().lower() != b"application/json":
            raise _RequestFailed(415, "speech_unsupported_media")
        if encoding is not None and encoding.strip().lower() != b"identity":
            raise _RequestFailed(415, "speech_unsupported_media")
        declared = None
        if length is not None:
            if not 1 <= len(length) <= 12 or not length.isdigit():
                raise _RequestFailed(400, "speech_invalid_request")
            declared = int(length)
            if declared > self.settings.max_request_bytes:
                raise _RequestFailed(413, "speech_request_too_large")
        chunks, size = [], 0
        deadline = monotonic() + self.settings.body_timeout
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise _RequestFailed(408, "speech_body_timeout")
            try:
                message = await asyncio.wait_for(receive(), remaining)
            except TimeoutError:
                raise _RequestFailed(408, "speech_body_timeout") from None
            if message["type"] == "http.disconnect":
                return None
            if message["type"] != "http.request":
                raise _RequestFailed(400, "speech_invalid_request")
            chunk = message.get("body", b"")
            size += len(chunk)
            # Check before extending/joining buffers, including chunked bodies.
            if size > self.settings.max_request_bytes:
                raise _RequestFailed(413, "speech_request_too_large")
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        if declared is not None and declared != size:
            raise _RequestFailed(400, "speech_invalid_request")
        return b"".join(chunks)

    def _payload(self, raw):
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise _RequestFailed(400, "speech_invalid_request") from None
        if (type(value) is not dict or set(value) - {"model", "input", "voice", "speed", "response_format"}
                or value.get("model") != self.settings.model or value.get("voice") != self.settings.voice
                or value.get("response_format", "wav") != "wav"):
            raise _RequestFailed(422, "speech_invalid_input")
        text, speed = value.get("input"), value.get("speed", 1.0)
        if (type(text) is not str or not 1 <= len(text) <= self.settings.max_text_characters or not text.strip()
                or any((ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127
                       or 0xD800 <= ord(c) <= 0xDFFF for c in text)
                or len(text.encode("utf-8")) > self.settings.max_text_bytes
                or type(speed) not in {int, float}
                or not self.settings.min_speed <= speed <= self.settings.max_speed
                or not math.isfinite(speed)):
            raise _RequestFailed(422, "speech_invalid_input")
        return text, float(speed)

    def _synthesize(self, text, speed):
        try:
            try:
                data = self._backend.synthesize(text, voice=self.settings.voice, speed=speed)
            except Exception:
                raise _BackendFailed() from None
            return _complete_pcm16(data, self.settings)
        finally:
            with self._state_lock:
                self._busy = False

    def _admit(self, text, speed):
        with self._state_lock:
            if not self._ready or self._closing:
                raise _RequestFailed(503, "speech_unavailable")
            if self._busy:
                raise _RequestFailed(429, "speech_busy")
            self._busy = True
            try:
                self._active = self._executor.submit(self._synthesize, text, speed)
            except RuntimeError:
                self._busy = False
                raise _RequestFailed(503, "speech_unavailable") from None
            return self._active

    async def _disconnected(self, receive):
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return

    async def _http(self, scope, receive, send):
        path, method = scope.get("path", ""), scope.get("method", "")
        if path in {"/health/live", "/health/ready"}:
            if method != "GET":
                raise _RequestFailed(405, "method_not_allowed")
            with self._state_lock:
                ready = self._ready and not self._closing
            ok = path == "/health/live" or ready
            await self._json(send, 200 if ok else 503, {"status": "ok" if ok else "unavailable"})
            return
        if path != "/v1/audio/speech":
            raise _RequestFailed(404, "not_found")
        if method != "POST":
            raise _RequestFailed(405, "method_not_allowed")
        headers = scope.get("headers", [])
        if not self._authorized(headers):
            raise _RequestFailed(401, "speech_unauthorized")
        raw = await self._body(headers, receive)
        if raw is None:
            return
        text, speed = self._payload(raw)
        native = asyncio.wrap_future(self._admit(text, speed))
        # Retrieve detached failures so a timed-out HTTP task cannot generate an
        # unhandled future traceback containing backend details in server logs.
        native.add_done_callback(lambda completed: None if completed.cancelled() else completed.exception())
        disconnect = asyncio.create_task(self._disconnected(receive))
        try:
            done, _ = await asyncio.wait({native, disconnect}, timeout=self.settings.synthesis_timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
            if disconnect in done:
                return
            if native not in done:
                raise _RequestFailed(504, "speech_timeout")
            try:
                data = native.result()
            except _InvalidAudio:
                raise _RequestFailed(502, "speech_invalid_audio") from None
            except _BackendFailed:
                raise _RequestFailed(503, "speech_backend_failed") from None
            await self._respond(send, 200, data, b"audio/wav")
        finally:
            # asyncio.wait never cancels native, even when this request task is
            # cancelled. Only the receive watcher belongs to the HTTP lifetime.
            disconnect.cancel()
            try:
                await disconnect
            except asyncio.CancelledError:
                pass
