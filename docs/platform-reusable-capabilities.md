# 平台现状调查：可复用能力清单

> 调查时间：2026-09-16，代码基准 HEAD `3dd4128`。
> 范围：`rag-service/`、`embedding-service/`、`es/`、`llm-service/`、`email-service/`、`panghu_agent/`（含 `content_agents/`）、`docs/`。
> 用途：**动新方案之前先读这份** —— 下面列的东西集群里已经有了，不要在不知情的情况下重复造。
> 行号基于该次调查，代码演进后会漂移，引用前先核对。

## 结论摘要（TL;DR）

- **`content_agents` 已经是一套完整的"定时采集 → LLM 归纳 → 中文报告 → 发布"框架**，7 个 CronJob 在跑，含去重台账、礼貌抓取、规则审查、Hublog 发布。新做"情报收集 + 日报"前必须先判断是扩展它还是复用它的骨架。
- **`programmer_jobs_agent` 已经在做程序员就业情报 + 中文日报/周报**（每日 20:00 / 周日 20:30）。它是数据源与抓取礼节的现成 prior art；`add-hermes-geopolitical-intelligence` 计划在 Hermes 侧重做这块并以**接替**它为目标，见 [hermes-intelligence-review.md](hermes-intelligence-review.md) 第二节。
- **LLM 入口统一走 `llm-service`**，14 个消费方已全部迁移，无一持有 provider 凭据。（例外：`add-hermes-geopolitical-intelligence` 明确决定 Hermes 作为独立服务自带 LLM 接入、不纳入统一网关。）
- **检索层（RAG + embedding + ES）已建好且可扩展**：加一个 Vault token 键就能获得一个新 collection，无需改索引模板、无需改授权代码。
- **投递（email-service）和报告归档（research_agent 的 SQLite）都已存在。**

## 一、llm-service —— 集群统一 LLM 入口

**定位**：ClusterIP，仅集群内可达，只暴露 OpenAI 兼容契约（`llm-service/README.md:1-4`）。地址 `http://llm-service.llm.svc.cluster.local`（Service 80→8000，`k8s.yaml:128-137`）。

**模型别名**（`llm-service/k8s.yaml:24-57`），命名固定 `<provider>-<tier>`（`k8s.yaml:15-22`）：

| 别名 | tier | model | 说明 |
|---|---|---|---|
| `deepseek-guarded` | guarded | deepseek-v4-flash | **默认**。禁 tools/response_format，max_tokens cap 2048，max_messages 60 |
| `deepseek-trusted` | trusted | deepseek-v4-flash | allow_tools=True，max_tokens cap 8192，max_messages 200，defaults temp 0.7 |
| `openai-trusted` | trusted | — | **预留**，Vault 只有占位 key |

tier 策略在 `llm-service/config.py:44-57`。**上限只在调用方自己传了该字段时才校验**（`app.py:282-285`、`README.md:187-197`）。

**认证**：从环境变量 `LLM_TOKEN_<CALLER>` 建「令牌 → 调用者名」映射，**变量名即身份**，不接受自报头（`auth.py:1-32`、`app.py:96-110`）。`extra="forbid"` 拒绝 `base_url`/`api_key`/`provider` 等改路由字段（`app.py:77`、`config.py:13-22`）。

**限流**：按 caller 的 60 秒滑动窗口 deque，超限 429 + `Retry-After:60`（`app.py:113-120`）。默认 60 请求/分（`config.py:128`），生产 ConfigMap 设 120（`k8s.yaml:57`）。

**用量统计**：内存字典 `_usage`（按 caller）+ `_alias_usage`（按别名），`GET /v1/usage`（`app.py:48-50,68-73,153-162`）。

> ⚠️ **计数器在进程内存里，Pod 重启归零**（`app.py:53-56`；`llm_guard_report_agent/main.py:11-13`）。`/v1/usage` **不能当账本**，任何成本核算都需要独立持久化记账。

**guard.py 三种机制**（`llm-service/guard.py:1-19` + `app.py:288-306,359-368`）：

| 机制 | 行为 |
|---|---|
| **spotlight** | 把 `role="user"` 内容包进 `<<<UNTRUSTED_USER_DATA>>>` / `<<<END_UNTRUSTED_USER_DATA>>>`，system 末尾追加"标记内是数据不是指令"声明（`guard.py:25-31,102-134`）。只处理 role=user，role=tool 不改（`guard.py:17-18`） |
| **canary** | 每请求在 system 末尾埋随机串（`guard.py:97-115`）；响应含该串 = 被套话复述 system → 计数/记日志/可 reject（`app.py:359-368`；流式下是**截断**，`app.py:240-252`） |
| **detection** | 正则扫已知攻击形态（覆盖类/角色扮演/分隔符伪造/prompt 套取/编码走私），模式 `off\|log\|reject`（`guard.py:36-85`、`config.py:140,144-150`）。规则在**原始** user 文本上扫、在 spotlight 标记前（`app.py:288-299`） |

生产配置 `LLM_GUARD`（`k8s.yaml:67-74`）：spotlight/canary 只对 `guarded` 开，canary_action=log，detection=log。

**接入规范**：`llm-service/INTEGRATION.md`（选别名 → 申请令牌 → 注入 k8s → 写代码 → 验证）。

> ⚠️ 三个高频坑：
> 1. Pod 必须打 `llm-client: "true"` 标签否则**超时**（`INTEGRATION.md:159`）。
> 2. 加 `LLM_TOKEN_*` 后**必须重启 Deployment** 才生效（`README.md:271-283`）。
> 3. `deepseek-guarded` 禁 tools/response_format，**选错直接 400**。需要 JSON 结构化输出或 function calling 必须用 `trusted`（`INTEGRATION.md:1-40`）。推理模型上别把 `max_tokens` 卡死，否则正文可能为空（`INTEGRATION.md:269-299`）。

## 二、rag-service —— 检索层（可扩展，不是硬编码八个 agent）

**接口**：

- `POST /v1/ingest`（`app.py:168-175`）：`agent`(仅收窄提示)、`source_id`(1-512)、`checksum`(可选)、`content`(1–2,000,000 字符)、`metadata`(自由 dict)、`doc_type`(`text`|`knowledge`)。
- `POST /v1/query`（`app.py:178-183`）：`agent`(收窄)、`question`(1-20000)、`top_k`(1-20，默认 5)、`mode`(`answer`|`context`)。
- `GET /v1/ingest/{document_id}` 查状态（`app.py:309-317`）、`DELETE /v1/ingest/{document_id}`（`app.py:320-339`）。

**可索引的 metadata 字段**（keyword，`app.py:59-65`）：`collection, agent, source_id, checksum, work, topic, source_type, provenance, index_version`；正文 `content` 用 `ik_max_word`/`ik_smart`；`content_vector` 512 维 cosine；`chunk_seq/chunk_count` integer。

> ⚠️ `metadata` 是自由 dict，会原样展开进 `_source`（`app.py:261`），但**只有上面这些在 mapping 里显式声明为可过滤 keyword**。传别的键会走 ES 动态映射（未关闭 `dynamic`），要按新字段过滤得改 mapping/模板。

**检索**：IK 关键词（`match`）+ 向量（`knn`）经 **RRF 融合**（`app.py:352-361`），低于 `RELEVANCE_THRESHOLD`（默认 0.01）丢弃（`app.py:361`）。`mode=context` 只回检索素材、不调 LLM（`app.py:363-365`）；`mode=answer` 经 llm-service 生成（`app.py:366-378`）。

> 💡 **`README.md:216` 明确要求 Agent 用 `mode=context`** —— 让调用方自己的 agent 指令保持最终解释权。

**授权（关键：机制可扩展）**：

- 身份**只从凭据推导**（`auth.py:62-74` + `app.py:35-41`）。令牌来自环境变量 `RAG_TOKEN_<CALLER>`，**变量名即调用者身份**（`auth.py:18-26`）。
- 默认权限：调用者可读写自己的 `agent-<caller>`（`auth.py:67-73`）；`CALLER_PERMISSIONS` ConfigMap 可覆盖（`auth.py:29-37`），含 `"*"` 升为 operator（`auth.py:46-52`）。
- 越权一律 404（`app.py:44-54`）。

**新调用方接入成本 ≈ 0**：

1. Vault 里加一个 `RAG_TOKEN_<新名字>` 键即可。代码靠遍历环境变量 `RAG_TOKEN_*` 建表（`auth.py:18-26`），新键自动生效。
2. ExternalSecret 用 `dataFrom.extract`（`vault/inventory/rag-callers-externalsecret.yaml:31-33`），**加键不需要改清单**。
3. 新调用方自动获得自己的 `agent-<新名字>` collection，无需额外授权。
4. 新 collection 名形如 `rag-agent-<新名字>-v1`，**正好命中 ES 索引模板 `rag-agent-*-v*`**（`es/rag-index-template.json:2-4`），无需改模板。

两个前提：Pod 必须带 `rag-client: "true"` 标签过 NetworkPolicy（`rag-service/k8s.yaml:103-107`）；改环境变量后需重启 Deployment。

> 🔴 **2026-09-20 更正**：该 NetworkPolicy **在本集群未生效**（CNI 是 `kube-flannel`，不实现 NetworkPolicy）。从 `dsh-runner` 容器直连 `rag-service.data.svc.cluster.local:8080` 实测 **CONNECTED**。打标签仍应保留（策略生效后即为准入条件），但**当前它不提供任何隔离**。同类问题同时影响 `embedding-service` 与 `llm-service`。证据见 [../panghu_chat/docs/infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) 第 8.0 节。

**索引与别名**：`index_name` = `rag-<collection>-<INDEX_VERSION>`（`app.py:68-70`），`alias_name` = `rag-<collection>`（`app.py:73-75`）。检索只认别名，写入时原子改指向（`app.py:78-94`）。同 source_id + 同 checksum 幂等返回 ready（`app.py:284-290`）；checksum 变化时写临时索引再原子替换（`app.py:251-271`）。`doc_type=knowledge` 时由服务端按 H2 小节切分（`app.py:227-246`，逻辑在 `chunking.py:34-62`）。

## 三、embedding-service

- 模型 `bge-small-zh-v1.5`，ONNX Runtime CPU，CLS 池化 + L2 归一化，**512 维**（`app.py:11-17,52-56`；`README.md:3`）。
- 部署：单副本，`nodeSelector: orangepi5-max-server1`，`ORT_INTRA_OP_THREADS=4`（`k8s.yaml:11-52`）。NetworkPolicy 只放行 `embedding-client: "true"` 标签（`k8s.yaml:54-68`）。模型随镜像发布，构建时从 hf-mirror 下载（`README.md:5-14`）。
- 接口：`POST /v1/embeddings`，body `{model, input(1-16 条，每条≤8192 字符), input_type(passage|query)}`（`app.py:21-24`）；`query` 会加中文检索指令前缀（`app.py:47-48`）。
- 地址 `http://embedding-service.data.svc.cluster.local:8080`（`README.md:28`）。

> ⚠️ **单进程单推理 + 一把锁，并发请求一律 429**（`app.py:38-39`；`README.md:60-62`）。调用方**必须自带退避重试**（rag-service 已实现，`app.py:205-224`）。资源：requests 1C/512Mi，limits 4C/1Gi。

## 四、Elasticsearch

- 版本 **8.15.3**（`es/README.md:9`），单节点 StatefulSet + Ceph RBD 30Gi（`es/k8s/statefulset.yaml:1-120`），JVM `-Xms2g -Xmx2g`（`:53-54`），Basic Auth 密码来自 Vault（`k8s/configmap.yaml:15-16`）。
- IK 插件 `analysis-ik 8.15.3` 镜像内置，加载版本化词典 `domain-v1.dic`（`es/README.md:1,193-196`；`es/analysis/IKAnalyzer.cfg.xml`）。**词典或 analyzer 变更需重建镜像并重建受影响索引**（`README.md:194`）。
- 索引模板 `es/rag-index-template.json` **只匹配 `rag-agent-*-v*`**（`:2-3`），不会动其它索引；`_meta` 记录 embedding_model（`:54-57`）。
- 命名空间 `data`，`http://elasticsearch.data.svc.cluster.local:9200`（`es/README.md:16`）。

> ⚠️ **容量天花板：2GB 堆 → 约 20～35 万条向量**（`docs/rag-service-spike.md:14,135-138`）。

## 五、email-service

- `POST /send`，body `{"to","subject","body"}`（`server.py:24-58`）；`GET /health`（`:17-21`）。
- **body 以 HTML 发送**（`msg.set_content(content, subtype="html")`，`:44`）。SMTP 默认 `smtp.qq.com:465`，465 用 SMTP_SSL 否则 STARTTLS；缺 `to`/`subject` 返回 400（`:35-37,46-54`）。
- 集群地址 `http://email.email-service.svc.cluster.local`；封装 `send_email()` 在 `panghu_agent/tools/email_client.py:6,9-18`（失败返回 False 不抛异常）。
- 已有使用先例：research_agent 用它发"调研完成"通知（`panghu_agent/app/api/research_agent.py:81-90`）。

> ⚠️ 边界：**没有鉴权**（任何集群内 Pod 都能 POST）、**没有重试**（fire-and-forget）、**不能带附件**、无收件人/订阅管理、无模板。跑一份 HTML 日报够用，别指望它做投递系统。

## 六、content_agents —— 最该先看的一节

`panghu_agent/content_agents/`，namespace `content-agents`。文档：`README.md`、`PLAN.md`。

### 6.1 已在跑的 7 个 CronJob

见 `docs/platform-k8s-conventions.md` 第七节。与本主题最相关的两个：

- **`programmer-jobs-agent`** —— `0 20 * * *`（Asia/Shanghai），**多源招聘情报采集 + 中文日报**
- **`programmer-jobs-weekly-agent`** —— `30 20 * * 0`，**中文周报**
- `llm-guard-report-agent` —— `15 4 * * *`，取集群内数据渲染 Markdown 报告，是"日报类 agent"最直接的模板

### 6.2 可直接复用的公共骨架

| 模块 | 内容 | 出处 |
|---|---|---|
| `runner.py` | 主线 `run_agent(config, collector, renderer)`：采集→生成→规则审查→发布→台账/重试 | `common/runner.py:18-120` |
| `models.py` | `ContentItem`/`Candidate`/`SourceRef`，含 `content_hash` 去重键 | `common/models.py:15-113` |
| `channel.py` | 通道适配器 `json`/`rss`/`hublog` | `common/channel.py:13-109` |
| `storage.py` | 去重台账 JSONL（按 content_hash + 源 external_id） | `common/storage.py:11-138` |
| `review.py` | 规则审查/黑名单/自动放行 | `common/review.py:10-22` |
| `http.py` | HTTP 客户端（含 502 重试一次） | `common/http.py` |
| `source.py` | RSS/榜单抓取器（财联社、百度热榜、B 站） | `common/source.py` |
| `llm.py` | 直连 OpenAI 兼容 LLM | `common/llm.py` |
| `config.py` | 环境变量驱动配置 | `common/config.py:22-56` |

**LLM 接入方式**：content_agents 的 bot **不直接调 llm-service**，而是调共享的 `content-llm-service`（CrewAI）的批量业务接口 —— 例如 `programmer_jobs_agent/main.py:537-561` 调 `/v1/jobs/programmer-summary`。`content-llm-service` 再用 `deepseek-trusted` 调 llm-service（`content-llm-service/crew.py:8-25`、`k8s.yaml:46-51`），因为它需要 function calling。批量接口：`/v1/meme/judge-batch`、`/v1/github/enrich-batch`、`/v1/jobs/programmer-summary`、`/v1/jobs/programmer-weekly-summary`（`content-llm-service/app.py:97-183`）。

**发布**：Hublog 通道适配器，`/api/v1/posts` + Bearer + `Idempotency-Key`（`common/channel.py:62-95`）。`PLAN.md:130` 提到 email/Portal 适配器是**计划但未实现**。

### 6.3 programmer_jobs_agent 的既成事实

`panghu_agent/content_agents/programmer_jobs_agent/`，`main.py:1-807`：

- 多源采集：RAMoteJobsCN / Remotive / RemoteOK / AI Dev Jobs / JDWatch
- 一次批量 LLM 归纳
- **中文日报** `render_daily`（`main.py:731-761`）+ **周报** `render_weekly`（`main.py:764-786`）
- **礼貌抓取**：详情页间随机 3–10s、403/429 停手（`main.py:426-447`）
- JSON-LD 解析（`main.py:85-140,378-393`）、source_id 幂等去重（`:45-46`）

**数据源调研已完成**：`programmer_jobs_agent/Reference.md`（RSS / 公开 API / 开源聚合器 / 注意事项，含 1100+ 职位数据源目录的指路）+ `docs/jdwatch-work-research.md`（`jdwatch.work` 采集方式调研）。

> 📌 **定位说明**：`add-hermes-geopolitical-intelligence` 把就业情报采集作为**给 Hermes 的一个新任务**（评估性质，看效果），不是接替工程、也不要求并存。这一节对它的价值是：**数据源清单和抓取礼节直接沿用，不必重新调研**；同时这个 agent 每天 20:00 的现成日报是"看效果"最省力的参照物——同一天同一题材，两份报告放一起就能看出差异。见 [hermes-intelligence-review.md](hermes-intelligence-review.md) 第二、三节。

### 6.4 别的 agent 形态

- **CrewAI 异步 agent**（经 FastAPI，不是 CronJob）：`game_review_agent` 四段式流水线产出中文评测报告（`game_review_agent/crew.py:1-224`，report_task 在 `:195-216`）；`research_agent` 异步提交调研 → 研究员/分析师/撰写者 → Markdown 报告存**共享 SQLite**，支持检索/下载/可选邮件通知（`app/api/research_agent.py:62-93,106-188`）。
- 8 家合乎周礼系列 agent 跑在 `app/api/*.py` + `app/ui/*.py`，用 `deepseek-guarded`（`panghu_agent/README.md:170-175`）。

## 七、`docs/` 下已有调研

| 文档 | 主题 |
|---|---|
| `ARC.md` | Actions Runner Controller 科普/部署指南。与情报/RAG 无关 |
| `llm-service-abuse-defense.md` | 反代滥用防护调研：威胁模型、业界现状、杠杆排序（`:52-62`）、落实状态（`:86-96`）、为什么"固定 system prompt"与"注入检测器"没做（`:98-121`）、用量的替代方案是每日报告（`:123-134`） |
| `rag-service-spike.md` | RAG 可行性实测：ES/embedding 基准（hybrid 47ms、单条向量化 18.7ms、吞吐 48.7 docs/s）、索引 schema 草案（`:93-115`）、容量估算、风险 |
| `jdwatch-work-research.md` | `jdwatch.work` 就业信息采集方式调研（结论：职位聚合站 + 自动化爬虫管道） |

> ⚠️ `rag-service-spike.md:93-115` 的索引 schema 草案里有 `author/language/edition/copyright_status/ingest_ts` 等字段，但**实际实现的 mapping 未包含**（见 `rag-service/app.py:59-65`）。以代码为准。

## 八、"动手前先确认"清单

下面前四行是**平台级基础设施**——这些确实不该重复造，新服务一律接现成的。后几行是**先例与素材**：不一定要复用，但在重做之前应该知道它存在、考虑是否沿用。

### 8.1 平台基础设施（接现成的）

| 如果你要建… | 已有的东西 | 证据 |
|---|---|---|
| 向量库 / 检索 | rag-service（加 token 键即可扩 collection）+ ES IK + RRF | 第二、四节 |
| 文本向量化 | embedding-service（512 维，注意 429） | 第三节 |
| 报告投递 | email-service（HTML，research_agent 已在用） | 第五节 |
| 身份/令牌模式 | 每调用方一个 Vault 键、令牌名即身份 | `llm-service/auth.py`、`rag-service/auth.py` |

### 8.2 先例与素材（重做前先看一眼）

| 如果你要建… | 已有的东西 | 证据 |
|---|---|---|
| 定时采集 + 中文报告 | content_agents 骨架 + CronJob 约定 | 第六节 |
| 就业/招聘情报 | `programmer_jobs_agent`（日报 + 周报，已在跑）—— 也是 Hermes 就业任务的**参照物** | `cronjobs.yaml:87,129` |
| 就业数据源 | `programmer_jobs_agent/Reference.md` + `docs/jdwatch-work-research.md` | 第六节 |
| 批量业务级 LLM 归纳 | content-llm-service 的 `/v1/...` 接口模式 | `content-llm-service/app.py:97-183` |
| 报告归档/检索 | research_agent 的共享 SQLite + `/reports`/`/download` | `app/api/research_agent.py:145-188` |
| 去重/幂等 | `common/storage.py`（content_hash）+ Hublog `Idempotency-Key` | `channel.py:88` |
| 礼貌抓取 / HTML 解析 | `common/http.py`、`common/source.py`、`programmer_jobs_agent` 的 JSON-LD 解析 | 第六节 |
| 发布到 Hublog | `common/channel.py:62-95` 通道适配器 | 第六节 |
| LLM 调用（若选择统一接入） | llm-service 别名 + tier + 限流 + guard | 第一节 |

> 📌 `add-hermes-geopolitical-intelligence` 已定：Hermes 是独立服务、**自带 LLM 接入**，因此第 8.2 节的 llm-service 一行对它不适用。但这意味着 Hermes 侧要自己承担限流、额度记账和不可信内容防护 —— 见 [hermes-intelligence-review.md](hermes-intelligence-review.md) 第五节。

## 九、新 agent 的最小落点

若走 content_agents 路线：新增一个目录 + 在 `k8s/cronjobs.yaml` 加一个 CronJob + 在 ConfigMap / `build.sh` / `deploy.sh` 做好命名约定即可（`deploy.sh:21-26`；`build.sh`）。
