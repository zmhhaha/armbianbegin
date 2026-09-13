"""上游转发：解析别名 → 附加 Vault 注入的凭据 → 调用 OpenAI 兼容端点。

凭据只在这里拼进请求头，绝不回传给调用方。

重试只针对超时 / 5xx / 429，并且**只在同一个别名上重试**：本服务不做跨上游转移，
调用方点名哪个别名，就只能由那个别名背后的模型作答。别名耗尽了重试次数就抛错，
由调用方决定怎么办 —— 绝不静默换成另一个 provider 或另一个模型。
"""
from __future__ import annotations

import httpx

from config import Alias


class UpstreamError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _payload(alias: Alias, messages: list, params: dict) -> dict:
    body = dict(alias.defaults)
    body.update({key: value for key, value in params.items() if value is not None})
    body["model"] = alias.model  # 调用方传的是别名，真正发给上游的是配置里的模型名
    body["messages"] = messages
    body["stream"] = False
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
