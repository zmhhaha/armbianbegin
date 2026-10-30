# RK3588 TTS 候选测量

只运行已在独立实验环境准备好的 rkvoice-stream / sherpa-onnx、模型和原生库；不下载或安装任何依赖，不修改驱动/服务。源码接口基线为 `suharvest/rkvoice-stream@f2c2d730403e1d4c732add799f0414da34695043`：`engine.tts.create_backend(name)` 返回 `TTSBackend`，调用 `preload()`，再调用 `synthesize()` 得到 `(WAV bytes, metadata)`。README 中的 `TTSEngine` 图示及 `create_tts(backend=..., model_dir=...)` 示例与该版本实际签名不符。CPU对照使用已审核的 `sherpa-onnx==2.0.1` 的 `GenerationConfig` 和 `OfflineTts.generate(text, generation)` 接口。

每个候选使用一个新进程，串行执行短句 smoke 和同一中文段落；smoke失败即停，候选失败后不继续下一候选。不自动重试、切换模型或下载文件。上游自身可能探测多种加载路径，原始日志及最终实际后端会保存；这与 harness 的重试次数零分别记录。

准备一个不含凭据的 JSON 文件，例如 Matcha：

```json
{
  "name": "matcha-rk3588",
  "backend": "matcha_rknn",
  "source_revision": "f2c2d730403e1d4c732add799f0414da34695043",
  "expected_matcha_backend": "ort",
  "env": {
    "RK_PLATFORM": "rk3588",
    "TTS_MODEL_DIR": "/opt/speech-service/models/matcha",
    "MATCHA_MODEL": "matcha-s64.rknn",
    "MATCHA_USE_ORT": "1",
    "MATCHA_ONNX_PATH": "/opt/speech-service/models/matcha/model-steps-3.onnx",
    "VOCOS_MODEL": "vocos-16khz-600.rknn",
    "VOCOS_FRAMES": "256"
  },
  "speed": 1.0
}
```

路径是示例，不证明 artifact 已就绪。上述配置对应预定的 **CPU声学模型+NPU Vocos** 混合路径：只有明确指定 `expected_matcha_backend: "ort"` 时才接受。不能把它称作全NPU声学推理。RK3588 bundle 的 `vocos-16khz-600.rknn` 文件名不代表真实600帧，已知该工件实际为256帧。候选必须填写与工件输入形状一致的 `MATCHA_MODEL_SEQ_LEN`、`MATCHA_MAX_PHONEMES`、`VOCOS_FRAMES` 等参数；若另行审核了单RKNN或split RKNN声学模型，可使用 `expected_matcha_backend: "rknn"` / `"rknn_split"` 并准备相应工件。不要把RK3576的split工件直接当成RK3588文件。模型/库的独立验收 receipt 可通过 `artifact_receipt` 记录其路径与 SHA256。

Kokoro 配置示例：

```json
{
  "name": "kokoro-rk3588",
  "backend": "kokoro_convonly",
  "source_revision": "f2c2d730403e1d4c732add799f0414da34695043",
  "env": {
    "RK_PLATFORM": "rk3588",
    "KOKORO_CONVONLY_ROOT": "/opt/speech-service/models/kokoro",
    "KOKORO_CONVONLY_MANIFEST_SHA256": "REVIEWED_MANIFEST_SHA256",
    "KOKORO_FRONTEND_INTRA_OP_THREADS": "2",
    "KOKORO_FRONTEND_INTER_OP_THREADS": "1"
  },
  "synthesis_kwargs": {"language": "zh", "voice": "zf_xiaobei"},
  "speed": 1.0
}
```

在 Linux 实验环境中执行，使用实际准备好的解释器与配置文件：

```bash
/opt/speech-service/venv/bin/python speech-service/benchmarks/benchmark.py \
  --candidate /opt/speech-service/experiments/matcha.json \
  --output /opt/speech-service/evidence/matcha-first-run \
  --timeout 300 --interval 0.25
```

同一harness也支持明确的纯CPU对照 `sherpa_matcha_cpu`，使用相同新进程、同样的smoke和paragraph、CPU/RSS/NPU load采样、WAV校验与RTF口径。CPU只构造 `provider="cpu"` 的完整Matcha声学模型和原始Vocos ONNX，不导入rkvoice/rknnlite，不接受provider覆盖。配置示例（实际路径应与单独审核的工件一致）：

```json
{
  "name": "matcha-cpu-reference",
  "backend": "sherpa_matcha_cpu",
  "speed": 1.0,
  "cpu_config": {
    "acoustic": "/opt/speech-service/models/matcha/matcha-icefall-zh-en/model-steps-3.onnx",
    "vocoder": "/opt/speech-service/models/matcha/vocos-16khz-univ.onnx",
    "tokens": "/opt/speech-service/models/matcha/matcha-icefall-zh-en/tokens.txt",
    "lexicons": ["/opt/speech-service/models/matcha/matcha-icefall-zh-en/lexicon.txt"],
    "rule_fsts": [
      "/opt/speech-service/models/matcha/matcha-icefall-zh-en/phone-zh.fst",
      "/opt/speech-service/models/matcha/matcha-icefall-zh-en/date-zh.fst",
      "/opt/speech-service/models/matcha/matcha-icefall-zh-en/number-zh.fst"
    ],
    "num_threads": 4,
    "noise_scale": 0.667
  }
}
```

`cpu_config`的全部字段都须显式填写；`rule_fsts: []` 明确关闭FST规则时也会记录，日常对照应保留日期、数字与电话规则。CPU使用sherpa原生lexicon/FST前端，与rkvoice的自定义前端不同；报告标记 `complete_cpu_reference_different_frontend`，因此这是完整CPU方案的参考，不是仅替换NPU、其他完全相同的速度归因实验。它的声码器也使用原始ONNX，而非RKNN重建版本。CPU路径不做额外warmup，smoke是首次生成，paragraph在同一进程中使用已加载引擎；NPU上游preload若有内部warmup，仍会明确单独记录，无法声称所有后端内部冷热状态完全一样。

CPU对照通过要求是正常的CPU provider、声学和声码器CPU metadata、0次NPU调用、无NPU Python模块载入或尝试导入。CPU工作进程阻断NPU Python模块导入，证据保存在 `loaded_backend.runtime_info` 及 `cpu_no_npu_python_imports`。系统NPU负载仍照常采样，可能来自其他进程；这项检查不声称系统其他程序没有使用NPU，也不代替原生库内部的硬件审计。CPU报告的 `execution_class` 是 `cpu_reference`，不会因没有NPU调用而失败，也不会被归类为NPU通过。

可重复 `--candidate` 顺序比较多个候选，但先准备并审核全部配置，输出目录必须不存在。默认通过 `/tmp/speech-service-benchmark.lock` 防止同时运行另一份harness；两个候选应使用相同 sample 文件、速度和环境条件，不要同时运行其他 NPU 工作负载。`--npu-load` 可指定实际可读的 RK3588 load 文件，程序不会挂载 debugfs 或提升权限，读不到会明确记录错误。线程数与CPU亲和性由实验配置控制并在外部记录；测量不会擅自调整调度器或清空系统文件缓存。

每个候选的输出：

- `backend.log`：完整stdout/stderr和异常，无截断重试。
- `samples.jsonl`：带阶段的进程树CPU/RSS和原始NPU load采样。CPU以一核100%计；进程树RSS之和可能重复计算共享页。系统NPU负载是旁证，不能证明负载来自该任务。
- `worker.json`：import/create/preload时间、进程冷启动（可能包含上游warmup）、各次真实合成时间、从PCM帧数计算的音频时长和RTF、WAV SHA256、峰值自身RSS、实际模块源码SHA256、后端原始metadata、每次推理调用计数、清理结果。
- `smoke.wav`、`paragraph.wav`：完整可解码PCM16文件。拒绝流式RIFF占位长度、截断、非PCM16、空音频或数字静音；不转码修复失败输出。
- `controller.json`：单次子进程退出码、墙钟期限、进程树采样峰值与失败原因；`run.json`汇总已实际运行的候选。

NPU子模块通过要求：合成期间观察到 `RKNNLite.inference` 或 Kokoro `RK3588CapiRuntime.inference` 成功返回，实际选中后端符合配置，而且没有未经声明的CPU回退。计数按已加载模型路径记录；包装器只调用原方法一次，不替换输入/输出；预加载调用与每次合成调用分开统计。`is_ready()`、模型文件名、load成功或看到NPU负载均不能单独通过。Matcha走未声明的ORT声学回退会在合成前停止，显式审核的ORT声学+NPU Vocos则记录为有意混合路径；Kokoro的CPU/mixed路由会保留已生成音频与证据后失败停止。通过仅表示这些NPU子模块调用成立，不表示整模型/前端/ISTFT都在NPU。

`source_revision` 是操作者声明；真正执行的engine/backend文件哈希另外保存，须与独立源码/工件receipt对应。不会把声明的commit伪装成已验证的整包来源。CPU文件缓存未清空，因此冷启动仅指新进程。smoke之后的paragraph是该进程内已加载测量。媒体完整性/NPU证据通过不等于中文发音、自然度、长句完整性或生产可用性，仍需完整试听。

无模型的媒体与测量判据检查：

```bash
python -m unittest discover -s speech-service/benchmarks -p test_measurement.py -v
```
