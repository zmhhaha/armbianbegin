"""调用者身份与 collection 权限。

身份**只从凭据推导**，绝不采用请求体里的 `agent` / `collection` 字段——那些只作收窄提示。

- 每个调用者在 Vault 里持有一个令牌，由 ExternalSecret 注入为环境变量 `RAG_TOKEN_<CALLER>`；
- 令牌 → 规范调用者名（`agent-daofaziran` 的调用者名为 `daofaziran`）；
- 调用者名 → 可读/可写 collection 由服务端映射决定（CALLER_PERMISSIONS 可覆盖，默认只能读写自己的 collection）。
"""
from __future__ import annotations

import json
import os

TOKEN_PREFIX = "RAG_TOKEN_"
WILDCARD = "*"


def _token_map() -> dict[str, str]:
    """凭据 → 规范调用者名。环境变量名即身份来源，客户端无法自称。"""
    mapping: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith(TOKEN_PREFIX) and value.strip():
            caller = key[len(TOKEN_PREFIX):].strip().lower().replace("_", "-")
            if caller:
                mapping[value.strip()] = caller
    return mapping


def _permissions() -> dict[str, dict[str, list[str]]]:
    raw = os.getenv("CALLER_PERMISSIONS", "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    return {
        str(name): {"read": list(item.get("read") or []), "write": list(item.get("write") or [])}
        for name, item in parsed.items()
    }


class Identity:
    def __init__(self, caller: str, read: list[str], write: list[str]):
        self.caller = caller
        self.read = read
        self.write = write

    @property
    def role(self) -> str:
        if WILDCARD in self.read or WILDCARD in self.write:
            return "operator"
        if self.write:
            return "writer"
        return "reader"

    def allowed(self, kind: str, collection: str) -> bool:
        scope = self.read if kind == "read" else self.write
        return WILDCARD in scope or collection in scope

    def collections(self, kind: str) -> list[str]:
        return self.read if kind == "read" else self.write


def resolve(token: str) -> Identity | None:
    """令牌无效/缺失时返回 None，由调用方转成 401。"""
    caller = _token_map().get(token)
    if not caller:
        return None
    override = _permissions().get(caller) or {}
    default = [f"agent-{caller}"]
    # 注意：显式给出的空列表（如 "write": []）表示"禁止写"，不能回落到默认值
    return Identity(
        caller=caller,
        read=list(override["read"]) if "read" in override else list(default),
        write=list(override["write"]) if "write" in override else list(default),
    )
