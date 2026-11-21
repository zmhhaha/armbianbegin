> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/video-learning-time-budget-20261119/findings.md`；正文 SHA-256：`55439e3bffd9bd387ad2a750ed54a462ebcf9fe4b71e44c1b664a0c276d33d86`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# 新提交视频学习任务失败调查

项目：荷塘鱼群的个体姿态、群体分布与水面亮纹（588a5b7ef481471b950f392f85223bed）。
实验：478486c62b364bd69f55c356f107effc。

## 已确认的失败阶段

首轮 author 对应 Agent job 8d3057d7-0076-4c36-9a1d-06875cf42491，状态 failed，错误码 model_error。整项冻结预算900秒，原实际Agent提交时限600秒。从创建到停止约211.609秒，距Agent截止仍余388.391秒。原job、worker与Kubernetes停止证据均已核对。没有renderer操作、帧输出或已冻结源码产物。

这次不属于整项预算到期、Agent600秒到期或单帧Shader截图超时。单纯延长预算不能解释或修复当前失败。

## 模型返回核对

精确绑定本次attempt的4条持久代理记录均为complete、HTTP200。实际SSE都有response.completed，response status completed、error null，无失败/不完整终态。最后一条响应约2.03MB，但实际工具参数仅20271字符，JSON有效；拼接delta、arguments.done、output_item.done、最终response四处摘要一致。usage字段类型一致，未发现截断、429、5xx或网络超时证据。

故障已缩小到Pi原生运行时报告的模型返回处理错误，但HTTP/SSE成功不等于整个Agent创作成功。原worker详细运行日志已回收，不能凭缺失日志编造具体异常；已以相同 pin 镜像内实际 Pi SDK 对原 SHA 的响应离线重放：3.509 秒正常完成，stopReason=toolUse，工具参数完整；网络禁用，零模型调用。该结果未复现历史故障，不能据此修改 SDK，也不能把问题归为响应过大。生产失败更具体的原生异常因日志回收尚无法完整还原。

## 时间政策

另已确认复杂shader的生产截图10秒、渲染默认360秒/最大600秒确实短于此前原版的实测30.6秒首帧、1201秒整片。完整时间链与未来视频专属扩时方案见audit.md。该旧瓶颈与本次model_error分别记录。尚未修改生产时限、CPU/内存、历史输入、准入或默认作品，也未重跑业务任务。由于本次未触发时间限制，未按资源耗尽处理或自动扩时；既有复杂渲染时间瓶颈仍单独保留。

## 证据

new-author-agent-job.json、new-author-agent-custody.json、job-model-responses-safe.json、last-tool-arguments-shape-safe.json、completed-shape-comparison-safe.json、worker-pod-events.json及last-response-fixture-receipt.json。原始响应仅用于受控离线复现，不包含输入prompt或凭据，不作为新的业务成功产物。
