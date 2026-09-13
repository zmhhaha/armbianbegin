"""上游转发：解析别名 → 附加 Vault 注入的凭据 → 调用 OpenAI 兼容端点。

凭据只在这里拼进请求头，绝不回传给调用方。

重试只针对超时 / 5xx / 429，并且**只在同一个别名上重试**：本服务不做跨上游转移，
调用方点名哪个别名，就只能由那个别名背后的模型作答。别名耗尽了重试次数就抛错，
由调用方决定怎么办 —— 绝不静默换成另一个 provider 或另一个模型。

流式（`stream: true`）走 `open_stream()`：**建立连接**与**读取流**分成两步，
这样「上游不可用」能在还没给调用方写任何字节之前变成正常的 5xx，
而不是一个已经开始的流被中途掐断。一旦开始读，就没有重试可言。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from config import Alias

# 流式时让上游在最后一帧带上 usage，否则流式请求拿不到 token 数、用量统计会缺口。
# DeepSeek 与 OpenAI 都支持这个字段。
STREAM_USAGE_OPTION = {"include_usage": True}


class UpstreamError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _payload(alias: Alias, messages: list, params: dict, *, stream: bool = False) -> dict:
    body = dict(alias.defaults)
    body.update({key: value for key, value in params.items() if value is not None})
    body["model"] = alias.model  # 调用方传的是别名，真正发给上游的是配置里的模型名
    body["messages"] = messages
    body["stream"] = stream
    if stream:
        body["stream_options"] = dict(STREAM_USAGE_OPTION)
    return body


async def forward(aliases: dict[str, Alias], alias_name: str, messages: list, params: dict) -> httpx.Response:
    """在请求的别名上重试 max_retries+1 次，返回上游响应；全部失败抛 UpstreamError。"""
    alias = aliases[alias_name]
    credential = alias.api_key()
    if not credential:
        # 配置问题，不是上游故障：直接报错，不重试也不换别名
        raise UpstreamError(503, f"别名 {alias_name} 缺少凭据（{alias.api_key_env} 未注入）")

    last_error: UpstreamError | None = None
    for _ in range(alias.max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=alias.timeout_seconds) as client:
                response = await client.post(
                    alias.chat_url,
                    headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json"},
                    json=_payload(alias, messages, params),
                )
        except httpx.HTTPError as error:
            last_error = UpstreamError(502, f"{alias_name} 请求失败: {error}")
            continue
        if response.status_code >= 500 or response.status_code == 429:
            last_error = UpstreamError(
                response.status_code, f"{alias_name} 返回 {response.status_code}: {response.text[:200]}"
            )
            continue
        return response

    raise last_error or UpstreamError(502, f"别名 {alias_name} 未返回可用响应")


class UpstreamStream:
    """一个已建立、尚未读取的上游流式连接。

    能拿到这个对象，说明响应头已经收到、且不是可重试的失败。
    4xx 不在这里抛 —— 调用方要按上游原样透传，所以先暴露 `status_code` 让它判断。
    """

    def __init__(self, client: httpx.AsyncClient, response: httpx.Response):
        self._client = client
        self._response = response
        self.status_code = response.status_code
        # 上游给什么 content-type 就照传（SSE 是 text/event-stream）
        self.content_type = response.headers.get("content-type", "text/event-stream")

    async def aread_text(self) -> str:
        """把非流式语义的响应体（通常是上游的错误 JSON）整个读出来。"""
        try:
            body = await self._response.aread()
        finally:
            await self.aclose()
        return body.decode("utf-8", "replace")

    async def aiter(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._response.aiter_bytes():
                yield chunk
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        try:
            await self._response.aclose()
        finally:
            await self._client.aclose()


async def open_stream(
    aliases: dict[str, Alias], alias_name: str, messages: list, params: dict
) -> UpstreamStream:
    """建立流式上游连接。失败抛 UpstreamError —— 此时还没有任何字节发给调用方。"""
    alias = aliases[alias_name]
    credential = alias.api_key()
    if not credential:
        raise UpstreamError(503, f"别名 {alias_name} 缺少凭据（{alias.api_key_env} 未注入）")

    last_error: UpstreamError | None = None
    for _ in range(alias.max_retries + 1):
        client = httpx.AsyncClient(timeout=alias.timeout_seconds)
        try:
            request = client.build_request(
                "POST",
                alias.chat_url,
                headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json"},
                json=_payload(alias, messages, params, stream=True),
            )
            response = await client.send(request, stream=True)
        except httpx.HTTPError as error:
            await client.aclose()
            last_error = UpstreamError(502, f"{alias_name} 请求失败: {error}")
            continue

        if response.status_code >= 500 or response.status_code == 429:
            detail = (await response.aread()).decode("utf-8", "replace")[:200]
            await response.aclose()
            await client.aclose()
            last_error = UpstreamError(
                response.status_code, f"{alias_name} 返回 {response.status_code}: {detail}"
            )
            continue

        return UpstreamStream(client, response)

    raise last_error or UpstreamError(502, f"别名 {alias_name} 未返回可用响应")
