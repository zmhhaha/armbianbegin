# 稳定模型路由设计（待实施）

日期：2026-10-17，2026-10-18 登记并修订为直接迁移。本文为评审草稿，尚未实施或部署。已通过 `.openspec-project.json` 指定的 MCP 项目登记为 `add-stable-llm-routing`，校验通过、尚未 apply；最新提案提交为 `896a988a024ff1ba2823f082cb8cec719c8b8b28`。

## 目标与选择

调用方只选择能力档位，运维在 llm-service 集中选择上游。推荐稳定名称 `llm-guarded` 和 `llm-trusted`，一次迁移后，后续 DeepSeek / custom 切换不再修改业务服务。

逻辑路径：业务 model → 固定档位的稳定路由 → 当前上游配置 → Chat Completions。

不增加一个独立代理服务；在现有 llm-service 的配置解析层增加间接引用。上游故障仍返回错误，不自动切换提供商。

## 配置结构

采用版本 2 的配置结构，将现有重复的连接信息提取为 upstreams，将档位、超时和默认参数放在路由中。示意如下（完整迁移时必须保留现有各别名的参数）：

```json
{
  "version": 2,
  "active_upstream": "custom",
  "upstreams": {
    "custom": {
      "provider": "custom",
      "base_url": "https://custom-llm-proxy.panghuer.top/v1",
      "model": "gpt-6",
      "api_key_env": "CUSTOM_API_KEY",
      "max_retries": 1
    },
    "deepseek": {
      "provider": "deepseek",
      "base_url": "https://api.deepseek.com/v1",
      "model": "deepseek-v4-flash",
      "api_key_env": "DEEPSEEK_API_KEY",
      "max_retries": 2
    }
  },
  "routes": {
    "llm-guarded": {"tier": "guarded", "upstream": "$active", "timeout_seconds": 60},
    "llm-trusted": {"tier": "trusted", "upstream": "$active", "timeout_seconds": 120}
  }
}
```

以后只修改 `active_upstream`，两个稳定路由一起切换。`$active` 是保留引用，upstreams 禁止同名；只允许一层引用，不支持链式别名和循环。需要例外时，route.upstream 可以明确指定已登记的 upstream ID。

现有 `custom-guarded`、`custom-trusted`、`deepseek-guarded`、`deepseek-trusted` 保持固定上游语义，作为新格式中显式配置的选择入口。已有 `openai-trusted` 也迁移到新格式，不恢复已删除的 `custom-gpt-6`。这些固定路由是业务选择，不是旧格式兼容层。只接受 version=2 的 upstreams/routes 配置；缺少版本、旧 aliases 结构或未知版本一律报配置错误，不自动转换、不回退到旧解析器。同名路由冲突必须报错。

## 策略与请求

guarded/trusted 由请求所选路由确定，切换上游不得改变档位。guarded 继续禁止 tools/response_format，限制 2048 tokens、60 条消息；trusted 保留 tools/response_format，限制 8192 tokens、200 条消息。现有 guard 配置、调用方认证和限流继续生效。

参数合并顺序：路由默认参数 → 请求显式参数；合并后的最终参数再按档位校验，防止默认参数绕过限制。上游连接参数不允许请求覆盖；密钥只通过 api_key_env 获取。路由选择本身不是调用方授权机制，本次不引入调用方 tier ACL。

`/v1/models` 返回稳定路由和保留的固定路由。无需向供应商发现模型。非流式响应和 SSE 内容保留原有 OpenAI 兼容行为；不依赖响应 model 字段承担路由标识。

## 生效、发布与回滚

第一版沿用启动加载配置：修改版本化 ConfigMap，更新 Deployment 引用并滚动发布 llm-service。现有 Deployment 是单副本 Recreate，实施时需明确改为 RollingUpdate（maxUnavailable=0、maxSurge=1），并验证临时双 Pod 的资源容量及排空行为。业务服务无需修改或重启。此方案不是即时热更新，也不承诺多副本同时切换；滚动期间新旧 Pod 可短暂使用不同上游。

发布前验证完整配置及所有活动路由所需凭据；活动上游缺失、未知档位、重复名称、非法参数或缺少活动凭据时，新 Pod 不得 ready。未使用的保留路由缺密钥不应阻断服务（如 openai-trusted）。就绪不代表外网上游健康，需额外执行两个档位的真实请求验收。

每个请求只使用接收时所在 Pod 的不可变路由快照，SSE 期间不重选上游。首次迁移将新镜像与新格式 ConfigMap 作为同一次 Deployment 模板更新发布，禁止新镜像搭配旧配置。回滚首次迁移时一起恢复旧镜像、旧 ConfigMap 和对应调用方模型配置；迁移后的日常切换则恢复上一版新格式配置。滚动部署应保持可用副本并允许已接收请求排空；超长 SSE 超过终止宽限仍可能中断，客户端按原有错误策略处理。

## 可观测性和缓存

日志及用量增加 requested_alias、resolved_upstream、configured_model、tier、route_revision；非流式和流式都记录。禁止记录凭据、完整 prompt。响应头提供 `X-LLM-Route-Revision`，其值是有效非敏感路由配置的确定性摘要；密钥轮换不改变摘要。revision 包括上游 ID、URL、模型、默认参数、档位、防护参数，防止配置变化复用旧结果。只在服务内部记录 URL。

百家争鸣当前 model_used 保存的是请求模型名，稳定别名后不足以区分真实模型。第一版规定：对稳定路由关闭报告缓存复用，生成结果继续保存 requested_alias，新增可空 route_revision 元数据；固定路由维持当前行为。不能用请求前单独查询 revision 来假装解决一致性，因为滚动期查询与生成可能落到不同 Pod。后续若恢复缓存，需另行设计可校验且可固定 revision 的协议。实现前还须盘点其他调用方持久缓存；凡以别名作为模型身份的缓存均需禁用或建立正确隔离，不得只修一个调用方。

百家争鸣公共入口仍取 Deployment LLM_MODEL；内部入口和 legacy 入口仍取名册 llm_model。两者可填稳定路由，也可按业务需要显式固定路由；不重新混淆两条入口的模型来源。

## 实施顺序与验收

1. 直接替换为新格式解析、不可变解析结果和校验，删除旧格式解析路径；为旧格式/缺版本/未知版本拒绝、未知引用、缺凭据、档位不变、最终默认参数约束编写测试。
2. 接入非流式/SSE 路径，补充路由日志、revision 响应头及统计；测试并发请求不串路由、不泄漏密钥、故障不自动换供应商。
3. 处理调用方缓存；一次转换所有网关配置、示例、测试配置及部署清单。先同时发布新网关镜像与新格式配置，待全部网关 Pod 就绪后，将各业务配置和百家争鸣名册改为 llm-guarded/llm-trusted，保持原档位。固定路由在新格式中显式定义，允许调用方完成部署切换；不引入旧配置读取、转换或 fallback 机制。
4. custom 上游下验证普通回答、SSE、trusted JSON 和工具调用、guarded 拒绝受限字段。
5. 仅修改 active_upstream 为 deepseek，滚动 llm-service；确认业务配置未变，两个档位的新请求命中 DeepSeek，再回滚 custom 并复验。
6. 验证滚动期请求快照、错误配置不 ready、旧报告不被稳定路由复用。记录每个 Pod revision 及切换窗口。

所有步骤当前均未完成；本次只设计。
