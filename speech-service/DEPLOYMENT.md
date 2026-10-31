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

实际发布摘要与验收结果在任务结束时补入下文。
