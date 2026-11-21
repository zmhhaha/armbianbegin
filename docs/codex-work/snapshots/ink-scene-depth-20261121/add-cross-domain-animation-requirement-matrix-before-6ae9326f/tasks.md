> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/ink-scene-depth-20261121/service-preflight/add-cross-domain-animation-requirement-matrix-before.json`，JSON 字段 `/artifacts/tasks.md`；正文 SHA-256：`0a171cfb9626723e645ff1f0a772f35392fc657343cdc6b2cfb0d8f478441f29`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

## 1. Requirements and rendering

- [x] 1.1 实现三类优先表达家族及每类至少四个不同领域、数据和事件过程的结构化需求。
- [x] 1.2 按需求重新设计原五类能力各三个跨领域样例；重建27例活动库和标注基线，不保留旧样例身份与历史意见，隔离业务数据。
- [x] 1.3 实现有种子、有界、可冻结的需求矩阵与覆盖统计/导出，报告实际执行范围。

## 2. Workbench and feedback

- [x] 2.1 增加领域与引擎筛选、需求原文和覆盖查看，接入新模块反馈迭代。
- [x] 2.2 实现真实SVG/HTML绝对时间渲染及语义/状态、动作和归零检查。

## 3. Verification and release

- [x] 3.1 完成相关Python/Node回归、基线一次性重置与旧报告隔离检查，以及有限真实原生浏览器采集，记录本轮失败与真实执行范围。
- [x] 3.2 发布独立Lab并验证实际资源、筛选、播放、需求及标注持久化边界。
- [x] 3.3 更新使用说明及OpenSpec实际状态，区分样例实现、已运行范围、审美和生产接入。

## 实际实现与验证

2026-11-07完成：按用户新指示重建8模块27需求、10领域（原五模块各3，新三家族各4），旧15公开身份退役，专用Lab旧快照/意见/分诊/任务清空；同corpus重启保留新记录，旧报告列表/静态文件/候选验证各入口均拒绝。生产项目、媒体与业务Deployment spec未变。

真实原生采样最终27例全部技术通过，54个A/B版本、62独立片段、1747张回执绑定原JPEG。初轮62采集有6例失败；3个过程基线补齐开发专用首帧/归零DOM观察，另采6段；3个跨镜空详情框修正精确检查器，用原观测/JPEG重审。实际68采集，全部容器清理确认；原失败记录保留。源目录/观察器原SHA分别记录，不将新源码标签覆盖原采样身份。模型、Agent、TTS调用0，未编码MP4。

Python定向回归覆盖各家族、真实SVG几何及HTML状态oracle、基线/旧报告隔离、HTTP权限/CSRF、反馈runner和冻结适配；333、62、121等分组通过，存在交集不相加。工作台Node28项，过程/连续观察器Node25项通过。Windows连接中断与长路径解包失败保留，重测/原归档短路径提取后完成核验。

独立ARM64 Lab上线源码8d00bc8345b421e4215ac493a83a5e4a81f0100b，latest@sha256:b43f3770fc262af96910763ae71b785e5c1691e605d255b407b6c7b7c39d21d6。后端核对54预览、27新快照、旧意见/任务0、需求集semantic_identity与CLI一致；实际Pod imageID及38个运行源文件与构建上下文字节一致。登录浏览器验证需求覆盖/筛选空态与恢复、HTML筛选排序和逐帧控制、技术标注保存；同镜像Pod替换后原记录SHA不变，浏览器真实重载仍读取到，随后撤回，当前有效意见0。本地另核对五层WebGL展开与领域职责。

入口https://video-service.panghuer.top/dev/animations/。分支codex/video-cross-domain-animation-matrix已推送，未合主线。使用说明video_workbench/docs/animation-requirement-suite.md；原始、修复、汇总和发布回执在既有rendered/feedback-20261106/animation-lab目录，短路径工作目录仍归后续统一清理。首轮为有限审校需求池，不是任意文稿生成，不自动接生产选型，不将技术通过当用户审美/真实旁白时序批准；真实Agent到PR环境仍未启用。
