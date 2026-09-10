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
# 允许透传的有界非敏感生成参数
ALLOWED_PARAMS = ("temperature", "top_p", "max_tokens", "stop", "presence_penalty", "frequency_penalty")


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
    fallback: tuple[str, ...] = ()
    defaults: dict = field(default_factory=dict)

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
    return Alias(
        name=name,
        provider=item["provider"],
        base_url=item["base_url"],
        model=item["model"],
        api_key_env=item["api_key_env"],
        timeout_seconds=float(item.get("timeout_seconds", 60)),
        max_retries=int(item.get("max_retries", 2)),
        fallback=tuple(item.get("fallback") or ()),
        defaults=dict(item.get("defaults") or {}),
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

    for alias in aliases.values():
        for target in alias.fallback:
            if target not in aliases:
                raise ConfigError(f"别名 {alias.name} 的 fallback {target} 未定义")

    limits = data.get("limits") or {}
    return aliases, float(limits.get("requests_per_minute_per_caller", 60))
