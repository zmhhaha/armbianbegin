# OpenSpec MCP 接入说明

让 Codex、Claude Code、Cursor 等 AI 编程工具直接读写你的 OpenSpec 规格库。
OpenSpec Service 对外提供**一个远程 MCP server**，复用 Casdoor JWT 认证与 Gitea 权限，
AI 工具只需"加一个远程 MCP"即可，不需要在本地装任何 OpenSpec 环境。

---

## 1. 连接信息

| 项 | 值 |
|---|---|
| MCP 地址 | `https://openspec.panghuer.top/mcp` |
| 传输 | streamable HTTP（协议版本 `2025-06-18`） |
| 认证 | `Authorization: Bearer <Casdoor JWT>` |
| 项目边界 | 服务端强制，客户端只传 `projectId`（UUID） |

## 2. 获取 JWT

### 2.1 网页版（推荐，给其他用户用）

打开 **`https://openspec.panghuer.top/token`** → 用 Casdoor 登录（GitHub / 邮箱）→ 页面直接
显示你的 JWT 和"复制"按钮，并给出 Codex / Claude Code 的配置命令。**无需装任何工具。**

前置：管理员已在 `panghu-suite` 白名单加入 `https://openspec.panghuer.top/token`，且服务
已配置 `CASDOOR_CLIENT_SECRET`（见 DEPLOY.md）。

### 2.2 脚本版（管理员 / 命令行环境）

用仓库里的脚本（浏览器授权码流，无需 Casdoor 密码；GitHub 注册用户也可用）：

```bash
bash openspec_service/scripts/get-token.sh      # 输出并写入 /tmp/casdoor.jwt
export CASDOOR_JWT="$(cat /tmp/casdoor.jwt)"
```

校验可用：`CASDOOR_JWT="$CASDOOR_JWT" bash openspec_service/scripts/preflight.sh --jwt "$CASDOOR_JWT"`

## 3. 配置客户端

### 3.0 选择项目

新项目登记、Gitea 授权和验证流程见 [`PROJECT_REGISTRATION.md`](PROJECT_REGISTRATION.md)。

OpenSpec Service 不会根据当前本地目录自动推断项目。`armbianbegin` 使用专用 Gitea OpenSpec store；首次登记请执行：

```bash
export CASDOOR_JWT='<Casdoor access_token>'
bash openspec_service/scripts/register-project.sh
```

脚本会在仓库根目录写入 `.openspec-project.json`，其中只包含 `baseUrl`、`owner`、`repository` 和 UUID `projectId`，不包含任何凭据。每次任务先读取该文件，或调用 `list_projects`，再把 `projectId` 传给 MCP 工具。源码仍可在 GitHub，OpenSpec store 是独立的 Gitea 私有仓库。

### Claude Code
```bash
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
- Header：`Authorization: Bearer <JWT>`

### 用 MCP Inspector 调试
```bash
npx @modelcontextprotocol/inspector
# 或直接对 streamable HTTP endpoint 发 initialize 验证连通性
curl -s -X POST https://openspec.panghuer.top/mcp \
  -H "Authorization: Bearer $CASDOOR_JWT" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'
```

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
| 401 | JWT 无效/过期/`aud` 不符 | 重新 `get-token.sh` |
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
- 跨副本部署、OAuth 动态授权（供第三方应用使用）在 backlog P2。
