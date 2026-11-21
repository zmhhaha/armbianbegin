> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/picture-learning-20261118/README.md`；正文 SHA-256：`6576fa5176604730f9b1ac81768d3a80a822c32ebd1476c2310ecd78bd17c548`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# 图片学习生产准入操作

操作文件仅写在此目录，并同步到服务器 `/root/video-releases/picture-learning-20261118/`。

- `picture_candidate_prepare.py`：固定干净 Git 源码、实际构建镜像的源码标签、输入像素、协议、模型能力和 disabled 候选；不执行模型。
- `picture_candidate_runner.py`：一次真实候选，最多 8 个模型请求；永久预留 3 个 UID，收集实际图片传输、工具、源码产物和原始 worker/proxy 停止证据。未知结果保留原现场，不自动重试。
- 共享源码中的 `agent_service.deploy.picture_learning_acceptance`：独立检查真实候选。作者另外绑定真实 PNG 渲染的源码、输入、HyperFrames 时钟和重复捕获证据；评审必须直接收到参考和结果的图片字节。
- `picture_activate.py`：默认只生成发版计划；`--execute` 单次执行。只增加两个图片 profile、专用 caller、两段新的永久 UID 和已准入 worker host；保留现有 route/pool/配置和凭据。专用 executor token 放入 `video-animation-creation/picture-learning-agent-20261118`，不会发给效果库网页。
- `deploy_picture_services.py`：独立的实验室和执行器部署工具。默认只保存计划；`--apply` 才修改两个 Deployment，保留原有参数与挂载，补充图片 caller Secret 挂载。构建目录和完整 Git revision 必须显式传入；逐项校验构建、源码、镜像 digest、运行时源码及 rollout。不会变更 Agent 路由、控制面、worker 或 renderer。
- `check_deploy_picture_services.py`：对已有两份 Deployment 快照进行离线补丁边界检查，不访问 Kubernetes 或凭据。

前端修正后的完整源码构建固定为 `7abec1d898d5b11431f89c11ec95df57563c5655`，输出在服务器 `/root/video-releases/picture-learning-20261118-r2/build/`。第一轮构建和准入凭证继续留在原位置，不覆盖。应用部署操作记录保存在原操作目录的 `lab-executor-*` 子目录。先等专用 caller 及路由准入成功，再部署应用；实验室和执行器仅使用新构建通过离线检查的 digest。

实际准入使用用户已上传的水墨参考图，原始字节从 `D:/codex-work/archives/video-service/20261117/ink-still-clear/reference.png` 固定；355,077 字节，SHA-256 `34874e709c5ae3540dd14e1ba6d40a7265a4a440c851676221f5e072aa955260`。

本操作不发布 WikiSkill，不把技术准入写成人类审美认可，也不声称图片传输证明模型理解。真实业务闭环与网页验收由主任务继续完成。
