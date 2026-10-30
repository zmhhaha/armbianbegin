# 2026-10-31 阶段验证

本阶段仅验证独立语音服务的实验路径，未交付 HTTP API 或视频配音功能。源码分支为 `codex/speech-service-rk3588`，未合主线。

## 真实执行

worker：192.168.137.211 / Orange Pi 5 Max / RK3588 / Python3.11.2 / RKNPU0.9.8。CPU与NPU小样分别串行启动；每次使用新进程，2核CPU配额、3GiB内存上限、300秒候选超时。未执行并行推理或自动生成重试。

统一文稿位于 `samples/benchmark-zh.txt`，包含数字、日期和 DSH、Cordis、SDK、ACP、PTY、LSP。不同引擎的前端并不相同，不能将下列值直接解释为同算法的纯硬件加速比。

| 项目 | CPU 参考 | Matcha 混合候选 |
| --- | ---: | --- |
| 预加载 | 3.958 秒 | 声学模型加载后，NPU运行库定位失败 |
| 短句合成 / 音频时长 | 0.405 / 2.588 秒 | 未生成 |
| 技术文稿合成 / 音频时长 | 5.292 / 35.037 秒 | 未生成 |
| 技术文稿 RTF | 0.1510 | 无 |
| 峰值自身 RSS | 288,706,560 B（275.3 MiB） | 262,180,864 B（初始化失败进程） |
| NPU 推理 | CPU provider；无NPU Python导入或调用 | 0次成功推理，不能算NPU通过 |

CPU 控制器的 `passed` 仅表示媒体/执行证据判据通过。日志对六个技术术语均报告 `OOV word skipped`，因此业务质量未通过，不能把较快生成时间当成可直接采用的成片能力。

Matcha失败原因为 Lite2 的 `_get_rknn_api_lib_path` 未识别私有目录，仅设置 `LD_LIBRARY_PATH` 不足以通过其文件路径检查。官方运行库已经校验并放在 `speech-service/lib/librknnrt.so`；尚无证据要求升级驱动。官方2.3.2文档的一般建议为driver≥0.9.2，现有0.9.8符合一般要求，但这不代替目标模型实测。

Kokoro源包共500,370,817B、161文件（160资产+manifest），manifest SHA256为 `83733c717e0ce5b76ac1295e4827cf3ad2e111955259e9d670897e100fabeb6e`。79个资产完成，余81个共87,460,503B；下载遭429后已停止。所有完成文件经过下载器的SHA256校验，未执行Kokoro推理。

## 工件与边界

- 官方运行库 SHA256：`d31fc19c85b85f6091b2bd0f6af9d962d5264a4e410bfb536402ec92bac738e8`，7,726,232B；来源固定 `rknn-toolkit2@42aa1d426c0a9e0869b6374edba009f7208a1926`。
- 源码归档 SHA256：`52aee0cb7f1bf25a04ad01ee906f27b7b665df22b2d266cfea97a7e43460718c`。
- 英语前端小模型：`en_core_web_sm-3.8.0-py3-none-any.whl`，12,806,118B，SHA256 `1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85`。
- worker原始证据：`/root/armbianbegin/speech-service/evidence/`；阶段归档 `stage-20261031.tar.gz`。
- 本地也已取回该归档及解包文件，位于此目录下被Git忽略的 `evidence/`。归档1,038,289B，SHA256 `1f5a67cdb984a46758e579ddd0500c4d1c1329b3f6f336b7128c3739e66c9aa4`。
- 包括CPU两条WAV、CPU/NPU控制器、逐请求JSON、负载采样、后端日志、实际依赖锁、源码/运行库receipt及worker检查点。

收尾时查询没有运行中的 `speech-lab-*` unit，未创建常驻语音HTTP服务或自动恢复任务；不在无人值守时继续生成。系统驱动、系统Python、系统动态库、线上视频服务、DNS及Casdoor均未改。

## 离线检查

23项通过：15项媒体与执行证据判据，8项源码/模型完整性及显式恢复。覆盖真实PCM帧数、截断/静音、CPU与NPU区分、预加载不冒充合成、意外回退、缺失/损坏文件、legacy receipt迁移、429部分文件恢复。修复后的完整性脚本尚未在worker重新运行，后续使用前先统一更新脚本再核验。
