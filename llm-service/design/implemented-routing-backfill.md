# 已实现模型接入与调用方迁移：OpenSpec 补录草稿

日期：2026-10-17，2026-10-18 补录。已通过 OpenSpec MCP 写入项目 ec663f5a-53d3-4a0e-9037-933eb788d183。变更 `backfill-custom-llm-integration` 校验通过，并以提交 `b6a563132600591bef6f0323e1acb96b5d1e0643` 合入正式规格 `custom-llm-integration`，新增 6 项要求，无校验问题或合入警告。远程 design.md 保留提交时的补录草稿，正式行为以主规格为准。

## 实现边界与证据

源码提交：主仓库 87a93e6，panghu_agent 9a4a1c1（此前内部模型路由 8bd5d84），panghu_game 88f8445。部署与测试证据来自本会话前序执行记录，本次仅复核相关源码，未重新执行部署或全部测试。

生产 15 个调用方 Deployment 已核验 LLM_MODEL。trusted：rag-service、content-llm-service、research-agent、scientific-agent、game-review-agent、literature-downloader。guarded：baijiazhengming、XuYe、TeWu、GuanLiao、QianFu、ShaPan agent-worker、School Of One 的 duel-judge/combo-judge/training-ground。TaShuo 只更新源码与部署配置，未有活动 Deployment，不能宣称已部署。

广泛迁移采用配置更新与滚动重启，未重新构建全部应用镜像；代码默认值已提交供后续构建使用。百家争鸣内部路由功能此前已单独构建部署。

## ADDED Requirements

### Requirement: Explicit custom upstream aliases
llm-service SHALL 提供 custom-guarded 和 custom-trusted，明确配置 provider=custom、model=gpt-6、base_url=https://custom-llm-proxy.panghuer.top/v1、凭据环境变量 CUSTOM_API_KEY；SHALL 使用 Chat Completions，不依赖上游模型发现。

#### Scenario: Route a custom request
- **WHEN** 已认证调用方提交有效 custom-trusted 请求
- **THEN** 服务使用服务器配置的凭据调用指定上游 /chat/completions，并返回兼容响应。

#### Scenario: Reject removed alias and caller routing overrides
- **WHEN** 调用方提交 custom-gpt-6 或未知别名，或尝试传入 base_url/api_key/provider
- **THEN** 服务拒绝请求；不恢复兼容别名，不采用调用方提供的上游连接参数。

### Requirement: Preserve tiers and explicit provider selection
服务 SHALL 保持 guarded/trusted 原有能力与 guard 策略；DeepSeek 固定别名 SHALL 保留。上游失败 SHALL NOT 导致自动切换供应商。

#### Scenario: Guarded capabilities remain bounded
- **WHEN** custom-guarded 请求包含 tools 或 response_format，或超过档位消息/token 限制
- **THEN** 请求被拒绝，边界为 60 条消息和 2048 max_tokens。

#### Scenario: Trusted standard capabilities
- **WHEN** custom-trusted 请求包含合法 tools 或 response_format 且处于 200 条消息、8192 max_tokens 限制内
- **THEN** 这些字段按原有契约转发上游。

### Requirement: Public and internal persona model sources
百家争鸣公共 POST /v1/agents/{slug}/tasks SHALL 使用 Deployment 的 LLM_MODEL；内部 POST /v1/internal/agents/{slug}/tasks 及 legacy POST /{service_name} SHALL 使用名册 llm_model。两个入口沿用 BAIJIA_API_TOKEN，不引入单独内部凭据；请求体不提供任意模型选择。

#### Scenario: Internal registry choice
- **WHEN** 内部调用提交名册已登记 persona 的任务
- **THEN** 对应 llm_model 被捕获到任务，并通过 runtime、plugin、Crew factory 传入 LLM；不得修改进程全局环境来切换模型。

#### Scenario: Public UI choice
- **WHEN** UI 经公共接口提交任务
- **THEN** 使用 LLM_MODEL，名册 llm_model 不覆盖公共入口配置。

### Requirement: Model-aware persona report cache
报告查询 SHALL 以任务选定模型名过滤缓存，保存结果时记录 model_used。当前 model_used 表示请求别名，不保证等同供应商返回的真实模型 ID。

#### Scenario: Different model aliases
- **WHEN** 主题相同但选定模型名不同
- **THEN** 不复用另一模型名下的报告。

### Requirement: Preserve capability tier during consumer migration
通过 llm-service 生成内容的既有调用方 SHALL 将 guarded 默认和部署配置迁移为 custom-guarded，将 trusted 迁移为 custom-trusted，并保持既有调用方 token 与档位分工。

#### Scenario: Running deployment migration
- **WHEN** 已运行调用方完成配置同步和滚动重启
- **THEN** Pod 实际 LLM_MODEL 与迁移后的别名一致；未部署应用仅记录配置已更新。

### Requirement: HTTPS relay transport
custom 上游 SHALL 通过 VPS 的 custom-llm-proxy.panghuer.top HTTPS 443 入口转发到既有 https://jingsi.asia:9080 上游。集群调用方不需要开放本地入站 9080。llm-service 保持 ClusterIP、调用方 token 与 llm-client 标签入口限制，出站允许 DNS 和 443。

#### Scenario: Cluster reaches custom upstream
- **WHEN** llm-service 转发 custom 别名请求
- **THEN** 经 HTTPS 443 连接中转入口，由 VPS 代理访问上游 9080。

## 验证记录

- 百家争鸣模型路由 unittest 4 项、literature_downloader 7 项、XuYe 13 项、GuanLiao Vitest 9 项、TaShuo Vitest 4 项通过。
- YAML/Python/Node 相关语法及 git diff 检查通过。
- 前序已验证 custom 普通响应、SSE 与八 persona 真实调用。
- custom-trusted JSON object 请求返回 200 及有效 JSON；required function tool 请求返回 200 及有效 tool_calls 参数。
- 15 个 Deployment 的实际 Pod 模型配置和 rollout 已核验。
- 上述是完成部分的历史证据，不代表未来稳定别名架构已实现或验证。
