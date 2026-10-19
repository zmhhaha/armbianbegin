# 接入 llm-service（调用方接入规范）

给**要把模型调用接到集群内 `llm-service` 的服务**看。照着做完就能调通，且不会撞上服务端的边界。

服务本身的边界、别名策略、错误处理语义见 [README.md](README.md)；这份文档只讲**调用方要做什么**。

---

## 0. 先定三件事

|  | 怎么定 | 影响 |
|---|---|---|
| **调用者名**（caller） | 小写、连字符，全集群唯一，通常就是服务名 | 决定 Vault 键名和用量统计里的身份 |
| **用哪个别名** | 用户会写 prompt → `guarded`；否则 → `trusted` | 决定能力面（见 §1，判错的两种情况见 §1.1） |
| **要不要函数工具 / `text.format`** | 要 → **必须** `trusted` | `guarded` 会 400 |

---

## 1. 选别名

普通业务使用稳定别名 **`llm-guarded` / `llm-trusted`**，上游由网关的 `active_upstream` 集中选择。`tier` 只有两档：

| 别名 | tier | 能力 | 给谁用 |
|---|---|---|---|
| `llm-guarded` | guarded | **禁** `tools` / `tool_choice` / `text.format`；显式 `max_output_tokens` ≤ 2048、规范化消息 ≤ 60 | 用户能自己写 prompt 的对话型服务 |
| `llm-trusted` | trusted | 支持的函数工具与结构化输出；显式 `max_output_tokens` ≤ 8192、规范化消息 ≤ 200 | 服务端生成、RAG、函数调用、内部机器对话 |
| `openai-trusted` | trusted | 同 trusted | **预留**：Vault 里只有一个占位 key，点名会带着它打到 OpenAI 拿 401 |

**普通业务的默认判断标准：用户能不能左右这段 prompt？**

- 能（对外对话 Agent）→ `guarded`。这是安全默认，选它最坏情况是「少了个能力」，选错 `trusted` 则是「用户能借你的服务白嫖任意 LLM 调用」。
- 不能（RAG 生成、定时任务、Agent 内部的中间步骤）→ `trusted`。

**选错的典型症状**：400，内部错误可能显示 `does not allow tools` 或 `response_format`；公共格式字段是 `text.format`。

DSH、Hermes、Pi 使用应用内配置的 `custom-llm` 公网直连，其专用网关别名已退役。
三者的配置方法见 [直连接入记录](../panghu_chat/docs/agents-custom-llm.md)。

使用网关的调用方需验收 Responses 参数、typed SSE 与函数工具往返。请求体拒绝未知字段，输出预算、工具数量和规范化后的消息数须符合档位限制。

调用方统一向 `/v1/responses` 发送 Responses 请求。custom 原生使用 Responses；DeepSeek 出站仍用 Chat Completions，由网关转换回 Responses。切换稳定别名的活动上游不要求业务更换入口，边界见 §4.7。

trusted 表示网关允许字段，不保证供应商支持全部参数组合。DeepSeek 默认思考模式支持 `tool_choice=auto`，不支持 `required`（上游返回 400）；跨供应商业务应使用共同支持的参数。本服务不静默改写 tool_choice 或关闭思考模式。

**需要别的 provider 或档位**时，在 `llm-service/k8s.yaml` 的新格式配置中登记 upstream，并通过 routes 引用，
需要独立切换模型的应用可登记自己的稳定别名，规则见 README「别名命名约定」。加别名不需要改任何代码。

**同一个服务两种用法**（对外的走 guarded、机内的走 trusted）→ 按代码路径选不同别名，不用开两个服务。

### 1.1 「程序生成」不等于「没有玩家文本」

上面那条判据是对的，但有两种情况会让你把它判错。

**① 模型自己的输出会绕回来。** 你看到某段内容来自世界状态、不是玩家打的字，就判它是「程序生成」——
但那段文字可能是**上一次模型调用写回去的**，而上一次调用里带着玩家输入。链子是：

```
玩家打字的输入 → 调用 A（guarded）→ 模型输出 → 写进状态 → 调用 B 的输入
```

- ShaPan：`local_battle` / `unit_autonomy` / `enemy_action` 都不含玩家文本，但后两者的
  `knownContext.ownState` 是整个 `unitStates[id]`，里面有 `summary`，而 `summary` 是更早的
  `order_response` 任务（带玩家军令原文）写回的。
- School of One：`duel-judge` / `combo-judge` 的输入是牌面 `description`，看着就是内容包数据；
  但自定义牌的 `description` 是玩家输入经 LLM 改写后存下来的（闭关模式的产出）。

判这种链子时，问的不是「这段文字谁生成的」，而是「**沿这条链往回走，能不能走到一个玩家能打字的输入框**」。

**② 一个调用点不等于一种任务。** 同一个 `fetch` 可能按 `jobType` 服务好几种任务，其中只有一种带玩家文本。
ShaPan 就是这样：一个调用点、四种任务、一个别名。这种情况档位只能就高（`guarded`），
除非你愿意按任务类型配两个别名分开选 —— 通常不值，见下。

**参考：`panghu_game` 的实际分配**（2026-09 审计，比照 `migrate-game-llm-to-service`）

| 服务 | 调用点 | prompt 里有玩家自由文本吗 |
|---|---|---|
| School of One · training-ground | 4 | 有，四处全有（`student_description` + 累积 history） |
| School of One · duel-judge | 3 | 表面没有 —— 但牌面 description 可能是玩家输入的改写版，见 ① |
| School of One · combo-judge | 1 | 同上 |
| TeWu | 2 | 有（`question` + `history`） |
| QianFu | 4 | 有（`playerText`；`plan.objective/steps/safeguards/abortCondition`；`terms.purpose/abortCondition`） |
| ShaPan | 1 个调用点 / 4 种任务 | 只有 `order_response` 有；其余见 ① |
| GuanLiao | 2 | 有（`orderText` / `receivedText`） |
| TaShuo | 3 | 有（评论、报告） |
| XuYe | 1 | 有（玩家写入的续写文字，在 user 消息里） |

这张表的用途不是照抄，是**别把档位分配当成顺手选的**：档位就是授予能力的地方。
哪天某个服务要用 `tools`，回来查这张表 —— 那才是需要认真判一次的时候。

**拿不准就选 `guarded`。** 能力分档应按输入来源与实际工具需求判断；将模型生成内容绕回下一轮输入，不会自动把来自用户的内容变成可信输入。

> 一个反直觉的细节：`deepseek-trusted` 的 `defaults` 里带 `max_tokens: 2048`，而 `deepseek-guarded` 不设。
> 这是内部默认参数名。对自己不发 `max_output_tokens` 的公共调用方，从 guarded 换到这个固定 trusted 路由，反而会收紧输出长度。

---

## 2. 申请一个调用方令牌

**每个调用方一个专属令牌，互不可见。** 令牌即身份：`llm-service` 从 `LLM_TOKEN_<CALLER>`
这个**环境变量名**反推调用者名，客户端无法自称是谁。

命名规则：

```
调用者名 zhougongjiemeng  →  Vault 键 LLM_TOKEN_ZHOUGONGJIEMENG
调用者名 game-review      →  Vault 键 LLM_TOKEN_GAME_REVIEW
调用者名 content-llm-service → LLM_TOKEN_CONTENT_LLM_SERVICE
```

即：**大写，连字符换下划线**。

写入 Vault（用 `kv patch`，别用 `kv put` 覆盖掉别人的键）：

```bash
kubectl -n vault exec vault-0 -- vault kv patch secret/llm-service/callers \
  LLM_TOKEN_<CALLER>="$(openssl rand -hex 32)"
```

> ⚠️ **不要打印令牌的值**。核对时只用 `kubectl describe secret`（它只显示字节数）。
> 命令输出会落进日志/终端记录，等于把凭据抄了一份出去。

---

## 3. 把令牌投进调用方的 Pod

### 3.1 ExternalSecret

复制 [panghu_agent/k8s/llm-token-externalsecret.yaml](../panghu_agent/k8s/llm-token-externalsecret.yaml)
这份模板，改两个占位符即可：

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: llm-token
  namespace: __NAMESPACE__
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: llm-token
    creationPolicy: Owner
  data:
    - secretKey: LLM_SERVICE_TOKEN        # ← 固定，不要改
      remoteRef:
        key: secret/data/llm-service/callers
        property: __VAULT_TOKEN_KEY__     # ← 你的 LLM_TOKEN_<CALLER>
```

要点：

- `secretKey` **固定叫 `LLM_SERVICE_TOKEN`** —— 消费方代码统一读这个名字，变的只是里面的值。
- `property` 只取**你自己那一个键**。这就是「拿不到别人的令牌」的实现方式，别改成 `dataFrom.extract`。
- 同步失败时先看 `kubectl describe externalsecret llm-token -n <ns>` 的 Events。
  最常见的两种：Vault 里键名拼错 → `Secret does not exist`；Vault 被 seal → 见 README 排查 §4。

### 3.2 Pod 标签与环境变量

```yaml
spec:
  template:
    metadata:
      labels:
        llm-client: "true"        # 通用调用方的入站放行条件，当前 Calico 会实际执行。
    spec:
      containers:
        - name: api
          env:
            - name: LLM_BASE_URL
              value: http://llm-service.llm.svc.cluster.local/v1
            - name: LLM_MODEL
              value: llm-trusted            # ← 按 §1 选
            - name: LLM_SERVICE_TOKEN
              valueFrom:
                secretKeyRef:
                  name: llm-token
                  key: LLM_SERVICE_TOKEN
```

`LLM_BASE_URL` 是**基址**（已含 `/v1`），代码拼 `/responses`。

DSH、Hermes、Pi 原有的专用网络例外已退役；未来如有新的网关调用方，仍需按本节
配置鉴权及网络访问，不因应用名称自动放行。清理记录见 [专用网关退役记录](design/agent-routing-integration.md)。

---

## 4. 代码里怎么调

业务统一使用 **`POST /v1/responses`**。网关根据路由选择出站协议，业务不能传入 `wire_api`、provider 地址或供应商密钥。

### 4.1 读取三个环境变量

```python
import os

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").rstrip("/")
LLM_TOKEN = os.getenv("LLM_SERVICE_TOKEN", "").strip()
LLM_ALIAS = os.getenv("LLM_MODEL", "llm-trusted")
if not LLM_BASE_URL or not LLM_TOKEN:
    raise RuntimeError("需要 LLM_BASE_URL 与 LLM_SERVICE_TOKEN")
```

进程启动即依赖模型时应尽早失败；模型只是可选增强时，在健康检查中报告 degraded。令牌只放在 Authorization 头中。

### 4.2 非流式请求与响应

```python
import httpx

with httpx.Client(timeout=120) as client:
    response = client.post(
        f"{LLM_BASE_URL}/responses",
        headers={"Authorization": f"Bearer {LLM_TOKEN}"},
        json={
            "model": LLM_ALIAS,
            "instructions": "请用中文回答。",
            "input": "介绍一下这个项目。",
            "store": False,
        },
    )
    response.raise_for_status()
    result = response.json()

if result["status"] == "incomplete":
    raise RuntimeError(f"模型输出未完成: {result.get('incomplete_details')}")
if result["status"] != "completed":
    raise RuntimeError("模型未正常完成")

answer = "".join(
    part["text"]
    for item in result["output"]
    if item["type"] == "message"
    for part in item["content"]
    if part["type"] == "output_text"
)
calls = [item for item in result["output"] if item["type"] == "function_call"]
```

`input` 可以是字符串，也可以是完整历史列表；`instructions` 转为前置 system 消息。普通示例：

```json
{
  "model": "llm-trusted",
  "store": false,
  "input": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "您好"},
    {"role": "user", "content": "继续"}
  ]
}
```

用户图片采用 `{"type":"input_image","image_url":"https://...","detail":"low"}`，与 `input_text` 一起放在 user 的 content 数组中。文件 ID、音频和未知内容类型会被拒绝。

顶层支持 `model`、`input`、`instructions`、`temperature`、`top_p`、`max_output_tokens`、`tools`、`tool_choice`、`text`、`stream`、`store`。公共请求不能继续使用 Chat 的 `messages`、`max_tokens`、`response_format`、`stop`、`seed`、`n` 或 penalties 字段。

### 4.3 函数工具与完整历史

只有 trusted 档允许函数工具和结构化输出。Responses 工具定义使用扁平结构：

```json
{
  "model": "llm-trusted",
  "store": false,
  "input": "查询北京的天气",
  "tools": [
    {
      "type": "function",
      "name": "weather",
      "description": "查询城市天气",
      "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
        "additionalProperties": false
      },
      "strict": false
    }
  ],
  "tool_choice": "auto"
}
```

输出中的 `function_call` 包含 `call_id`、`name`、字符串形式的 `arguments`。由业务校验工具名与参数，执行允许的工具后，把原输出中的可重放 message / function_call 项和结果追加到历史，发起下一轮：

```json
{
  "model": "llm-trusted",
  "store": false,
  "input": [
    {"role": "user", "content": "查询北京的天气"},
    {"type": "function_call", "call_id": "call_1", "name": "weather", "arguments": "{\"city\":\"北京\"}"},
    {"type": "function_call_output", "call_id": "call_1", "output": "晴，20℃"}
  ]
}
```

保留每个 `call_id`；并行工具结果按对应 ID 关联。网关不执行工具，不提供内置 web/file/MCP 工具。工具函数的 `strict` 应显式填写：从旧 Chat 迁移并希望保持宽松语义时使用 `false`；省略时按 Responses 的严格默认值处理。

当前历史子集不接受 reasoning 项、非空输出 annotations 或其他无法转换的元数据。每次请求带上完整可重放历史，不能使用 `previous_response_id`、`conversation` 或 `store: true` 依赖上游保存状态。

SDK 输出项的 `model_dump()` 可用于上述历史，包括 `namespace: null`、`phase: null`、`logprobs: null`；phase 也接受 `commentary` 与 `final_answer`。非空工具 namespace 会被拒绝，因为 Chat 上游无法表达它。

### 4.4 JSON 输出

结构化输出通过 `text.format` 指定，不能发送旧的 `response_format`：

```json
{
  "model": "llm-trusted",
  "store": false,
  "input": "用JSON给出答案",
  "text": {
    "format": {
      "type": "json_schema",
      "name": "answer",
      "schema": {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": false
      },
      "strict": true
    }
  }
}
```

也支持 `{"format":{"type":"json_object"}}` 和文本格式。guarded 档禁止显式 `text.format`。供应商仍可能拒绝某个格式或 Schema 组合，调用方不能把格式错误吞掉后当成成功 JSON。

### 4.5 流式、预算与失败

设置 `stream: true` 后，客户端始终收到带 `type` 的 Responses SSE：

- `response.created` / `response.in_progress`：生成开始。
- `response.output_text.delta`：正文增量。
- `response.function_call_arguments.delta`：工具参数增量；结合 output item 的 `call_id`、name 和索引处理。
- `response.refusal.delta`：拒绝内容增量。
- `response.completed` / `response.incomplete`：终态对象，包含完整 output 与 usage。
- `error`：上游失败、协议错误或中途断流；不能当作成功。

Responses 不以 Chat 的 `[DONE]` 作为完成标志。流已建立后的 HTTP 200 只表示连接成功：发生 error 或 EOF 前没有正常终态，都应按生成失败处理。一旦开始发送内容就不再自动重试，避免重复输出。上游 4xx 原状态返回；连接阶段耗尽重试后返回 502。

`usage` 使用 `input_tokens`、`output_tokens`、`total_tokens`，并带缓存与推理 token 详情。网关 `/v1/usage` 的汇总仍使用 `prompt_tokens` / `completion_tokens`。DeepSeek 的私有 `reasoning_content` 不会被拼成正文。

显式 `max_output_tokens` 的上限为 guarded 2048、trusted 8192。它同时覆盖推理和正文；预算耗尽时可能没有正文，终态为 `incomplete`，原因是 `max_output_tokens`。不要仅凭 HTTP 200 判断长文生成成功。省略预算且路由 defaults 没有默认值时使用上游默认预算；省略预算不是成本上限。

请求超时应覆盖完整生成时间。单轮对话可从 60 秒起观察，长文与结构化输出可从 120 秒起观察，并按实际 `latency_ms` 调整。

### 4.6 SDK 与防护

使用支持 Responses 的 SDK：

```python
from openai import OpenAI

client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_TOKEN)
result = client.responses.create(
    model=LLM_ALIAS,
    input="你好",
    store=False,
)
```

框架默认的 ChatCompletion 客户端不能只替换 URL 后继续使用。CrewAI 等框架需使用项目提供的 Responses 适配层，或明确选择 Responses 调用方式；不要把供应商凭据交回业务 Pod。

guarded 请求默认会包裹 user 内容、补充 system 声明与随机 canary。trusted 默认不做这些改写；检测与用量统计仍按调用方归因。流式 canary 命中且策略为 reject 时会截断输出，已发送部分无法撤回。

网关和调用方都不应静默切换供应商或别名。需要业务降级时应明确返回降级状态。诊断当前防护模式可调用 `GET /v1/guard`。

### 4.7 上游与滚动迁移

业务入口始终是 `/v1/responses`：

| 活动上游 | 网关出站 | 网关返回给业务 |
|---|---|---|
| custom，`wire_api: responses` | 原生 `/v1/responses` | Responses 对象与 typed SSE |
| DeepSeek，默认 `wire_api: chat_completions` | `/v1/chat/completions` | 转换后的 Responses 对象与 typed SSE |

`wire_api` 只由网关配置决定，别名、token、档位策略与切换方式不变。SDK 或模型可能不支持某些参数组合，例如 DeepSeek 的思考模式可能拒绝强制工具选择；应测试实际使用的参数，不能依赖网关静默改写。

旧 `/v1/chat/completions` 入口已 deprecated，仅用于滚动更新期间接住旧 Pod。新业务与迁移后的业务应使用 Responses。迁移包括路径、请求体、响应解析、工具循环与 SSE 事件，不能只替换路径。

---

## 5. 错误语义（调用方视角）

| 状态 | 含义 | 你该做什么 |
|---|---|---|
| 400 | `unknown model alias` | 别名拼错，或服务端还没配这个别名。查 `GET /v1/models` |
| 400 | `does not allow tools` / `text.format` | 你在 `guarded` 别名上用了扩权字段 → 换 `trusted` |
| 400 | `max_tokens exceeds the cap` / `too many messages` | 撞档位上限。`guarded` 上限低，别拿它跑长上下文 |
| 400 | Responses 不支持该参数或结构 | 对照 §4 修改请求；不能传服务端状态、内置工具或无法转换的历史 |
| 401 | `invalid caller token` | 令牌不对或没同步。查 `llm-token` ExternalSecret 是否 Ready |
| 422 | 请求体有非法字段 | 检查是不是传了 §4.2 列的「改路由」字段 |
| 429 | 超限流 | 默认每调用方 120 请求/分钟。带 `Retry-After` 退避 |
| 502 | 上游故障 / 响应无效 / **别名缺凭据** | 见下 |
| 503 | 服务端本身没配好（`LLM_TOKEN_*` 一个都没有）或配置错误 | 找运维，不是你的问题 |

**502 要注意**：它同时覆盖三种情况 —— 上游超时/5xx、上游给了 2xx 但响应体无效、
**以及别名本身没有 provider 凭据**（此时 message 里会写「别名 X 缺少凭据（ENV 未注入）」）。
看到 message 提「凭据」说明是运维配置问题，重试无用。

服务端把防护调到更强模式后，还会多出这两种（**默认都不开**，要运维显式配置）：

- `400 request blocked by prompt-injection detection` —— `detection=reject`
- `502 response withheld: system prompt leakage detected` —— `canary_action=reject`

---

## 6. 接入检查清单

- [ ] 调用者名定了，小写连字符
- [ ] 别名按 §1 选好，确认不会用到 `guarded` 禁的能力；判「有没有玩家文本」时对照 §1.1
- [ ] Vault `secret/llm-service/callers` 里有 `LLM_TOKEN_<CALLER>`（`kv patch` 加的，没用 `kv put` 覆盖）
- [ ] ExternalSecret 已 apply，`kubectl get externalsecret llm-token -n <ns>` 是 `SecretSynced=True`
- [ ] Pod 带 `llm-client: "true"` 标签，或属于已登记的专属入站规则；客户端出站也允许访问网关
- [ ] 三个环境变量都注入了（`LLM_BASE_URL` / `LLM_MODEL` / `LLM_SERVICE_TOKEN`）
- [ ] 代码在变量缺失时早失败，或在健康检查里报 degraded
- [ ] 用 `guarded` 档的话，确认 §4.6 的 prompt 改写不影响你的输出解析或缓存策略
- [ ] `/v1/responses` 普通请求成功；若使用 SSE / 函数工具 / JSON 输出，也完成对应验收
- [ ] llm-service 日志里那条 `{"event":"chat", "caller":"<你的名字>" ...}` 的 caller 是**你自己的名字**，不是 `unknown`

最后一条最关键 —— 它是「令牌真的按 per-caller 生效」的唯一证据。

---

## 7. 参考实现

| 场景 | 看哪个 |
|---|---|
| 最简单：httpx 直调 | [`rag-service/app.py`](../rag-service/app.py) |
| Responses 适配层 + 函数调用 | [`panghu_agent/content-llm-service/crew.py`](../panghu_agent/content-llm-service/crew.py) |
| Responses `text.format` JSON 输出 | [`panghu_agent/literature_downloader/search_planner.py`](../panghu_agent/literature_downloader/search_planner.py) |
| 多 Agent 共享一个 LLM 工厂 | [`panghu_agent/research_agent/crew.py`](../panghu_agent/research_agent/crew.py) |
| 可选增强 + 健康检查降级 | [`panghu_agent/app/api/research_agent.py`](../panghu_agent/app/api/research_agent.py) |
