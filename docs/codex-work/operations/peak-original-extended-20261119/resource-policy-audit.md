> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/peak-original-extended-20261119/resource-policy-audit.md`；正文 SHA-256：`df3a8fc8661a76b406e6ab7421345d09976e2bbdcb5b05a483e25f7053ec915e`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# 原版峰林扩资源重渲染与资源失败策略审计

日期：2026-11-19。范围：本地源码、既有部署文档与保存的 OpenSpec 内容；没有为本审计启动业务、模型或渲染操作。父任务正在独立执行已获授权的原版扩时/资源离线实验，本审计不干预该执行。

## 当前用户目标

原始复杂作品先保留，给足明确且有限的时间和资源后原样重渲染，再比较实际效果。视觉质量优先；只有实际输出表明效果相近时，才以成本较低为选择理由。超时本身不能证明源码错误、GPU 故障、内存不足或简化后的作品质量等效。

原版项目：`68240ff5aecd482289612cde58124dad`，效果为“逆光峰林与云层的纵深和遮挡”。原始源码 SHA-256：`330a60ff88a97581ff61b9db2d35d3a09d8141ec2706b02cc41d7d9c95f0b3b3`。先前首帧截图 10 秒超时，没有完成帧。后续几何/云纹理候选确实完整导出，但原版没有完整媒体，因此不能声称后者已达到原版的同等视觉质量。

后续修复候选 round 2（`0442d32a6bea4796a211aa21a266376b`）为 1280×720、24 fps、6 秒、144 帧，审阅分数 61，且仍有局部自定义 Shader；不能称为“完全无 Shader”。后续 round 3 已完成 114/144 帧后耗尽总体剩余预算，不应混写成又一次首帧 10 秒超时。硬件、源码、单帧、总时长和审美差距必须分别依证据判断。

## 发现的策略冲突

1. `learning_execution_guidance.py` 曾把反复出现的 source、initialization 和 performance failure 一起要求实现修复。资源/时间症状因此被默认为需要改写创作。
2. `animation_method_renderer.py::_failure_diagnostic` 曾对 `method_frame_capture_timeout` 返回 `source_repair_recommended=True`，且固定建议以 reduce per-frame work / lower-cost method 开头。
3. `video_learning_repair.py::_schedule_render_repair` 原先信任该 recommendation；`_restore_render_repair` 在历史失败的 retry 时重新读取诊断，也会把技术重试自动转为作者重新创作。
4. `video_workbench/docs/video-learning-render-recovery-20261119.md` 记录了上述当时已实现的行为。历史事实应保留，但需要追加当前策略边界，不应继续把该历史行为描述为未来应采用的恢复方式。
5. 保存的 OpenSpec `evolve-video-agent-creation-and-effect-library` 中，`design.md` 的 2026-11-19 小节和 `specs/reference-animation-effect-library/spec.md` 的“已停止渲染失败的一次有界源码修复”仍包括性能症状；“历史首帧超时请求再次重试”场景要求交回作者。这与新决定冲突，需要收窄。

OpenSpec 项目映射：`https://openspec.panghuer.top/mcp`，projectId=`ec663f5a-53d3-4a0e-9037-933eb788d183`。本审计读取既有本地保存文件，没有修改 OpenSpec。保存来源为 `D:/codex-work/operations/video-learning-render-repair-20261119/openspec-update.args.json` 等记录。

## 预算与限制是多层的

| 层级 | 当前正式链路配置 | 提高实验总时间是否会改变 |
| --- | --- | --- |
| 学习实验总预算 | 默认 900 秒，最多 3600 秒，各阶段共用截止时间 | 只有新建/继续实验的显式预算能改变；普通 retry 复制原预算 |
| 单次 renderer | 默认 360 秒，构造参数上限 600 秒 | 不会；实际还受实验剩余时间约束 |
| 容器资源 | 固定 2 CPU、1 GiB，无硬件 GPU，CPU SwiftShader | 不会 |
| 清理预留 | 总操作预算中预留 15 秒 | 不会 |
| 页面加载/重载 | 20 秒 | 不会 |
| 单帧 screenshot | 10 秒 | 不会 |
| 媒体子进程 | 180 秒 | 不会 |

源码位置：`picture_learning_service.py::_budget/_new_experiment/next_experiment/_operation`、`video_learning_renderer.py::__init__`、`animation_method_renderer.py::execute_method_render/MethodAnimationRenderer.__init__`、`animation_method_host.mjs`。

Host SHA-256 仍为 `df7253899839aef3df112e13ccc3a2c2ca09ceee96b037c84800021e1dd26d81`。本次最小策略修改不改 host、准入、资源默认值、API 或 UI。

## 普通 retry 的明确局限

`next_experiment` 的 retry 请求只接受 `request_id` 和 `mode`，会复制原 `frozen`、预算和有效源码。新实验截止时间重新给足原 `max_seconds`；它可能解决原实验剩余总时间过少，但没有扩大原预算额度。

`_operation` 复用原有效 input，仅替换新实验身份；新操作 ID 实际执行一次同源渲染。360/600 秒 renderer、2 CPU/1 GiB、10 秒截图等限制仍相同。停止 timeout 自动回作者以后，普通 retry 仍不是“增加资源后重跑”的产品入口，不能向用户声称点击重试就增加了资源。

这次没有新增重试入口、额外付费动作或自动资源扩容。未来如需产品化，应在既有恢复流程中明确提供一个新的有限资源配置并保存新身份、源码摘要、资源配置、产物和停止证据；不要借此另起大型工作台或静默提高所有任务的全局默认值。

## 最小策略修正

经父任务授权，子任务仅修改三个实现模块和对应三个测试模块，未提交 Git 或部署：

- 新 capture timeout 固定诊断保持症状分类，`source_repair_recommended=False`，明确保留原源码/证据，并说明可提高有限资源或时间后同源重渲染；当前 retry 本身不提高限制。
- repair 入口只接受已绑定且已停止的明确 scene-interface / absolute-seek / reverse-seek 故障，不信任历史 timeout 的 `recommended=True`。
- 即使不安排修复，绑定的失败候选仍保存原源码、失败操作身份和诊断；原 operation input 与 renderer ledger/媒体不改写。
- 对明确源码/seek 故障，原有一次修复、原探索轮次与截止时间、至少 90 秒剩余、停止证明及不自动采用/发布的约束保留。
- 新创作 guidance 强调视觉质量优先和已观察的相近效果；未知执行或停止不明仍先核实，不能制造重复操作。

## 文档与 OpenSpec 建议

保留已完成 RR.1–RR.4 的历史事实和结果，不反向修改旧冻结输入或取消已验证任务。追加一项小范围当前策略说明：

> 资源与时间上限症状不得单独触发作者改写；必须保留原实现及失败证据，说明已观察到的限制层。只有明确源码/初始化接口/确定性 seek 故障可按原有有限预算修复。用户明确授权提高有限资源后，建立独立同源渲染尝试；不得静默削弱视觉目标、降低输出约束、切换明确指定能力或自动采用/发版。

把历史首帧 timeout 的 retry 场景改为“保留源码，普通 retry 不自动转 author，扩大资源需要独立明确配置”。仍保留“效果相近时选择低成本”的要求，但相近必须有实际输出支持。

`reference-learning-libraries-design.md` 已有的有限预算、保留较好版本、无进展停止及后续新实验规则可继续使用。`shader-mali-rendering-design.md` 的效果优先、软件基线、Mali 候选未准入及同源逐后端取证规则也保持有效。

## 验证边界

定向测试覆盖真实 adapter 的绑定 host-timeout 报告安全投影到 service、timeout 不自动创作、旧推荐值不使 retry 转 author、重试保留原有效源码与输入、明确 scene/seek 仍最多一次修复、未知或停止不明仍不重提任务，以及冻结 guidance 与历史 input 不变。

测试用模拟的 host 收据与实际本地 FFmpeg 参考片段验证编排和证据绑定；它们不能证明真实服务器视觉、性能或音画质量。测试日志目录：`D:/codex-work/tmp/video-service/resource-first-20261119/`。最终通过数量以该目录内日志和子任务报告为准。

最终定向结果：三个测试模块共 **90 passed in 109.46s**，日志 `D:/codex-work/tmp/video-service/resource-first-20261119/pytest-final.log`。新增实际 adapter 绑定 timeout 集成测试单独确认 **1 passed in 4.67s**。六个修改文件的 `git diff --check` 通过；host SHA-256 核对保持不变。未部署、未提交 Git、未改 host/准入/API/UI、未触发业务或模型操作。
