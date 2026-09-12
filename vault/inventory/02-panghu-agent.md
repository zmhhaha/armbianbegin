# Panghu Agent — 模型凭据

## 现状：模型凭据已收归集群内 llm-service

原来每个 Agent 的 namespace 各有一份 `agent-secret`（从 Vault `secret/data/<ns>/api`
同步 DeepSeek 凭据），外加一份 `agent-config` ConfigMap 保存 `PROVIDER` / `DEEPSEEK_*`。

**这套配置已经全部退役：**

- 模型调用统一走集群内 `llm-service`，provider 凭据只存在于它自己的 Secret
  （`vault/inventory/llm-service-externalsecret.yaml` → `secret/data/llm-service/providers`）。
- 各 Agent 只需要 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_SERVICE_TOKEN` 三个变量，
  令牌由 `panghu_agent/k8s/llm-token-externalsecret.yaml` 从 `secret/data/llm-service/auth` 注入。
- 各 namespace 的 `agent-secret` ExternalSecret 与 `agent-config` 已删除。
  模型凭据分散在各 Agent 的 Vault `secret/<ns>/api` 路径也已清除。

详见 `panghu_agent/README.md` 的「模型调用：统一走 llm-service」。

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

模型凭据同上，走 llm-service（`LLM_MODEL=chat-default`）。它自己的 `agent-config` 仍在用，
但只放检索参数（`LITERATURE_*`），由 `literature_downloader/deploy.sh` 应用。

## 令牌同步与重启

```bash
# 强制同步 llm-token 并校验（可选 --restart）
bash panghu_agent/scripts/sync-llm-token.sh --restart
```
