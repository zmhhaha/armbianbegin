# 平台 MCP 服务器认证设计：以 Casdoor 作为授权服务器

> 调研日期 **2026-09-29**（**2026-10-02 补实测结果**）。官方文档是按 **Casdoor v4.13.0** 读的，
> 但**本集群实际跑的是 4.11.0**（由镜像身份确认），两者有差异 —— 凡涉及版本能力的判断一律以
> 本集群实测为准，见 §七。升级实录：[../oauth/wiki/casdoor升级记录.md](../oauth/wiki/casdoor升级记录.md)。
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
> **现状（2026-10-02 更新）**：**发现链路已实现并上线**（提交 `a8316f7`）—— 服务已发布 PRM、401 带
> 挑战头，标准 MCP 客户端能自动找到 Casdoor；`§3.1` / `§3.2` 含线上实测响应。
> 仍缺**走完授权码流程的那一半**：Casdoor 侧还没有 MCP 专用应用（§3.3），而 4.11.0 上不存在 DCR
> 开关（§3.4、§七），所以客户端拿不到 `client_id`，自动流程目前到"发现"为止。三个待定决策仍未定（§四）。
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
| 取 token 的方式 | **手工复制**：浏览器 `/token` 走一次授权码，再把 JWT 贴进各工具配置（**仍在用，本次未改**） | [src/token.mjs:5-6](../openspec_service/src/token.mjs) |
| Protected Resource Metadata | ✅ **已实现**（2026-10-02，`a8316f7`）：两种形状都匿名可读，见 §3.1 | [src/auth.mjs](../openspec_service/src/auth.mjs)、[src/rest.mjs](../openspec_service/src/rest.mjs) |
| 401 挑战头 | ✅ **已实现**：`/mcp` 与 REST 两侧的 401 都带 `resource_metadata`，见 §3.2 | [src/mcp.mjs](../openspec_service/src/mcp.mjs)、[src/rest.mjs](../openspec_service/src/rest.mjs) |

所以"每个 MCP 服务器要不要自建 OAuth 授权服务器"的答案是 **不要** —— Casdoor 已经覆盖了那一半。
服务侧该补的是「**发现自己该找谁授权**」那半段：它不是"从零做认证"，而是两处小改动，**目前已经补上**
（§3.1、§3.2）；剩下的只有「让客户端拿到 `client_id`」那一步（§3.3）。

---

## 三、服务侧要做的事：两处已实现 + 一处待建 + 一处可选

### 3.1 Protected Resource Metadata（RFC 9728）—— ✅ 已实现（2026-10-02）

服务在 `authenticate` **之前**公开返回该文档，**两种形状都可匿名读取**：

```http
GET /.well-known/oauth-protected-resource        # 根形式（兼容回退）
GET /.well-known/oauth-protected-resource/mcp    # 路径插入式（401 挑战头里给的就是这个）
```

线上实测响应（2026-10-02，HTTP 200，两种形状内容一致）：

```json
{
  "resource": "https://openspec.panghuer.top/mcp",
  "authorization_servers": ["https://auth.panghuer.top"],
  "bearer_methods_supported": ["header"]
}
```

四点实现注意：

- **URL 形状按 RFC 9728 §3.1 的原文**（已取规范原文核对）：resource 带路径时，把
  `/.well-known/oauth-protected-resource` 插在 **host 与 path 之间**（原文例子：resource
  `https://resource.example.com/resource1` → `GET /.well-known/oauth-protected-resource/resource1`）。
  根形式只在 resource 不含路径时才是正解，这里一并提供作为部分客户端的兼容回退。
- **必须匿名可读**，且这不是"补一个已有路由"：改之前该路径会落到服务的鉴权中间件上返回 **401**
  （**不是 404**，也**不是 oauth2-proxy 拦的** —— 响应体是服务自己的
  `{"error":"unauthorized","message":"Bearer token required"}`）。所以隧道与 oauth2-proxy
  **不需要任何改动**，只在服务里加一个公开分支。
- **故意不声明 `scopes_supported`**。服务当前只校验 issuer + audience，不校验 scope
  （`src/auth.mjs` 的 `jwtVerify` 只传这两个参数）。声明了却不校验，只会让客户端去申请一堆
  无效 scope。等 §4.2 的 scope 门真的实现之后再加。
- 两种形状都返回 **200 且不带挑战头**；只有 401 才带。

### 3.2 401 时给出发现入口 —— ✅ 已实现（2026-10-02）

MCP 客户端是靠 401 响应头找到授权服务器的。线上实测（`POST /mcp` 不带凭据）：

```http
HTTP/2 401
www-authenticate: Bearer resource_metadata="https://openspec.panghuer.top/.well-known/oauth-protected-resource/mcp"
```

- 挑战头里给的是 **路径插入式** 那个地址（与 §3.1 的 RFC 依据一致），**不是**原先草案里的根形式。
- REST 侧的 401（如 `GET /v1/projects`）也带上同一个头 —— 两处 catch（`src/mcp.mjs`、
  `src/rest.mjs`）各加一行。
- **只加响应头**：状态码与 body 都不变，所以手工贴 JWT 的老用法完全不受影响；也没有触碰
  `src/mcp.mjs` 里「未知方法必须返回 200、绝不能 404」那条 Codex/RMCP 约束。

### 3.3 Casdoor 侧建一个 **Agent / MCP** 应用 —— ⏳ 待建（这一步才决定 audience）

按 §1.1 的六步配置（custom scopes / consent / grant types）。注意：**现有 `panghu-suite` 是
Default 应用**，它的 TokenFormat 已被改成 `JWT-Custom` + 字段白名单（含 `sub`/`email`，对现在
的校验是够的），但**只有 Agent/MCP 类型才能配 custom scopes 与 consent**。

⚠️ **这一步是唯一会动到存量 token 的地方**：新应用签发的 token 其 `aud` 是新应用的 client_id，
而服务当前只接受**一个** audience（`config.mjs:17` 的单值）。要么改 `OIDC_AUDIENCE`（老 token
立刻全部 401，见 [../openspec_service/TROUBLESHOOTING.md](../openspec_service/TROUBLESHOOTING.md) §1.2），
要么把 audience 改成列表让新旧并存 —— 后者只需改 `config.mjs:17` 一行（`jose` 6.x 的
`audience` 接受 `string | string[]`），**但要同步改 `scripts/preflight.sh` 的整串比对**，
否则它会误报失败。

### 3.4 （可选）打开组织级 DCR —— ⏳ 可选，但 **4.11.0 上不存在这个开关**

只有当你要让**别人**用标准客户端接进来时才需要（Claude Desktop 会在首次使用时自助注册）。
自己用的话可以先不开。

⚠️ **2026-10-02 实测：本集群的 4.11.0 没有这个开关。** 全库扫
`column_name like '%dynamic%' or '%registration%'` 只命中 `application.registration_access_token`
（RFC 7592 的管理令牌，说明 DCR 的**端点侧**在），`organization` 表只有
`enable_exclusive_signin` / `enable_soft_deletion` / `enable_tour` 三个 `enable*` 列，
前端产物里也搜不到 "Dynamic Client Registration" 文案。
**所以"在组织设置里打开 DCR"这条在当前版本上无法执行** —— 要么升级 Casdoor，要么走 §3.3 的
预注册应用路线。

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

### 已执行（2026-10-02，提交 `a8316f7`，已上线）

```bash
# 2) 服务端：/.well-known/oauth-protected-resource（§3.1）   ✅ 已实现
# 3) 服务端：401 加 WWW-Authenticate 挑战头（§3.2）          ✅ 已实现
```

上线与验收实录：`bash openspec_service/scripts/build.sh` → `kubectl -n openspec rollout restart
deploy/openspec-service`；验收 = 两种 PRM 形状匿名可读（200）、`POST /mcp` 无凭据返回 401 且带
挑战头、REST 侧 401 同样带头、`mcp-call.sh --check` 退出码 0（手工路线回归）。
测试：`node --test` 25/25 通过（新增 `test/mcp-metadata.test.mjs` 6 条）。

> ⚠️ **回退锚点**：上线前先把当时的线上镜像按 digest 固定成 `openspec-service:pre-prm`。
> 该 Deployment 用 `:latest` + `imagePullPolicy: Always`，**`kubectl rollout undo` 无效**
> （它会重新拉 `latest`，也就是新代码）。回退必须显式指版本：
> `kubectl -n openspec set image deploy/openspec-service api=<registry>/openspec-service:<不可变 tag>`
> —— 所以**每次构建都应同时推一个不可变 tag**（本次是 `a8316f7`）。

### 仍待执行

```bash
# 0) 确认当前实现没被改坏：现有手工流程仍然可用（本次已跑通）
CASDOOR_JWT="<Casdoor JWT>" bash ../openspec_service/scripts/mcp-call.sh --check

# 1) Casdoor 侧：新建 Agent/MCP 应用 + custom scopes + consent
#    记下它的 client_id；确认它签发的 token 里仍有 sub 与 email（JWT-Custom + TokenFields）
#    ⚠️ 同时决定 audience 怎么办（见 §3.3）；DCR 那条在 4.11.0 上做不了（见 §3.4）

# 4) 验证（用能走 OAuth 2.1 的客户端，例如 Claude Desktop）
#    期望：客户端自动发现 auth.panghuer.top → 拉起授权 → 回来能 list_projects
#    现状：只能走到「发现」这一步 —— 还没有 client_id，授权码流程走不完
curl -s https://openspec.panghuer.top/.well-known/oauth-protected-resource | python3 -m json.tool
curl -s -D - -o /dev/null -X POST https://openspec.panghuer.top/mcp \
  -H 'content-type: application/json' -d '{}' | grep -i www-authenticate

# 5) 回归：现有手工贴 JWT 的用法不能坏（[../openspec_service/MCP_INTEGRATION.md](../openspec_service/MCP_INTEGRATION.md) §3 的命令仍应通过）
```

> 第 4 步原先写的是 `curl -sI ... /mcp`（HEAD）—— 那条**验证不了挑战头**：`server.mjs` 只把
> `POST`/`GET` 路由给 `mcpHandler`，HEAD 不会走那条路。已改成上面的 POST 形式。

---

## 六、可以先做的零代码一步

因为 OpenSpec 已经信任 Casdoor，**现在就能**在 Casdoor 后台 **Servers** 页把
`https://openspec.panghuer.top/mcp` 登记为外部 MCP 服务器，选中应用后点 **Get access token**
自动填 token —— 不必再手工复制粘贴。这条与后面的 OAuth 2.1 改造不冲突，可以先用来省手。

（2026-10-02 补：4.11.0 的前端产物里确实有 `ServerListPage` / `ServerEditPage` /
`ServerStorePage`，以及 `"MCP Servers"` / `"MCP Store"` / `"MCP Scan"` 文案，所以这一步在本集群
版本上是有依据的。但**它不解决"客户端自动发现"** —— 那只是把 token 换个地方存，别把它当成
OAuth 2.1 改造已经做完。）

---

## 七、未验证项与实测更正（诚实记录）

| 项 | 状态 |
|---|---|
| 本集群 Casdoor 的**确切版本** | ✅ **`4.11.0`**（2026-10-02 由镜像身份三方确认：registry 里 `casdoor:4.11.0` 的 manifest digest `073c0e22…` = 运行中容器的 imageID，且该镜像来自上游 `casbin/casdoor:4.11.0`）。**不是本文抬头原先写的 4.13.0。** 另更正一处：`/api/get-version-info` 用**有效但非管理员**的 token 也返回 `Unauthorized operation` —— 它要的是管理员身份，不只是"需要鉴权" |
| 组织设置的 **DCR 开关** | ❌ **4.11.0 上没有这个开关**：全库只有 `application.registration_access_token` 一个相关列，`organization` 的 `enable*` 只有 `enable_exclusive_signin` / `enable_soft_deletion` / `enable_tour`，前端也搜不到对应文案。DCR 的端点侧存在（`/api/oauth/register`，空 body → 400） |
| §3.1 的 PRM 响应 | ✅ **已实现并取得线上真实响应**（2026-10-02），见 §3.1 —— 原先标注的"规范样例"已被实测值替换 |
| Casdoor 侧的六步配置 | 🟡 **能力存在、未实操**：4.11.0 的前端产物里已有 `AgentListPage` / `AgentEditPage`、`ConsentPage`、`ServerListPage` / `ServerEditPage` / `ServerStorePage`，以及 `"MCP"` / `"MCP Servers"` / `"MCP Store"` / `"Consents"` 文案，应用编辑页里也有 `category==="Agent"` 分支 ⇒ §3.3 那条路在 4.11.0 上**大概率可行**。但 **`Type = MCP` 是否真的作为选项出现**没有逐项渲染确认 |

来源：[Casdoor as MCP Auth Provider](https://casdoor.org/docs/mcp-auth/overview/)、
[MCP auth setup](https://casdoor.org/docs/mcp-auth/setup/)、
[Third-party MCP server integration](https://casdoor.org/docs/mcp-auth/third-party-integration/)、
[MCP server overview](https://casdoor.org/docs/how-to-connect/mcp/overview/)。
