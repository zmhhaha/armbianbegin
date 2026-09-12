# rag-service

内部 RAG API：Elasticsearch（IK 混合检索）+ embedding-service（bge-small-zh-v1.5）+ 经 `llm-service` 生成回答。

- **仅集群内可达**（ClusterIP），不提供公网入口。
- **不持有任何 provider API Key**；模型凭据在 `llm-service`。
- 调用必须携带凭据，身份由凭据推导，请求体里的 `agent`/`collection` 只作收窄。

## 前置

1. `elasticsearch`（带 IK 插件）已部署，且 `elasticsearch-secret` 已由 Vault 同步。
2. `embedding-service` 已部署。
3. `llm-service` 已部署（RAG 通过它生成回答）。
4. Vault 处于 **unsealed** 状态。

## 部署

### 1. 写入 Vault 凭据

```bash
# 调用者令牌：每个 Agent 一个；变量名决定调用者身份（RAG_TOKEN_<CALLER>，连字符换下划线）
kubectl exec -n vault vault-0 -- vault kv put secret/rag-service/callers \
  RAG_TOKEN_DAOFAZIRAN="$(openssl rand -hex 32)" \
  RAG_TOKEN_FOFAWUBIAN="$(openssl rand -hex 32)" \
  RAG_TOKEN_ZHONGKUIFUMO="$(openssl rand -hex 32)" \
  RAG_TOKEN_ZHOUGONGJIEMENG="$(openssl rand -hex 32)" \
  RAG_TOKEN_ZHENZHUZHIDA="$(openssl rand -hex 32)" \
  RAG_TOKEN_YIMANEILI="$(openssl rand -hex 32)" \
  RAG_TOKEN_XIAOTANRENJIAN="$(openssl rand -hex 32)" \
  RAG_TOKEN_BINGBICHUNQIU="$(openssl rand -hex 32)" \
  RAG_TOKEN_RAG_OPERATOR="$(openssl rand -hex 32)"
```

`secret/llm-service/auth`（调用 llm-service 的令牌）由 `llm-service` 部署时创建，RAG 复用同一份，不再单独保存。

### 2. 构建并部署

```bash
cd rag-service
bash build.sh --push
bash deploy.sh
```

`deploy.sh` 会：应用并等待两个 ExternalSecret（`rag-callers-secret`、`rag-llm-secret`）→ 应用 `k8s.yaml`
（Service / Deployment / ConfigMap / NetworkPolicy）→ 设置镜像 → 滚动重启。

两个 ExternalSecret 未就绪时脚本只告警不中断：缺 `rag-callers-secret` 会导致**所有调用 401**，
缺 `rag-llm-secret` 会让查询**退化为只返回检索片段**。

## 鉴权与权限

| 概念 | 来源 |
|---|---|
| 令牌 | Vault `secret/rag-service/callers` → `RAG_TOKEN_<CALLER>` 环境变量 |
| 身份 | **由令牌推导**：令牌属于哪个环境变量，调用者就是谁（`RAG_TOKEN_DAOFAZIRAN` → `daofaziran`） |
| 权限 | ConfigMap `rag-config` 的 `CALLER_PERMISSIONS`；未列出的调用者默认只能读写 `agent-<caller>` |

```json
{"rag-operator": {"read": ["*"], "write": ["*"]}}
```

- `reader` / `writer`：默认形态，只能读写自己的 collection。
- `operator`：权限里含 `"*"`，可读写任意 collection。
- 权限**可收窄**：显式写 `"write": []` 表示只读。

请求体里的 `agent` **只是收窄提示**：不在授权范围内一律按 404 处理，绝不放宽。

## 配置（ConfigMap `rag-config`）

```yaml
LLM_URL: http://llm-service.llm.svc.cluster.local/v1/chat/completions
LLM_MODEL: chat-default          # llm-service 注册的"模型别名"，不是上游模型名
LLM_TIMEOUT: "120"
CALLER_PERMISSIONS: |
  {"rag-operator": {"read": ["*"], "write": ["*"]}}
```

`LLM_URL` 留空则 `/v1/query` 只返回检索片段，不调用 LLM。改 ConfigMap 后需
`kubectl -n data rollout restart deployment/rag-service`（环境变量在 Pod 启动时注入）。

## 知识入库（knowledge.md → 条目）

Agent 把**整份 `knowledge.md`** POST 给 `/v1/ingest`，**转换在服务端完成**——
这样转换规则永远只有一份实现，不会出现"各 Agent 各写一套、与已有语料不一致"。

```json
{"source_id": "knowledge.md", "doc_type": "knowledge", "content": "<整份 knowledge.md>", "metadata": {"copyright_status": "public-domain"}}
```

**转换规则**（`chunking.py: split_knowledge`）

| 规则 | 说明 |
|---|---|
| 切分粒度 | 每个 `## ` 小节 → 一个 chunk（同一文档，`chunk_seq` 递增） |
| 跳过 | 标题含 `守则/边界/原则/禁忌/篇幅/自检/开头/例子/工作步骤/工具箱` 的小节——属 Agent 的 skill 行为，不是可检索知识 |
| `topic` | 小节标题（去掉"一、"这类序号） |
| `work` | 小节里第一个《…》，没有则省略 |
| `provenance` | `<caller>:knowledge.md#<小节标题>` |
| `copyright_status` | 由调用方在 `metadata` 里给出（默认不填）：相声 `copyrighted`，圣经/古兰经 `mixed`，其余 `public-domain` |

整份文件是**一个文档**（`source_id` 固定 `knowledge.md`），重新同步即**原子替换**——
不会残留已删除小节的旧条目。

## API

地址：`http://rag-service.data.svc.cluster.local:8080`

除健康检查外都需要 `Authorization: Bearer <调用者令牌>`。

### `POST /v1/ingest`

```json
{"source_id": "zhanguoce-1", "content": "……正文……", "metadata": {"work": "战国策", "topic": "纵横"}}
```

`agent` 可省略（调用者只有一个可写 collection 时）。返回 `document_id` / `chunk_count` / `status`。
相同 `source_id` + 相同 checksum 幂等；checksum 变化时原子替换（先建临时索引再切换）。

### `POST /v1/query`

```json
{"question": "《史记》是什么体例？", "top_k": 5, "mode": "answer"}
```

`mode` 两种：

- **`answer`（默认）**：检索 + 由本服务经 `llm-service` 生成答案。返回 `answer`、`collection`、`sources`（含 `content`/`score`/`source_id`/`work`/`topic`）、`index_version`。
- **`context`**：**只回检索素材**，`answer` 为 `null`，另给 `context`（拼好的参考文本）。**Agent 用这个模式**：自己按 `skill.md` 生成，避免两层 LLM 打架、也省一次生成。

召回采用 IK 关键词 + 向量并做 RRF 融合；低于 `RELEVANCE_THRESHOLD` 时 `sources` 为空
（`answer` 模式会明确回答"索引知识不足"，不编造）。LLM 超时或返回格式错误时返回 **502**，不伪造生成结果。

### 健康

`GET /health/live`、`GET /health/ready`（ready 会检查 Elasticsearch 连通性），无需鉴权。

## 网络

NetworkPolicy 只允许带 `rag-client: "true"` 标签的 Pod 访问 RAG；出站不限制
（需访问 Elasticsearch / embedding-service / llm-service）。RAG 自身带 `llm-client: "true"` 标签，
以通过 llm-service 的入站策略。

## 本地运行与测试

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
ELASTICSEARCH_PASSWORD=... RAG_TOKEN_DAOFAZIRAN=dev-token \
  uvicorn app:app --port 8080

python -m unittest discover -s tests
```

## 已知问题与排查

**1. Agent 要的是"素材"而不是"答案"**
`/v1/query` 默认 `mode=answer` 会调 llm-service 生成答案；Agent 再基于它生成，就成了**两层 LLM**——
风格打架、token 翻倍。所以 **Agent 一律用 `mode=context`** 只取素材。新增调用方时先确认 mode 用对了。

**2. 并发灌库撞 embedding 忙限（429）→ ingest 返回 500**
embedding 服务只有一个推理锁，忙时返回 429。多台 Agent 同时启动时会被打爆，`/v1/ingest` 直接 500，
**同步静默失败**（探针正常、Pod 正常，只是知识没进库）。
现在两侧都做了退避重试：RAG 侧 `embed()` 对 429/5xx 重试（1.5s→3s→6s），同步脚本重试 3 次。
若日志里仍出现 `POST /v1/ingest ... 500`，说明并发仍超限——错峰部署，或给 embedding-service 加副本。

**3. ConfigMap 加了键，Deployment 没引用 → 等于没配**
`CALLER_PERMISSIONS` 曾只写进 `rag-config`，而 Deployment 的 `env` 是逐个 `configMapKeyRef` 引用的，
漏引用就完全无效——现象是 operator 通配权限失灵、灌库全 404。
**改 ConfigMap 后务必确认 Deployment 里有对应 env 引用，并重启 Pod。**

**4. 换摄入模式后要清旧文档**
pilot 期是"每个 H2 小节一篇"（`source_id=knowledge-01-xxx`），现在是"整份 knowledge.md 一篇"
（`source_id=knowledge.md`）。两者共存会让检索出现重复内容，迁移时先删旧的：

```bash
kubectl -n data exec elasticsearch-0 -- bash -c 'curl -s -u elastic:$ELASTIC_PASSWORD -X POST "localhost:9200/rag-agent-*/_delete_by_query?refresh=true&conflicts=proceed" -H "Content-Type: application/json" -d "{\"query\":{\"prefix\":{\"source_id\":\"knowledge-\"}}}"'
```

