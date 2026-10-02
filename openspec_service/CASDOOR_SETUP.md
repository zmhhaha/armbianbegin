# Casdoor 配置

OpenSpec 用**两个** Casdoor 应用，分工如下（2026-10-02 起）：

| 应用 | client_id | 谁在用 |
|---|---|---|
| `panghu-suite` | `ece3f52410b046fe0952` | 13 个 oauth2-proxy 实例等老流程 |
| **`panghu-mcp`** | `315cbdaf565b82103c6f` | 标准 MCP 客户端自动授权（RFC 9728 发现 + PKCE）、`scripts/get-token.sh`、项目申请表单登录 |

两者共同要求：

- issuer：`https://auth.panghuer.top`
- jwks_uri：`https://auth.panghuer.top/.well-known/jwks` —— **注意结尾没有 `.json`**，以 discovery
  实际返回的为准（本文早先写成 `.json` 是错的）
- JWT 必须携带可信的 `email` claim：服务靠它按邮箱**精确匹配** Gitea 账号（绑定失败见
  [TROUBLESHOOTING.md](TROUBLESHOOTING.md) §1.7）
- 服务端**只校验 JWT 公钥，不需要任何 client secret**。`panghu-mcp` 是**公共客户端** ——
  2026-10-02 实测授权码 + PKCE 换 token 时**不带 secret 也返回 200**，所以服务端不再持有 Casdoor 机密

`OIDC_AUDIENCE`（在 `k8s/core.yaml` 的 ConfigMap 里）是**逗号分隔列表**：

```text
ece3f52410b046fe0952,315cbdaf565b82103c6f
```

前者是留给**未过期 JWT** 的过渡（它们在 2026-10-06 到期后即可删除），后者是 MCP 应用。服务端把
它 `split(',')` 成数组交给 jose 校验（`jose` 的 `audience` 接受 `string | string[]`），
所以**两个应用签发的 token 同时有效** —— 这也是"手工贴 JWT"与"MCP 客户端 OAuth"能并存的原因。

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
