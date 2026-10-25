# OpenSpec 提交回执

更新时间：2026-10-22（Asia/Shanghai）。

最新生产部署证据见 [上线记录](rollout-20261022.md)。最终同步已完成，首次登记回执作为历史保留。

## 最终部署同步与校验

- 时间：2026-10-22 21:16:54 +08:00。
- revision：`3a48cc63e935d9226cd025a9b6c8b491c98a330f`。
- 任务：**44/47 完成，3 项保留**（F4、E7、I1.2）。缺少的对照和部署前后快照详见上线记录。
- 服务端：`valid=true`、`issues=[]`；四份工件读回与提交载荷逐字节相同。
- 源码：`panghu_agent` 的 `75ee2e699c5af71a337a5434c0b554defd4dbbf8` 已先行推送，外层记录该 gitlink。
- 保留远端原有设计、协议和实现附录，追加最终部署证据；未 apply/archive。

[最终机器回执](remote-rollout-receipt.json) 记录每份工件的大小、SHA-256 和服务端校验；[最终提交载荷](rollout-submission-payload.json) 保存精确上传文本。上传通过既有 OpenSpec MCP 授权，使用 ASCII JSON 转义避免历史 UTF-8 分块问题，更新前核对上一回执中的工件摘要并使用最新 revision 防止覆盖并发修改。

## 首次登记与校验（历史）

- Change ID：`add-scientific-pi-worker`
- 项目：`ec663f5a-53d3-4a0e-9037-933eb788d183`（`openspec-service/armbianbegin`）
- MCP：`https://openspec.panghuer.top/mcp`
- 该次 revision：`383738bda99cf9e106a8bfa54feeaf6480098030`
- 时间：2026-10-22 13:49:27 +08:00
- 服务端：`valid=true`，`issues=[]`，1项change通过、0失败。
- 47项任务：9完成、38待验收。
- 保持 active，没有 apply/archive，也没有切换生产科学服务。

[机器回执](remote-submission-receipt.json) 保存四份工件字节数、SHA-256、原文读回比对和服务端校验结果。

## 本次同步内容

完整上传 [proposal.md](proposal.md)、[design.md](design.md)、[tasks.md](tasks.md) 和 [科研执行需求增量](specs/scientific-execution/spec.md)。远端设计内嵌 [contracts.md](contracts.md) 与 [implementation.md](implementation.md)，符合服务允许的工件路径。

此次更新登记 ARM64 候选镜像、146项 Linux 回归、7项系统隔离测试、真实科学网关工具回合、网络对照结果及已修复的三个问题。全部四份工件读回后与 [提交载荷](submission-payload.json) 完全一致。

新完成：I0.3、A1/A2/A3/A5/A6、E5、F7；此前 I0.4 已完成。其余任务按完整验收要求保留，不能解读为没有本地实现。生产独立 caller、PVC/真实报告发布、学术来源网络、浏览器和 canary 等尚未完成。

## 保留与清理

已有 `enhance-scientific-agent-skills` 是独立 CrewAI 变更，本次未修改。其他 active changes 和主 specs 未变。

临时4个 Pod、2个专属 NetworkPolicy、1个 ConfigMap 已清理，见 [清理回执](evidence/20261022-arm64/cleanup-receipt.json)。独立候选镜像和脱敏证据保留；线上 API 仍为 `agent-api:ac61414`，CrewAI 默认路径不变。

## 传输与后续

早期创建遇到服务按数据块解码 UTF-8 导致少量中文损坏。本次继续使用等价 ASCII JSON Unicode 转义，经上次已核验工件摘要与当前 revision 保护后更新，最终逐字节一致。没有修改或部署 OpenSpec 服务代码。

后续从远端同名 change 读取最新任务状态，再依据实际证据更新；生产条件完成前不 apply/archive。本地工件是交接副本。
