# 让 Casdoor 不下发第三方 token（顺带甩掉整个 User 结构）

> 起因：OpenSpec 的 MCP 要用户把 Casdoor JWT 贴进各种 AI 工具（见
> [`openspec_service/MCP_INTEGRATION.md`](../../openspec_service/MCP_INTEGRATION.md) §2），
> 实测发现那个 JWT 的 payload 里裹着 **GitHub 的 access token**。
> 本文给出根治办法，并记录改之前必须核对的东西。

## 一、改前的实测现象：不止 GitHub token

> 📌 本集群已在 **2026-09-29** 改完并验证（结果见 §八）。本节记录的是**改前**的状态 ——
> 保留下来是为了说明"为什么必须改"，以及新实例上线时怎么自查。

拿一个真实签发的 JWT 解 base64（**JWT 是 base64，不是加密**），payload 顶层有 **86 个 claim** ——
约等于把整个 User 结构原样搬了进去（确切说，是 §5.0 里那个 **75 字段的
`UserWithoutThirdIdp`**，默认格式 `JWT` 走的就是它）。其中值得警惕的：

| claim | 内容 | 风险 |
|---|---|---|
| `properties.oauth_GitHub_accessToken` | 用 GitHub 登录时，Casdoor 把 provider 的 access token 存进用户记录 | 拿到 JWT 即拿到这把 GitHub token |
| `properties.oauth_GitHub_*` | username / id / email / avatarUrl | 同上 |
| `password` | 已被 `refineUser()` 清空 | 暂无 |
| `passwordSalt` / `passwordType` | **实测非空**（salt 与哈希类型） | 配合库泄露才能利用，但没有任何理由下发 |
| `totpSecret` / `recoveryCodes` | 当前为空（未启用 2FA） | **一旦启用 2FA，密钥与恢复码会被塞进每一个 JWT** |
| `hash` / `preHash` / `lastSigninIp` 等 | 会话/审计类字段 | 不必要的信息暴露 |

前两类就是本次要解决的；第三、四类是**同一个开关的附带收益** —— 值得一并理解，因为
"以后启用 2FA 会不会把 `totpSecret` 发出去"取决于这里怎么配。

## 二、根因

1. Casdoor 在"用 GitHub 登录"时会把 provider 的 access token 存进**用户记录的 `Properties`**，
   键名形如 `oauth_GitHub_accessToken`（这也是 `oauth_GitHub_username` 那些字段的来源）。
2. 应用的 **Token format** 默认是 **`JWT`**：把**所有 User 字段**放进 token payload。
   `Properties` 是 User 的一个字段，于是它连同两边一起进了 JWT。

## 三、正解：`JWT-Custom` + 字段白名单

改应用的 **Token format = `JWT-Custom`**，再在 **Token fields** 里只勾需要的字段
（**不要勾 `Properties`**）。

> ✅ **版本前提**：本集群的 Casdoor **v3.113.0 已确认支持**（§5.0 有源码级核对）。
> 换成别的实例时按 §5.0 复核一遍；确实没有这个功能的，看 §5.4 的退路。

Casdoor 支持的四种格式（官方文档 [Token overview](https://casdoor.ai/zh/docs/token/overview/)）：

| 格式 | payload 内容 |
|---|---|
| `JWT`（默认） | **所有** User 字段 ← 现在就是这个 |
| `JWT-Empty` | 仅非空 User 字段（仍会带 `Properties`） |
| **`JWT-Custom`** | **只带你勾选的那些 User 字段** ← 正解 |
| `JWT-Standard` | 标准声明集（新版才有） |

机制（源码 `object/token_jwt.go` 的 `getClaimsCustom`）：标准声明
`iss`/`sub`/`aud`/`exp`/`nbf`/`iat`/`jti`/`tokenType`/`nonce`/`tag`/`scope` **无条件带上**，
其余按 `TokenFields` 白名单从 User 结构体按字段名反射取。
所以**不勾 `Properties`，`oauth_GitHub_*` 就再也不会出现在任何 token 里**。

## 四、改之前必须核对：谁会因为字段变少而坏掉

⚠️ **`TokenFormat` 对 access_token 与 id_token 同时生效**（官方文档：
"You cannot configure separate claims for access_token and id_token"）。
`panghu-suite` 这个应用被**所有** oauth2-proxy 实例与 OpenSpec 共用，所以字段白名单必须覆盖
它们的并集。以下依赖是**在本仓库里逐个查出来的**，不是推测：

| 消费者 | 依赖的 claim | 依据 |
|---|---|---|
| oauth2-proxy（八个人格 / hublog / txt2img / game 等） | `sub`（`userIDClaim`）、`email`（`emailClaim`） | `oauth/k8s/proxy-configmap.yaml` 第 23–24 行 |
| OpenSpec MCP | `sub`（`subject()` 缺它直接 401）、`email`（查 Gitea 用户名） | `openspec_service/src/auth.mjs` 第 4 行、`identity.mjs` 第 11 行 |
| OpenSpec MCP（校验） | `iss`、`aud`、`exp` | `auth.mjs` 第 3 行的 `jwtVerify{issuer,audience}` |

关键结论：

- **必须手动勾的只有 `Email`** —— `sub`/`iss`/`aud`/`exp` 等标准声明在 `JWT-Custom` 下无条件带；
- **没有任何消费者读 `Properties`**（OpenSpec 用 `sub`+`email`，oauth2-proxy 用 `sub`+`email`），
  所以去掉它不会破坏任何现有功能；
- `injectRequestHeaders` 里那三个头（`X-Forwarded-User` / `-Email` / `-Preferred-Username`）：
  前两个分别取自 `sub`/`email`；`preferred_username` **在当前 token 里本来就不存在**（实测），
  所以它空着是现状，不会因为这次改动变坏。

**已知坑**：issue [#4648](https://github.com/casdoor/casdoor/issues/4648) 报告 `JWT-Custom`
默认会丢 `nonce` / `scope` / `signinMethod`。本仓库的消费者都不用它们，但如果别处依赖 `scope`，
改完要额外确认。

**建议勾选的字段**（在 `Email` 之外，都是展示/授权用、非敏感）：

```text
Name, DisplayName, Email, Avatar, Id, Owner, Type, SignupApplication,
IsAdmin, Roles, Permissions, Groups
```

## 五、操作步骤

### 5.0 版本前提：本集群的 Casdoor（v3.113.0）**支持**

已按运行中版本核对（`curl -s https://auth.panghuer.top/api/get-version-info` →
`v3.113.0`，commit `8f7b4ff`）。该 commit 的源码里：

- `object/token_jwt.go` 有 `JWT-Custom` 分支，调用 `getClaimsCustom(claims, application.TokenFields, …)`；
- `object/application.go` 有 `TokenFormat string` 与 `TokenFields []string`；
- 前端 `web/src/ApplicationEditPage.js` 有 **Token format** 与 **Token fields** 两个控件。

所以**不需要升级**。若换到别的 Casdoor 实例，再按下面的办法确认一遍即可
（`JWT-Custom` 由 #2594 于 2024-01 引入，前端控件可能更晚；老版本没有字段白名单，
做任何配置都关不掉 `Properties`）：

```bash
curl -s https://auth.panghuer.top/api/get-version-info     # 任一版本都能问
```

或者看 **Token format 下拉里有没有 `JWT-Custom` 这个选项**；没有就是版本太老，直接看 5.4。

> **为什么现在会带出去**：默认格式是 `JWT`（`tokenFormat` 为空时代码会置为 `"JWT"`），
> 它走 `getClaimsWithoutThirdIdp()`，而那个结构体 **`UserWithoutThirdIdp` 有 75 个字段、
> 其中就包含 `Properties`**（连带 `PasswordSalt`、以及启用 2FA 后的 `TotpSecret`/`RecoveryCodes`）。
> 实测本集群签发的 token 有 86 个 claim —— 与此吻合。

### 5.1 UI（最省事，但控件藏在不容易找的位置）

**Applications → 选中 `panghu-suite` → 打开编辑页 → 找到 `Custom scopes` 这一项，
`Token format` 就在它下面一行，`Token fields` 再下面一行。**

⚠️ **`Token fields` 在 `Token format` 选成 `JWT-Custom` 之前是灰的**（源码里
`disabled={tokenFormat !== "JWT-Custom"}`）—— 这多半就是"找不到"的原因：先在上一行选
`JWT-Custom`，下面那个框才会亮。

然后按 §四 勾选字段（**不要勾 `Properties`**）→ 保存。

### 5.2 API（不依赖 UI 是否有控件）

Casdoor 的 update 接口要求提交**整个应用对象**，所以先读再改再回写：

```bash
AUTH="Authorization: Bearer <Casdoor 管理凭据>"
BASE=https://auth.panghuer.top

curl -s "$BASE/api/get-application?id=admin/panghu-suite" -H "$AUTH" -o app.json   # id 格式是 <owner>/<name>

jq '.tokenFormat="JWT-Custom"
    | .tokenFields=["Name","DisplayName","Email","Avatar","Id","Owner","Type",
                    "SignupApplication","IsAdmin","Roles","Permissions","Groups"]' \
   app.json > app.new.json

curl -s -X POST "$BASE/api/update-application?id=admin/panghu-suite" \
     -H "$AUTH" -H 'Content-Type: application/json' -d @app.new.json
```

改完用同一条 `get-application` **读回来确认** `tokenFields` 是数组 —— 这一步也能顺便验证
写进去的格式没被搞坏。

### 5.3 DB（API 也不方便时）

`application` 表的 `token_format` / `token_fields`（字段定义见 `object/application.go` 的
`TokenFormat` / `TokenFields []string`）。改完**必须重启 casdoor 刷新缓存** ——
`oauth/k8s/casdoor-configmap.yaml` 只有 10 行，不重启会继续用旧值。
⚠️ `token_fields` 是 `varchar(1000)` 存 JSON 数组，手写容易写坏，改完**务必用 5.2 的 get 读回验证**。

### 5.4 只有在版本真的不支持时才用到

**本集群不需要这一节**（v3.113.0 支持，见 5.0）。留着是为了换实例 / 换版本时能查。

若某个实例的 Token format 下拉里没有 `JWT-Custom`，结构性修法只有**升级** ——
`oauth/build.sh` 的 tag 本来就是参数化的：

```bash
CASDOOR_TAG=4.11.0 bash oauth/build.sh     # 具体版本按需选；注意 Docker tag 不带 v
```

> ⚠️ **tag 形状（2026-09-29 踩过）**：Casdoor 的 CI 把 release tag 的 `v` 去掉再推镜像
> （`build.yml`：`version=${GITHUB_REF_NAME#v}`，注释写明 "tag `v1.2.3` publishes `1.2.3`"）。
> 所以 **GitHub 上游是 `v4.11.0`，Docker Hub / 私有 registry 上是 `4.11.0`**。
> 写成 `v4.11.0` 时各加速源回 403/404，daemon 再 fallback 到 `registry-1.docker.io`，
> 最终报一个与真实原因毫无关系的 `Get "https://registry-1.docker.io/v2/": EOF` ——
> 该报错误导性极强，遇到先核对 tag 形状。

✅ **没有自定义补丁要处理**：曾有一个支付宝 PKCS#8 回退补丁（`oauth/casdoor_fix/`），
**已于 2026-09-29 删除** —— 该集成从未正常使用，已放弃。所以升级是纯粹的换 tag。

不想升级的话，有三条**不改 Casdoor token 逻辑**的退路（按性价比）：

| 退路 | 做法 | 效果 |
|---|---|---|
| **收窄 GitHub scope** | Casdoor → Providers → github → **Scopes** 改成 `read:user user:email` | 被下发的那把 token 价值极低（字段确实存在：`Provider.Scopes`） |
| 换掉 GitHub 登录 | 该应用不用 GitHub 登录 | 没有 provider token 可下发 |
| 接受现状 | 7 天有效期 + 只有两个人用 | 风险有限；但**启用 2FA 后 `totpSecret` 会进 token**，那时必须回来处理 |

**组织级兜底**：应用这两个字段留空时会回落到组织的
`DefaultTokenFormat` / `DefaultTokenFields`（见 `object/organization.go`），所以**两处都要看一眼**，
否则改了应用却被组织默认覆盖会很困惑。

## 六、验证

重新登录取一个新 JWT（**旧 token 到期前仍带着旧 payload**），然后**只列 key 名、不打印值**：

```bash
python3 - <<'PY'
import base64, json, os
tok = os.environ["JWT"].strip()
p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
keys = sorted(json.loads(base64.urlsafe_b64decode(p)))
print(len(keys), keys)
PY
```

期望：`properties` **不在**列表里；`sub` / `email` / `iss` / `aud` / `exp` 仍在；
claim 总数从 86 掉到二十几个（本集群实测 **23**，见 §八）。

改完请顺手验一遍**八个域名 + OpenSpec MCP**都能正常登录/调用 —— 字段白名单是全局生效的。

## 七、附带措施（不替代上面那条）

- **收窄 GitHub OAuth app 的 scope** 到最低（`read:user user:email`）：万一又被带出去，价值也低；
- 这份 JWT 已是"高价值密钥"，**别贴进聊天、日志、公开配置**（它的用途恰恰是交给各种 AI 工具）；
- 已经流出去的那把 GitHub token，去 GitHub → Settings → Applications → Authorized OAuth Apps
  撤销 Casdoor 的授权即可立刻失效。

## 八、本集群的实测结果（2026-09-29 已改并验证）

`panghu-suite` 的 Token format 已切到 `JWT-Custom` + 字段白名单，**改前/改后各取一把真实
token 对比**：

| | 改前 | 改后 |
|---|---|---|
| claim 总数 | **86** | **23** |
| `properties`（GitHub token 的家） | 有 | **已移除** |
| `properties.oauth_GitHub_*` | 有 | **已移除** |
| `password` / `passwordSalt` / `passwordType` | 有（salt 非空） | **已移除** |
| `totpSecret` / `recoveryCodes` | 有（空值） | **已移除** |
| `hash` / `preHash` / `lastSigninIp` 等 | 有 | **已移除** |
| `sub` / `email` / `iss` / `aud` / `exp` | 有 | **都在** ✅ |
| `name` / `displayName` / `roles` / `groups` | 有 | **都在** ✅ |

改后的完整 claim 集合：

```text
aud, avatar, azp, displayName, email, exp, groups, iat, id, isAdmin, iss, jti,
name, nbf, nonce, owner, permissionNames, roles, scope, signupApplication, sub,
tokenType, type
```

### 验证方式（本地解 + 端到端调）

1. **本地解 payload**（§六 那条命令）：86 → 23，危险字段全清、必需字段全在；
2. **端到端调 OpenSpec MCP**（`scripts/mcp-call.sh`，走公网 HTTPS）：
   `initialize` + `tools/list` ✅、`list_projects` ✅、`list_specs` ✅。
   其中 `list_projects` 最关键 —— 它走 `subject()`（`sub`）+ `email → Gitea 用户名`
   那条身份映射链，证明**瘦身没有打断认证**（即 §四 担心的那一点不成立）。

### 仍待人工确认的一项

`tokenFormat` 对 `panghu-suite` **全局生效**，八个人格与
hublog / txt2img / game 等代理共用这一个应用。因此应**抽一个域名实测一次登录**
（如 `daofaziran-agent.panghuer.top`）—— 需要浏览器，容器里验不了。
理论上 `email`/`sub` 都在就没问题。

### 附带收获

改完之后这把 JWT **才真正适合交给 AI 工具**：不再包含任何第三方凭据，只剩必要的身份声明。
原先的用法（贴进 Codex / Claude Code / Cursor 或对话里）等于连带交出 GitHub token，
现在最坏只暴露邮箱与头像 URL —— 这才是这个设计本来该有的样子。
