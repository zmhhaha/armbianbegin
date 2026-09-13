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
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from auth import resolve, token_map
from config import ALLOWED_PARAMS, ConfigError, load_config, load_guard_config
from guard import detect, harden, leaked, new_canary, user_texts
from upstream import UpstreamError, UpstreamStream, forward, open_stream

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("llm-service")

app = FastAPI(title="llm-service", version="0.1.0")

STARTED_AT = time.time()

try:
    ALIASES, RPM_LIMIT = load_config()
    CONFIG_ERROR: str | None = None
except ConfigError as error:
    ALIASES, RPM_LIMIT, CONFIG_ERROR = {}, 60.0, str(error)

try:
    GUARD = load_guard_config()
except ConfigError as error:
    # 防护配置写错要让服务 not-ready，而不是静默退化成「不防护」——那是最危险的失败方式
    GUARD = None
    CONFIG_ERROR = CONFIG_ERROR or str(error)

_usage: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0})
# 按别名记账：它回答的是「哪个模型被用了多少」，与「谁在用」是两个维度，所以两张表都留着。
_alias_usage: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0})
_windows: dict[str, deque] = defaultdict(deque)

# 防护计数（内存态；Pod 重启归零，日报里会带 since 时间戳说明这一点）
_guard_stats: dict[str, dict] = defaultdict(
    lambda: {"detection_hits": defaultdict(int), "canary_leaks": 0, "rejected": 0}
)


def _guard_view(caller: str) -> dict:
    stats = _guard_stats[caller]
    return {
        "detection_hits": dict(stats["detection_hits"]),
        "canary_leaks": stats["canary_leaks"],
        "rejected": stats["rejected"],
    }


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


def _guard_or_503():
    if GUARD is None:
        raise HTTPException(503, f"guard config error: {CONFIG_ERROR}")
    return GUARD


@app.get("/v1/guard")
def guard_self(authorization: str | None = Header(default=None)):
    """调用方看**自己**的防护计数与当前生效的模式。"""
    guard = _guard_or_503()
    caller = authorize(authorization)
    return {
        "caller": caller,
        "since": datetime.fromtimestamp(STARTED_AT, timezone.utc).isoformat(),
        "counters": _guard_view(caller),
        "modes": {
            "spotlight": guard.spotlight,
            "canary": guard.canary,
            "canary_action": guard.canary_action,
            "detection": guard.detection,
        },
    }


@app.get("/v1/guard/report")
def guard_report(authorization: str | None = Header(default=None)):
    """**全量**汇总，只给 LLM_GUARD.report_callers 白名单（日报生产者用）。

    普通调用方只能从 /v1/guard 看自己的；这个端点会暴露所有人的用量，
    所以必须显式列白名单，不能默认开放。
    """
    guard = _guard_or_503()
    caller = authorize(authorization)
    if not guard.may_read_report(caller):
        raise HTTPException(403, "this caller may not read the aggregate guard report")
    return {
        "since": datetime.fromtimestamp(STARTED_AT, timezone.utc).isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "callers": {name: {**_usage[name], **_guard_view(name)} for name in sorted(_usage)},
        "by_alias": {name: dict(counter) for name, counter in sorted(_alias_usage.items())},
    }


def _stream_usage(text: str) -> dict:
    """从 SSE 尾部取 usage。

    流式请求注入过 `stream_options.include_usage`，上游会在最后一帧带 usage；
    取不到就返回空 dict，用量统计会缺这次 —— 不因此报错。
    """
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except ValueError:
            continue
        usage = data.get("usage")
        if isinstance(usage, dict):
            return usage
    return {}


async def _relay(stream: UpstreamStream, canary: str | None, caller: str, alias_name: str, started: float):
    """把上游字节转发给调用方，顺带做 canary 检查与用量统计。

    流式下 `canary_action=reject` 的语义是**截断**而不是「拒绝」：已经吐出去的字收不回来，
    所以发现泄漏时只能停止继续转发。这一点写进了 README。
    """
    keep = 8192  # 只留尾部：usage 在最后，canary 检测也不需要留全文
    tail = ""
    leak_seen = False
    async for chunk in stream.aiter():
        tail = (tail + chunk.decode("utf-8", "ignore"))[-keep:]
        # canary 一旦落进尾部窗口就会一直留在里面，所以只判一次，否则每个后续 chunk 都会重复计数
        if canary and not leak_seen and canary in tail:
            leak_seen = True
            _guard_stats[caller]["canary_leaks"] += 1
            log.info(json.dumps({"event": "guard_canary_leak", "caller": caller, "alias": alias_name,
                                 "stream": True}, ensure_ascii=False))
            if GUARD.canary_action == "reject":
                _guard_stats[caller]["rejected"] += 1
                log.info(json.dumps({"event": "guard_stream_truncated", "caller": caller,
                                     "alias": alias_name}, ensure_ascii=False))
                return
        yield chunk

    tokens = _stream_usage(tail)
    _record_usage(alias_name, caller, tokens)
    log.info(json.dumps({
        "event": "chat", "caller": caller, "alias": alias_name, "stream": True,
        "prompt_tokens": tokens.get("prompt_tokens"),
        "completion_tokens": tokens.get("completion_tokens"),
        "latency_ms": int((time.time() - started) * 1000),
    }, ensure_ascii=False))


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

    # --- 防护：先在**原始** user 文本上扫攻击特征（要在 spotlight 包标记之前，否则扫的是自己加的标记）---
    hits: list[str] = []
    for text in user_texts(request.messages):
        for name in detect(text):
            if name not in hits:
                hits.append(name)
    if hits and GUARD.detection != "off":
        stats = _guard_stats[caller]
        for name in hits:
            stats["detection_hits"][name] += 1
        log.info(json.dumps({"event": "guard_detection", "caller": caller, "alias": request.model,
                             "rules": hits}, ensure_ascii=False))
        if GUARD.detection == "reject":
            stats["rejected"] += 1
            raise HTTPException(400, "request blocked by prompt-injection detection")

    # --- 防护：按档位改写发给上游的 messages（包标记 / 埋 canary）---
    canary = new_canary() if GUARD.canary_for(alias.tier) else None
    messages = harden(request.messages, spotlight=GUARD.spotlight_for(alias.tier), canary=canary)

    params = {key: getattr(request, key) for key in ALLOWED_PARAMS}
    started = time.time()

    # --- 流式分支：连接与读取分开，让「上游不可用」在还没写任何字节前变成正常的 5xx ---
    if request.stream:
        try:
            stream = await open_stream(ALIASES, request.model, messages, params)
        except UpstreamError as error:
            log.info(json.dumps({"event": "upstream_error", "caller": caller, "alias": request.model,
                                 "status": error.status, "detail": error.message, "stream": True},
                                ensure_ascii=False))
            raise HTTPException(502, f"upstream error: {error.message}")

        if stream.status_code >= 400:
            # 上游的 4xx 原样透传（和上面的非流式路径一致）
            detail = await stream.aread_text()
            log.info(json.dumps({"event": "upstream_reject", "caller": caller, "alias": request.model,
                                 "status": stream.status_code, "stream": True}, ensure_ascii=False))
            raise HTTPException(stream.status_code, detail[:500])

        return StreamingResponse(
            _relay(stream, canary, caller, request.model, started),
            media_type=stream.content_type,
        )

    try:
        response = await forward(ALIASES, request.model, messages, params)
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

    # --- 防护：响应里出现 canary，说明模型被套话把 system 复述出来了 ---
    if canary:
        message = data["choices"][0].get("message") or {}
        if leaked(message.get("content"), canary):
            _guard_stats[caller]["canary_leaks"] += 1
            log.info(json.dumps({"event": "guard_canary_leak", "caller": caller,
                                 "alias": request.model}, ensure_ascii=False))
            if GUARD.canary_action == "reject":
                _guard_stats[caller]["rejected"] += 1
                raise HTTPException(502, "response withheld: system prompt leakage detected")

    tokens = data.get("usage") or {}
    _record_usage(request.model, caller, tokens)
    log.info(json.dumps({
        "event": "chat", "caller": caller, "alias": request.model,
        "model": data.get("model"), "prompt_tokens": tokens.get("prompt_tokens"),
        "completion_tokens": tokens.get("completion_tokens"),
        "latency_ms": int((time.time() - started) * 1000),
    }, ensure_ascii=False))
    return data
