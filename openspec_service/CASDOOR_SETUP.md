# Casdoor 配置

OpenSpec 用**两个** Casdoor 应用，分工如下（2026-10-02 起）：

| 应用 | client_id | 谁在用 | 是否为 OpenSpec 接受的 audience |
|---|---|---|---|
| `panghu-suite` | `ece3f52410b046fe0952` | 13 个 oauth2-proxy 实例等老流程 | ❌ 已于 2026-10-02 从 `OIDC_AUDIENCE` 移除 |
| **`panghu-mcp`** | `315cbdaf565b82103c6f` | 标准 MCP 客户端自动授权（RFC 9728 发现 + PKCE）、`scripts/get-token.sh`、项目申请表单登录 | ✅ 唯一 |

两者共同要求：

- issuer：`https://auth.panghuer.top`
- jwks_uri：`https://auth.panghuer.top/.well-known/jwks` —— **注意结尾没有 `.json`**，以 discovery
  实际返回的为准（本文早先写成 `.json` 是错的）
- JWT 必须携带可信的 `email` claim：服务靠它按邮箱**精确匹配** Gitea 账号（绑定失败见
  [TROUBLESHOOTING.md](TROUBLESHOOTING.md) §1.7）
- 服务端**只校验 JWT 公钥，不需要任何 client secret**。`panghu-mcp` 是**公共客户端** ——
  2026-10-02 实测授权码 + PKCE 换 token 时**不带 secret 也返回 200**，所以服务端不再持有 Casdoor 机密

`OIDC_AUDIENCE`（在 `k8s/core.yaml` 的 ConfigMap 里）必须**同时**列两个值：

```text
315cbdaf565b82103c6f,https://openspec.panghuer.top/mcp
```

两者来源不同 —— **同一个应用签发的 token，其 `aud` 取决于客户端有没有带 `resource` 参数**：

| 取值 | 什么时候出现 | 谁 |
|---|---|---|
| `https://openspec.panghuer.top/mcp` | 客户端带了 `resource`（MCP 规范要求），Casdoor 照 **RFC 8707** 把 `aud` 设成该 URL | Claude Code 等标准 MCP 客户端（**实测就是这种**） |
| `315cbdaf565b82103c6f` | 不带 `resource`，`aud` = 应用的 client_id | `scripts/get-token.sh`、项目申请表单登录 |

⚠️ **少任一个都会有一类客户端静默 401**：只配 client_id → MCP 客户端表现为「浏览器授权成功、
但状态一直 `needs-auth`」（它其实已经拿到 token，只是 `aud` 不被接受）；只配 resource URL →
命令行与表单登录失效。

⚠️ **2026-10-02 起 `panghu-suite` 的 `ece3f52410b046fe0952` 已从该值中移除** —— 在该时点**之前签发的
JWT 全部失效**（包括各工具配置里手工贴的旧 token），用 `scripts/get-token.sh` 重新取即可。
`panghu-suite` 仍在服务 oauth2-proxy 的**浏览器会话**，那类会话不经过本服务的 JWT 校验，不受影响。

服务端把这个字段 `split(',')` 后交给 jose 校验（`audience` 接受 `string | string[]`），
所以将来要再并存别的应用，加一个值即可，不用改代码。

回调地址：

- **`panghu-mcp`**：`http://localhost:*`、`http://127.0.0.1:*`（桌面 MCP 客户端），
  以及 `https://openspec.panghuer.top/project-requests/login`（服务端表单登录路由）
- **`panghu-suite`**：各类 oauth2-proxy 回调 + Gitea / Hermes / DSH 的回调，共 **24 条**。
  ⚠️ **它的改动会影响全站登录**，动手前必须逐条查实消费方；2026-10-02 已清理掉 3 条失效的，
  清单与依据见 [`../docs/platform-mcp-auth.md`](../docs/platform-mcp-auth.md) §五

⚠️ **改 Casdoor 应用配置的坑**：应用对象被 Casdoor **缓存在内存**里 —— 直接改数据库必须
**重启 Casdoor** 才生效，而且后续任何一次从后台保存该应用，都可能把内存里的旧列表**写回库里
覆盖**你的改动。**优先走后台 UI**，它自己会更新缓存。

验证：登录 Casdoor 拿到 JWT 后运行 `scripts/preflight.sh --jwt <JWT>`，它会检查 `aud`、`email`、
`sub` 是否满足要求。命令行取 JWT 用 `scripts/get-token.sh`。

> 旧的「网页版 JWT 领取器」`GET /token` 已于 2026-10-02 退役，代码与复活步骤归档在
> [`../oauth/token-dispenser/`](../oauth/token-dispenser/README.md)。
