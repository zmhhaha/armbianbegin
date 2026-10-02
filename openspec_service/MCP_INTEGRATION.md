# OpenSpec MCP 接入说明

让 Codex、Claude Code、Cursor 等 AI 编程工具直接读写你的 OpenSpec 规格库。
OpenSpec Service 对外提供**一个远程 MCP server**，复用 Casdoor JWT 认证与 Gitea 权限，
AI 工具只需"加一个远程 MCP"即可，不需要在本地装任何 OpenSpec 环境。

---

## 访问范围

这个服务**只给所有者和一位朋友两个人用**，不是开放平台：

- 不提供自助注册，没有公开门户页，也没有面向第三方应用的门户集成。
- 能登录的就是 Casdoor `panghu-suite` 应用允许的那两个账号；在此之上再用 Gitea 仓库 ACL 收窄到项目级。
- 项目登记走 `/project-requests` 表单 → Gitea Issue → 管理员加 `status:approved` 审批
  （见 [PROJECT_REQUEST_APPROVAL.md](PROJECT_REQUEST_APPROVAL.md)），不靠门户自助开通。
- ~~`/token` 页面~~ **已于 2026-10-02 退役**：它当年给这些账号签发长期 JWT、让人贴进 AI 工具配置，
  现在标准 MCP 客户端自己走 OAuth 2.1 授权（见 §2），不再需要人工取 JWT。
  服务端那部分代码归档在 [`../oauth/token-dispenser/README.md`](../oauth/token-dispenser/README.md)。
  项目申请表单的登录**没有**跟着退役 —— 它拆出来成了 `GET /project-requests/login`，并改绑 MCP 专用应用。

因此原计划里的 `add-project-portal` 变更（同源门户页、OAuth session cookie/PKCE、脚本 Job 运行器）
**已明确不做**，不再排期。多租户隔离能力仍由服务端强制（见 [MULTI_TENANCY.md](MULTI_TENANCY.md)），
只是没有对外界面。

---

## 1. 连接信息

| 项 | 值 |
|---|---|
| MCP 地址 | `https://openspec.panghuer.top/mcp` |
| 传输 | streamable HTTP（协议版本 `2025-06-18`） |
| 认证（推荐） | 客户端自己走 **OAuth 2.1**：撞 `POST /mcp` 拿到 401 + `WWW-Authenticate` 后自动发现并授权，**不需要人工配任何 header** |
| 认证（兜底） | `Authorization: Bearer <Casdoor JWT>` —— 只给不支持 OAuth 发现的客户端或命令行用（见 §2.2） |
| 项目边界 | 服务端强制，客户端只传 `projectId`（UUID） |

> **MCP 认证的总体设计**（Casdoor 侧的两块 MCP 能力、平台侧只需补什么、以本服务为参考实现、
> 以及三个待定决策）：见 [../docs/platform-mcp-auth.md](../docs/platform-mcp-auth.md)。
> 其中「发现链路」已于 2026-10-02 上线并端到端实测通过（PRM + 401 挑战头），该文档有完整实录。

## 2. 认证：优先让客户端自己走 OAuth

> ⚠️ **只有在你要手工取 JWT 时才需要读这段。** JWT 是明文可解的（它只是 base64）—— payload 里
> 可能带着 Casdoor 记在用户记录 `Properties` 上的第三方凭据（用 GitHub 登录时就是
> **`oauth_GitHub_accessToken`**），而默认的 `JWT` token 格式还会把**整个 User 结构**塞进去。
> 贴进聊天、日志或公开配置，等于连带交出这些东西。
>
> 想从根上让 Casdoor 不下发：见
> [`../oauth/wiki/casdoor不下发第三方token.md`](../oauth/wiki/casdoor不下发第三方token.md)
> —— 把应用的 Token format 改成 `JWT-Custom`、只勾必需字段（别勾 `Properties`）即可。
> **这也是优先走 OAuth 的理由之一：长期凭据根本不用写进任何配置文件。**

### 2.1 推荐：让 MCP 客户端自动授权（不需要取 JWT）

支持 MCP OAuth 的客户端只需要填 MCP 地址，其余自己完成：

```text
① POST https://openspec.panghuer.top/mcp（无凭据）
   → 401 + WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource/mcp"
② GET  该 PRM            → authorization_servers = ["https://auth.panghuer.top"]
③ GET  Casdoor AS metadata
④ 浏览器弹出授权页，同意一次（授权码 + PKCE）
⑤ 重试 POST /mcp 带上 token → 200
```

**不需要 `client_secret`。** 服务端信任的是 **MCP 专用 Casdoor 应用**（`panghu-mcp_my29ub`，
client_id `315cbdaf565b82103c6f`）—— 它是公共客户端，2026-10-02 实测不带 secret 也能换到 token。

如果所用客户端的 OAuth 实现要求手工填 client_id（有些客户端不做动态注册，而本集群 Casdoor
4.11.0 的 DCR 是关的），填 `315cbdaf565b82103c6f`，**secret 留空**。

### 2.2 兜底：手工取 JWT（命令行 / 不支持 OAuth 的客户端）

用仓库里的脚本（浏览器授权码 + PKCE，无需 Casdoor 密码，也无需 secret）：

```bash
bash openspec_service/scripts/get-token.sh      # 输出并写入 /tmp/casdoor.jwt
export CASDOOR_JWT="$(cat /tmp/casdoor.jwt)"
```

校验可用：`CASDOOR_JWT="$CASDOOR_JWT" bash openspec_service/scripts/preflight.sh --jwt "$CASDOOR_JWT"`

> 原来的网页版领取器 `https://openspec.panghuer.top/token` 已于 2026-10-02 退役，
> 归档（含依赖与复活步骤）见 [`../oauth/token-dispenser/README.md`](../oauth/token-dispenser/README.md)。

## 3. 配置客户端

### 3.0 选择项目

新项目登记、Gitea 授权和验证流程见 [`PROJECT_REGISTRATION.md`](PROJECT_REGISTRATION.md)。

OpenSpec Service 不会根据当前本地目录自动推断项目。`armbianbegin` 使用专用 Gitea OpenSpec store；首次登记请执行：

```bash
export CASDOOR_JWT='<Casdoor access_token>'
bash openspec_service/scripts/register-project.sh
```

脚本会在仓库根目录写入 `.openspec-project.json`，其中只包含 `baseUrl`、`owner`、`repository` 和 UUID `projectId`，不包含任何凭据。每次任务先读取该文件，或调用 `list_projects`，再把 `projectId` 传给 MCP 工具。源码仍可在 GitHub，OpenSpec store 是独立的 Gitea 私有仓库。

> 下面各客户端**先试不带 header 的写法**：支持 OAuth 的客户端会自己完成 §2.1 的授权。
> 只有在客户端不支持、或它报 401 且不会自动授权时，才换成带 `Authorization` header 的写法
> （那需要先用 §2.2 取一把 JWT）。

### Claude Code
```bash
# 推荐：不加 header，客户端自己走 OAuth
claude mcp add --transport http openspec https://openspec.panghuer.top/mcp

# 兜底：客户端不支持 OAuth 时，用 §2.2 取来的 JWT
claude mcp add --transport http openspec \
  https://openspec.panghuer.top/mcp \
  --header "Authorization: Bearer $CASDOOR_JWT"
```
想全局生效可写入 `~/.claude.json` 的 `mcpServers`，或按项目放 `.mcp.json`。

### Codex CLI
```bash
codex mcp add openspec --transport streamable-http \
  https://openspec.panghuer.top/mcp \
  --header "Authorization: Bearer $CASDOOR_JWT"
```

### Cursor / Windsurf / 其他支持远程 MCP 的工具
设置 → MCP → 添加远程 MCP server：
- URL：`https://openspec.panghuer.top/mcp`
- 认证：**优先留空**，让客户端走 OAuth；只有客户端不支持 OAuth 时，才填
  `Authorization: Bearer <JWT>`，并手工指定 client_id `315cbdaf565b82103c6f`（**不要 secret**）

### 用 MCP Inspector 调试
```bash
npx @modelcontextprotocol/inspector
# 或直接对 streamable HTTP endpoint 发 initialize 验证连通性
curl -s -X POST https://openspec.panghuer.top/mcp \
  -H "Authorization: Bearer $CASDOOR_JWT" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'
```

### 命令行 / agent 直接调用（不装 MCP 客户端）

MCP 这里是 **streamable HTTP + JSON-RPC**，任何 HTTP 客户端都能用，不必有 MCP 客户端。
仓库里带了一个薄封装 `scripts/mcp-call.sh`（只要 `curl` + `python3`；凭据只从环境变量或
`/tmp/casdoor.jwt` 读，**不进命令行参数、不落盘**）：

```bash
export CASDOOR_JWT='<Casdoor JWT>'
bash openspec_service/scripts/mcp-call.sh --check          # initialize + tools/list
bash openspec_service/scripts/mcp-call.sh --tools
bash openspec_service/scripts/mcp-call.sh --call list_projects
bash openspec_service/scripts/mcp-call.sh --call list_specs \
  --args '{"projectId":"<uuid>"}'
```

它按协议走三步：`initialize` → 从响应头取 `Mcp-Session-Id` → `notifications/initialized`，
之后的 `tools/call` 复用同一个 session。两个要点：

- **session 不跨进程**：服务端单副本、session 在进程内存里（见 §9），所以每次运行都会重新
  `initialize`。连续调多个工具就是多跑几次 —— 每次多一个往返，不影响正确性。
- **写工具别忘 `expectedRevision`**：它必须是当前 HEAD SHA，见 §5 的关键规则。

## 4. 工具清单

| 工具 | 必填参数 | 所需权限 | 说明 |
|---|---|---|---|
| `list_projects` | — | 任意已认证用户 | 列出当前用户可见的项目 |
| `list_specs` | `projectId` | Read | 列出主 specs（返回 `revision`） |
| `list_changes` | `projectId` | Read | 列出 active changes（返回 `revision`） |
| `get_change` | `projectId`, `changeId` | Read | 读 change 工件与 taskStatus |
| `create_proposal` | `projectId`, `changeId`, `expectedRevision` | Write | 创建 change（`files` 可选） |
| `update_proposal` | `projectId`, `changeId`, `expectedRevision`, `files` | Write | 更新已有 change 工件 |
| `validate_change` | `projectId`, `changeId` | Write | 校验 change/spec（不要求 revision） |
| `apply_specs` | `projectId`, `changeId`, `expectedRevision` | Write | delta 合并进主 specs，保留 change |
| `archive_change` | `projectId`, `changeId`, `expectedRevision` | **Admin** | 归档 change（合并 specs 后移入 archive） |

**权限映射**（以 Gitea 仓库 ACL 为准）：`Read`=viewer（读）、`Write`=editor（写/校验）、`Admin`=owner（归档）。

## 5. 典型工作流（Agent 该怎么用）

```text
1. list_projects                -> 找到 projectId
2. list_specs / list_changes    -> 取当前 revision（乐观并发基准）
3. create_proposal:
     projectId, changeId(如 add-login),
     expectedRevision=<上一步 revision>,
     files = { "proposal.md": "…", "specs/auth/spec.md": "## ADDED Requirements\n…" }
4. validate_change              -> 确认 valid=true（失败看 message 修内容）
5. 需要改时 update_proposal（用最新 revision）
6. apply_specs                  -> delta 合入主 specs
7. archive_change               -> 归档（需 owner 权限）
```

**关键规则：`expectedRevision` 必须是当前 HEAD SHA。** 每次写操作都会改变 revision，
所以"先读列表拿 revision → 写 → 若 409 再读再写"。写失败返回 409 时重新 `list_specs`/`list_changes`
取最新 revision 重试即可。

`files` 里的 spec 内容必须是合法 OpenSpec delta 格式（`## ADDED/MODIFIED/REMOVED Requirements`，
每条 `### Requirement:` 至少带一个 `#### Scenario:`，见 TROUBLESHOOTING.md §4.1）。

## 6. 幂等与重试

- 写工具（create/update/apply/archive）**幂等**：客户端可传 `Idempotency-Key` HTTP 头；
  **不传时服务自动按 用户+项目+工具+参数 派生确定性键**，因此：
  - 重试同一次调用 → 重放原响应，不会重复写入；
  - 不同调用 → 不同键，互不冲突。
- 这意味着标准 MCP 客户端（固定请求头）**无需额外配置即可安全地多次写入**。

## 7. 错误码

| 状态 | 含义 | 处理 |
|---|---|---|
| 401 | JWT 无效/过期/`aud` 不符 | 走 OAuth 的客户端会自己重新授权；手工 header 的场景重新跑 `get-token.sh` |
| 404 | 项目不存在或当前用户无权限（刻意不区分，防探测） | 检查 projectId / Gitea 权限 |
| 409 | `expectedRevision` 过期或幂等键与上次请求不一致 | 重新取 revision 重试 |
| 422 | validate/archive 内容不合法 | 按 message 修 spec 内容 |
| 503 | Gitea/DB/Vault 依赖不可用 | 稍后重试 |

## 8. 权限与安全

- 每个开发者用自己的 Casdoor JWT；权限**完全以 Gitea 仓库 ACL 为准**。
- 从 Gitea 移除成员后，下一次请求立即 404，无缓存延迟（当前实现逐请求查 ACL）。
- 项目隔离由服务端强制：客户端只提交 `projectId`，无法触碰其他项目的工作区/Git 历史。
- 服务不调用 LLM；proposal/spec 内容由 Agent 自己生成，服务只负责授权、持久化、校验与 Git 审计。

## 9. 已知限制

- 当前单副本部署：MCP session 在进程内存，Pod 重启后客户端需重新 `initialize`。
- 写操作是"先读后写"乐观并发，不适合无 revision 概念的纯流式调用。
- `archive_change` 要求 Gitea Admin 权限，普通编辑者无法归档。
- 跨副本部署、OAuth **动态客户端注册（DCR）** 在 backlog P2。注意 DCR 在本集群 Casdoor 4.11.0 上
  开关存在但默认关闭，而且**与固定 audience 天然不兼容**（注册出来的是随机 client_id，没法预先
  加进 `OIDC_AUDIENCE`）—— 详见 [../docs/platform-mcp-auth.md](../docs/platform-mcp-auth.md)。
