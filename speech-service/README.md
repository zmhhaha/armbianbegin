# speech-service

独立语音服务目录，与 `llm-service` 同级。已有 RK3588 实验工具和内部 HTTP API 原型；视频应用原版 SpeechClient 已用云健男声完成完整技术文稿联调。用户选定云健继续调整，完整文稿听感仍待试听。

## 当前结果

2026-10-31 继续验证（各候选单次测量）：

| 路线 | 实际结果 | 结论 |
| --- | --- | --- |
| Matcha + Vocos，CPU 参考 | 技术文稿生成 35.037 秒音频，合成 5.292 秒，进程峰值 RSS 275.3 MiB | 能生成音频，但日志明确跳过 DSH、Cordis、SDK、ACP、PTY、LSP，尚不满足技术旁白需求 |
| Matcha CPU 声学 + RK3588 NPU Vocos | 修复私有库路径后，44.24秒音频用时13.455秒，段落19次成功NPU调用，峰值328.3MiB | 能执行；日期逐位走英文，ACP/PTY等缩写读法仍需修正 |
| Kokoro ConvOnly + 显式中英文前端 | 原文稿52秒音频用时34.349秒，8段覆盖全文，段落788次成功NPU调用，峰值约2.85GiB | 无CPU生成器回退；用户试听认为机械、不自然，明确要求男声，当前小贝女声不作为默认旁白 |
| Kokoro + 云健男声 | 通过真实API及视频原版客户端生成42秒完整技术文稿，用时31.434秒；短样音11秒、159次成功NPU调用 | 用户比较云希/云健后选择云健继续；完整文稿听感仍待试听 |

这些值不是同算法的纯硬件加速比，也不能证明NPU比CPU更快。详细证据见 [VALIDATION.md](VALIDATION.md)，后续事项见 [NEXT_STEPS.md](NEXT_STEPS.md)。

## 目录与版本

- 实验节点：`orangepi5-max-server1`（192.168.137.211），RK3588 / 约16GB内存，驱动0.9.8。
- worker 根目录：`/root/armbianbegin/speech-service`；模型、vendor、虚拟环境和原始证据均在此目录内。
- RKVoice 源码：`suharvest/rkvoice-stream@f2c2d730403e1d4c732add799f0414da34695043`。
- 转换模型：`harvestsu/seeed-local-voice-rk-artifacts@3f8d58c8446ec4b18891624ad4ae4ce75e0f3d3e`。
- RKNN Runtime / Lite2：2.3.2；ORT：1.19.2；NumPy：1.26.4；sherpa-onnx：2.0.1。

模型、二进制和 WAV 不进入 Git。下载器固定来源与内容身份，完整性失败即停止；重新运行时检查已有源码、模型和前端文件，已有 marker 不代表内容仍然完整。

## 工具

- `scripts/prepare_source.py`：固定源码归档及逐文件校验。
- `scripts/download_runtime.py`：下载官方 ARM64 运行库至私有 `lib/`，不写 `/usr/lib`。
- `scripts/download_matcha.py`：Matcha 中文前端、CPU Vocos 与 RK3588 Vocos 工件；`--cpu-only` 可先准备 CPU 参考。
- `scripts/download_kokoro_bundle.py`：完整 Kokoro 包及逐文件校验；在公开源恢复后显式重跑，保留有效文件。当前不自动重试。
- `scripts/with_private_runtime.py`：在Linux私有mount namespace中为Lite2提供固定库路径，原宿主 `/usr/lib` 不安装或覆盖库；实验由有限时长的systemd unit管理。
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

依赖仅装在专用虚拟环境。worker 的系统 Python 缺少 ensurepip，本轮使用系统 pip 的 `--python` 选项将 pip 装入隔离环境，没有安装系统软件包。基础版本见 `requirements-lab.txt`，中文前端 ABI 约束见 `constraints-lab.txt`，worker 实际依赖锁及源码/运行库 receipt 随原始证据保存。

Kokoro 中文使用 `misaki[zh]==0.9.4`、spaCy3.8.7、Thinc8.3.10、`en_core_web_sm==3.8.0`；不需要 Torch 或 transformer 英语模型。小型英语模型是中文夹杂缩写路径的依赖，本轮已装入虚拟环境。

配置及测量命令见 [benchmarks/README.md](benchmarks/README.md)。环境就绪、媒体完整性和 NPU 子模块调用成功，分别与中文质量验收区分。

## 内部语音 API 原型

`speech_service/` 提供 `POST /v1/audio/speech`、`GET /health/live` 和 `GET /health/ready`。管理员固定模型/音色，凭据只从 `TOKEN_FILE` 读取。单进程、单HTTP worker、单合成槽位；忙时429，不自动重试或换模型。HTTP超时或断开后，原生合成未结束时仍保持忙状态；清理在同一执行线程中排到合成之后。

输入、JSON body、速度、音频字节和实际时长均有限制；只发布完整且非全零的PCM16 WAV。试验后端在CPU生成器profile渲染前拒绝回退，并检查输出分段覆盖。中英文策略保留中文数字规则，英文单词走Misaki英语前端，多字母大写缩写明确按字母朗读；不擅自展开术语含义。

已有视频 `SpeechClient` 的base URL应以 `/v1` 结尾；云健完整文稿实联已验证42秒/24kHz/mono WAV及401、固定模型拒绝。用户选择云健`zm_yunjian`继续，运行设置见[API.md](API.md)。实验服务只监听worker回环地址并已停止；视频业务配音、字幕及MP4仍待接入。

## 离线验证

```bash
python -m unittest discover -s speech-service/tests -p 'test_*.py' -v
python -m unittest discover -s speech-service/benchmarks -p test_measurement.py -v
```

从仓库根目录运行，共79项在Windows及ARM通过。测试不安装、下载或执行模型；包含真实socket超时/断连、忙槽位、男声工件校验及初始化失败保护。Windows使用Uvicorn0.49.0，ARM使用已安装的0.54.0；API运行要求固定0.54.0。
