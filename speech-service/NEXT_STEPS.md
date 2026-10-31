# 下一阶段

代码位于独立分支`codex/speech-service-rk3588`，目录`speech-service`与`llm-service`同级。worker目录`/root/armbianbegin/speech-service`；复用已有模型、vendor和venv，不升级驱动、不覆盖宿主库。

K8s 内部服务已部署于 namespace `speech-service`、节点 `orangepi5-max-server1`；接入地址 `http://speech-service.speech-service.svc.cluster.local/v1`。云健原201字符文稿经原版客户端合成一次通过：34.912秒返回42秒音频。本次 cgroup 峰值约2.89GiB、限制4GiB，OOM计数均0。部署身份与权限边界见 [DEPLOYMENT.md](DEPLOYMENT.md)。

1. **按用户选定的中文男声云健继续。** 用户拒绝小贝女声，认为机械、不自然；云希/云健同稿样音均通过真实NPU和voice绑定后，用户选定`zm_yunjian`继续调整。完整技术文稿及六个术语、日期数字、长句、分段仍需试听，不能把WAV可播放当作听感通过。
2. 观察较长时间运行、不同长度文稿和资源余量。K8s 完整文稿联调、401/422和客户端网络隔离已通过；Pod重建后自动预加载、Ready恢复、digest及PID1能力复核和客户端经集群DNS健康200均已通过，未额外合成。已有真实socket并发/取消测试，运行配置和边界见`API.md`。执行通过不代替完整文稿听感验收。
3. 改进不支持的短文本NPU profile、读音修正及必要的停顿；禁止悄悄CPU回退、删词或截断。如果云健仍不自然，先比较新的男声提供者，不直接接入线上工作台。
4. 在视频应用独立分支接持久化、owner隔离、不可变的逐镜头音频候选，上传替代配音、试听、明确采用和历史。绑定旁白版本、模型/音色/读音策略及媒体摘要，防旧任务覆盖新文稿。
5. 按采用音频的实测时长协调镜头和留白，再做字幕对齐、校正、预览与冻结快照的带声音MP4，保留SVG/HTML及ZIP导出。
6. K8s 内部服务已交付，继续完成工作台全流程和失败路径验证，再评估线上业务接入及合入。当前未改线上视频、DNS或Casdoor；完成验证后按约定请示合主线。镜像只用`latest`，发布身份记录labels/annotations/digest。

Matcha混合NPU已跑通，但日期逐位走英文、ACP/PTY读法仍有问题；CPU参考曾跳过六个术语，均不能因速度快就作为已验收替代。原失败与后续修复证据同时保留。
