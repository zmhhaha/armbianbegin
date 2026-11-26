"""上游转发：解析别名 → 附加 Vault 注入的凭据 → 调用 OpenAI 兼容端点。

凭据只在这里拼进请求头，绝不回传给调用方。

重试只在同一个别名上执行。流式重试包括连接失败和内容产生前的 Responses 失败。
调用方点名哪个别名，就只能由那个别名背后的模型作答。别名耗尽了重试次数就抛错，
由调用方决定怎么办 —— 绝不静默换成另一个 provider 或另一个模型。

流式（`stream: true`）走 `open_stream()`。原生 Responses 请求在首批输出前暂存
少量状态事件，确定是否需要重试。开始转发内容后，流在同一次上游请求中完成。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
import asyncio
import copy
import json
import logging

import httpx

from config import Alias, thaw
from responses_adapter import (
    ResponsesProtocolError, ResponsesRequestError, build_request, translate_response, translate_stream, _events,
    sanitize_response, sanitize_event,
)
from chat_adapter import from_chat_response, from_chat_stream

# 流式时让上游在最后一帧带上 usage，否则流式请求拿不到 token 数、用量统计会缺口。
# DeepSeek 与 OpenAI 都支持这个字段。
STREAM_USAGE_OPTION = {"include_usage": True}
_NATIVE_METADATA = {"response.created", "response.in_progress", "response.metadata"}
_PRELUDE_MAX_BYTES = 128 * 1024
_PRELUDE_MAX_EVENTS = 32
_RETRY_TRANSPORT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout,
                    httpx.ReadError, httpx.ReadTimeout, httpx.RemoteProtocolError)
_PERMANENT_PROVIDER_CODES = {
    "content_filter", "content_policy_violation", "context_length_exceeded", "empty_image_file",
    "failed_to_download_image", "image_content_policy_violation", "image_file_not_found",
    "image_parse_error", "image_too_large", "image_too_small", "insufficient_quota",
    "invalid_api_key", "invalid_base64_image", "invalid_image", "invalid_image_format",
    "invalid_image_url", "invalid_prompt", "invalid_request_error", "model_not_found",
    "unsupported_image",
}
_PERMANENT_PROVIDER_TYPES = {
    "authentication_error", "invalid_request_error", "not_found_error", "permission_error",
}
_log = logging.getLogger(__name__)


def _timeout(alias: Alias) -> httpx.Timeout:
    """Allow slow model output while bounding connection and request I/O."""
    read = alias.timeout_seconds
    return httpx.Timeout(read=read, connect=min(10.0, read),
                         write=min(60.0, read), pool=min(30.0, read))


class UpstreamError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class _EarlyResponseFailure(ResponsesProtocolError):
    """The provider explicitly ended a native stream before output."""


def _retryable_early_failure(event: dict) -> bool:
    response = event.get("response")
    if event["type"] != "response.failed" or not isinstance(response, dict):
        return False
    error = response.get("error")
    if response.get("status", "failed") != "failed" or response.get("output", []) != [] or not isinstance(error, dict):
        return False
    code, kind = error.get("code"), error.get("type")
    return ((code is None or isinstance(code, str) and code not in _PERMANENT_PROVIDER_CODES)
            and (kind is None or isinstance(kind, str) and kind not in _PERMANENT_PROVIDER_TYPES))


def _payload(alias: Alias, messages: list, params: dict, *, stream: bool = False,
             native_body: dict | None = None) -> dict:
    if native_body is not None:
        if alias.wire_api != 'responses':
            raise ResponsesRequestError('native history requires a Responses upstream')
        # Only the fixed alias supplies the wire model and credentials. Defaults
        # are converted once; the validated caller history is never flattened.
        body = build_request(alias.model, [], thaw(alias.defaults), stream=stream)
        body.update(copy.deepcopy(native_body))
        body.update(model=alias.model, store=False, stream=stream)
        return body
    body = thaw(alias.defaults)
    body.update({key: value for key, value in params.items() if value is not None})
    if alias.wire_api == "responses":
        return build_request(alias.model, messages, body, stream=stream)
    body["model"] = alias.model  # 调用方传的是别名，真正发给上游的是配置里的模型名
    body["messages"] = messages
    body["stream"] = stream
    if stream:
        body["stream_options"] = dict(STREAM_USAGE_OPTION)
    return body


async def forward(aliases: dict[str, Alias], alias_name: str, messages: list, params: dict,
                  *, output_api: str = "chat_completions", native_body: dict | None = None) -> httpx.Response:
    """在请求的别名上重试 max_retries+1 次，返回上游响应；全部失败抛 UpstreamError。"""
    alias = aliases[alias_name]
    payload = _payload(alias, messages, params, native_body=native_body)
    credential = alias.api_key()
    if not credential:
        # 配置问题，不是上游故障：直接报错，不重试也不换别名
        raise UpstreamError(503, f"别名 {alias_name} 缺少凭据（{alias.api_key_env} 未注入）")

    last_error: UpstreamError | None = None
    for _ in range(alias.max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=_timeout(alias)) as client:
                response = await client.post(
                    alias.request_url,
                    headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as error:
            last_error = UpstreamError(502, f"{alias_name} 请求失败: {error}")
            continue
        if response.status_code >= 500 or response.status_code == 429:
            last_error = UpstreamError(
                response.status_code, f"{alias_name} 返回 {response.status_code}: {response.text[:200]}"
            )
            continue
        if response.status_code < 400 and (alias.wire_api == "responses" or output_api == "responses"):
            try:
                data = response.json()
                if alias.wire_api == "responses":
                    converted = translate_response(data)  # Validate native terminal objects too.
                    if output_api != "responses":
                        data = converted
                    else:
                        data = sanitize_response(data)
                else:
                    data = from_chat_response(data)
            except (ValueError, ResponsesProtocolError) as error:
                raise UpstreamError(502, f"invalid Responses response: {error}") from error
            return httpx.Response(response.status_code, json=data)
        return response

    raise last_error or UpstreamError(502, f"别名 {alias_name} 未返回可用响应")


class UpstreamStream:
    """Own an upstream response and any native events read before forwarding."""

    def __init__(self, client: httpx.AsyncClient, response: httpx.Response,
                 wire_api: str = "chat_completions", output_api: str = "chat_completions"):
        self._client = client
        self._response = response
        self.status_code = response.status_code
        self.wire_api = wire_api
        self.output_api = output_api
        self.failed = False
        self.failure_diagnostics: dict[str, str] = {}
        self.usage = None
        self.sequence_number = -1
        self._native_events = None
        self._prefetched: list[dict] = []
        self._opening_error: ResponsesProtocolError | httpx.HTTPError | None = None
        # 上游给什么 content-type 就照传（SSE 是 text/event-stream）
        self.content_type = response.headers.get("content-type", "text/event-stream")

    async def prime_native_responses(self) -> None:
        """Hold status events until content, a terminal response or a failure."""
        self._native_events = _events(self._response.aiter_lines())
        metadata_bytes = 0
        metadata_events = 0
        async for event in self._native_events:
            kind = event["type"]
            if _retryable_early_failure(event):
                raise _EarlyResponseFailure("Responses stream reported a failure", failure_event=event)
            if kind in ("error", "response.failed", "response.cancelled"):
                raise ResponsesProtocolError("Responses stream reported a failure", failure_event=event)
            response = event.get("response")
            if kind not in _NATIVE_METADATA or (kind != "response.metadata"
                    and (not isinstance(response, dict) or response.get("output", []) != [])):
                self._prefetched.append(event)
                return
            metadata_bytes += len(json.dumps(event))
            metadata_events += 1
            if metadata_events > _PRELUDE_MAX_EVENTS or metadata_bytes > _PRELUDE_MAX_BYTES:
                raise ResponsesProtocolError("Responses stream status events exceeded their limit")
            if kind != "response.metadata":
                self._prefetched.append(event)
        raise ResponsesProtocolError("Responses stream ended without a terminal event")

    def retain_opening_error(self, error: ResponsesProtocolError | httpx.HTTPError) -> None:
        self._prefetched.clear()
        self._opening_error = error.with_traceback(None)

    async def _native_response_events(self) -> AsyncIterator[dict]:
        if self._opening_error is not None:
            raise self._opening_error
        for event in self._prefetched:
            yield event
        iterator = self._native_events
        if iterator is None:
            iterator = _events(self._response.aiter_lines())
        async for event in iterator:
            yield event

    async def aread_text(self) -> str:
        """把非流式语义的响应体（通常是上游的错误 JSON）整个读出来。"""
        try:
            body = await self._response.aread()
        finally:
            await self.aclose()
        return body.decode("utf-8", "replace")

    async def aiter(self) -> AsyncIterator[bytes]:
        try:
            if self.wire_api == "responses" or self.output_api == "responses":
                try:
                    if self.output_api == "responses":
                        iterator = (self._native_responses() if self.wire_api == "responses"
                                    else from_chat_stream(self._response.aiter_lines()))
                    else:
                        iterator = translate_stream(self._response.aiter_lines())
                    async for chunk in iterator:
                        if self.output_api == "responses":
                            for line in chunk.decode("utf-8").splitlines():
                                if line.startswith("data:"):
                                    event = json.loads(line[5:].strip())
                                    if type(event.get("sequence_number")) is int:
                                        self.sequence_number = event["sequence_number"]
                                    if event.get("type") in ("response.completed", "response.incomplete"):
                                        self.usage = event["response"].get("usage")
                        yield chunk
                except (ResponsesProtocolError, httpx.HTTPError) as error:
                    self.failed = True
                    self.failure_diagnostics = (error.failure_diagnostics
                        if isinstance(error, ResponsesProtocolError)
                        else {"failure_category": "transport_error"})
                    message = str(error) if isinstance(error, ResponsesProtocolError) else "Responses stream transport failed"
                    data = {"error": {"type": "upstream_error", "message": message}}
                    prefix = ""
                    if self.output_api == "responses":
                        data = {"type": "error", "code": "upstream_error", "message": message,
                                "param": None, "sequence_number": self.sequence_number + 1}
                        prefix = "event: error\n"
                    yield (prefix + "data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode("utf-8")
            else:
                async for chunk in self._response.aiter_bytes():
                    yield chunk
        finally:
            await self.aclose()

    async def _native_responses(self) -> AsyncIterator[bytes]:
        async for event in self._native_response_events():
            event = sanitize_event(event)
            if event is None:
                continue
            kind = event["type"]
            if kind in ("error", "response.failed", "response.cancelled"):
                raise ResponsesProtocolError("Responses stream reported a failure", failure_event=event)
            terminal = kind in ("response.completed", "response.incomplete")
            if terminal:
                response = event.get("response")
                translate_response(response)
                expected = kind.removeprefix("response.")
                if response.get("status") != expected:
                    raise ResponsesProtocolError("Responses terminal event status mismatch")
            yield ("event: " + kind + "\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode("utf-8")
            if terminal:
                return
        raise ResponsesProtocolError("Responses stream ended without a terminal event")

    async def aclose(self) -> None:
        try:
            await self._response.aclose()
        finally:
            await self._client.aclose()


async def open_stream(
    aliases: dict[str, Alias], alias_name: str, messages: list, params: dict,
    *, output_api: str = "chat_completions", native_body: dict | None = None,
) -> UpstreamStream:
    """Open a stream after resolving any retryable failures before content."""
    alias = aliases[alias_name]
    payload = _payload(alias, messages, params, stream=True, native_body=native_body)
    credential = alias.api_key()
    if not credential:
        raise UpstreamError(503, f"别名 {alias_name} 缺少凭据（{alias.api_key_env} 未注入）")

    native_responses = alias.wire_api == output_api == "responses"
    deadline = asyncio.get_running_loop().time() + alias.timeout_seconds
    last_error: UpstreamError | None = None
    for attempt in range(alias.max_retries + 1):
        client = httpx.AsyncClient(timeout=_timeout(alias))
        response = None
        retained = False
        cause = None
        diagnostics = {}
        try:
            async with asyncio.timeout_at(deadline):
                request = client.build_request(
                    "POST",
                    alias.request_url,
                    headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json"},
                    json=payload,
                )
                response = await client.send(request, stream=True)
                status = response.status_code
                if status >= 500 or status == 429:
                    cause = "http"
                    last_error = UpstreamError(status, f"upstream HTTP {status}")
                else:
                    stream = UpstreamStream(client, response, alias.wire_api, output_api)
                    if native_responses and status == 200:
                        try:
                            await stream.prime_native_responses()
                        except ResponsesProtocolError as error:
                            if isinstance(error, _EarlyResponseFailure) and attempt < alias.max_retries:
                                cause = "provider_response_failed"
                                last_error = UpstreamError(502, "Responses stream reported a failure")
                                diagnostics = error.failure_diagnostics
                            else:
                                stream.retain_opening_error(error)
                        except httpx.HTTPError as error:
                            if isinstance(error, _RETRY_TRANSPORT) and attempt < alias.max_retries:
                                cause = "transport"
                                last_error = UpstreamError(502, "upstream stream transport failed")
                            else:
                                stream.retain_opening_error(error)
                    if cause is None:
                        retained = True
                        return stream
        except _RETRY_TRANSPORT:
            cause = "transport"
            last_error = UpstreamError(502, "upstream stream transport failed")
        except TimeoutError as error:
            raise UpstreamError(504, "upstream stream deadline exceeded") from error
        except httpx.HTTPError as error:
            raise UpstreamError(502, "upstream stream transport failed") from error
        finally:
            if not retained:
                try:
                    if response is not None:
                        await response.aclose()
                finally:
                    await client.aclose()
        if attempt < alias.max_retries:
            delay = min(0.25 * 2 ** attempt, 2.0)
            if asyncio.get_running_loop().time() + delay >= deadline:
                break
            _log.info(json.dumps({"event": "upstream_stream_retry", "alias": alias_name,
                                  "failed_attempt": attempt + 1, "cause": cause, **diagnostics}))
            await asyncio.sleep(delay)

    raise last_error or UpstreamError(502, f"别名 {alias_name} 未返回可用响应")
