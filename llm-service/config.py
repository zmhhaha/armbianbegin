"""别名路由配置。

只读取 ConfigMap 提供的非敏感配置（provider、上游 base URL、模型别名、默认参数、超时、重试）。
凭据一律通过 api_key_env 指向的环境变量读取（由 Vault ExternalSecret 注入），配置文件里不允许内嵌凭据。
"""
from __future__ import annotations

import json
import os
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

    @property
    def policy(self) -> dict:
        return TIERS[self.tier]

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "").strip()


def _alias_from(name: str, item: dict) -> Alias:
    missing = [key for key in ("provider", "base_url", "model", "api_key_env") if not item.get(key)]
    if missing:
        raise ConfigError(f"别名 {name} 缺少字段: {', '.join(missing)}")
    if any("key" in key.lower() or key.lower().endswith("secret") for key in item if key != "api_key_env"):
        raise ConfigError(f"别名 {name} 不能内嵌凭据，只能通过 api_key_env 引用")
    tier = str(item.get("tier") or DEFAULT_TIER).strip().lower()
    if tier not in TIERS:
        raise ConfigError(f"别名 {name} 的 tier={tier} 未定义，可选值：{', '.join(TIERS)}")
    return Alias(
        name=name,
        provider=item["provider"],
        base_url=item["base_url"],
        model=item["model"],
        api_key_env=item["api_key_env"],
        timeout_seconds=float(item.get("timeout_seconds", 60)),
        max_retries=int(item.get("max_retries", 2)),
        defaults=dict(item.get("defaults") or {}),
        tier=tier,
    )


def load_config() -> tuple[dict[str, Alias], float]:
    """返回 (别名表, 每调用方每分钟请求上限)。"""
    inline = os.getenv("LLM_ALIASES", "").strip()
    path = os.getenv("LLM_CONFIG_FILE", "").strip()
    if inline:
        data = json.loads(inline)
    elif path:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        raise ConfigError("LLM_ALIASES 或 LLM_CONFIG_FILE 未配置")

    aliases = {name: _alias_from(name, item) for name, item in (data.get("aliases") or {}).items()}
    if not aliases:
        raise ConfigError("未配置任何模型别名")

    limits = data.get("limits") or {}
    return aliases, float(limits.get("requests_per_minute_per_caller", 60))


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
