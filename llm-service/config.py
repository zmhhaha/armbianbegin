"""别名路由配置。

只读取 ConfigMap 提供的非敏感配置（provider、上游 base URL、模型别名、默认参数、超时、重试）。
凭据一律通过 api_key_env 指向的环境变量读取（由 Vault ExternalSecret 注入），配置文件里不允许内嵌凭据。
"""
from __future__ import annotations

import json
import os
import hashlib
import math
import re
from types import MappingProxyType
from urllib.parse import urlsplit
from dataclasses import dataclass, field

# 请求体里禁止出现的字段：任何"调用方自己指定上游"的尝试都必须被拒绝
FORBIDDEN_REQUEST_FIELDS = (
    "base_url",
    "url",
    "endpoint",
    "api_key",
    "api_keys",
    "provider",
    "upstream",
    "headers",
)
# 允许透传的有界非敏感生成参数。
# 含 tools/tool_choice/response_format：内部受信调用方（如 content-llm-service 的
# CrewAI 工具调用）需要，属于标准 OpenAI 兼容字段。**改路由**的字段仍然一律拒绝
# （见 FORBIDDEN_REQUEST_FIELDS）。
ALLOWED_PARAMS = (
    "temperature", "top_p", "max_tokens", "stop",
    "presence_penalty", "frequency_penalty",
    "tools", "tool_choice", "response_format", "seed", "n",
)


# ---------------------------------------------------------------------------
# 类别（tier）：策略定义在这里，别名只负责「选类别」。
#
# 为什么要分类：有的调用方由**用户写 prompt**（道法自然系列等对话型 Agent），
# 需要收窄能力面防提示词劫持；有的调用方**不由用户写 prompt**（内容生成、RAG、
# 内部机器对话），限制它们只会误伤。所以至少两档。
#
# 默认 guarded —— 漏配的后果是「更严」而不是「更松」，这是安全默认。
# ---------------------------------------------------------------------------
TIERS: dict[str, dict] = {
    "trusted": {
        "description": "内部受信调用方（内容生成、RAG、内部机器对话）：标准字段透传",
        "allow_tools": True,
        "max_tokens_cap": 8192,
        "max_messages": 200,
    },
    "guarded": {
        "description": "面向用户、用户可写 prompt 的对话型服务：收窄能力面，防提示词劫持",
        "allow_tools": False,
        "max_tokens_cap": 2048,
        "max_messages": 60,
    },
}
DEFAULT_TIER = "guarded"


class ConfigError(RuntimeError):
    """配置缺失或非法。服务应进入 not-ready，而不是用错误配置转发请求。"""


@dataclass(frozen=True)
class Alias:
    name: str
    provider: str
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: float = 60.0
    max_retries: int = 2
    defaults: dict = field(default_factory=dict)
    # 类别：策略在 TIERS 里定义，别名只选档位
    tier: str = DEFAULT_TIER
    upstream: str = ""
    revision: str = ""
    active: bool = False
    wire_api: str = "chat_completions"

    def metadata(self) -> dict:
        return {"requested_alias": self.name, "resolved_upstream": self.upstream,
                "configured_model": self.model, "tier": self.tier, "route_revision": self.revision,
                "wire_api": self.wire_api}

    @property
    def policy(self) -> dict:
        return TIERS[self.tier]

    @property
    def request_url(self) -> str:
        path = "/responses" if self.wire_api == "responses" else "/chat/completions"
        return self.base_url.rstrip("/") + path

    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "").strip()


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, (dict, MappingProxyType)):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(v) for v in value]
    return value


def _object(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ConfigError(f"{label}: invalid object or unsupported fields")
    return value


def _number(value, low, high, label, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high
            or (integer and not isinstance(value, int))):
        raise ConfigError(f"{label}: invalid number")
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("duplicate configuration key")
        result[key] = value
    return result


def validate_params(params, tier):
    _object(params, ALLOWED_PARAMS, "defaults")
    bounds = {"temperature": (0, 2), "top_p": (0, 1), "max_tokens": (1, TIERS[tier]["max_tokens_cap"]),
              "presence_penalty": (-2, 2), "frequency_penalty": (-2, 2), "n": (1, 4)}
    for key, value in params.items():
        if value is None:
            continue
        if key in bounds:
            _number(value, *bounds[key], key, integer=key in ("max_tokens", "n"))
        if key == "seed" and (isinstance(value, bool) or not isinstance(value, int)):
            raise ConfigError("invalid seed")
        if key in ("tools", "tool_choice", "response_format") and not TIERS[tier]["allow_tools"]:
            raise ConfigError(f"tier {tier} does not allow {key}")
        if key == "tools" and (not isinstance(value, list) or len(value) > 32 or any(not isinstance(v, dict) for v in value)):
            raise ConfigError("invalid tools")
        if key == "response_format" and not isinstance(value, dict):
            raise ConfigError("invalid response_format")
        if key == "tool_choice" and not isinstance(value, (str, dict)):
            raise ConfigError("invalid tool_choice")
        if key == "stop" and (not isinstance(value, list) or len(value) > 4 or any(not isinstance(v, str) for v in value)):
            raise ConfigError("invalid stop")


def load_config() -> tuple[dict[str, Alias], float]:
    """返回 (别名表, 每调用方每分钟请求上限)。"""
    inline = os.getenv("LLM_ALIASES", "").strip()
    path = os.getenv("LLM_CONFIG_FILE", "").strip()
    try:
        if inline:
            data = json.loads(inline, object_pairs_hook=_unique)
        elif path:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle, object_pairs_hook=_unique)
        else:
            raise ConfigError("LLM_ALIASES 或 LLM_CONFIG_FILE 未配置")
    except (ValueError, OSError) as error:
        raise ConfigError("cannot read valid routing JSON") from error
    _object(data, ("version", "active_upstream", "upstreams", "routes", "limits"), "config")
    if type(data.get("version")) is not int or data["version"] != 2:
        raise ConfigError("only configuration version=2 is supported")
    upstreams, routes = data.get("upstreams"), data.get("routes")
    if not isinstance(upstreams, dict) or not upstreams or not isinstance(routes, dict) or not routes:
        raise ConfigError("upstreams and routes must be nonempty objects")
    active = data.get("active_upstream")
    if not isinstance(active, str) or active not in upstreams:
        raise ConfigError("unknown active_upstream")
    for name, item in upstreams.items():
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name):
            raise ConfigError("invalid upstream name")
        _object(item, ("provider", "base_url", "model", "api_key_env", "max_retries", "wire_api"), "upstream")
        if item.get("wire_api", "chat_completions") not in ("chat_completions", "responses"):
            raise ConfigError("unsupported upstream wire_api")
        if any(not isinstance(item.get(k), str) or not item[k].strip() for k in ("provider", "base_url", "model", "api_key_env")):
            raise ConfigError("upstream missing required string")
        try:
            url = urlsplit(item["base_url"])
            url.port
        except ValueError as error:
            raise ConfigError("invalid upstream URL") from error
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ConfigError("invalid upstream URL")
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", item["api_key_env"]):
            raise ConfigError("invalid credential environment reference")
        _number(item.get("max_retries", 2), 0, 5, "max_retries", integer=True)
    if not os.getenv(upstreams[active]["api_key_env"], "").strip():
        raise ConfigError("active upstream credential missing")
    guard = load_guard_config()
    guard_revision = {"spotlight": guard.spotlight, "canary": guard.canary,
                      "canary_action": guard.canary_action, "detection": guard.detection}
    aliases = {}
    for name, route in routes.items():
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name):
            raise ConfigError("invalid route name")
        _object(route, ("upstream", "tier", "timeout_seconds", "defaults"), "route")
        tier, target = route.get("tier"), route.get("upstream")
        if not isinstance(tier, str) or tier not in TIERS:
            raise ConfigError("unknown tier")
        target = active if target == "$active" else target
        if not isinstance(target, str) or target not in upstreams:
            raise ConfigError("unknown route upstream")
        if name in ("llm-guarded", "llm-trusted") and (tier != name[4:] or route["upstream"] != "$active"):
            raise ConfigError("stable routes must keep their tier and use $active")
        item = upstreams[target]
        defaults = route.get("defaults", {})
        validate_params(defaults, tier)
        if item.get("wire_api") == "responses":
            from responses_adapter import ResponsesRequestError, build_request
            try:
                build_request(item["model"], [], defaults)
            except ResponsesRequestError as error:
                raise ConfigError(f"unsupported Responses defaults: {error}") from error
        timeout = _number(route.get("timeout_seconds", 60), 1, 600, "timeout_seconds")
        resolved = {**item, "upstream": target, "tier": tier, "timeout_seconds": timeout, "defaults": defaults, "guard": guard_revision}
        revision = hashlib.sha256(json.dumps(resolved, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
        aliases[name] = Alias(name=name, **item, tier=tier, defaults=freeze(defaults), timeout_seconds=timeout,
                              upstream=target, revision=revision, active=route["upstream"] == "$active")
    for name in ("llm-guarded", "llm-trusted"):
        if name not in aliases:
            raise ConfigError("both stable tier routes are required")
    limits = _object(data.get("limits", {}), ("requests_per_minute_per_caller",), "limits")
    rpm = _number(limits.get("requests_per_minute_per_caller", 60), 1, 1000000, "rpm")
    return MappingProxyType(aliases), float(rpm)


# ---------------------------------------------------------------------------
# 防护配置（LLM_GUARD）
#
# 与 LLM_ALIASES 分开：那边是路由，这边是「怎么防滥用」。分开之后改防护不用碰别名表。
#
# 默认值刻意保守 —— 上线当天行为不变，只多日志：
#   spotlight / canary 只对 guarded 开（它们是唯一会改写发给上游 prompt 的机制），
#   detection 只记日志不拦，report_callers 为空（没人能读全量汇总）。
# ---------------------------------------------------------------------------
GUARD_MODES = ("off", "log", "reject")
# canary 的「注入开关」按档位控制（见下），命中之后怎么办是全局的
CANARY_ACTIONS = ("log", "reject")

DEFAULT_GUARD: dict = {
    "spotlight": {"guarded": True, "trusted": False},
    "canary": {"guarded": True, "trusted": False},
    "canary_action": "log",
    "detection": "log",
    "report_callers": [],
}


@dataclass(frozen=True)
class GuardConfig:
    spotlight: dict[str, bool]
    canary: dict[str, bool]
    canary_action: str
    detection: str
    report_callers: tuple[str, ...]

    def spotlight_for(self, tier: str) -> bool:
        return bool(self.spotlight.get(tier, False))

    def canary_for(self, tier: str) -> bool:
        return bool(self.canary.get(tier, False))

    def may_read_report(self, caller: str) -> bool:
        return caller in self.report_callers


def _tier_flag(value: object, name: str) -> dict[str, bool]:
    """接受 `true`（所有档位）或 `{"guarded": true, "trusted": false}` 两种写法。"""
    if isinstance(value, bool):
        return {tier: value for tier in TIERS}
    if isinstance(value, dict):
        unknown = [key for key in value if key not in TIERS]
        if unknown:
            raise ConfigError(f"LLM_GUARD.{name} 里有未知档位: {', '.join(unknown)}；可选值：{', '.join(TIERS)}")
        return {tier: bool(value.get(tier, False)) for tier in TIERS}
    raise ConfigError(f"LLM_GUARD.{name} 必须是布尔值或档位映射，实际是 {type(value).__name__}")


def load_guard_config() -> GuardConfig:
    """读取 LLM_GUARD；没配置就用 DEFAULT_GUARD。

    非法值一律 ConfigError —— 防护配置写错时服务应该 not-ready，
    而不是静默退化成「不防护」（那正好是最危险的失败方式）。
    """
    raw = os.getenv("LLM_GUARD", "").strip()
    data: dict = {}
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ConfigError(f"LLM_GUARD 不是合法 JSON: {error}") from error
        if not isinstance(parsed, dict):
            raise ConfigError("LLM_GUARD 必须是 JSON 对象")
        data = parsed

    merged = {**DEFAULT_GUARD, **data}

    detection = str(merged["detection"]).strip().lower()
    if detection not in GUARD_MODES:
        raise ConfigError(f"LLM_GUARD.detection 必须是 {GUARD_MODES} 之一，实际是 {detection!r}")

    canary_action = str(merged["canary_action"]).strip().lower()
    if canary_action not in CANARY_ACTIONS:
        raise ConfigError(f"LLM_GUARD.canary_action 必须是 {CANARY_ACTIONS} 之一，实际是 {canary_action!r}")

    report_callers = merged["report_callers"]
    if not isinstance(report_callers, (list, tuple)):
        raise ConfigError("LLM_GUARD.report_callers 必须是调用方名字的数组")
    normalized: list[str] = []
    for item in report_callers:
        caller = str(item).strip().lower().replace("_", "-")
        if caller and caller not in normalized:
            normalized.append(caller)

    return GuardConfig(
        spotlight=_tier_flag(merged["spotlight"], "spotlight"),
        canary=_tier_flag(merged["canary"], "canary"),
        canary_action=canary_action,
        detection=detection,
        report_callers=tuple(normalized),
    )
