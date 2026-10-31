# speech-service

独立语音服务目录，与 `llm-service` 同级。云健语音 API 已在自有 K8s 内部部署，运行于 `orangepi5-max-server1`，namespace 为 `speech-service`。集群内客户端地址：`http://speech-service.speech-service.svc.cluster.local/v1`。

2026-10-31 已用视频原版 SpeechClient 经 K8s Service 完成一次 201 字符技术文稿合成：34.912秒生成42秒音频。随后重建Pod，自动预加载、Ready恢复及客户端经集群DNS健康200均通过，未重复合成。用户选定云健 `zm_yunjian` 继续调整，完整文稿听感尚待试听；工作台逐镜头配音采用、字幕和 MP4 仍待开发。部署配置与发布身份见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 当前结果

2026-10-31 继续验证（各候选单次测量）：

| 路线 | 实际结果 | 结论 |
| --- | --- | --- |
| Matcha + Vocos，CPU 参考 | 技术文稿生成 35.037 秒音频，合成 5.292 秒，进程峰值 RSS 275.3 MiB | 能生成音频，但日志明确跳过 DSH、Cordis、SDK、ACP、PTY、LSP，尚不满足技术旁白需求 |
| Matcha CPU 声学 + RK3588 NPU Vocos | 修复私有库路径后，44.24秒音频用时13.455秒，段落19次成功NPU调用，峰值328.3MiB | 能执行；日期逐位走英文，ACP/PTY等缩写读法仍需修正 |
| Kokoro ConvOnly + 显式中英文前端 | 原文稿52秒音频用时34.349秒，8段覆盖全文，段落788次成功NPU调用，峰值约2.85GiB | 无CPU生成器回退；用户试听认为机械、不自然，明确要求男声，当前小贝女声不作为默认旁白 |
| 回环实验的 Kokoro + 云健男声 | 通过真实API及视频原版客户端生成42秒完整技术文稿，用时31.434秒；短样音11秒、159次成功NPU调用 | 用户比较云希/云健后选择云健继续；完整文稿听感仍待试听 |
| K8s 内部服务 + 云健男声 | 原版客户端经 Service 合成42秒完整技术文稿，用时34.912秒；24kHz/mono/PCM16，未自动重试 | 集群内部 API 实联通过；网络隔离、鉴权及应用进程能力清除已实测 |

这些值不是同算法的纯硬件加速比，也不能证明NPU比CPU更快。详细证据见 [VALIDATION.md](VALIDATION.md)，后续事项见 [NEXT_STEPS.md](NEXT_STEPS.md)。

当前单副本、单合成槽位，请求1CPU/3GiB，限制2CPU/4GiB；本次 cgroup 内存峰值约2.89GiB，未发生 OOM。模型只读挂载，服务无出站网络，客户端需 `speech-client=true` 标签及 Bearer 凭据。

Pod 使用 root 且未启用 `privileged`。引导阶段临时持有 `SYS_ADMIN` 和 `SETPCAP`，只在容器私有挂载命名空间提供 RK3588 兼容信息；启动应用前清除全部能力及 bounding 集合。真实应用 PID 1 的五组能力均为0、`NoNewPrivs=1`，固件视图只读。这个引导权限例外及复核方法见部署文档。

## 目录与版本

- 实验节点：`orangepi5-max-server1`（192.168.137.211），RK3588 / 约16GB内存，驱动0.9.8。
- worker 根目录：`/root/armbianbegin/speech-service`；模型、vendor、虚拟环境和原始证据均在此目录内。
- RKVoice 源码：`suharvest/rkvoice-stream@f2c2d730403e1d4c732add799f0414da34695043`。
- 转换模型：`harvestsu/seeed-local-voice-rk-artifacts@3f8d58c8446ec4b18891624ad4ae4ce75e0f3d3e`。
- RKNN Runtime / Lite2：2.3.2；ORT：1.19.2；NumPy：1.26.4；sherpa-onnx：2.0.1。
- 设备插件：由 `squat/generic-device-plugin@7626d567413ce3831e5ec99471dcdd3a9250cf81` 固定源码构建 ARM64 静态程序并打包为 scratch 镜像，成组分配 NPU DRM 与 DMA heap 设备。

模型、二进制和 WAV 不进入 Git。下载器固定来源与内容身份，完整性失败即停止；重新运行时检查已有源码、模型和前端文件，已有 marker 不代表内容仍然完整。

## 工具

- `scripts/prepare_source.py`：固定源码归档及逐文件校验。
- `scripts/download_runtime.py`：下载官方 ARM64 运行库至私有 `lib/`，不写 `/usr/lib`。
- `scripts/download_matcha.py`：Matcha 中文前端、CPU Vocos 与 RK3588 Vocos 工件；`--cpu-only` 可先准备 CPU 参考。
- `scripts/download_kokoro_bundle.py`：完整 Kokoro 包及逐文件校验；在公开源恢复后显式重跑，保留有效文件。当前不自动重试。
- `scripts/with_private_runtime.py`：在Linux私有mount namespace中为Lite2提供固定库路径，原宿主 `/usr/lib` 不安装或覆盖库；实验由有限时长的systemd unit管理。
- `scripts/prepare_image.py`、`Dockerfile`、`build.sh`：从已测 ARM64 环境按固定版本提取并逐文件记录 Python 依赖，准备已校验源码、运行库与英语模型，构建 `latest` 镜像。
- `speech_service/container_bootstrap.py`：隔离 Python 引导、容器内兼容信息挂载与能力清除；应用启动前复核实际能力和只读挂载。
- `k8s.yaml`、`k8s-device-plugin.yaml`、`deploy.sh`：集群内部服务、设备插件及发布校验，操作说明见部署文档。
- `scripts/audit_matcha_frontend.py`：只加载文字前端，逐项核验词典/音素覆盖、缩写与数字风险，不调用模型或NPU。
- `scripts/download_male_voices.py`：两个官方中文男声固定工件及无Torch转换，资产在原bundle之外单独校验。
- `scripts/sample_male_voice.py`：男声短样音、真实voice绑定和NPU调用证据；不自动重试。
- `benchmarks/benchmark.py`：单并发、新进程、相同短句与技术文稿，保存真实媒体属性、CPU/RSS、NPU负载及实际推理调用证据。
- `scripts/matcha_cpu_baseline.py`：独立 CPU 参考脚本；统一比较优先使用 benchmark 控制器。

准备固定源码与工件的示例（在专用实验目录运行）：

```bash
python3 scripts/prepare_source.py --root "$PWD"
python3 scripts/download_runtime.py --root "$PWD"
python3 scripts/download_matcha.py --root "$PWD/models/matcha" --cpu-only
python3 scripts/download_kokoro_bundle.py "$PWD/models/kokoro-convonly-rk3588" --jobs 1 --interval 1
```

实验依赖使用专用虚拟环境。worker 的系统 Python 缺少 ensurepip，实验准备时使用系统 pip 的 `--python` 选项将 pip 装入隔离环境，没有安装宿主系统软件包。容器从这个已测环境提取固定版本分发文件闭包并生成逐文件 receipt；基础版本见 `requirements-lab.txt`，中文前端 ABI 约束见 `constraints-lab.txt`，容器版本清单见 `requirements-container.txt`。

Kokoro 中文使用 `misaki[zh]==0.9.4`、spaCy3.8.7、Thinc8.3.10、`en_core_web_sm==3.8.0`；不需要 Torch 或 transformer 英语模型。小型英语模型是中文夹杂缩写路径的依赖，本轮已装入虚拟环境。

配置及测量命令见 [benchmarks/README.md](benchmarks/README.md)。环境就绪、媒体完整性和 NPU 子模块调用成功，分别与中文质量验收区分。

## 内部语音 API

`speech_service/` 提供 `POST /v1/audio/speech`、`GET /health/live` 和 `GET /health/ready`。管理员固定模型/音色，凭据只从 `TOKEN_FILE` 读取。单进程、单HTTP worker、单合成槽位；忙时429，不自动重试或换模型。HTTP超时或断开后，原生合成未结束时仍保持忙状态；清理在同一执行线程中排到合成之后。

输入、JSON body、速度、音频字节和实际时长均有限制；只发布完整且非全零的PCM16 WAV。试验后端在CPU生成器profile渲染前拒绝回退，并检查输出分段覆盖。中英文策略保留中文数字规则，英文单词走Misaki英语前端，多字母大写缩写明确按字母朗读；不擅自展开术语含义。

已有视频 `SpeechClient` 的base URL应以 `/v1` 结尾；K8s 内部地址和接入设置见 [API.md](API.md)。云健完整文稿已验证42秒/24kHz/mono WAV、无凭据401和错误模型422；未标记客户端在4秒内网络超时，加 `speech-client=true` 后健康检查200。视频业务配音、字幕及MP4仍待接入。

## 离线验证

```bash
python -m unittest discover -s speech-service/tests -p 'test_*.py' -v
python -m unittest discover -s speech-service/benchmarks -p test_measurement.py -v
```

从仓库根目录运行。此前79项已在Windows及ARM通过；本次 K8s 部署未重跑该套测试，新增验证为编译、实际容器预加载及 K8s 原版客户端实联。既有测试不安装、下载或执行模型，包含真实socket超时/断连、忙槽位、男声工件校验及初始化失败保护。Windows使用Uvicorn0.49.0，ARM和镜像使用0.54.0。
