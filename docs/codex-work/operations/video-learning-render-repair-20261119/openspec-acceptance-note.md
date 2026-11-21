> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/video-learning-render-repair-20261119/openspec-acceptance-note.md`；正文 SHA-256：`b42149ccb135d6f0c0947898f31292825341002665091412bc872520543d5f25`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

### RR 原项目实际验收（2026-11-19）

单次 request `645fa23954804583b5f5e5250aedcc67` 只绑定 experiment `fea43008d5ff405ca9609f7103c92fba`。第2轮 author 获得原源码与绑定的截图超时反馈，生成 Three.js 新候选 `0442d32a6bea4796a211aa21a266376b`。源 SHA 从 `330a60ff88a97581ff61b9db2d35d3a09d8141ec2706b02cc41d7d9c95f0b3b3` 变为 `506cb959ea90b888a1f535da1b7ad1e3e5e2bcf4521392dc1961abb3bb52232a`，原参考与知识绑定保留，repair_of 指向失败作品。本次只有一次技术源码修复。

Agent 把全屏山体/体积云的多步光线积分改为山体网格、云高度场、透明云团及缓存纹理，仍有少量自定义 Shader；未以更换技术名称作为成功标准。经原 HyperFrames/Three.js/SwiftShader 后端实际导出1280×720、24fps、6秒、144帧，耗时141.704秒。媒体 SHA `1d9699d6c8af5f6f0ca064c910d55cc4d115ed1fe87eec1232550553c0e62559` 与结果、收据和实际字节一致。反向/重复/空闲/重新加载seek均通过，原容器已移除；本地ffprobe读取144帧、ffmpeg整段解码exit0。17项输入核验和37项候选绑定核验通过。

独立评审比较8张参考和8张输出，评分61：基本空间推进可辨认，但云海体积、岩石细节、局部逆光和前景退场节奏仍有差距。原预算内第3轮视觉修订源 `c7237a6e168d80efe1006ca5777440dfbbb046aa54fb758ae3016b93642f9ad9` 后续渲染失败，最终实验state为failed、stop_proven=true。该候选没有成功媒体或评审，不以首个成功版掩盖最终失败状态；成功版仍是project/run的best。API对末次失败只给出runtime_failure_unknown，不能据此断言具体根因。

因此，RR.4完成的是实际修复、导出、评审及边界记录；不是参考效果已完全复现。换内容验证、连续播放、音频和开发者艺术认可均未验证。未自动采用样片或发布WikiSkill，旧失败、成功样片与后续失败源码均保留。完整证据在开发机 `D:/codex-work/operations/video-learning-render-repair-20261119/` 与 `...-20261119-r2/`，媒体及源码在 `D:/codex-work/archives/video-service/20261119/peak-render-repair/`。
