# llm-service

集群内统一的 LLM 入口：集中 provider 凭据、模型别名路由、超时与重试、限流与用量统计。
**仅集群内可达（ClusterIP）**，不提供任何公网入口，也不做业务逻辑。

对应 OpenSpec change `add-rag-service` 中的 `llm-service` capability。

## 边界

- 调用方只能传**允许的模型别名 + 有界的非敏感生成参数**（`temperature`、`top_p`、`max_tokens`、`stop`、`presence_penalty`、`frequency_penalty`）。
- 请求体里出现 `base_url` / `api_key` / `provider` 之类字段，或使用未知别名，一律拒绝。
- 凭据只从 Vault 注入进程环境，**绝不回传给调用方**。
- 非敏感路由（provider、上游 base URL、模型别名、默认参数、超时、重试、fallback）放 ConfigMap。

## 抗滥用（Prompt hijack resistance，后续阶段）

防止调用方把它当成通用 LLM 白嫖（用户注入 prompt 废掉 persona 后反问任意问题）。
**不属于 llm-service 第一阶段**；调研与设计要点见 [`docs/llm-service-abuse-defense.md`](../docs/llm-service-abuse-defense.md)。

第一阶段已有的边界照旧生效：请求体 `extra="forbid"` 会拒掉 `tools` / `base_url` / `provider` 等扩权字段，
生成参数由 `ALLOWED_PARAMS` 限定。后续阶段再补：system prompt 固化（服务持有或指纹校验）、
不可信内容分隔（spotlighting）、注入检测、canary 泄漏检测、终端用户配额。

## API

地址：`http://llm-service.llm.svc.cluster.local`（Service 80 → 容器 8000）

请求头：

| 头 | 说明 |
|---|---|
| `Authorization: Bearer <LLM_SERVICE_TOKEN>` | 必填，内部鉴权 |
| `X-Caller: <service-name>` | 调用方标识，用于限流与用量统计，**不参与授权判定** |

### `POST /v1/chat/completions`

```json
{"model": "chat-default", "messages": [{"role": "user", "content": "你好"}], "temperature": 0.7}
```

`model` 是**别名**，不是上游模型名。服务按别名解析 provider / base_url / 模型 / 凭据后转发，响应与 OpenAI 兼容（含 `usage`）。

### 其他

- `GET /v1/models` — 列出当前允许的别名
- `GET /v1/usage` — 返回调用方自己的用量计数
- `GET /health/live`、`GET /health/ready` — 存活与就绪（就绪要求配置已加载且至少有一个可用凭据）

`stream=true` 暂不支持（返回 400）。

## 配置

ConfigMap `llm-service-config`：

```json
{
  "aliases": {
    "chat-default": {
      "provider": "deepseek",
      "base_url": "https://api.deepseek.com/v1",
      "model": "deepseek-v4-flash",
      "api_key_env": "DEEPSEEK_API_KEY",
      "timeout_seconds": 60,
      "max_retries": 2,
      "fallback": ["chat-backup"],
      "defaults": {"temperature": 0.7, "max_tokens": 2048}
    }
  },
  "limits": {"requests_per_minute_per_caller": 120}
}
```

凭据（Vault → `llm-service-secret`）：

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/llm-service/providers \
  DEEPSEEK_API_KEY='...' OPENAI_API_KEY='...'
kubectl exec -n vault vault-0 -- vault kv put secret/llm-service/auth \
  LLM_SERVICE_TOKEN="$(openssl rand -hex 32)"
```

`fallback` 指向另一个别名：主别名彻底失败（超时 / 5xx / 429）时按顺序转移。

## 构建和部署

```bash
cd llm-service
bash build.sh --push     # 国内 pip 源，构建并推送
bash deploy.sh           # 应用 Vault ExternalSecret + k8s，重启并等待就绪
```

部署到命名空间 `llm`。NetworkPolicy 只允许带 `llm-client: "true"` 标签的 Pod 访问；出站只放行 DNS 与 443。

## 迁移现有服务

各 Agent、`content-llm-service`、RAG 在各自迭代中把直连 provider 换成
`http://llm-service.llm.svc.cluster.local`，并**删除自己那份 provider API Key**；对外 API 与业务逻辑不变。

## 本地运行与测试

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
LLM_SERVICE_TOKEN=dev \
LLM_ALIASES='{"aliases":{"chat-default":{"provider":"deepseek","base_url":"https://api.deepseek.com/v1","model":"deepseek-v4-flash","api_key_env":"DEEPSEEK_API_KEY"}}}' \
DEEPSEEK_API_KEY=... uvicorn app:app --port 8000

python -m unittest discover -s tests
```

## 已知问题与排查

**1. 依赖安装超时**
镜像构建走国内 pip 源（`PIP_INDEX_URL`，默认清华）。若退回默认 PyPI，在这套小集群上会以几 KB/s 的速度超时。

**2. 多源 COPY 必须带斜杠**
`COPY app.py config.py upstream.py .` 会报 `destination must be a directory and end with a /`；
要写成 `./`。构建脚本改动时容易踩。

**3. `deploy.sh` 的顺序：命名空间必须先于 ExternalSecret**
ExternalSecret 要落到 `llm` 命名空间，而命名空间定义在 `k8s.yaml` 里、位于后半段——曾因此报
`namespaces "llm" not found`。脚本已改为先执行 `kubectl create namespace llm`。

**4. Vault 被 seal → 所有 ExternalSecret 同步失败**
现象：`ClusterSecretStore vault-backend` 显示 `InvalidProviderConfig`，ExternalSecret 全部 `SecretSyncedError`。
注意：**服务本身仍在跑**（凭据早已注入进程），只是新同步不会发生。排查：
`kubectl -n vault exec vault-0 -- vault status` 看 `Sealed`，unseal 后
`kubectl annotate externalsecret <name> -n <ns> force-sync="$(date +%s)" --overwrite` 立即重同步。

