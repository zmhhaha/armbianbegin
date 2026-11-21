> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/video-learning-completion-20261118/video-learning/README.md`；正文 SHA-256：`c629397392df997cdbf85081ac627b9af9b0333c4bf6f26c8d1a732f080379c5`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# 原创视频学习实测准备

独立账号 `codex-learning-completion-20261118`，本目录只测试原生学习链路，不向用户 `27714443` 账号放任何内容。不使用历史被否定样片。参考是本地 PIL + ffmpeg 生成的原创 6 秒无声技术图形，Agent 只能看到实际上传视频的采样帧，不能取得生成代码或截图作为交付素材。

`prepare` 仅本地生成媒体、原创来源回执及冻结请求；等待根协调确认 executor 已上线后，才能运行 `upload --executor-confirmed` 与 `start --executor-confirmed`。建项目只提交一次，先 fsync 保存原始 request_id 和正文摘要。超时后用 `status` 按原 request_id 对账，拒绝盲目重投。

约束为 1 新项目、1 实验、`max_rounds=1`、总时间上限 1800 秒、HTML/SVG 或 Canvas、native-js/GSAP。请求建议必要时至多 1 个真实技法 probe、2 个职责部件；API 固定硬上限仍为 2/3，不伪造更小的冻结策略。无价值可不分解。复现源码由 Agent 自主生成并由 HyperFrames 真实渲染；独立评审后在同一预算内做一次换内容验证。不能用假策略、假媒体或假观察回执补全链路。

命令按次执行：`prepare`、只读 `preflight`、确认上线后的 `upload`、`start`、只读 `status`、最终只读 `collect`。`collect` 保存真实源码、视频、渲染回执、每个角色输入及实际多模态传输回执，区分内部小样、正常作品和迁移作品。始终保持 `continuous_motion_verified=false`、`audio_verified=false`，技术验收不等于美术认可。
