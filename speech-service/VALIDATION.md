# 2026-10-31 阶段验证

云健语音 API 已部署于自有 K8s，分段修复版已完成工作台八镜头真实合成与采用，206 秒 MP4 独立技术检查和工作台重启后持久化均通过。完整文稿听感尚未获用户认可。源码分支为 `codex/speech-service-rk3588`，未合主线；DNS 和 Casdoor 保持不变。最新修复与此前镜像的检查分开记录，后文保留原始失败及修复记录。

## 最新：分段修复已部署与八镜头真实联调

| 检查 | 当前证据与边界 |
| --- | --- |
| 工作台真实语音 | 验收副本全部 8 镜已真实合成并明确采用，修复后第 6–8 镜真实通过；两个旧失败不覆盖 |
| 第三镜根因 | 原 CLI 文本 `--patch` 的 U+002D 不在 Kokoro 词表；不是空标点片段误拒。工作台显式读音修正第 3／5／6 镜的 CLI、路径和文件名，原旁白不改，历史失败保留 |
| 第六镜历史失败 | operation `03d700c9-e71d-4dd7-bbff-fa608acc82c1` 保留 failed；隔离 CPU 前端 probe 显示首段 D=181→target 200，snap 约 10.497%，超过原 10% 阈值；新 intent 已在修复版成功 |
| 修复实现 | 源码 `c506bb3c105c81200bc3b86577b65fb96f3361e8` 在任何 NPU 渲染前规划完整连续分段，有限搜索相邻文本边界；保留原文、语速、profile 与 10% 限制，不启用 CPU waveform fallback |
| 修复版隔离 probe | 首段改边界后 D=172→160，完整 5 段均满足现有 NPU profile 条件；仅 CPU 前端／规划检查，没有 NPU 波形生成 |
| 单元测试 | **82 项通过**；不与此前 79 项历史结果相加，也不把 CPU probe 记作 NPU 合成通过 |
| 发布状态 | 源码 `c506bb3c105c81200bc3b86577b65fb96f3361e8`，latest digest `sha256:adb9d87b15b461db56a2f4aca5fd6999221fe4c715ee3751250b3a4b21423634`；Pod `speech-service-758cbd54f9-bfczb` Ready，PID1 五组 capabilities 全 0、NoNewPrivs=1 |
| 工作台上传／播放 | 视频 VPS 上限已改为 34m；第二镜真实 WAV（1,248,044B、26 秒）上传 A2、明确采用、恢复 A1，A2 历史保留；真实 audio clock 驱动第 1→2 镜通过 |
| 完整 MP4 | render `5641dc62-01d7-4540-8e79-501ec801cced`，206 秒、H.264／AAC、1280×720@24fps、4944 帧完整解码通过；SHA-256 `75ab83eba053d20b0d8beee8687709ee5aadd10eabef8549dfc4b55122358c31` |
| 独立音画／字幕检查 | 8 镜音频首尾匹配，全片相关系数 0.9999445、NRMSE 0.010601；8 参考 PNG 画面与顺序通过，第 03／06 镜中心帧目视中文正常；44 条字幕时间／文本与 timeline 一致，仍为 estimated |
| 工作台回归 | render 冻结 revision 67、编辑恢复 revision 69 局部失效通过；ZIP 19 文件含 8 source、其他 owner 404、损坏 WAV 422 且项目不变通过 |
| 工作台重启持久化 | rollout restart 后新 Pod `video-workbench-6454f4845f-bj52n` Ready、工作台镜像仍为 `sha256:ccd2509379ad55029760cf5229d09dd33b0577213172a20e791d9818ad06c6fe`、异常重启 0；8 录音逐一 SHA 匹配、A2 历史保留、MP4 SHA 匹配、SQLite integrity ok、原 DSH revision 27 保留 |
| 重启后运行状态 | 工作台 PID1 五组 capabilities 全 0／NNP=1；PVC 当时可用 988,618,752B；speech Pod `speech-service-758cbd54f9-bfczb` 仍 Running、异常重启 0 |
| 归档／人工边界 | 最终证据已下载校验并安全解包；完整稿自然度、术语听感和字幕人工校对尚未获认可 |

修复未通过删词、补词、改速、放宽 snap 限制或静默 CPU 生成器回退取得成功。第三镜原 operation `0f99c230-d5b4-414c-8c4e-8175e464ea67` 与第六镜原 failed 均保留；后续显式读音修正、发布和新 intent 成功分别记录，不反写历史失败。

重启通过回执为 master `/root/video-audio-release-20261031/postflight.json`。最终证据归档 19,122,821B，SHA-256 `64cbe74652f62513504df98d4fa2ea483d5400fdfecd69fe02d2409b7269bec0`，已下载校验并安全解包至 `D:\github\armbianbegin\.runtime\video-audio-production\evidence-final\`；成片为其中 `live-audio/dsh-narrated.mp4`。

OpenSpec 变更 `add-video-workbench-audio-production` 已同步至 revision `49692535c5004b27a6fc4132900185422bb75f3d`，验证 `valid=true`、无 issues。19 项完成 14 项，剩余 1.1 整稿听感、4.2 术语人工试听和 5.1–5.3 BGM；未执行 apply／archive。

## 此前 K8s 内部服务验证

namespace为`speech-service`，固定节点`orangepi5-max-server1`；内部 base URL为`http://speech-service.speech-service.svc.cluster.local/v1`，模型别名`kokoro-rk3588`，云健音色`zm_yunjian`。部署步骤、引导权限及镜像核验见 [DEPLOYMENT.md](DEPLOYMENT.md)。本次发布身份：

- 应用源码：`615c92bad88c21ad4b0cde30f8adab343dfa330f`。
- 应用镜像：`arm-cluster-master:5000/speech-service:latest`，digest `sha256:c34944342aea009482b71443fb26cb9736b99f8a101166a76eb0fe7e746e102e`。
- 设备插件：固定`squat/generic-device-plugin@7626d567413ce3831e5ec99471dcdd3a9250cf81`源码构建ARM64静态程序，scratch镜像`arm-cluster-master:5000/rknpu-device-plugin:latest`，digest `sha256:72210a0df7998b715088bdadde7f325a7d81d01e3450b1f0aa3b4bb20473ae96`。

使用原版视频SpeechClient，对原201字符技术文稿只生成一次，未自动重试：

| 项目 | 本次实际结果 |
| --- | --- |
| 合成请求耗时 / 音频时长 | 34.9121797059197秒 / 42秒 |
| 媒体 | PCM16、24000Hz、mono、2,016,044B |
| WAV SHA256 | `be70d486fc685436d6bc27f7671ffe3712ceffc11f461884ba23872899987997` |
| 鉴权与配置错误 | 无鉴权401，错误模型422 |
| 网络策略 | 未标记客户端4秒网络超时；加`speech-client=true`后健康200 |
| 资源配置 | 请求1CPU/3GiB，限制2CPU/4GiB |
| cgroup内存峰值 | 3,103,371,264B，约2.89GiB |
| OOM | `oom=0`、`oom_kill=0` |
| 宿主本次MemAvailable | 4,086,452kB，约3.90GiB |

这些耗时和内存是本次单次请求及对应cgroup观测，不代表长期稳定性或所有文稿的上界。该HTTP运行没有额外逐调用插桩，不能把早期短样的NPU调用次数用于这次长文。媒体SHA与先前云健全文相同；这不代替用户对自然度、术语及日期数字读音的试听确认。

真实应用PID 1的`CapInh/CapPrm/CapEff/CapBnd/CapAmb`均0、`NoNewPrivs=1`，固件视图只读。Pod为root且未启用`privileged`；**引导阶段临时具备SYS_ADMIN和SETPCAP**，通过隔离Python仅在容器私有挂载命名空间提供SDK要求的兼容信息，随后清除所有能力再执行应用。该例外需要如实保留，不能称作整个启动过程零能力。模型只读，服务无出站；宿主库和驱动未改。

本轮编译、实际容器预加载及K8s真实客户端实联已通过。随后执行`rollout restart`替换为`speech-service-6cd6865bd6-4sp9z`，新Pod自动预加载并恢复Ready、容器异常重启计数为0；digest及实际PID1五组能力全0/NoNewPrivs1再次通过。客户端经集群DNS健康200，恢复验证没有进行第二次合成。临时验证Pod与ConfigMap均已删除。

证据已取回本地`speech-service/evidence/20261031-k8s/`；发布与恢复详情见部署文档，原始媒体和日志保持Git忽略。

## 历史：首次实验执行

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

Kokoro源包共500,370,817B、161文件（160资产+manifest），manifest SHA256为 `83733c717e0ce5b76ac1295e4827cf3ad2e111955259e9d670897e100fabeb6e`。首次实验收尾时79个资产完成，余81个共87,460,503B；下载遭429后已停止。该阶段所有完成文件经过下载器的SHA256校验，尚未执行Kokoro推理。

## 工件与边界

- 官方运行库 SHA256：`d31fc19c85b85f6091b2bd0f6af9d962d5264a4e410bfb536402ec92bac738e8`，7,726,232B；来源固定 `rknn-toolkit2@42aa1d426c0a9e0869b6374edba009f7208a1926`。
- 源码归档 SHA256：`52aee0cb7f1bf25a04ad01ee906f27b7b665df22b2d266cfea97a7e43460718c`。
- 英语前端小模型：`en_core_web_sm-3.8.0-py3-none-any.whl`，12,806,118B，SHA256 `1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85`。
- worker原始证据：`/root/armbianbegin/speech-service/evidence/`；阶段归档 `stage-20261031.tar.gz`。
- 本地也已取回该归档及解包文件，位于此目录下被Git忽略的 `evidence/`。归档1,038,289B，SHA256 `1f5a67cdb984a46758e579ddd0500c4d1c1329b3f6f336b7128c3739e66c9aa4`。
- 包括CPU两条WAV、CPU/NPU控制器、逐请求JSON、负载采样、后端日志、实际依赖锁、源码/运行库receipt及worker检查点。

首次实验收尾时查询没有运行中的 `speech-lab-*` unit，该阶段尚未创建常驻语音HTTP服务或自动恢复任务；不在无人值守时继续生成。系统驱动、系统Python、系统动态库、线上视频服务、DNS及Casdoor均未改。

## 离线检查

23项通过：15项媒体与执行证据判据，8项源码/模型完整性及显式恢复。覆盖真实PCM帧数、截断/静音、CPU与NPU区分、预加载不冒充合成、意外回退、缺失/损坏文件、legacy receipt迁移、429部分文件恢复。修复后的完整性脚本尚未在worker重新运行，后续使用前先统一更新脚本再核验。

## 2026-10-31 继续验证

已将完整性修复同步到worker，重新校验固定源码、官方运行库和Matcha解包闭包，升级为逐文件receipt；installed Matcha/Kokoro源码与固定vendor逐字节相同。

Lite2二进制确认只查询`/usr/lib/librknnrt.so`。新脚本通过`unshare --mount --propagation private`与临时overlay提供该路径；库仍来自私有`lib/`。探针与真实合成前后均确认宿主库路径仍不存在，没有写入宿主库、升级驱动或改系统Python。

| 候选/原始文稿 | 预加载 | 合成/音频时长 | RTF | 峰值自身RSS | 实际NPU调用 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Matcha CPU声学+NPU Vocos r2 | 2.620秒 | 13.455/44.24秒 | 0.3041 | 344,236,032B | 段落19次成功；另有短句1次、预加载1次 |
| Kokoro r1原前端 | 4.870秒 | 短句7.855/4秒；原段落拒绝 | 短句1.9637 | 2,413,740,032B | 短句70次成功；段落未生成 |
| Kokoro r2显式英文策略 | 4.816秒 | 34.349/52秒 | 0.6606 | 3,061,694,464B（约2.85GiB） | 段落788次成功；另有短句70次 |

统一2核CPU配额；比较候选使用3GiB内存上限和300秒墙钟上限，每个候选新进程，未自动重试。所有RTF包含本次实际文字前端、声学/生成、声码器及WAV输出，不能当作纯NPU耗时或同算法加速比。Kokoro使用CPU前端及混合算术，`engine=npu`不代表整个模型都在NPU。

Kokoro剩余81个文件通过单线程/每请求2秒间隔下载完毕，全部160个资产的SHA256通过。r1失败经Misaki0.9.4源码定位：`ZHG2P(version=None)`走legacy路径，绕过en_callable，把部分大写字母直接留下；官方`_ids`拒绝未知音素。新增独立`pronunciation.py`，保留整句中文数字规范化，英文词单独转音素，多字母大写缩写按字母读。未改vendor或过滤未知音素，r1失败证据保留。

r2原段落SHA256仍为`7ef052b21689a04e0c6b25ec3d56c2146bcc3aa86f8e460b93ceb4d1978eb69b`；8个分段覆盖0..201字符，六个术语及日期/数字未被删掉。生成WAV为PCM16/24kHz/mono、52秒，SHA256 `1039f981217c883ee880001470a3305f855e1046666a97a389b926944b1cb1b2`。所有分段声明NPU且无CPU生成器回退；成功调用同时被Python RKNN和原生C API观测。**这证明执行与覆盖，不能代替实际听感**。用户已试听并反馈声音机械、不自然，明确希望男声；小贝女声未获采用。

Matcha独立无模型审计：源码/词典/tokens校验通过、espeak C API可用、无未知覆盖，审计token序列与真实前端一致。但`8`、日期和`1.0`逐位走英文；ACP读作`ˈækp`、PTY读作`tˈaɪ`。覆盖成功不代表术语读音正确，当前配置仍不能直接作为技术解说默认。

### HTTP原型与客户端实联

新增ASGI API与固定Kokoro试验适配。管理员配置model/voice和TOKEN_FILE；输入/音频有界，PCM16容器完整、无全零假成功。原生任务保持单并发，客户端超时/断连不会提前释放，cleanup在同一executor排队到推理结束后。CPU生成器profile在父类渲染前即拒绝，另有mock计数验证父实现0次调用。

在worker回环18092端口短暂启动，使用视频应用原版SpeechClient（源码SHA256`4ce02745006f5109d5975716b451718dc07a7465c18c496791152e66cb499ccd`）实际POST。成功取得192,044B/24kHz/mono/4秒完整WAV，6.802秒返回；无凭据401，错误model被拒绝且不合成。临时unit停止、TOKEN_FILE删除、宿主库仍不存在。该实联使用小贝女声配置，仅证明接口兼容，不作为用户音色采用；男声配置需要单独实测。

Windows与ARM均通过67项（52项完整性/前端/API/适配，15项测量）；含真实socket客户端超时后仍429、原生结束才下一请求200、静音拒绝、ASGI取消和shutdown次序。Windows Uvicorn0.49.0，ARM已安装Uvicorn0.54.0，运行要求固定0.54.0；仅在隔离venv新增httpx0.28.1/httpcore1.0.9用于真实客户端验证。

本轮原始证据已取回`evidence/resume-20261031/`；归档`resume-20261031.tar.gz`大小3,305,777B，SHA256`6c4f3b7580e656b6d1506282bde5fe66956a7aa287829933746b0351988c1b0d`，解包5,074,956B。它记录上述女声及Matcha阶段，不包含之后的男声试验。线上视频配音/字幕/MP4仍未接通。

## 用户要求中文男声后的验证

用户反馈小贝机械、不自然，明确要求男声。官方`hexgrad/Kokoro-82M@f3ff3571791e39611d31c381e3a41a3af07b4987`列出4个中文男声。本轮固定下载两个约0.5MiB候选：

| 音色 | 官方.pt SHA256 | 导出522,240B音色表SHA256 |
| --- | --- | --- |
| 云希zm_yunxi | dbe6e1ce7c3dbaf2f5667432947b638b1c6831ccbe154c4610dbcc44f431e27b | 7243892fb4e560d47014090ddf010f8b8b790f3c6b029ff82b2ac06aa4e27c8b |
| 云健zm_yunjian | 76cbf8bad35901d011d9628a2fdceb7b4f1f127e7a3269cb393b3941eb7fc417 | de48a00bdbf3649f07162269a2b6e0513604389bfac8a2e6c75cb34b323ad6fa |

真实ZIP中的165B tensor descriptor完全相同，固定SHA256`645dea33b46e50fdda6c8a43b39ec4b7adcf28e4643408c02d74fef10ff9d712`，已用pickletools仅查看指令，确认float32/CPU/offset0/shape(510,1,256)/stride(256,256,1)。正式转换只校验该descriptor hash、固定5成员及little-endian有限float，不执行pickle、不导入Torch。启动时由固定.pt重解，再比较.bin与receipt，测试覆盖同时篡改bin+receipt。

男声资产位于`models/voices`，原bundle的161文件闭包与所有hash再次通过。适配层保留原manifest验证，以实例级style选择在自然时长/stem推理前注入男声；请求验证及metadata同步实际voice，不重命名小贝文件、不改全局VOICES、不关闭完整性检查。CPU生成器profile仍在渲染前拒绝。

同一45字左右中文短样句、速度1.0、每款新进程串行、2核CPU/4GiB内存/150秒候选上限：

| 音色 | 合成/音频时长 | 成功NPU调用 | 实际metadata |
| --- | ---: | ---: | --- |
| 云希 | 9.229/8秒 | 108 | 单段zm_yunxi，无回退 |
| 云健 | 11.401/11秒 | 159 | 两段zm_yunjian，无回退 |

用户试听两条同稿后，明确选云健`zm_yunjian`继续调整。云希真实API短稿也通过（9.308/8秒）。随后以云健配置，原版视频SpeechClient经worker回环API对原201字符技术文稿只生成一次：31.434秒返回42秒、24kHz/mono/PCM16、2,016,044B WAV，SHA256`be70d486fc685436d6bc27f7671ffe3712ceffc11f461884ba23872899987997`。输入摘要`c479980ee04ccfa4bbec60d12ec8c3ed0fbb7ec1b4618726c27ac15bfabd153b`；API适配层核验全部分段来源与实际voice，拒绝CPU生成器回退。该HTTP运行未另外插入逐调用观测，因此不把短样的NPU调用数当作这次长文的调用数。

该阶段云健API另验证无凭据401、错误model拒绝，临时unit与凭据均清理。API执行成功与用户选择音色，不等于完整技术文稿听感已经获采用。男声实验阶段尚未常驻部署或接入线上视频路由；后续K8s部署结果见本文顶部。

最终Windows及ARM均78项通过（63项完整性/前端/API/音色，15项测量），编译和空白检查通过。收尾确认无运行中的speech-lab unit、无临时token、宿主库路径不存在。男声阶段归档2,262,947B，SHA256`de5acb58b94e491796d20991297f3e6cd27aa2f0df3f9a3935c5b72caad108d5`，已取回`evidence/male-stage-20261031/`，解包3,435,648B；包括两条男声样音、云希/云健API WAV、report、官方metadata、音色receipts和测试日志，不含模型权重。

最终独立审查补充：若原模型ready后男声资产加载失败，直接调用适配器也必须禁止合成。新增初始化成功gate和失败清理，覆盖“错误男声文件不能退回默认女声”的测试。追加后Windows/ARM均为79项通过（64+15），并在ARM重新验证云健正常预加载与style表形状，无额外音频生成。新增日志在worker及本地 `evidence/final-review-tests.log`、`final-review-preload.log`；额外日志归档`final-review-20261031.tar.gz`为1,112B，SHA256`beb71c5a8a7e74b1363800acb576eff7510f89641e2450fdd5bef326a9f478b7`。上述男声阶段归档保留修复前78项的阶段快照。
