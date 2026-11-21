> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/video-learning-completion-20261118/formal/README.md`；正文 SHA-256：`071f111e02d19338aac0361e27c51557a64269ecd430ff42e798a5bdc1ddfd21`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# 正式视频读取新 WikiSkill 的独立验收

准备脚本，不代表验收已完成。仅根协调确认新版 WikiSkill 实际发布成功后，才能执行 `prepare` 及后续模型步骤。

独立测试身份 `codex-wikiskill-use-20261118`，发布者固定为 `27714443`。新主题为“夜航灯列”，沿正式工作台 API 执行统筹、采用方案、单镜 Agent 源码创作、TTS 与真实 HyperFrames 草稿。不得正式导出、自动精修或写人工时序确认。

按次运行，不循环提交：

1. `python -B formal_acceptance.py preflight`：只读检查。不会保存或输出 CSRF。
2. `python -B formal_acceptance.py prepare --release-id <实际发布ID> --release-sha256 <实际发布SHA256> --sequence <实际序号> --confirm-published`：仅冻结验收意图。
3. `python -B formal_acceptance.py init`：唯一一次建元数据项目。
4. `python -B formal_acceptance.py plan`：唯一一次提交指定发布版的统筹任务。
5. `python -B formal_acceptance.py status`：只读查询；未完成继续等待，不重复提交。
6. `python -B formal_acceptance.py adopt`：只允许采用成功、未过时、恰好一镜且版本身份完全一致的候选。
7. `python -B formal_acceptance.py draft`：唯一一次正式制作草稿；旁白允许 TTS，原始绘制源码必须由 Agent 生成。
8. `python -B formal_acceptance.py status`：持续只读查看。
9. `python -B formal_acceptance.py audit`：只读验证原生 `skill_search`/`skill_read`、SKILL.md 实际读取、声明使用、冻结发布版、真实源码包及媒体字节来源，核对 HyperFrames 产物和 HTTP Range。

每个 POST 的正文与原始幂等键在网络请求前 fsync 落盘。网络结果未知时只能使用 `status` 按原始身份对账，脚本拒绝重投。建项目接口没有幂等支持，因而按独立账号、唯一标题和原脚本精确查找；不确定但没有找到时仍拒绝盲目再次创建。SQLite 只以 `mode=ro`、`query_only` 打开，范围仅限该测试身份和项目。不实例化服务或工作流。

审计将目录可用、实际阅读、声明应用、Agent 原始源码、真实渲染分别记录。技术验收不等于美术质量达标，也不替代用户时序试听。
