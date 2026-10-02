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
> **现状（2026-10-02 更新）**：**整条链路已上线并端到端实测通过。** 服务发布了 PRM 与 401 挑战头
> （§3.1 / §3.2），Casdoor 侧建了 MCP 专用应用（§3.3），audience 改成可多个。实测走完：
> `401 + 挑战头 → PRM → Casdoor AS metadata → 授权码 + PKCE → token(aud=新 client_id) →
> POST /mcp 200 → tools/list 返回 9 个工具`，且 **`client_secret` 不需要**。
> 这条路可用之后，**旧的「人工取长期 JWT 再贴进工具配置」路径已退役**（见 §五末），
> 服务端那部分能力归档在 `oauth/token-dispenser/`。§四的决策已落到 §3.3 / §4.2；
> DCR 那条在 4.11.0 上仍不可用（§3.4、§七）。
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
| audience | Casdoor **client_id**：`315cbdaf565b82103c6f`（`panghu-mcp`）。字段仍是逗号分隔列表、可多值，当前只列这一个 | [src/config.mjs](../openspec_service/src/config.mjs) |
| 身份映射 | `sub`（必需）+ `email` → Gitea 用户名；项目级权限由 **Gitea ACL** 决定 | [src/identity.mjs:8-11](../openspec_service/src/identity.mjs) |
| 取 token 的方式 | **客户端自己走 OAuth 2.1**（RFC 9728 发现 → Casdoor 授权码 + PKCE）；命令行用 `scripts/get-token.sh`。旧的网页版手工领取器 `/token` **已于 2026-10-02 退役** | [src/project-login.mjs](../openspec_service/src/project-login.mjs)、[../oauth/token-dispenser/](../oauth/token-dispenser/README.md) |
| Protected Resource Metadata | ✅ **已实现**（2026-10-02，`a8316f7`）：两种形状都匿名可读，见 §3.1 | [src/auth.mjs](../openspec_service/src/auth.mjs)、[src/rest.mjs](../openspec_service/src/rest.mjs) |
| 401 挑战头 | ✅ **已实现**：`/mcp` 与 REST 两侧的 401 都带 `resource_metadata`，见 §3.2 | [src/mcp.mjs](../openspec_service/src/mcp.mjs)、[src/rest.mjs](../openspec_service/src/rest.mjs) |

所以"每个 MCP 服务器要不要自建 OAuth 授权服务器"的答案是 **不要** —— Casdoor 已经覆盖了那一半。
服务侧该补的是「**发现自己该找谁授权**」那半段：它不是"从零做认证"，而是两处小改动，**目前已经补上**
（§3.1、§3.2）；「让客户端拿到 `client_id`」那一步也已落地（§3.3 预注册应用 + audience 列表化），
所以这条路现在**整条通了**。

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

### 3.3 Casdoor 侧建一个 **Agent / MCP** 应用 —— ✅ 已建（2026-10-02）

已建应用：**`panghu-mcp`**，`client_id = 315cbdaf565b82103c6f`，`category = Agent`、
`type = MCP`、`organization = Normal-User`、`grant_types` 含 `authorization_code` + `refresh_token`、
`redirect_uris = ["http://localhost:*","http://127.0.0.1:*"]`、`token_format = JWT-Custom`、
`token_fields` 含 `Email`。（它的 `token_fields` 与 `panghu-suite` **完全相同**，两者都不列 `Sub`；
而 `panghu-suite` 签出的 token **确有 `sub`** —— 说明 `sub` 是标准 claim、不依赖 `token_fields`，
所以身份绑定需要的 `sub` / `email` 两个 claim 都齐。）

三个实测结论：

- **`Category` 选 `Agent` 会自动把 `Type` 设成 `MCP`** —— 前端代码是
  `onChange: h => { l("category",h), l("type", h==="Agent" ? "MCP" : "All") }`。
  所以 **Type 下拉里看不到 `MCP` 是正常的**，不用去那儿找。
- **不需要 `client_secret`**：授权码 + PKCE 换 token 时**不带 secret 也返回 200**（实测）。
  这是关键收益 —— 桌面客户端不用分发任何密钥。
- **audience 从「只能一个」改成「可以多个」**：新应用签发的 token 其 `aud` 是新 `client_id`，而服务
  原先只认 `ece3f52410b046fe0952`。按 §4.1 的「现状」路线把 `OIDC_AUDIENCE` 改成逗号分隔列表、
  先让新旧并存过渡；**2026-10-02 当天又收敛回单个值** `315cbdaf565b82103c6f` —— 旧应用不再需要，
  去掉它也就同时关死了「人工取长期 JWT 贴进工具配置」那条路（在那之前签发的 JWT 全部失效）。
  连带改动：`src/config.mjs` 把 `oidcAudience` 拆成数组（`jose` 6.x 的 `audience` 接受
  `string | string[]`，所以 `auth.mjs` 那行不用动）、`scripts/preflight.sh` 的判据从
  「整串相等」改成「包含期望值」。

✅ **该应用当前的 Redirect URLs（2026-10-02 已确认）**：

```text
http://localhost:*
http://127.0.0.1:*
https://openspec.panghuer.top/project-requests/login     ← 项目申请表单登录用（已加入）
```

前两条给桌面 MCP 客户端（授权码 + PKCE 后回调本机），第三条给服务端的表单登录路由。
`GET /project-requests/login` 已实测能正确 302 到 Casdoor（带这个 `redirect_uri` + PKCE S256）。

### 3.4 （可选）组织级 DCR —— ❌ 本集群不可用，且启用也解决不了问题

只有当你要让**别人**用标准客户端接进来时才需要（Claude Desktop 会在首次使用时自助注册）。

**2026-10-02 实测（含一处对本文早先结论的更正）**：开关是 **`organization.dcr_policy`**
（`varchar(100)`，默认空）：

```text
built-in    → [disabled]
Normal-User → []            ← 空值 = 不启用
```

Casdoor 的 AS metadata **会公布** `registration_endpoint = /api/oauth/register`，所以规范型客户端
会去试动态注册，然后拿到：

```json
{"error":"invalid_client_metadata",
 "error_description":"dynamic client registration is disabled for this organization"}
```

> ⚠️ **更正**：本节早先写的是「4.11.0 上不存在这个开关」，**那是错的** —— 当时我用
> `column_name like '%dynamic%' or '%registration%'` 去扫，**漏了 `dcr_*` 这个命名**，把
> 「我搜不到」当成了「不存在」。列是存在的。另：4.11.0 的**前端产物里搜不到 `dcr_policy`**，
> 说明这个开关在当前版本**没有 UI 控件**，只能走 API 设置，或升级 Casdoor。

**但光打开 DCR 走不通**，原因是结构性的：DCR 每次注册发出的是**随机 client_id**，token 的
`aud` 就是它，而资源服务器**没法预先把这个随机值加进 `OIDC_AUDIENCE` 白名单**。

> ⚠️ **更正（2026-10-02，已查 tag 源码）**：本文早先写「本集群没有验证过 4.11.0 是否支持
> `resource` 参数」，并据此断言「即便打开 DCR 也走不通」——**后半句是错的**。`v4.11.0` 源码确认
> **RFC 8707 已实现**（PR #5098 于 2026-02-15 合并；v4.11.0 发布于 2026-09-26，远在其后）：
>
> - `object/token_jwt.go`：`if resource != "" { claims.Audience = []string{resource} }`
>   —— **带了 `resource` 时 `aud` 就等于该 resource URL**，不再等于 client_id；
> - `object/token_oauth.go`：`GetOAuthToken` / `GetAuthorizationCodeToken` 都带 `resource`，
>   并校验「token 请求里的 resource 必须与授权请求里的一致」；
> - `controllers/token.go`：从 query 与 body 两处读 `resource`。

所以 **DCR + RFC 8707 是一条可行的「零配置」路线**：MCP 客户端按规范会带
`resource=https://openspec.panghuer.top/mcp`，只要把该 URL 也加进 `OIDC_AUDIENCE`，
随机 client_id 就不再是障碍。DCR 的开启条件也已从源码确认：`object/oauth_dcr.go`
里 `if org.DcrPolicy == "" || org.DcrPolicy == "disabled"` 即拒绝，**非空且非 `disabled` 即启用**。

**这条路暂未采用**，两个原因：（a）DCR 等于对任何能访问 `auth.panghuer.top` 的人开放客户端注册，
是个滥用面；（b）Casdoor 关于 `resource` 透传的若干后续修复（#5294 / #5666 / #5689 / #5690 / #5744，
涉及 web 登录流、consent 流、`fastAutoSignin`、refresh_token）**未逐一确认是否已进入 v4.11.0**；
其中 #5666「consent flow drops RFC 8707 resource parameter」若不在，授权码交换会以 `invalid_grant`
失败。现阶段采用 §3.3 的预注册应用 + 客户端指定 `--client-id`
（Claude Code 实测可用的写法见 [../openspec_service/TROUBLESHOOTING.md](../openspec_service/TROUBLESHOOTING.md) §1.8）。

---

## 四、三个必须先定的决策

### 4.1 audience 用 client_id 还是 resource indicator？

| 选项 | 含义 | 影响 |
|---|---|---|
| **现状：`aud` = client_id（已采用）** | `OIDC_AUDIENCE` **只列 MCP 应用** `315cbdaf565b82103c6f`（2026-10-02 先扩成列表做过渡、当天又收敛；字段本身仍是逗号分隔、可多值） | 简单；但同一个应用签发的 token 对**所有**信任它的资源服务器都有效，无法按资源收窄。**代价是换应用就得改这份白名单** —— 这也是 DCR 单纯靠 client_id 走不通的原因（随机 client_id 无法预先列进去）；改用 `resource` 做 audience 才能解，见 §3.4 |
| RFC 8707：`aud` = MCP 资源 URL | 需要 Casdoor 侧按 resource 签发、且 `OIDC_AUDIENCE` 改成 `https://openspec.panghuer.top/mcp` | 半径更小（token 只对该资源有效）；但要改 Casdoor 应用配置 + 服务端配置，且**旧 token 会校验不过**（需过渡期） |

### 4.2 scope 与 Gitea ACL 的分工

现在**项目级权限完全由 Gitea ACL 决定**（`subject()` → Gitea 用户名 → 仓库权限）。OAuth scope 是
另一层。建议：

- **scope 只做粗粒度能力门**（`specs:read` / `specs:write` / `archive`）；
- **项目级仍归 Gitea ACL**，不在 scope 里表达 `projectId`。

否则会出现两套并行授权，排查权限问题时无法一眼判断是哪一层拒的。

### 4.3 复用 `panghu-suite` 还是新建 MCP 专用应用？

- 复用：省事，但 `panghu-suite` 被所有 oauth2-proxy 共用，改它的 scope/consent 会影响全站登录；
  而且它是**机密客户端**（旧 `token.mjs` 就要求 `CASDOOR_CLIENT_SECRET`），把这个 secret 发给桌面
  客户端等于全平台 OIDC secret 外泄。**已排除。**
- **新建（已采用，2026-10-02）**：`panghu-mcp` / `315cbdaf565b82103c6f`，scope/consent/DCR
  互不干扰，而且是**公共客户端 —— 免 secret**，详见 §3.3。代价是用户要**授权两次**
  （浏览器登录一次 + MCP 客户端授权一次）。

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

### 第二轮：audience 列表化 + 旧的手工 JWT 路径退役（2026-10-02，已上线）

```bash
# 1) Casdoor 侧建 MCP 专用应用                      ✅ 已建（见 §3.3）
# 2) 服务端 audience 改成可多个                      ✅ 已上线
# 4) 验证：走完整条 OAuth 2.1 链路                   ✅ 实测通过（见下）
# 5) 旧路径退役：GET /token（网页版 JWT 领取器）      ✅ 已删除，能力归档 oauth/token-dispenser/
```

**端到端实测记录**（用真实授权码 + PKCE 走了一遍，不是推断）：

```text
① POST /mcp 无凭据        → 401 + WWW-Authenticate: Bearer resource_metadata="…/oauth-protected-resource/mcp"
② GET  该 PRM             → 200，authorization_servers = ["https://auth.panghuer.top"]
③ GET  Casdoor AS metadata
④ authorize + PKCE        → state 校验通过，拿到 code
⑤ token 交换（不带 secret）→ 200，aud=['315cbdaf565b82103c6f']、sub、email 齐全
⑥ POST /mcp 带 token      → 200 + mcp-session-id
⑦ tools/list              → 9 个工具全部返回
```

**退役「人工取长期 JWT 再贴进工具配置」这条旧路**：

| 旧物 | 处置 |
|---|---|
| `openspec_service/src/token.mjs` | **删除**。给人取 JWT 的那半归档到 `oauth/token-dispenser/`（含原文 + README 说明依赖与复活步骤） |
| `GET /token` 路由 | **删除**，`server.mjs` 不再有该分支 |
| 项目申请表单的登录（原 `?return=/project-requests`） | **保留** —— 拆成 `src/project-login.mjs` + 新路由 `GET /project-requests/login`，改绑 MCP 专用应用、加 PKCE、**去掉 client_secret** |
| `CASDOOR_CLIENT_ID` / `CASDOOR_CLIENT_SECRET` | 前者改名 `CASDOOR_MCP_CLIENT_ID`；后者**不再注入**（已从 ExternalSecret 移除）。Vault 里的值没删，留着不影响 |
| `scripts/get-token.sh` | 重写：改绑新应用、**无需 secret**、加 PKCE、回调改 `http://localhost:39399/callback`。**它仍是命令行取 JWT 的正路** |
| 门户页 `portal/apps/tool/openspec-mcp.html`、`MCP_INTEGRATION.md`、`DEPLOY.md`、`PROJECT_REGISTRATION.md`、`TROUBLESHOOTING.md` | 同步改成新口径并记录退役 |

> ⚠️ **这次部署踩到并顺手修掉的一个坑**：`scripts/deploy.sh` 的 `--core-only` / `--skip-vault` 分支
> 只 `apply -k`，**没有 rollout restart**。而 `OIDC_*` 是通过 `envFrom(configMapRef)` 注入的，
> 环境变量只在容器启动时读一次 —— 不重启就是「apply 成功、配置没生效」。Vault 分支里那次 restart
> 只覆盖那条路径，已在 `--core-only` 分支补上。

### 第三轮：回调清理（2026-10-02）

`panghu-suite` 是**所有 13 个 oauth2-proxy 实例共用**的应用，它的 Redirect URLs 里混进了几条已经
没用的，按「逐条查实消费方」的方式清理（**27 → 24**）：

| 删除 | 依据 |
|---|---|
| `https://openspec.panghuer.top/mcp` | 旧 `get-token.sh` 用它做回调；现已改用 MCP 专用应用 + `http://localhost:39399/callback` |
| `https://openspec.panghuer.top/token` | 已退役的 `/token` 页用它 |
| `https://obsidian.panghuer.top/oauth2/callback` | obsidian 前面的 oauth2-proxy **早已删除**、路由直连 CouchDB（实测该域名返回的是 CouchDB 自己的 `WWW-Authenticate: Basic realm="administrator"`，不是 302 到 Casdoor；`obsidian` 命名空间里也没有代理） |

**保留的 24 条及依据**（清点而非猜测）：

- **12 条**与线上 12 个 oauth2-proxy Deployment 的 `--redirect-url` **逐字相同**；
- **8 条**人格域名由共享实例 `oauth2-proxy-baijiazhengming` 使用 —— 它只给
  `--whitelist-domain=.panghuer.top`、**回调按请求 Host 现生成**，所以这 8 个 host 的回调每条都在用；
- **4 条**分别是 Gitea 的 OAuth 登录源、Hermes 外层代理、Hermes 原生 OIDC、DSH 代理 ——
  前三条已用线上 302 的 `redirect_uri` 或登录页按钮实测确认，第 4 条（Hermes 原生 OIDC）按
  文档描述的两层认证保留（未直接探到，但留着无害）。

**清理结果已核对**（2026-10-02）：直接读库确认 `redirect_uris` 恰好 **24 条**、上面 3 条均不在其中，
必须保留的 24 条**逐条在位**；并复验 `hermes` / `dsh`（302 的 `redirect_uri` 未变）与 `gitea`
（登录页的 Casdoor 按钮仍在）。

> ⚠️ **改 Casdoor 应用配置的坑**：应用对象被 Casdoor **缓存在内存**里，所以
> （a）直接改数据库**必须重启 Casdoor** 才生效，否则运行时仍用旧列表；
> （b）后续任何一次从后台保存该应用，都可能把内存里的旧列表**写回库里覆盖**你的改动。
> 优先走后台 UI —— 它自己会更新缓存。
> 当时的实况：用 SQL 改但**事务没提交**，库里一条没变（`json_length` 仍是 27）。

### 仍待执行

```bash
# 回归：命令行取 JWT 的老用法仍然可用
bash ../openspec_service/scripts/get-token.sh
CASDOOR_JWT="$(cat /tmp/casdoor.jwt)" bash ../openspec_service/scripts/mcp-call.sh --check
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
| 组织设置的 **DCR 开关** | ⚠️ **更正：开关存在，是 `organization.dcr_policy`**（`varchar(100)`；`built-in`=`disabled`、`Normal-User`=空，空值即不启用）。本节早先写的「4.11.0 上不存在这个开关」**是错的** —— 当时用 `%dynamic%` / `%registration%` 扫，**漏了 `dcr_*` 命名**，把「搜不到」当成了「不存在」。另：4.11.0 前端产物里搜不到 `dcr_policy`，所以这个开关**没有 UI 控件**。即便打开也要配合 RFC 8707 的 resource audience 才行，开关判定见源码 `object/oauth_dcr.go`，详见 §3.4 |
| **Casdoor 的 RFC 8707 支持** | ✅ **v4.11.0 已实现**（2026-10-02 查 tag 源码确认，非推测）：PR #5098 于 2026-02-15 合并；`object/token_jwt.go` 在带 `resource` 时把 `aud` 设为该 resource URL。本文早先「未验证 4.11.0 是否支持 `resource`」的措辞与"打开 DCR 也走不通"的结论已一并更正，见 §3.4 |
| §3.1 的 PRM 响应 | ✅ **已实现并取得线上真实响应**（2026-10-02），见 §3.1 —— 原先标注的「规范样例」已被实测值替换 |
| Casdoor 侧的六步配置 | ✅ **已实操**：应用 `panghu-mcp` 已建（`category=Agent`、`type=MCP`），并走完了整条授权码 + PKCE。两个反直觉点已被实测确认，见 §3.3：**Type 下拉里没有 `MCP` 是正常的**（选 `Category=Agent` 会自动设成 `MCP`）；**不需要 `client_secret`** |
| **新观察：`list_projects` 的 `structuredContent` 是数组** | ⚠️ MCP schema（2025-06-18）里 `structuredContent?: { [key: string]: unknown }` 要求是**对象**，而 `src/mcp.mjs` 把 `db.visibleProjects(...)` 的返回值（**数组**）直接塞了进去 —— 其余 8 个工具都返回对象。严格按 schema 校验的客户端可能在 `list_projects` 上报错。**尚未修**：修法是包一层 `{items:...}`，但那会同时改变 `content[].text` 的载荷形状，属破坏性改动，需所有者定 |
| 旧的手工 JWT 路径 | ✅ **已退役**（2026-10-02）：`GET /token` 与 `src/token.mjs` 删除，能力归档 `oauth/token-dispenser/`；项目申请登录保留为 `GET /project-requests/login`。详见 §五 |

来源：[Casdoor as MCP Auth Provider](https://casdoor.org/docs/mcp-auth/overview/)、
[MCP auth setup](https://casdoor.org/docs/mcp-auth/setup/)、
[Third-party MCP server integration](https://casdoor.org/docs/mcp-auth/third-party-integration/)、
[MCP server overview](https://casdoor.org/docs/how-to-connect/mcp/overview/)。
