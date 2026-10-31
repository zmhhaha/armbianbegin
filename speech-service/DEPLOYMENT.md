# RK3588 内部语音服务

目标节点为 `orangepi5-max-server1`（192.168.137.211），固定中文男声云健 `zm_yunjian`，模型别名 `kokoro-rk3588`。接口为集群内部 `http://speech-service.speech-service.svc.cluster.local/v1`；工作台已接入音频候选、上传、试听采用、字幕和 MP4 功能，八镜头真实配音、206 秒 MP4 独立技术检查及工作台重启后持久化均已通过。完整稿听感尚未获用户认可。

## 2026-10-31 分段修复已部署与八镜联调

真实验收副本已完成并采用全部 8 镜语音。第三镜此前 operation `0f99c230-d5b4-414c-8c4e-8175e464ea67` 失败已定位为 CLI 文本 `--patch` 中的 U+002D 不在 Kokoro 词表；通过工作台显式读音修正处理第 3／5／6 镜的 CLI、路径和文件名，原旁白文稿不改。第六镜原 operation `03d700c9-e71d-4dd7-bbff-fa608acc82c1` 随后因分段 profile 失败；两次旧 failed 均保留，没有自动重试，以新 intent 完成后续真实合成。

第六镜的隔离 CPU 前端 probe 证实：原首段自然时长 D=181 选择 target D=200 时，snap 比例约 10.497%，超过原有 10% 限制，因禁止 CPU generator 回退而拒绝。修复源码 `c506bb3c105c81200bc3b86577b65fb96f3361e8` 在任何 NPU 波形渲染前规划完整分段，只有限尝试相邻文本边界，不改文稿、语速或 10% 限制，不开启 CPU 波形回退。隔离 CPU probe 中改选首段边界后 D=172→160，完整 5 段均满足原 NPU profile 条件；单元测试 **82 项通过**。

修复已构建并部署 `arm-cluster-master:5000/speech-service:latest@sha256:adb9d87b15b461db56a2f4aca5fd6999221fe4c715ee3751250b3a4b21423634`，源码 `c506bb3c105c81200bc3b86577b65fb96f3361e8`。Pod `speech-service-758cbd54f9-bfczb` Ready；实际 PID1 的 CapInh／Prm／Eff／Bnd／Amb 全部为 0、NoNewPrivs=1。修复版真实完成第 6–8 镜，工作台全 8 镜录音已采用；此前仅 CPU 规划 probe 与之后真实波形验证分别记录，不混为同一次检查。

206 秒 MP4 render `5641dc62-01d7-4540-8e79-501ec801cced` 已完成并独立验证 H.264／AAC、1280×720@24fps、4944 帧完整解码。8 镜音频首尾匹配通过，全片相关系数 0.9999445、NRMSE 0.010601；8 张参考 PNG 的画面与顺序通过，44 条字幕时间／文本与 timeline 一致但仍为 estimated。MP4 SHA-256 `75ab83eba053d20b0d8beee8687709ee5aadd10eabef8549dfc4b55122358c31`。这些技术检查不代替完整稿自然度、发音和人工字幕校对。

工作台 rollout restart 后新 Pod `video-workbench-6454f4845f-bj52n` Ready，工作台镜像仍为 `sha256:ccd2509379ad55029760cf5229d09dd33b0577213172a20e791d9818ad06c6fe`、异常重启 0。8 条采用录音逐一 SHA 匹配、上传 A2 历史保留、MP4 SHA 匹配、SQLite integrity ok、原 DSH revision 27 保留，PID1 五组 capabilities 全 0／NNP=1；PVC 当时可用 988,618,752B。speech Pod `speech-service-758cbd54f9-bfczb` 仍 Running、异常重启 0。回执位于 master `/root/video-audio-release-20261031/postflight.json`。分支保持 `codex/speech-service-rk3588`，未合主线。

最终证据归档 19,122,821B，SHA-256 `64cbe74652f62513504df98d4fa2ea483d5400fdfecd69fe02d2409b7269bec0`，已下载校验并安全解包至 `D:\github\armbianbegin\.runtime\video-audio-production\evidence-final\`，成片为 `live-audio/dsh-narrated.mp4`；第 03／06 镜中心帧已目视检查，中文正常。OpenSpec 变更 `add-video-workbench-audio-production` 已同步并验证 `valid=true`、无 issues，19 项完成 14 项；剩余 5 项为整稿听感、术语人工试听与 BGM 的 3 项任务，不将技术验收冒充人工认可。

## 资源与设备

单副本、Recreate 更新、单原生合成槽位；申请 1 CPU / 3GiB，限制 2 CPU / 4GiB。设备插件把同一 NPU 的 `card1`、`renderD129` 与三个 `dma_heap` 字符设备作为一个 `panghuer.top/rknpu` 资源交给 kubelet，避免仅挂载目录却没有设备 cgroup 权限。

原模型及官方男声音色分别从节点的专用目录只读挂载，模型不在镜像中；不能任意迁移到其他 ARM 节点。插件使用默认 proc 遮罩，挂载只读设备目录和可写 kubelet 插件 socket 目录。

推理进程按设备原权限使用 UID0，禁止提权、只读根文件系统、不挂载 ServiceAccount token。RKNN Lite2 还检查 `/proc/device-tree/compatible`；该链接指向默认 OCI 遮罩下的 `/sys/firmware`，显式挂载单文件仍被遮蔽。Docker 单独运行可用 Unmasked，但现有 K8s API 将未启用的该字段恢复成 Default，因此部署保留默认遮罩。

启动引导程序仅临时持有 `SYS_ADMIN` 和 `SETPCAP`：隔离挂载传播，把只包含原始板卡兼容标识的私有目录只读挂载到本容器 `/sys/firmware`，随后用 setpriv 清空全部 capability bounding/inheritable/ambient sets，再验证有效与允许 capabilities 均为 0、NoNewPrivs 为 1，才执行 TTS。引导阶段用隔离且禁用 site 的 Python，不加载语音依赖；不会将两项启动权限交给处理 HTTP 文稿的进程。Pod 不是 privileged，也不更改集群 feature gates 或宿主挂载。

容器内独立安装已校验的 RKNN 动态库，宿主 `/usr/lib`、驱动、系统 Python 均不修改。所有前端和模型启动时离线加载；网络策略仅允许带 `speech-client: "true"` 标签的客户端访问，服务本身无网络出站。

## 构建与部署

语音镜像准备脚本从现有 ARM64 CPython3.11 虚拟环境提取固定的 103 个分发包，逐文件记录 SHA256，不复制虚拟环境执行文件、editable 路径或模型。英语前端 wheel、原始 vendor 及运行库分别核验；构建内执行 pip check、实际模块导入和动态库加载检查。初次在线安装依赖遭遇下载超时，因此当前构建使用已验证依赖的离线快照。

在语音节点的专用目录运行：

```bash
PYTHON=.venv/bin/python3 SOURCE_REVISION=<完整源码提交> bash build.sh
```

每个 Docker 构建 RUN 限制 1.5GiB、2 CPU，使用该节点已支持的 legacy builder，不安装新构建器。应用及插件镜像均使用内部仓库的 `latest` 标签，源码身份写入 OCI labels，实际摘要记录于部署注解。`deploy.sh` 需要已推送镜像的真实摘要、源码 revision 以及有 PyYAML 的 Python：

```bash
SOURCE_REVISION=<语音镜像源码提交> \
SPEECH_IMAGE_DIGEST=sha256:<语音镜像摘要> \
PLUGIN_SOURCE_REVISION=<设备插件固定上游提交> \
PLUGIN_IMAGE_DIGEST=sha256:<插件镜像摘要> \
PYTHON=<带PyYAML的Python> bash deploy.sh
```

脚本仅在 Secret 不存在时生成随机凭据，不打印凭据。先等待插件及 NPU 注册，再启动推理容器；rollout 后用 Pod 实际 imageID 核验摘要。调用方同时需要客户端标签和 Bearer 凭据文件；视频工作台通过 `VIDEO_TTS_URL`、`VIDEO_TTS_MODEL`、`VIDEO_TTS_VOICE` 与 `VIDEO_TTS_TOKEN_FILE` 使用适配器。

## 验收与回退

临时客户端挂载原版视频 SpeechClient 和 contracts 的准确字节，先验证 NetworkPolicy、401 和错误模型拒绝，再只生成一次完整技术稿，保存真实 WAV 与 JSON。`scripts/smoke_k8s.py` 会在 HTTP 前声明尝试标记，禁止重复执行同一证据目录。原始源码通过 SHA256 验证，不使用替代客户端。

回退时先将 `speech-service` Deployment 缩容为 0，等待 Pod 退出后可删除同命名空间的 `rknpu-device-plugin` DaemonSet。模型、男声资产和 Secret 均保留，不影响既有视频工作台。

## 历史：2026-10-31 首次实际发布

- 语音镜像：`arm-cluster-master:5000/speech-service:latest`，ARM64，682,834,788B。源码 `615c92bad88c21ad4b0cde30f8adab343dfa330f`；实际摘要 `sha256:c34944342aea009482b71443fb26cb9736b99f8a101166a76eb0fe7e746e102e`。
- 设备插件：`arm-cluster-master:5000/rknpu-device-plugin:latest`，scratch ARM64，13,774,080B。固定上游 `squat/generic-device-plugin@7626d567413ce3831e5ec99471dcdd3a9250cf81`；实际摘要 `sha256:72210a0df7998b715088bdadde7f325a7d81d01e3450b1f0aa3b4bb20473ae96`。
- 插件二进制 SHA256：`096af0b7e21e2801aa88ec1970e83354ba2de125a9b945b4f100d03d1493c044`。上游源码及官方 Go1.26.0 SDK 校验、受限编译和收据由 `scripts/build_device_plugin.py` 管理；SDK 只保存在服务专用缓存，不安装宿主 Go。
- Python 离线快照：103 个分发包、9,538 文件、484,445,470B；收据 SHA256 `e5e245628ab935751ead4e1965654408426bef556d5a9394cdef0743494c5861`。

### 验收结果

1. 默认 OCI 遮罩下的独立 Docker 容器预加载成功，随后 K8s Pod Ready。实际 PID1 的 CapInh/Prm/Eff/Bnd/Amb 全部为 0，NoNewPrivs=1；板卡信息与只读输入一致，五个设备均为真实字符设备。
2. 未带客户端标签的临时 Pod 请求健康接口，4.017 秒超时；添加 `speech-client=true` 后同一接口返回 200。服务端拒绝无凭据请求（401）及错误模型（422）。
3. 挂载原版视频 SpeechClient（SHA256 `4ce02745006f5109d5975716b451718dc07a7465c18c496791152e66cb499ccd`），只进行一次完整技术稿合成，无自动重试。201 字符文稿用时 34.912 秒，生成 42 秒、24kHz/单声道/PCM16 WAV，2,016,044B；SHA256 `be70d486fc685436d6bc27f7671ffe3712ceffc11f461884ba23872899987997`。全部 PCM 帧及 RIFF 边界通过检查，音频非全零。本次 HTTP 运行未额外统计逐 NPU 调用数。
4. 合成后 cgroup 内存峰值 3,103,371,264B（约 2.89GiB），4GiB 上限；OOM/OOM-kill/内存上限事件均为 0。节点当时 MemAvailable 4,086,452KiB（约 3.90GiB）；这是单次样本，不是全部长度的容量承诺。
5. 执行一次 Deployment rollout restart，旧 Pod `speech-service-7f9f984b8-vxzt8` 替换为 `speech-service-6cd6865bd6-4sp9z`。新 Pod 离线预加载恢复，Ready、0 次异常重启；客户端经集群 DNS 请求健康接口仍为 200。实际镜像摘要、PID1 权限和只读挂载再次验证通过；未重复完整文稿合成。
6. 最终仅语音服务与设备插件各一个 Ready Pod、均 0 次异常重启。临时客户端和 ConfigMap 已删除，Secret 保留。宿主 `/usr/lib/librknnrt.so` 仍不存在；无驱动、系统 Python、现有视频服务或域名配置变更。

原始 WAV、JSON、运行日志、镜像和编译收据均已取回 Git 忽略目录 `speech-service/evidence/20261031-k8s/`。master 归档 1,369,767B，SHA256 `2e1f65bfef5a65925a83572e37a7be57c30b57d6ca5d3e5ad5de3984826da0cb`；worker 归档 468,748B，SHA256 `100972959edfb5abe87aad53720b0b1bf6dcdf6240f9535e8992eb5c147d4946`。归档仅包含明确列出的证据，不包含 Secret 或 token。

上述首次内部部署及客户端互通已通过；它不代替后续工作台业务验收，最新进度见本文顶部。完整文稿听感仍需试听认可。代码保留在 `codex/speech-service-rk3588`，未合主线。
