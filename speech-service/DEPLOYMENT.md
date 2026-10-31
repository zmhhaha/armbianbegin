# RK3588 内部语音服务

目标节点为 `orangepi5-max-server1`（192.168.137.211），固定中文男声云健 `zm_yunjian`，模型别名 `kokoro-rk3588`。接口为集群内部 `http://speech-service.speech-service.svc.cluster.local/v1`；工作台的音频候选、试听采用、字幕和 MP4 仍需后续接入。

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

脚本仅在 Secret 不存在时生成随机凭据，不打印凭据。先等待插件及 NPU 注册，再启动推理容器；rollout 后用 Pod 实际 imageID 核验摘要。调用方同时需要客户端标签和 Bearer 凭据文件；现有视频客户端配置 `VIDEO_TTS_URL`、`VIDEO_TTS_MODEL`、`VIDEO_TTS_VOICE` 与 `VIDEO_TTS_TOKEN_FILE` 即可使用适配器，业务制作入口另行实现。

## 验收与回退

临时客户端挂载原版视频 SpeechClient 和 contracts 的准确字节，先验证 NetworkPolicy、401 和错误模型拒绝，再只生成一次完整技术稿，保存真实 WAV 与 JSON。`scripts/smoke_k8s.py` 会在 HTTP 前声明尝试标记，禁止重复执行同一证据目录。原始源码通过 SHA256 验证，不使用替代客户端。

回退时先将 `speech-service` Deployment 缩容为 0，等待 Pod 退出后可删除同命名空间的 `rknpu-device-plugin` DaemonSet。模型、男声资产和 Secret 均保留，不影响既有视频工作台。

## 2026-10-31 实际发布

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

内部部署及客户端互通已通过；完整文稿听感仍需试听。工作台业务的配音候选、上传/采用、字幕与 MP4 未因此自动完成。代码保留在 `codex/speech-service-rk3588`，未合主线。
