# 下一阶段

2026-11-01 四男声已部署，新增对比项目的三声线真实联调通过。云夏、云扬新增资产已传至 worker，官方固定 revision 元数据／实际 SHA、5 成员闭包和只读 float32 style 均核验；全部 4 声线启动校验与鉴权 `/v1/voices` catalog 通过。服务支持同一模型按请求选择云健、云希、云夏、云扬，默认仍云健，上层工作台按项目统一音色。完整离线／HTTP 测试 91 项通过；浏览器同一短稿、speed=1.0，对云希／云夏／云扬各真实生成一次，三条完整 WAV、不同 SHA 及候选 metadata 对提交请求的 voice 绑定通过，无自动重试。服务代码强制检查逐段 NPU 来源与音色，本轮未额外持久化逐段 metadata 或调用插桩；执行结果不等于自然度获认可。

对比项目为 `9d025676-7138-4a45-83fb-7987b6d15872`（“男声音色对比（项目统一音色验收）”），revision 11，当前项目音色云扬；三候选均未采用，留待用户试听。云希／云夏候选因项目切换音色标 stale，仍可试听；云扬非 stale。原 DSH 项目 revision 27 与八镜项目 revision 69 均保留，原八条采用音频指针和非 stale 状态不变。证据已取回 `D:\github\armbianbegin\.runtime\video-audio-production\multi-male-voices\browser-comparison-evidence\`，完整部署与媒体核验见 [VALIDATION.md](VALIDATION.md)。

2026-10-31 最新用户反馈：完整云健成片仍有明显机械感，声音质量未通过认可。用户已选定无字幕图解，先用短口语稿、把技术标识留画面来改善表达，再分别判断音色与节奏。现 API 没有情绪、局部重音或 SSML；尚无同 Kokoro/云健/文本/前端的 CPU 与 NPU 人工听感 A/B，不能把机械感原因直接定为模型上限，或宣称调速已解决。八镜技术验收保留，完整稿听感继续待办。

代码位于独立分支`codex/speech-service-rk3588`，目录`speech-service`与`llm-service`同级。worker目录`/root/armbianbegin/speech-service`；复用已有模型、vendor和venv，不升级驱动、不覆盖宿主库。

K8s 内部服务已部署于 namespace `speech-service`、节点 `orangepi5-max-server1`；接入地址 `http://speech-service.speech-service.svc.cluster.local/v1`。当前四男声源码 `a0f43e04eab5b77a88ddfcf4e08fa1287f2b47e0` 已部署为 latest digest `sha256:96b4bc880e18c9b3570b263da3b34d67574a0a1a700f252deadba658870287b7`，Pod `speech-service-d97d54fb6-8vbb2` Ready、异常重启 0，实际 PID1 capabilities 全 0、NNP=1。此前分段修复版完成的工作台 8 镜真实语音采用、206 秒 MP4 独立技术检查与工作台重启持久化结果保留；**完整稿听感未获用户认可**。引导权限边界见 [DEPLOYMENT.md](DEPLOYMENT.md)，当前部署身份与具体证据以 [VALIDATION.md](VALIDATION.md) 为准。

此前八镜证据归档 19,122,821B，SHA-256 `64cbe74652f62513504df98d4fa2ea483d5400fdfecd69fe02d2409b7269bec0`，已下载校验并安全解包至 `D:\github\armbianbegin\.runtime\video-audio-production\evidence-final\`，成片为 `live-audio/dsh-narrated.mp4`。该阶段 OpenSpec 已同步并验证通过，19 项完成 14 项，保留 1.1 整稿听感、4.2 术语人工试听及 5.1–5.3 BGM；这是历史快照，后续工作台与规格更新由发布负责人单独记录。工作台上传／播放／导出／局部失效／重启及归档均无需重复执行；第三／六镜历史失败继续保留。

1. **试听新项目中三条男声对比，再决定是否调整项目音色。** 云健仍为服务默认，用户此前选云健继续调整，不代表本轮已接受云希、云夏或云扬。三条候选均未自动采用；完整稿自然度、术语、日期数字、长句和停顿仍需人工认可，不能把可播放或波形匹配当作听感通过。
2. 人工校正 44 条 estimated 字幕。时间／文本与 timeline 一致已验证，仍不能宣称强制对齐或人工校对完成。
3. 后续实现 BGM／混音，并补充全服务音频容量管理与删除流程；保持原文、语速、10% snap 限制与禁止静默 CPU generator 回退。
4. 观察不同长度文稿、运行时长和资源余量。此前单次 201 字符合成 34.912 秒生成 42 秒音频、cgroup 峰值约 2.89GiB／上限 4GiB、OOM 为 0，只是历史样本，不作所有文稿的容量承诺。

独立分支未合主线，DNS／Casdoor 保持不变。镜像只用 `latest`，源码身份继续记录 labels／annotations／digest。

Matcha混合NPU已跑通，但日期逐位走英文、ACP/PTY读法仍有问题；CPU参考曾跳过六个术语，均不能因速度快就作为已验收替代。原失败与后续修复证据同时保留。
