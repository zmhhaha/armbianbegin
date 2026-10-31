# 下一阶段

2026-10-31 最新用户反馈：完整云健成片仍有明显机械感，声音质量未通过认可。用户已选定无字幕图解，先用短口语稿、把技术标识留画面来改善表达，再分别判断音色与节奏。现 API 没有情绪、局部重音或 SSML；尚无同 Kokoro/云健/文本/前端的 CPU 与 NPU 人工听感 A/B，不能把机械感原因直接定为模型上限，或宣称调速已解决。八镜技术验收保留，完整稿听感继续待办。

代码位于独立分支`codex/speech-service-rk3588`，目录`speech-service`与`llm-service`同级。worker目录`/root/armbianbegin/speech-service`；复用已有模型、vendor和venv，不升级驱动、不覆盖宿主库。

K8s 内部服务已部署于 namespace `speech-service`、节点 `orangepi5-max-server1`；接入地址 `http://speech-service.speech-service.svc.cluster.local/v1`。分段修复 `c506bb3c105c81200bc3b86577b65fb96f3361e8` 已部署为 latest digest `sha256:adb9d87b15b461db56a2f4aca5fd6999221fe4c715ee3751250b3a4b21423634`，Pod `speech-service-758cbd54f9-bfczb` Ready／Running、异常重启 0，实际 PID1 capabilities 全 0、NNP=1。工作台 8 镜真实语音均已采用，206 秒 MP4 独立技术检查与工作台重启后持久化均通过；**完整稿听感未获用户认可**。部署身份与权限边界见 [DEPLOYMENT.md](DEPLOYMENT.md)，具体证据见 [VALIDATION.md](VALIDATION.md)。

最终证据归档 19,122,821B，SHA-256 `64cbe74652f62513504df98d4fa2ea483d5400fdfecd69fe02d2409b7269bec0`，已下载校验并安全解包至 `D:\github\armbianbegin\.runtime\video-audio-production\evidence-final\`，成片为 `live-audio/dsh-narrated.mp4`。OpenSpec 已同步并验证通过，19 项完成 14 项，保留 1.1 整稿听感、4.2 术语人工试听及 5.1–5.3 BGM。工作台上传／播放／导出／局部失效／重启及归档均无需重复执行；第三／六镜历史失败继续保留。

1. **按用户选定的中文男声云健继续试听。** 用户拒绝小贝女声，认为机械、不自然；云希／云健同稿样音均通过真实 NPU 和 voice 绑定后，用户选定 `zm_yunjian`。完整稿自然度、术语、日期数字、长句和停顿仍需人工认可，不能把可播放或波形匹配当作听感通过。
2. 人工校正 44 条 estimated 字幕。时间／文本与 timeline 一致已验证，仍不能宣称强制对齐或人工校对完成。
3. 后续实现 BGM／混音，并补充全服务音频容量管理与删除流程；保持原文、语速、10% snap 限制与禁止静默 CPU generator 回退。
4. 观察不同长度文稿、运行时长和资源余量。此前单次 201 字符合成 34.912 秒生成 42 秒音频、cgroup 峰值约 2.89GiB／上限 4GiB、OOM 为 0，只是历史样本，不作所有文稿的容量承诺。

独立分支未合主线，DNS／Casdoor 保持不变。镜像只用 `latest`，源码身份继续记录 labels／annotations／digest。

Matcha混合NPU已跑通，但日期逐位走英文、ACP/PTY读法仍有问题；CPU参考曾跳过六个术语，均不能因速度快就作为已验收替代。原失败与后续修复证据同时保留。
