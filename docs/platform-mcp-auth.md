# 平台 MCP 服务器认证设计：以 Casdoor 作为授权服务器

> 调研日期 **2026-09-29**，针对 **Casdoor v4.13.0**（本集群已从 v3.113.0 升级到 v4.x，
> 实录见 [../oauth/wiki/casdoor升级记录.md](../oauth/wiki/casdoor升级记录.md)）。
>
> **这是平台级设计，不是某一个服务的私事**：本集群以后新增的 MCP 服务器都该照同一套认证口径做，
> 免得每个服务各写一遍 OAuth 2.1。**OpenSpec 的 MCP 是当前唯一的落地实例**，所以本文用它当参考实现
> （§二）。
>
> **结论先行**：MCP 规范要求服务器侧实现 OAuth 2.1，而 **Casdoor 已经把授权服务器那一半做完了**
> （RFC 8414 metadata / OIDC discovery / 7591 DCR / PKCE / 8707 resource indicators / JWKS +
> consent + custom scopes）—— 平台侧不需要自建授权服务器，只需让每个 MCP 服务器**发布
> Protected Resource Metadata 指向 Casdoor** 并校验它签发的 JWT。
>
> 现状：OpenSpec 已经在做 JWT 校验与身份映射，缺的是**让标准 MCP 客户端自助完成 OAuth 2.1** 的
> 三处实现（§三）与三个待定决策（§四）。
>
> 相关：[../openspec_service/MCP_INTEGRATION.md](../openspec_service/MCP_INTEGRATION.md)（OpenSpec 的工具清单与现有接入方式）、
> [../openspec_service/MULTI_TENANCY.md](../openspec_service/MULTI_TENANCY.md)（项目隔离）、
> [../oauth/wiki/casdoor不下发第三方token.md](../oauth/wiki/casdoor不下发第三方token.md)（JWT 字段白名单）。

---

## 一、Casdoor 侧有两块 MCP 能力（容易混，先分清）

### 1.1 Casdoor 作为 **MCP 的授权服务器**（对本文最重要的那块）

MCP 规范把**授权服务器**与**资源服务器**分开，并要求服务器侧实现 OAuth 2.1。Casdoor 的定位是
"这些基础设施你都不用自己造"：把 MCP 服务器的 **Protected Resource Metadata** 指向 Casdoor 即可。

| 规范 | 能力 | 本集群实测 |
|---|---|---|
| RFC 8414 | Authorization Server Metadata：`/.well-known/oauth-authorization-server` | ✅ 200 |
| OIDC Discovery | `/.well-known/openid-configuration` | ✅ 200 |
| RFC 7517 | JWKS：`/.well-known/jwks`（验签用） | ✅ 早就在用 |
| **RFC 7591** | **动态客户端注册（DCR）**：`POST /api/oauth/register`；开关在**组织设置**（不是应用设置）的 *Enable Dynamic Client Registration* | ✅ 端点存在（空 body → 400，说明路由已实现；**开关是否打开未验证**） |
| RFC 7636 | PKCE（授权流程内建） | — |
| RFC 8707 | Resource Indicators（可签发受众受限的 token） | — |
| — | consent 屏（Always / Once / Never）、custom scopes（`resource:action` 命名） | — |

**接入方向是反的**：不是 Casdoor 来连你的 MCP，而是**你的 MCP 服务器发布 Protected Resource
Metadata 指向 Casdoor**，然后自己校验 JWT（JWKS + audience + scope）。

官方 `mcp-auth/setup` 的六步（Casdoor 侧）：

1. 建应用：**Category = Agent** → **Type = MCP**（这一步才解锁 custom scope 配置）
2. Redirect URIs：开发期加 `http://localhost:*`、`http://127.0.0.1:*`；生产加
   `https://<mcp-server>/oauth/callback`
3. Grant types：勾 `authorization_code` + `refresh_token`
4. Custom Scopes：按 `resource:action` 定义（如 `specs:read`、`specs:write`）
5. Consent Policy：敏感能力建议 `Always` 或 `Once`
6. （可选）组织设置里打开 **DCR** —— Claude Desktop 这类客户端首次使用会自助注册

### 1.2 Casdoor **自己的** MCP server（以及它能当 MCP 客户端）

- 端点 `/api/mcp`，JSON-RPC 2.0，`protocolVersion` `2024-11-05`；用途是**管理 Casdoor 资源**
  （应用、用户…），不必走 REST。
- **本集群实测**：无凭据 `initialize` 成功 →
  `{"serverInfo":{"name":"Casdoor MCP Server","version":"1.0.0"}}`。
- 后台多了 **Servers** 页，可登记**外部** MCP 服务器（字段：URL / Application / Token / Tools，
  工具可逐个 allowed·blocked）。若外部服务器信任 Casdoor 作为 OAuth 提供方，
  **不必手工粘 token**：选中 Application 后点 **Get access token**，Casdoor 会为当前登录用户签发
  一个 token 并自动填入。

---

## 二、参考实现：OpenSpec 这个 MCP 服务器现在的样子

（它是本集群目前**唯一**的 MCP 服务器，也是以后新服务的参照。逐条有代码依据。）

| 能力 | 现状 | 依据 |
|---|---|---|
| 校验 Casdoor 签发的 JWT | ✅ `jwtVerify{issuer, audience}` + 远程 JWKS | [src/auth.mjs:3](../openspec_service/src/auth.mjs) |
| audience | 固定为 Casdoor **client_id**（默认 `ece3f52410b046fe0952`） | [src/config.mjs:17](../openspec_service/src/config.mjs) |
| 身份映射 | `sub`（必需）+ `email` → Gitea 用户名；项目级权限由 **Gitea ACL** 决定 | [src/identity.mjs:8-11](../openspec_service/src/identity.mjs) |
| 取 token 的方式 | **手工复制**：浏览器 `/token` 走一次授权码，再把 JWT 贴进各工具配置 | [src/token.mjs:5-6](../openspec_service/src/token.mjs) |
| Protected Resource Metadata | ❌ 没有（全仓库无 `oauth-protected-resource`） | — |
| 401 挑战头 | ❌ 只有 `{"error":"unauthorized"}`，无 `WWW-Authenticate` | [src/errors.mjs:2](../openspec_service/src/errors.mjs) |

所以"每个 MCP 服务器要不要自建 OAuth 授权服务器"的答案是 **不要** —— Casdoor 已经覆盖了那一半，
服务侧只需补**发现自己该找谁授权**的那半段（§三），而不是从零做认证。

---

## 三、缺口：三处实现 + 一处可选

### 3.1 Protected Resource Metadata（RFC 9728）

```http
GET /.well-known/oauth-protected-resource
```

```json
{
  "resource": "https://openspec.panghuer.top/mcp",
  "authorization_servers": ["https://auth.panghuer.top"],
  "scopes_supported": ["specs:read", "specs:write", "changes:write", "archive"]
}
```

> ⚠️ 上面的 JSON 是**规范样例**，不是我实测的响应（本仓库尚未实现该端点）。

### 3.2 401 时给出发现入口

MCP 客户端是靠 401 响应头找到授权服务器的：

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer resource_metadata="https://openspec.panghuer.top/.well-known/oauth-protected-resource"
```

### 3.3 Casdoor 侧建一个 **Agent / MCP** 应用

按 §1.1 的六步配置（custom scopes / consent / grant types）。注意：**现有 `panghu-suite` 是
Default 应用**，它的 TokenFormat 已被改成 `JWT-Custom` + 字段白名单（含 `sub`/`email`，对现在
的校验是够的），但**只有 Agent/MCP 类型才能配 custom scopes 与 consent**。

### 3.4 （可选）打开组织级 DCR

只有当你要让**别人**用标准客户端接进来时才需要（Claude Desktop 会在首次使用时自助注册）。
自己用的话可以先不开。

---

## 四、三个必须先定的决策

### 4.1 audience 用 client_id 还是 resource indicator？

| 选项 | 含义 | 影响 |
|---|---|---|
| 现状：`aud` = client_id | `OIDC_AUDIENCE` 固定为 `ece3f52410b046fe0952` | 简单；但同一个应用签发的 token 对**所有**信任它的资源服务器都有效，无法按资源收窄 |
| RFC 8707：`aud` = MCP 资源 URL | 需要 Casdoor 侧按 resource 签发、且 `OIDC_AUDIENCE` 改成 `https://openspec.panghuer.top/mcp` | 半径更小（token 只对该资源有效）；但要改 Casdoor 应用配置 + 服务端配置，且**旧 token 会校验不过**（需过渡期） |

### 4.2 scope 与 Gitea ACL 的分工

现在**项目级权限完全由 Gitea ACL 决定**（`subject()` → Gitea 用户名 → 仓库权限）。OAuth scope 是
另一层。建议：

- **scope 只做粗粒度能力门**（`specs:read` / `specs:write` / `archive`）；
- **项目级仍归 Gitea ACL**，不在 scope 里表达 `projectId`。

否则会出现两套并行授权，排查权限问题时无法一眼判断是哪一层拒的。

### 4.3 复用 `panghu-suite` 还是新建 MCP 专用应用？

- 复用：省事，但 `panghu-suite` 被所有 oauth2-proxy 共用，改它的 scope/consent 会影响全站登录；
- 新建（推荐）：MCP 专用应用，scope/consent/DCR 互不干扰；代价是用户要**授权两次**
  （浏览器登录一次 + MCP 客户端授权一次），且要给它配独立的 `sub`/`email` 字段白名单。

---

## 五、实施清单（真要动手时照这个走）

```bash
# 0) 先确认当前实现没被改坏：现有手工流程仍然可用
CASDOOR_JWT="$(cat /workspace/.openspec.jwt)" bash ../openspec_service/scripts/mcp-call.sh --check

# 1) Casdoor 侧：新建 Agent/MCP 应用 + custom scopes + consent（+ 可选 DCR）
#    记下它的 client_id；确认它签发的 token 里仍有 sub 与 email（JWT-Custom + TokenFields）

# 2) 服务端：新增 /.well-known/oauth-protected-resource（§3.1 的 JSON，resource 用 MCP 地址）
# 3) 服务端：401 响应加 WWW-Authenticate 挑战头（§3.2）

# 4) 验证（用能走 OAuth 2.1 的客户端，例如 Claude Desktop）
#    期望：客户端自动发现 auth.panghuer.top → 拉起授权 → 回来能 list_projects
curl -s https://openspec.panghuer.top/.well-known/oauth-protected-resource | python3 -m json.tool
curl -sI https://openspec.panghuer.top/mcp | grep -i www-authenticate

# 5) 回归：现有手工贴 JWT 的用法不能坏（[../openspec_service/MCP_INTEGRATION.md](../openspec_service/MCP_INTEGRATION.md) §3 的命令仍应通过）
```

---

## 六、可以先做的零代码一步

因为 OpenSpec 已经信任 Casdoor，**现在就能**在 Casdoor 后台 **Servers** 页把
`https://openspec.panghuer.top/mcp` 登记为外部 MCP 服务器，选中应用后点 **Get access token**
自动填 token —— 不必再手工复制粘贴。这条与后面的 OAuth 2.1 改造不冲突，可以先用来省手。

---

## 七、未验证项（诚实记录）

| 项 | 状态 |
|---|---|
| 本集群 Casdoor 的**确切版本** | ❓ 升级后 `/api/get-version-info` **需要鉴权**（v3.113.0 时是公开的），我这边查不到；需从后台 System Info 页确认。仓库里 `CASDOOR_TAG` 默认仍是 `4.11.0`，而文档最新是 `4.13.0` |
| 组织设置的 **DCR 开关**是否已打开 | ❓ 只确认了 `/api/oauth/register` 路由存在（空 body → 400） |
| §3.1 的 PRM 响应 | ❓ 规范样例，本仓库未实现 |
| Casdoor 侧的六步配置 | ❓ 来自官方文档（`mcp-auth/setup`），未在本集群实操 |

来源：[Casdoor as MCP Auth Provider](https://casdoor.org/docs/mcp-auth/overview/)、
[MCP auth setup](https://casdoor.org/docs/mcp-auth/setup/)、
[Third-party MCP server integration](https://casdoor.org/docs/mcp-auth/third-party-integration/)、
[MCP server overview](https://casdoor.org/docs/how-to-connect/mcp/overview/)。
