# Pi worker 协议 v1 补充契约

状态：共享 Python 契约、固定测试向量和本地协议测试已实现；OpenSpec 已登记。与 [design.md](design.md) 一同读取。I 为唯一契约作者；后续协议变更仍须同步 schema、向量及各执行适配。生产验证见实现记录。

## 输入、重放和摘要

公共 engine 为 crewai/pi，Pi mode 为 brief/review；Pi user_id 为空返回 422。topic 在 API 去除首尾空白后验证 1..500 字符，email/user_id 最长 200。Idempotency-Key 为 1..128 个可打印 ASCII 字符，保留 180 天；不把原 key 写入日志。

CanonicalJSON 只使用 object/array/string/integer/boolean/null：递归按 Unicode code point 排序对象键，数组保持顺序，UTF-8、无 BOM、无额外空白、ensure_ascii=false，双引号/反斜杠/控制字符按 JSON 转义，不转义斜杠，不做 Unicode 归一化，禁止 NaN/浮点数。schema 中所有时间为 UTC RFC3339 字符串，秒数和 size 为整数。

input_digest = sha256(CanonicalJSON({topic,user_id,engine,mode,timeout_seconds}))。email 属于通知配置，不传 worker；重放时不得静默覆盖原邮箱。服务生成的 created_at/deadline_at/技能/runtime 版本不进入 input_digest，第一次接受后固定，重放不同时间配置返回原快照，不修改任务。

report_sha256 = sha256(report_markdown 的精确 UTF-8 字节)。result_digest 使用同一 CanonicalJSON 对以下对象计算，artifact 数组按 artifact_id 排序：

```json
{
  "schema_version": "1",
  "task_id": "00000000-0000-4000-8000-000000000001",
  "attempt": 1,
  "report_sha256": "<64 lowercase hex>",
  "artifacts": [
    {"artifact_id":"report","media_type":"text/markdown","size":3,"sha256":"<64 lowercase hex>"}
  ],
  "provenance": {"runtime_revision":"pinned","skill_bundle_revision":"pinned","model":"actual model","image_digest":"sha256:..."}
}
```

不包括可变任务状态、事件、notification、发布时刻或 result_digest 本身。manifest 的 artifacts 不列 manifest 自身；manifest.json 下载可由服务计算其传输摘要，不参与递归 hash。report_sha256 基础向量：report_markdown="abc"，UTF-8 十六进制 616263，SHA256=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad。I 的 schema 测试必须补齐完整 result_digest 向量。

## 内部 PUT 示例

```json
{
  "schema_version":"1",
  "task_id":"00000000-0000-4000-8000-000000000001",
  "input_digest":"<64 lowercase hex>",
  "topic":"研究题目",
  "user_id":"trusted-opaque-user",
  "engine":"pi",
  "mode":"review",
  "timeout_seconds":1800,
  "created_at":"2026-10-21T14:00:00Z",
  "execution_deadline_at":"2026-10-21T14:30:00Z",
  "skill_bundle_revision":"pinned",
  "runtime_revision":"pinned"
}
```

URL 与 body task_id 必须一致。worker 检查 digest、期限、版本和配置，不执行客户端指定命令、工具路径或任意技能目录。schema_version 不支持、未知字段或类型错误返回 422。创建 201，重放 200；幂等/内容冲突 409，用户活动限额 429。

## TaskSnapshot

所有 v1 task 操作成功时返回同一对象，下列字段均存在；可空者显式 null：

| 字段 | 类型/约束 |
|---|---|
| schema_version | 固定字符串 "1" |
| id/topic/engine/mode | string；engine 固定 pi |
| state | queued/running/cancel_requested/validating/publishing/succeeded/failed/cancelled/timed_out |
| status | pending/running/done/failed，按设计表映射 |
| revision/attempt | 非负整数；revision 单调递增，尚未运行 attempt=0 |
| stage | search/screen/extract/synthesize/write/validate/publish 或 null |
| progress | 整数 0..100 或 null；无真实进度为 null |
| created_at/updated_at/execution_deadline_at | UTC RFC3339 string |
| started_at/finished_at | UTC RFC3339 string 或 null |
| error_code/error | string 或 null，脱敏且有长度上限 |
| report_id/result_digest/report_sha256 | string 或 null；报告 ID 等于任务 ID |
| report | string 或 null；内部快照可不承载正文，公共成功查询必须提供正文 |

公共 TaskResponse 额外保留 user_id（string 或 null）、notification_status（pending/sent/failed/unknown/null）。内部不暴露 lease token 给 API/UI；worker 进程管理内部 fence 不属于外部身份凭据。

PUT 请求最大 16 KiB；事件单条 8 KiB，错误 message 最长 2000 字符；结果正文 <=2 MiB、总登记成果 <=50 MiB。以实际字节计限，不相信 Content-Length 或模型填报。

## 错误与就绪

内部失败统一 JSON：

```json
{"error":{"code":"worker_unavailable","message":"脱敏说明","retryable":true,"task_id":null}}
```

- 401：缺失/错误 token；403：调用来源被明确拒绝；404：任务或 artifact 不存在。
- 409：task_conflict/stale_attempt/result_not_ready/publication_conflict。
- 410：artifact_expired（任务快照仍保留）。
- 413：请求/成果超限；422：无效字段/协议/身份/摘要。
- 429：user_busy/queue_full，Retry-After 提示非强保证。
- 503：worker_unavailable/storage_unavailable/runtime_not_ready/configuration_missing。

公共 API 保留 FastAPI detail；兼容旧字符串 detail，同时 ambiguous dispatch 使用 detail 对象 {code,message,task_id,retryable}，UI 兼容解析两种格式并保留可查 ID。网络故障不能伪装为任务 404。

result 仅 publishing/succeeded 可取；其他状态 409 result_not_ready。取消 queued 返回 cancelled；取消运行任务返回 cancel_requested；取消 publishing/succeeded/其他终态返回原快照 200，不撤销已提交成果。execution_deadline_at 到期只终止 queued/running/validating，不终止 publishing；publishing 占用户 Pi 活动位直到成功或管理员明确处置。

## 发布分页和状态

列表响应：{items:[TaskSnapshot],next_cursor:string|null}。limit 默认 50，范围 1..100。cursor 是不透明的、基于固定 created_at+id 的 keyset 值；无下一页 null，无数据 items=[]。列表只返回待发布且 result 已持久化的记录；一次扫描完成后从头周期性扫描，避免漏掉旧任务刚进入 publishing。

publication-ack body：{attempt:positive integer,result_digest:64hex,report_id:UUID}。不匹配 409；匹配且已 succeeded 幂等返回快照。进入 publishing 后 immutable result 不再重生成。保存正文使用 insert-if-absent 再核对 report_sha256，禁止覆盖同 ID 异内容。

派单 intent prepared/ambiguous 可重放，accepted 只能查询/同步，rejected 永不重放。429/409/422 是明确拒绝；传输超时不确定，外部 503 返回 task_id，reconciler 继续确认。幂等 key 的不同用户作用域隔离。

## 固定摘要测试向量

以下只是协议机制样例，不是完整科研成果或真实 runtime 验收。所有数字限制为 JSON safe integer，字符串不允许孤立 surrogate。

input 的精确 CanonicalJSON（不含末尾换行）：

```json
{"engine":"pi","mode":"review","timeout_seconds":1800,"topic":"研究题目","user_id":"trusted-opaque-user"}
```

input_digest = `a225a6308ec7a6a96463c5ea75fbfef814ec3ef4aa141cdf286a4e33cceb5851`。

result envelope 的精确 CanonicalJSON（不含末尾换行）：

```json
{"artifacts":[{"artifact_id":"report","media_type":"text/markdown","sha256":"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","size":3}],"attempt":1,"provenance":{"image_digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000","model":"fixture-model","runtime_revision":"pinned","skill_bundle_revision":"pinned"},"report_sha256":"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","schema_version":"1","task_id":"00000000-0000-4000-8000-000000000001"}
```

result_digest = `510fcd75b79cbd4357a361a1e2a4463bcf8ef00767f59f61424d7e2222b2bb7a`。此 fixture 的 model/image 只是固定输入，不宣称存在相应可运行镜像。各包必须重算并匹配这些值，禁止拿漂亮 JSON 的缩进文本直接计算。

## 明确的首版选择

- 每个 engine 独立并发门控；灰度期间允许同用户一项 CrewAI 与一项 Pi，并非全局限一。
- 队列、索引和幂等记录保留至少 180 天，成果文件默认 30 天；清理不得破坏未完成发布。
- 契约样例的 hash 占位符只用于文档，不是有效请求；I0.3 交付真实 JSON schema 与完整向量后才允许各包声明协议测试通过。
