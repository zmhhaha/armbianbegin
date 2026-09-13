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

from auth import resolve, token_map
from config import ALLOWED_PARAMS, ConfigError, load_config
from upstream import UpstreamError, forward

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("llm-service")

app = FastAPI(title="llm-service", version="0.1.0")

try:
    ALIASES, RPM_LIMIT = load_config()
    CONFIG_ERROR: str | None = None
except ConfigError as error:
    ALIASES, RPM_LIMIT, CONFIG_ERROR = {}, 60.0, str(error)

_usage: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0})
# 按别名记账：它回答的是「哪个模型被用了多少」，与「谁在用」是两个维度，所以两张表都留着。
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


def authorize(authorization: str | None) -> str:
    """身份**只从令牌推导**，不接受任何客户端自称。

    一个 `LLM_TOKEN_*` 都没配属于**配置错误**（503），不是鉴权失败（401）—— 两者要分得开，
    否则漏配令牌会被误当成调用方用错了凭据。
    """
    if not token_map():
        raise HTTPException(503, "llm-service 未配置任何 LLM_TOKEN_<CALLER> 调用方令牌")
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    caller = resolve(token)
    if not caller:
        raise HTTPException(401, "invalid caller token")
    return caller


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
    return {
        "status": "ready",
        "aliases": len(ALIASES),
        "credentialed": len(credentialed),
        # 已注入几个调用方令牌；为 0 时服务能起来但谁都调不通
        "callers": len(token_map()),
    }


@app.get("/v1/models")
def models(authorization: str | None = Header(default=None)):
    authorize(authorization)
    return {
        "object": "list",
        "data": [{"id": name, "object": "model", "owned_by": alias.provider} for name, alias in sorted(ALIASES.items())],
    }


@app.get("/v1/usage")
def usage(authorization: str | None = Header(default=None)):
    caller = authorize(authorization)
    return {
        "caller": caller,
        "limits": {"requests_per_minute": RPM_LIMIT},
        "usage": _usage[caller],
        # 别名维度：回答「哪个模型被用了多少」，与「谁在用」是两个问题
        "by_alias": {name: dict(counter) for name, counter in _alias_usage.items()},
    }


@app.post("/v1/chat/completions")
async def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
):
    caller = authorize(authorization)
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
        response = await forward(ALIASES, request.model, request.messages, params)
    except UpstreamError as error:
        log.info(json.dumps({"event": "upstream_error", "caller": caller, "alias": request.model,
                             "status": error.status, "detail": error.message}, ensure_ascii=False))
        raise HTTPException(502, f"upstream error: {error.message}")

    if response.status_code >= 400:
        log.info(json.dumps({"event": "upstream_reject", "caller": caller, "alias": request.model,
                             "status": response.status_code}, ensure_ascii=False))
        raise HTTPException(response.status_code, response.text[:500])

    # 上游给了一个 2xx，不代表它给了能用的内容。这里只做结构校验：
    # 不是合法 JSON、或 choices 缺失/为空，都当作上游故障报错，不把无效响应透传给调用方。
    # 刻意不检查 message.content 是否为空 —— 工具调用时 content 本来就是 null。
    try:
        data = response.json()
    except ValueError:
        log.info(json.dumps({"event": "upstream_invalid_body", "caller": caller, "alias": request.model,
                             "status": response.status_code}, ensure_ascii=False))
        raise HTTPException(502, "upstream error: response body is not valid JSON")
    if not isinstance(data.get("choices"), list) or not data["choices"]:
        log.info(json.dumps({"event": "upstream_no_choices", "caller": caller, "alias": request.model,
                             "status": response.status_code}, ensure_ascii=False))
        raise HTTPException(502, "upstream error: response contains no choices")

    tokens = data.get("usage") or {}
    _record_usage(request.model, caller, tokens)
    log.info(json.dumps({
        "event": "chat", "caller": caller, "alias": request.model,
        "model": data.get("model"), "prompt_tokens": tokens.get("prompt_tokens"),
        "completion_tokens": tokens.get("completion_tokens"),
        "latency_ms": int((time.time() - started) * 1000),
    }, ensure_ascii=False))
    return data
