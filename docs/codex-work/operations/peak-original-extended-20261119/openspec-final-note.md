> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/peak-original-extended-20261119/openspec-final-note.md`；正文 SHA-256：`448289941d43f3fdb8c260f4dbbd53482c20e98e2233d79afc359d271ba3a316`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

### QF 原版扩资源与策略上线验收（2026-11-19）

原源码 `330a60ff88a97581ff61b9db2d35d3a09d8141ec2706b02cc41d7d9c95f0b3b3` 保持原1280×720/24fps/6秒。服务器CPU probe在4CPU/3GiB、单帧180秒限制下成功，捕获30.587秒；原10秒截图限制确实不足以获取这次画面。独立CPU full继续使用原SwiftShader/HyperFrames runtime，只延长派生host超时，144帧与全部seek/解码通过，总运行1201.125秒，媒体SHA `e4a1d05190f134fbeb83d72dec50670e0b4630ca6029e38121627d89270f98e8`，容器按身份清理并确认不存在。资源与host/request/source/媒体证据已归档，没有改生产准入或历史实验。

同源码另在本机RTX2070 SUPER/ANGLE D3D11离线导出，启动至144帧及seek/编码解码结束共19.172秒，媒体SHA `040530ff6690b2071aa99bc34228c6eab9c21ffb3c476dab6248bc4ba95263d4`。硬件GPU与CPU证据分开，不宣称跨后端逐像素一致或已正式准入GPU。

实际8帧对比认为原版云海的层叠、山脚遮挡与纵深更强，简化版损失这部分表现力；原版仍有条带、山体过黑与构图过满问题，不宣布全面复现参考。没有连续播放/音频/开发者认可或知识发布结论。

90项定向测试通过。策略代码revision `1b10d4ec126cb23969856e313b5b58a88bc724df` 已完整Git构建latest并按digest `sha256:be66a34d1c1a9f354bf2436302f30a70c0d06b7f0cfbc1f4620dbc4d7976e10a` 上线；58项运行源码核对、19库备份及health200通过。生产host、准入、WikiSkill和其他5个部署保持。新timeout不自动改源码，旧recommended=true也不能触发新创作；明确source/seek错误仍有一次有界修复。普通retry仍无扩资源字段，本次扩时参数是独立对照而非生产默认。

操作与证据：`D:/codex-work/operations/peak-original-extended-20261119/`、`D:/codex-work/operations/video-resource-priority-release-20261119/`；对照视频在 `D:/codex-work/archives/video-service/20261119/peak-original-extended/full/` 与 `.../peak-original-local-gpu/`。
