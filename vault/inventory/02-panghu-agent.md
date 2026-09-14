# Panghu Agent — 模型凭据

## 现状：模型凭据已收归集群内 llm-service

原来每个 Agent 的 namespace 各有一份 `agent-secret`（从 Vault `secret/data/<ns>/api`
同步 DeepSeek 凭据），外加一份 `agent-config` ConfigMap 保存 `PROVIDER` / `DEEPSEEK_*`。

**这套配置已经全部退役：**

- 模型调用统一走集群内 `llm-service`，provider 凭据只存在于它自己的 Secret
  （`vault/inventory/llm-service-externalsecret.yaml` → `secret/data/llm-service/providers`）。
- 各 Agent 只需要 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_SERVICE_TOKEN` 三个变量，
  令牌由 `panghu_agent/k8s/llm-token-externalsecret.yaml` 从 `secret/data/llm-service/callers` 里
  **只取本调用方那一个键**（`LLM_TOKEN_<CALLER>`）注入 —— 每个命名空间拿不到别人的令牌，
  llm-service 由变量名反推身份。
- 各 namespace 的 `agent-secret` ExternalSecret 与 `agent-config` 已删除。
  模型凭据分散在各 Agent 的 Vault `secret/<ns>/api` 路径也已清除（**清除过程见下节，
  第一次并没有清干净**）。

详见 `panghu_agent/README.md` 的「模型调用：统一走 llm-service」。

## ⚠️ 第一次清理没有清干净（2026-09-14 发现）

原文写的是「`secret/<ns>/api` 路径也已清除」。**那句话当时是错的** —— 实际只做了
`vault kv delete`，它只**软删除当前版本**；KV v2 默认 `max_versions: 0`（无限保留历史版本），
所以每个路径的历史版本都还在，且全部可读、可恢复。

复查时 12 条路径中 10 条仍有存活版本，且**每条的最新存活版本里装的就是当时 llm-service
正在使用的那把 DeepSeek key**（指纹 `0c881ff6…`）：

```
secret/daofaziran-agent/api        v1,2,3   ← v3 = 在用 key
secret/research-agent/api          v1–v5    ← v5 = 在用 key
secret/scientific-agent/api        v1,2,3
secret/game-review-agent/api       v1,2,3
secret/zhongkuifumo-agent/api      v1,2,3
secret/fofawubian-agent/api        v1,2,3
secret/yimaneili-agent/api         v1,2,3
secret/zhenzhuzhida-agent/api      v1,2,3
secret/bingbichunqiu-agent/api     v1
secret/xiaotanrenjian-agent/api    v1
secret/literature-downloader/api   已全软删（无存活版本）
secret/zhougongjiemeng-agent/api   已全软删（无存活版本）
```

**为什么常规检查查不出来**：`kv list` 仍列出路径、`kv get` 返回 `data: null`、
`kv metadata get` 不看 `versions` 字段也看不出来 —— 三种查法全部显示「已删除」。

已用 `vault kv metadata delete` 重做，12 条全部核实为无存活版本。
**教训与核对命令写进了 `vault/rules.migrate.md` 的「退役一个组件」一节。**

## 涉及过的 namespace

`research-agent`、`scientific-agent`、`daofaziran-agent`、`fofawubian-agent`、
`yimaneili-agent`、`zhenzhuzhida-agent`、`zhongkuifumo-agent`、`zhougongjiemeng-agent`、
`xiaotanrenjian-agent`、`bingbichunqiu-agent`、`game-review-agent`、`literature-downloader`

## game-review-agent（游戏试玩评价）

模型凭据同上，走 llm-service。本 namespace 还保留一个**与模型无关**的 Secret：

| 属性 | 值 |
|------|-----|
| **Secret** | `game-auth`（受保护游戏的登录 cookie） |
| **Vault 路径** | `secret/data/game-review-agent/auth` |
| **ExternalSecret** | `vault/inventory/game-review-agent-externalsecret.yaml` |

```bash
# 游戏访问 cookie（可选，不配则只能访问公开页面）
kubectl exec -n vault vault-0 -- vault kv put secret/game-review-agent/auth \
  GAME_AUTH_COOKIE="name=_oauth2_proxy;value=<cookie值>;domain=.panghuer.top;path=/;secure"

kubectl apply -f inventory/game-review-agent-externalsecret.yaml
```

> 注意：`game-auth` 的 ExternalSecret 目前是 `SecretSyncedError` —— `secret/data/game-review-agent/auth`
> 在 Vault 里不存在。这与模型迁移无关，是既有的待办；不配 cookie 时 agent 只能访问公开页面。

## literature-downloader

模型凭据同上，走 llm-service（`LLM_MODEL=deepseek-trusted`）。它自己的 `agent-config` 仍在用，
但只放检索参数（`LITERATURE_*`），由 `literature_downloader/deploy.sh` 应用。

## 令牌同步与重启

```bash
# 强制同步 llm-token 并校验（可选 --restart）
bash panghu_agent/scripts/sync-llm-token.sh --restart
```
