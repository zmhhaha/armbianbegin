# speech-service

独立语音服务目录，与 `llm-service` 同级。当前交付 RK3588 中文语音的可复现实验工具，尚未实现或启动 HTTP 服务，也未接入线上视频工作台。

## 当前结果

2026-10-31 阶段收尾：

| 路线 | 实际结果 | 结论 |
| --- | --- | --- |
| Matcha + Vocos，CPU 参考 | 技术文稿生成 35.037 秒音频，合成 5.292 秒，进程峰值 RSS 275.3 MiB | 能生成音频，但日志明确跳过 DSH、Cordis、SDK、ACP、PTY、LSP，尚不满足技术旁白需求 |
| Matcha CPU 声学 + RK3588 NPU Vocos | 加载声学模型成功；Lite2 未在其支持的查找路径找到私有 `librknnrt.so`，停止于初始化 | 没有执行成功的 NPU 推理，不能据此判断模型效果或硬件不兼容 |
| Kokoro ConvOnly | 固定包 160 个资产文件已完成 79 个，剩约 83.4 MiB；HTTP 429 后停止 | 尚未合成，无质量和速度结论 |

实验已结束，检查时没有运行中的 `speech-lab-*` 任务。没有升级驱动、修改系统 Python、系统动态库或线上工作台。详细证据见 [VALIDATION.md](VALIDATION.md)，恢复步骤见 [NEXT_STEPS.md](NEXT_STEPS.md)。

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

## 离线验证

```bash
python -m unittest discover -s speech-service/tests -p 'test_*.py' -v
python -m unittest discover -s speech-service/benchmarks -p test_measurement.py -v
```

从仓库根目录运行；当前共23项通过。测试不安装、下载或执行模型。
