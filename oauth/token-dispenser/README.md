# token-dispenser（已退役）：OpenSpec 的网页版 JWT 领取器

**状态：已退役，归档保留。** 这里没有任何代码被 import，也没有被部署。

## 它当年是什么

`openspec-service` 的 `GET /token`：用户浏览器打开 → 302 到 Casdoor 授权 → 回调带 `code` →
服务端用 **`panghu-suite` 的 client_id + `CASDOOR_CLIENT_SECRET`** 换 `access_token` →
把 JWT 渲染成一个带复制按钮的页面，页面里还印着用法：

```
claude mcp add --transport http openspec https://openspec.panghuer.top/mcp --header "Authorization: Bearer <token>"
codex mcp add openspec --transport streamable-http https://openspec.panghuer.top/mcp --header "Authorization: Bearer <token>"
```

`token.mjs` 是当年的完整实现（逐字保留）。注意它的 import 路径是**当年在
`openspec_service/src/` 下**的相对路径，放到这里之后已失效 —— 故意保留原样，方便整体复制回去。

## 为什么退役（2026-10-02）

它解决的是「MCP 客户端不会自己走 OAuth，所以人替它取一把长期 JWT 贴进配置」。
现在服务端已经支持 **RFC 9728 的发现链路**（PRM + 401 `WWW-Authenticate`），标准 MCP 客户端
能自己完成 OAuth 2.1：

```
① POST /mcp 无凭据            → 401 + WWW-Authenticate: Bearer resource_metadata=…
② GET  /.well-known/oauth-protected-resource/mcp
                              → authorization_servers = ["https://auth.panghuer.top"]
③ GET  Casdoor 的 AS metadata → authorization_endpoint / token_endpoint
④ 授权码 + PKCE（浏览器同意一次）→ 拿到 token
⑤ POST /mcp 带 token          → 200
```

于是「人手取 JWT 并贴进明文配置」这条路没有存在价值了 —— 它还有一个固有的安全代价：
那把 token 是**长期凭据**，会被写进各 AI 工具的配置文件里（例如 `.mcp.json`）。

设计记录见 [`../../docs/platform-mcp-auth.md`](../../docs/platform-mcp-auth.md)。

## 当时留在服务里的那一半

`token.mjs` 其实干了两件事，退役时被拆开：

| | 内容 | 去向 |
|---|---|---|
| **A** | `html(token)` —— 展示 JWT + 客户端配置命令 | **就是这里**，退役归档 |
| **B** | `?return=/project-requests` → 换 token 后渲染项目申请表单 | **留在服务里**，改名 `src/project-login.mjs`，路由从 `/token` 改成 `/project-requests/login`，并改绑新应用、去掉 `client_secret` |

B 不是「给人取 token」用的，它是项目申请网页表单的登录管道 —— 那条链路仍然需要，所以没跟着退役。

## 怎么复活

需要的话按这个顺序做：

1. **把 `token.mjs` 复制回** `openspec_service/src/`。
2. **恢复配置**：`src/config.mjs` 里加回 `casdoorClientId` / `casdoorClientSecret`
   （`process.env.CASDOOR_CLIENT_ID` / `CASDOOR_CLIENT_SECRET`）。
3. **恢复路由**：`src/server.mjs` 的 `createServer` 分支里加回
   `req.url?.split('?')[0]==='/token' && req.method==='GET'`。
4. **Casdoor 侧**：所用应用的 **Redirect URLs 必须包含 `${PUBLIC_BASE_URL}/token`**
   （当年是 `https://openspec.panghuer.top/token`）。克隆应用时最容易漏这一条。
5. **选一个应用身份**，两者行为不同：

   | 方案 | 需要 secret？ | 需要动 audience？ |
   |---|---|---|
   | 沿用 `panghu-suite`（`ece3f52410b046fe0952`） | 需要，从 Vault 注入 | **需要** —— 该 client_id 已于 2026-10-02 从 `OIDC_AUDIENCE` 移除，复活这条路线前得先把它加回去 |
   | 用 MCP 专用应用 `315cbdaf565b82103c6f` | **不需要**（2026-10-02 实测：不带 `client_secret` 也返回 200） | 需要把它的 client_id 加进 `OIDC_AUDIENCE` |

6. **别忘了那条固有代价**：复活它 = 重新开启「长期 JWT 写进各工具明文配置」这条路。
   如果只是需要一把 token 给脚本用，优先考虑 `openspec_service/scripts/get-token.sh`
   （命令行授权码流，不落地长期凭据到工具配置里）。

## 历史

退役于 2026-10-02，与 PRM / 401 挑战头上线同一轮工作。
