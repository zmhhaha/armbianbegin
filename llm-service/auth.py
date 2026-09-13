"""调用方身份：**只从凭据推导**。

- 每个调用方在 Vault 里持有一个专属令牌，由 ExternalSecret 注入为环境变量 `LLM_TOKEN_<CALLER>`；
- **变量名即身份来源**，客户端无法自称 —— 请求头里的 `X-Caller` 之类一律不采信；
- 令牌 → 规范调用者名（`LLM_TOKEN_ZHOUGONGJIEMENG` 的调用者名为 `zhougongjiemeng`）。

与 `rag-service/auth.py` 同一套约定，两个服务的令牌命名规则刻意保持一致：
换个服务读代码时不用重新理解一遍。
"""
from __future__ import annotations

import os

TOKEN_PREFIX = "LLM_TOKEN_"


def token_map() -> dict[str, str]:
    """凭据 → 规范调用者名。环境变量名即身份来源。"""
    mapping: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith(TOKEN_PREFIX) and value.strip():
            caller = key[len(TOKEN_PREFIX):].strip().lower().replace("_", "-")
            if caller:
                mapping[value.strip()] = caller
    return mapping


def resolve(token: str) -> str | None:
    """令牌缺失或无效时返回 None，由调用方转成 401。"""
    if not token:
        return None
    return token_map().get(token)
