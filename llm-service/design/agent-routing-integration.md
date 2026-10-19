# DSH、Pi、Hermes 独立模型路由与后续接入

OpenSpec change：`add-independent-agent-routes`，项目映射见仓库根 `.openspec-project.json`。

## 当前接入选择（2026-10-19）

三个通用 Agent 选择自行管理提供方并直连 `custom-llm`，配置与验证状态见
[DSH、Hermes、Pi 接入记录](../../panghu_chat/docs/agents-custom-llm.md)。DSH 已验证对话，
Hermes 已收到用户成功反馈，Pi 已提供教程、待确认执行结果。

本文件保留此前的可选网关方案及其验证记录。三条网关路由和网络例外仍保留；
直连不使用网关调用令牌，也不受此处网关参数限制影响。下文的 DeepSeek 初始配置和
待接入步骤是网关方案实施时的记录，不代表三个 Agent 当前都必须接入网关。

## 本次网关配置

| 应用 | 固定请求别名 | 初始共享上游 | 初始实际模型 |
|---|---|---|---|
| DSH | `dsh-trusted` | `custom` | `gpt-6-astra` |
| Pi | `pi-trusted` | `custom` | `gpt-6-astra` |
| Hermes | `hermes-trusted` | `custom` | `gpt-6-astra` |

三条路由均为 trusted，超时 120 秒，直接引用现有 upstream。分别修改
`routes.<别名>.upstream` 即可独立选择 `custom`、`deepseek` 或其他已登记上游。
共享 upstream 的模型、地址和凭据引用统一维护；修改共享模型会影响所有引用它的路由。
`active_upstream` 和 `UPSTREAM=...` 仅选择普通业务的 `$active` 路由。

配置以仓库为准，同时维护 `k8s.yaml` 和 `config.example.json`，同步后执行
`bash llm-service/deploy.sh --skip-build`。路由不继承其他别名的 defaults。
现有 v2 解析器、网关镜像、调用方鉴权和请求快照机制均可直接使用。

## 后续客户端接入

网关路由与三个主 Agent Pod 的网络通路已纳入配置；应用里的模型设置由所有者另行配置。
网络可达不代表原生模型协议已经通过验收。

共同地址：`http://llm-service.llm.svc.cluster.local/v1`，协议为 Chat Completions。
分别申请 `LLM_TOKEN_DSH`、`LLM_TOKEN_PI`、`LLM_TOKEN_HERMES`，客户端 Secret
只映射自己的调用令牌。网络采用专属策略，无需修改 Pod 标签或重启 Agent：

- 三个应用各自的 `k8s/llm-egress.yaml` 只选择 `dsh/app=dsh-web`、`pi/app=pi`、
  `hermes/app=hermes-web`，目标同时匹配 `namespace=llm` 和 `app=llm-service`。
- `llm-service/k8s.yaml` 的 `llm-agent-clients` 入站规则只接受上述三个 namespace + app 组合。
- 端口为 TCP 8000，Calico 按 Service DNAT 后的目标 Pod 端口匹配；客户端仍访问 Service 80。
- 普通调用方继续使用 `llm-client: "true"` 规则。DSH runner、Hermes publisher 和旧 pi-cage
  未包含在此次例外中。NetworkPolicy 的作用范围是整个 Pod，包含同 Pod 的其他容器和进程。
- 本阶段只开放网络，没有签发新调用令牌，也没有修改应用模型设置。无令牌请求模型接口应返回 401。

### DSH

- 已从部署的插件确认：Settings → Models 支持手工添加 custom provider、endpoint、
  `api: openai-completions` 和模型列表，无需从上游拉模型目录。
- provider 使用网关和 `apiKeyEnv`，模型填写 `dsh-trusted`。原生 `/model` 或输入框模型控件
  可切当前会话；默认模型用于新建 Agent，已有会话需单独选择。
- 已安装 pi-ai 的兼容选项可关闭 `supportsUsageInStreaming`，并将 `maxTokensField`
  设为 `max_tokens`；DSH 模型设置支持 `reasoningEfforts: false`。这些是待验收的接入候选配置，
  不能据此声称工具循环已可运行。
- 仓库入口：`panghu_chat/dsh/k8s/web.yaml`、`k8s/llm-egress.yaml`、
  `vault/inventory/dsh-externalsecret.yaml`。原生用户 profile 由 DSH 持久化管理。
- 模型请求由 web 发出，runner 负责远端工具执行；后续验证应包含工具执行和结果回传。

### Pi

- 已从线上安装包文档确认：`models.json` 可注册自定义 provider 的 `baseUrl`、
  `api: openai-completions`、凭据环境变量和模型列表，模型填写 `pi-trusted`。
- 原生 `/model` 可选择并重新加载模型配置，Ctrl+S 保存新会话默认；`/scoped-models`
  设置 Ctrl+P 的轮换范围。网页封装的实际入口需对应部署实例确认。
- 仓库入口：`panghu_chat/pi/k8s/core.yaml`、`k8s/llm-egress.yaml`、
  `vault/inventory/pi-externalsecret.yaml`，持久 home 是 `/home/pi`。
- 已核对 frpc 的 `pi.panghuer.top` 路由指向 `pi-web.pi.svc.cluster.local:4180`，目标是
  `pi/pi`。旧 `pi-cage/pi-cage` 及其数据已删除。原生配置路径后续已核对为
  `/home/pi/.pi/agent/models.json`，具体操作见上方直连接入记录。
- 本次未验证 Pi 实际发送的全部参数，仍需检查输出上限、推理字段、流式与工具循环。

### Hermes

- 网关方案调查时，线上 `/opt/data/config.yaml` 的 model 使用 `deepseek-flash`、provider deepseek、
  `https://api.deepseek.com/v1` 和 `api_mode: chat_completions`。
- 通过原生 provider 配置改为网关地址、自己的令牌和 `hermes-trusted`，保留其他 profile 设置。
- 当时核对的日报任务 model、provider、base_url 均为空；网关迁移仍需验证网页会话和原生调度器
  实际继承网关配置，不以单独的连通探测代替原生任务验证。
- 仓库入口：`panghu_chat/hermes/k8s/core.yaml` 的 web Pod、`k8s/llm-egress.yaml`、
  `vault/inventory/hermes-externalsecret.yaml`。无模型的 publisher 不参与接入。

### 接入验收边界

网关拒绝未知顶层请求字段，目前不接受 `stream_options`、`max_completion_tokens`、
`reasoning_effort`；请求中的 max_tokens 上限 8192、消息上限 200、工具上限 32。
应先验证原生客户端的兼容配置，必要的协议扩展另行明确设计和测试。
验收至少覆盖短对话、SSE、工具调用与结果回传、多轮以及默认模型的持久化。
切换只影响配置生效后的请求，正在进行的请求继续使用已有快照；长会话后续请求可能采用新模型。

## 网关验证

- 现有 unittest：54 项通过。
- 部署清单与示例 JSON 一致；三个别名初始绑定、档位、超时与模型符合设计。
- 分别切换任意一个新别名时，其余路由的解析结果保持相同。
- 修改 active_upstream 不改变三条显式绑定；共享 model 更新影响所有引用它的路由。
- 单独切到 deepseek 不继承 deepseek-trusted 的默认 max_tokens。
- 两个 active_upstream 的部署渲染均保留三条显式绑定，ConfigMap 名称与 Deployment 引用匹配。
- 本地 `/v1/models` 与 `/health/ready` 均返回三条新路由。
