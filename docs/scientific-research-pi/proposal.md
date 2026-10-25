# Change: 为 scientific-research 增加独立 Pi worker

日期：2026-10-21（Asia/Shanghai）
Change ID：`add-scientific-pi-worker`
项目：`ec663f5a-53d3-4a0e-9037-933eb788d183`
状态：本地实现、ARM64 候选镜像构建/推送、146项 Linux 回归及7项隔离测试、真实科学网关工具回合已通过；尚未部署生产 worker，外部学术来源/正式凭据/PVC/canary 仍待验收。详见 [实现与验证记录](implementation.md)。

## Why

当前 scientific-research 在 API 后台线程中运行固定的 CrewAI 五角色流程。API 重启会清理未完成任务；科研中间证据没有独立的持久化成果契约，技能与方法主要写在 Python 提示词中。用户希望复用 Pi agent 运行时执行服务提交的非交互科研任务。

Pi 作为首个新后端：服务负责任务与成果管理，Pi 专注单项研究的工具调用、分析和写作。选择基于职责匹配；尚未通过资源测量证明 Pi 比 Hermes 更省内存或更快。

## What Changes

- 增加专用 Pi worker，独立于现有人用 Pi 网页终端；每项研究使用独立 Pi 进程、会话和任务目录，首版单 worker、并发 1。
- 使用持久化队列、租约和 PVC 保存任务与产物；API 重启不终止外部 Pi 任务。
- 保留已有提交、查询、报告搜索与 Markdown 下载接口；CrewAI 后端继续可用，配置切换默认后端，失败时不自动换后端重跑。
- 固定任务、事件、文献、证据、报告和校验结果格式，规定取消、超时、恢复与报告发布行为。
- 引入经过审查并固定版本的精选科研技能，明确工具依赖、许可证、来源与摘要/全文边界。
- 以独立工作包分配给多个 agent，固定文件所有权、依赖与验收标准。

## Scope

包含：Pi 非交互能力验证；专用 worker；任务与成果持久化；精选技能及科研工具；现有 API/UI 接入；科学服务专用部署；兼容性和故障验收。

后续：Hermes/DSH 适配、跨 agent 协作、进程池、多副本 worker、自动续跑中断模型会话、重型数据分析环境。

不修改现有人用 Pi 的监听方式、会话、模型凭据或 PVC；不接管 Hermes 定时任务。

## Impact

- 应用代码主要在 `panghu_agent` 子模块；本目录是外层仓库的设计交接副本。
- 专用 worker/PVC/Service/NetworkPolicy 位于 scientific-agent 命名空间；不向公网开放 worker。
- 现有报告仍通过共享 SQLite 服务搜索和下载；新队列和完整产物由 worker 自己的持久化存储管理，使用可恢复的报告发布协议。
- 新模块及依赖需要构建镜像；现有 ConfigMap 仅覆盖 API 入口，不能替代模块和 worker 镜像构建。
- 内部鉴权及模型凭据使用 Vault → ExternalSecret，不复制私人 Pi HOME 中的凭据。

## Review and Delivery

详细决策以 [design.md](design.md) 为准；并行任务见 [tasks.md](tasks.md)；需求增量见 [科研执行规格](specs/scientific-execution/spec.md)。远端成功创建后，OpenSpec change 是规格和任务状态权威来源，本目录是交接快照。

OpenSpec 登记不代表生产验收完成。任务按证据逐项更新；真实模型、Linux 与线上验收完成前不 apply 或 archive。
