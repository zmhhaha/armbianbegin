"""上游转发：解析别名 → 附加 Vault 注入的凭据 → 调用 OpenAI 兼容端点。

凭据只在这里拼进请求头，绝不回传给调用方。重试只针对超时/5xx/429；
某个别名彻底失败时按配置的 fallback 顺序转移。
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


async def forward(aliases: dict[str, Alias], alias_name: str, messages: list, params: dict) -> tuple[str, httpx.Response]:
    """按 [别名, *fallback] 顺序尝试，返回 (实际使用的别名, 上游响应)。"""
    chain = [alias_name, *aliases[alias_name].fallback]
    last_error: UpstreamError | None = None

    for name in chain:
        alias = aliases[name]
        credential = alias.api_key()
        if not credential:
            last_error = UpstreamError(503, f"别名 {name} 缺少凭据（{alias.api_key_env} 未注入）")
            continue
        for attempt in range(alias.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=alias.timeout_seconds) as client:
                    response = await client.post(
                        alias.chat_url,
                        headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json"},
                        json=_payload(alias, messages, params),
                    )
            except httpx.HTTPError as error:
                last_error = UpstreamError(502, f"{name} 请求失败: {error}")
                continue
            if response.status_code >= 500 or response.status_code == 429:
                last_error = UpstreamError(response.status_code, f"{name} 返回 {response.status_code}: {response.text[:200]}")
                continue
            return name, response

    raise last_error or UpstreamError(502, "没有可用的上游别名")
