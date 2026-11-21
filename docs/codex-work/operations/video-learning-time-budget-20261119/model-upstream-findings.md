> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/video-learning-time-budget-20261119/model-upstream-findings.md`；正文 SHA-256：`fdc1200f424005f532cdbe6cef77ec428fc9838d879c2ee089b9dfe271b7f55f`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# 失败任务的模型代理与LLM上游只读核查

项目 `588a5b7ef481471b950f392f85223bed`，实验 `478486c62b364bd69f55c356f107effc`，job `8d3057d7-0076-4c36-9a1d-06875cf42491`，attempt `4ef651b5-7900-4fd9-a904-bc50ce1131c4`。

任务窗口2026-11-19 10:39:32.718至10:43:04.327 UTC；停止时约212秒，早于600秒预算。停止/worker归因由并行diagnostics调查，本核查只处理代理数据库与服务日志。

## 已确认

- attempt对应4次模型请求，均为durable `complete`、HTTP200、text/event-stream。没有admitted悬而未决调用。
- 四份实际SSE均有唯一 `response.completed`，response status=completed，error=null；没有error/failed/incomplete/cancelled事件，也没有坏JSON事件。
- 最后一次响应2,032,045字节，但工具参数实际20,271个字符，JSON有效。7095个delta拼接、arguments.done、output_item.done及response.completed里的参数SHA一致，未发现参数截断或分叉。
- LLM结构日志在同一时段有4次llm-trusted→custom/Responses的正常route/chat事件，未记录upstream_error/reject/stream_error。末次服务耗时169044ms，于10:42:56.381 UTC正常结束，约8秒后job以model_error停止。日志无独立job关联ID，按时间与4次请求对应核对，durable请求记录才是精确attempt证据。
- 没有发现429、5xx、上游读/连接超时的证据。目标agent-model-proxy pod在该时间窗口没有日志，不应将缺日志解释为服务健康证明；其restart count为0。

## 尚未确定

HTTP200和正常终态不单独保证所有SSE语义及Pi SDK处理正确。末次output类型为reasoning、reasoning、message、function_call，需要结合worker/native诊断定位消费端model_error；不能据此断言重复reasoning就是根因。不可把这次失败解释成制作时长不足、渲染超时或未经证实的上游限流。

## 证据

- `job-model-responses-safe.json`：准确绑定attempt的4次请求状态、响应hash与SSE事件计数。
- `last-tool-arguments-shape-safe.json`：参数长度、JSON有效性及四处一致hash。
- `llm-structured-events-safe.json`：固定字段过滤后的route/chat日志。
- `upstream-log-summary.json`：初步HTTP日志统计。其中搜索字符串502的两项实际HTTP状态都是200，仅数字子串碰撞，不能当作502错误。

未导出prompt、参数内容、原始响应或token；未重跑、部署或写数据库。
