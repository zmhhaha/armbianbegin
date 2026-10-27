# Pi 图片工具历史的原生 Responses 转发

Pi 0.73 读取图片后，会将工具结果编码成 `function_call_output.output` 数组，包含文字说明和内嵌图片。原公共入口先将 Responses 历史转换为 Chat，再由原生上游适配器转回 Responses；Chat 的工具结果不能表达图片，这条路径会拒绝第二次模型请求。assistant 的 `phase` 也不应在原生上游路径中消失。

本补丁只修复 Pi 当前需要的历史传递，不增加 Hermes 的 `reasoning`、`include`、`parallel_tool_calls` 请求字段，也不改变模型、凭据、别名或路由配置。

## 请求与路由

出站协议取自选定别名的不可变 `wire_api`，不根据模型名或供应商名推断。`responses` 路由直接发送受限原生 body，独立保留 `input`、`instructions`、函数工具定义、`tool_choice`、生成参数，以及 SDK 可空字段。配置中的模型覆盖请求别名，`store` 固定为 `false`；配置 defaults 仍转换并合并，显式公共参数优先。

支持的历史包括消息、`function_call` 和 `function_call_output`。assistant 的 `phase` 仅接受空值、`commentary` 或 `final_answer`；工具结果必须引用同一请求中此前出现的调用 ID。工具结果可以是字符串，或包含以下两类项的数组：

```json
[
  {"type": "input_text", "text": "Image read from preview.png"},
  {"type": "input_image", "image_url": "data:image/png;base64,iVBORw0KGgo=", "detail": "auto"}
]
```

示例只演示协议结构，图片数据不是可用于真实视觉验收的完整图片。工具图片的媒体类型限定为 PNG、JPEG、WebP；detail 使用协议有限值。工具图片只能内嵌，不能以 URL 或文件 ID 引用。既有 user 消息的图片 URL 支持保持原契约，网关不自行请求图片 URL。每条消息内容及工具结果数组限定为 1–200 项，历史限定为 1–200 项，并计入档位消息数上限。未知项、远程会话/响应/文件引用、托管工具、非空工具 namespace、reasoning 历史和非空 annotations 继续拒绝。

`chat_completions` 路由继续走既有适配器。文本工具结果可转换；图片工具结果在请求上游之前返回 400，不删图片、不改角色、不转换为其他消息。

## 公共策略

原生分支仍通过同一个 `_complete` 路径执行调用方认证、别名/tier 校验、合并参数上限、消息数限制、每调用方限流、路由版本标记及请求/用量统计。原生历史的单独文本视图只用于这些检查，不作为出站历史。

检测扫描原始 user 文字，包含 typed `input_text`。spotlight 只包装 user 文字，并把防护声明和 canary 附加到 `instructions`；工具结果、图片、assistant phase 和调用 ID 不改写。非流式 Responses 的 canary 检查覆盖全部输出项，包括工具参数；流式继续复用原有逐块检查与截断。输出协议校验、已知代理 metadata 清理、失败流处理及路由记账保持共用。

## 验证和发布边界

在 `llm-service` 目录运行：

```bash
python -m unittest discover -s tests
```

原 125 项测试和新增 11 项 Pi HTTP 回归曾完整通过，共 136 项；随后补充 user 图片 URL 保持既有契约、数组边界/畸形值和 defaults 不变性检查，新增 Pi 回归共 12 项，针对这些更新单独运行并通过。原 native 请求测试的断言改为检查独立 `instructions` 和原始 `input`，反映这次有意修复的保真行为。`git diff --check` 通过。

此前 Hermes 扩展测试草稿保留在 `tests/test_native_responses_api.py.deferred`，不参与 unittest 自动收集，不属于本次补丁的实现范围。此记录仅表示本地验证；没有执行真实模型调用或部署共享 llm-service，线上 Pi PPT 图片复核仍须后续验收。
