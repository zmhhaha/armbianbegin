"""llm-service：集群内统一的 LLM 入口。

按 spec 的边界实现：
- 只暴露 OpenAI 兼容契约，调用方传"允许的别名 + 有界生成参数"；
- 任意 base URL / API Key / provider / 未知别名一律拒绝；
- 凭据只在服务内存在，绝不回传调用方；
- 仅集群内可达（由 k8s NetworkPolicy + ClusterIP 保证，服务本身不做公网入口）。
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from config import ALLOWED_PARAMS, ConfigError, load_config
from upstream import UpstreamError, forward

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("llm-service")

app = FastAPI(title="llm-service", version="0.1.0")

SERVICE_TOKEN = os.getenv("LLM_SERVICE_TOKEN", "").strip()

try:
    ALIASES, RPM_LIMIT = load_config()
    CONFIG_ERROR: str | None = None
except ConfigError as error:
    ALIASES, RPM_LIMIT, CONFIG_ERROR = {}, 60.0, str(error)

_usage: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0})
# 按别名记账：调用方未必会带 X-Caller（如 litellm 就不带），
# 但每个调用方用自己的别名档位，所以别名维度足以区分谁在用。
_alias_usage: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0})
_windows: dict[str, deque] = defaultdict(deque)


def _record_usage(alias_name: str, caller: str, tokens: dict) -> None:
    for counter in (_usage[caller], _alias_usage[alias_name]):
        counter["requests"] += 1
        counter["prompt_tokens"] += int(tokens.get("prompt_tokens") or 0)
        counter["completion_tokens"] += int(tokens.get("completion_tokens") or 0)


class ChatRequest(BaseModel):
    # extra="forbid"：请求体里出现 base_url / api_key / provider 之类字段直接 422
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=64)
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=200)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    stop: list[str] | None = Field(default=None, max_length=4)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    # 函数调用相关：内部受信调用方需要（如 CrewAI 的网页工具），透传给上游
    tools: list[dict[str, Any]] | None = Field(default=None, max_length=32)
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    seed: int | None = None
    n: int | None = Field(default=None, ge=1, le=4)
    stream: bool = False


def authorize(authorization: str | None, caller: str | None) -> str:
    if not SERVICE_TOKEN:
        raise HTTPException(503, "llm-service 未配置 LLM_SERVICE_TOKEN")
    if authorization != f"Bearer {SERVICE_TOKEN}":
        raise HTTPException(401, "invalid internal token")
    return (caller or "unknown").strip()[:64] or "unknown"


def check_rate(caller: str) -> None:
    now = time.time()
    window = _windows[caller]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RPM_LIMIT:
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "60"})
    window.append(now)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    if CONFIG_ERROR:
        raise HTTPException(503, f"config error: {CONFIG_ERROR}")
    credentialed = [name for name, alias in ALIASES.items() if alias.api_key()]
    if not credentialed:
        raise HTTPException(503, "no provider credential available")
    return {"status": "ready", "aliases": len(ALIASES), "credentialed": len(credentialed)}


@app.get("/v1/models")
def models(authorization: str | None = Header(default=None), x_caller: str | None = Header(default=None)):
    authorize(authorization, x_caller)
    return {
        "object": "list",
        "data": [{"id": name, "object": "model", "owned_by": alias.provider} for name, alias in sorted(ALIASES.items())],
    }


@app.get("/v1/usage")
def usage(authorization: str | None = Header(default=None), x_caller: str | None = Header(default=None)):
    caller = authorize(authorization, x_caller)
    return {
        "caller": caller,
        "limits": {"requests_per_minute": RPM_LIMIT},
        "usage": _usage[caller],
        # 调用方没带 X-Caller 时（如 litellm），用别名维度区分
        "by_alias": {name: dict(counter) for name, counter in _alias_usage.items()},
    }


@app.post("/v1/chat/completions")
async def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
    x_caller: str | None = Header(default=None),
):
    caller = authorize(authorization, x_caller)
    if CONFIG_ERROR:
        raise HTTPException(503, f"config error: {CONFIG_ERROR}")
    if request.model not in ALIASES:
        raise HTTPException(400, f"unknown model alias: {request.model}")
    if request.stream:
        raise HTTPException(400, "stream=true is not supported by this service")
    # 按别名的「类别」施加策略：trusted 透传标准字段；guarded 收窄能力面，防提示词劫持
    alias = ALIASES[request.model]
    policy = alias.policy
    if request.tools and not policy["allow_tools"]:
        raise HTTPException(400, f"model alias '{request.model}' (tier={alias.tier}) does not allow tools")
    if request.response_format and not policy["allow_tools"]:
        raise HTTPException(400, f"model alias '{request.model}' (tier={alias.tier}) does not allow response_format")
    if request.max_tokens and request.max_tokens > policy["max_tokens_cap"]:
        raise HTTPException(400, f"max_tokens exceeds the cap ({policy['max_tokens_cap']}) for tier={alias.tier}")
    if len(request.messages) > policy["max_messages"]:
        raise HTTPException(400, f"too many messages for tier={alias.tier} (max {policy['max_messages']})")
    check_rate(caller)

    params = {key: getattr(request, key) for key in ALLOWED_PARAMS}
    started = time.time()
    try:
        used_alias, response = await forward(ALIASES, request.model, request.messages, params)
    except UpstreamError as error:
        log.info(json.dumps({"event": "upstream_error", "caller": caller, "alias": request.model,
                             "status": error.status, "detail": error.message}, ensure_ascii=False))
        raise HTTPException(502, f"upstream error: {error.message}")

    if response.status_code >= 400:
        log.info(json.dumps({"event": "upstream_reject", "caller": caller, "alias": used_alias,
                             "status": response.status_code}, ensure_ascii=False))
        raise HTTPException(response.status_code, response.text[:500])

    data = response.json()
    tokens = data.get("usage") or {}
    _record_usage(used_alias, caller, tokens)
    log.info(json.dumps({
        "event": "chat", "caller": caller, "alias": request.model, "upstream_alias": used_alias,
        "model": data.get("model"), "prompt_tokens": tokens.get("prompt_tokens"),
        "completion_tokens": tokens.get("completion_tokens"),
        "latency_ms": int((time.time() - started) * 1000),
    }, ensure_ascii=False))
    return data
