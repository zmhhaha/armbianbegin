# 内部语音 API

默认中文男声继续使用云健`zm_yunjian`。支持管理员明确启用的八个中文音色：男声云健、云希、云夏、云扬，女声晓贝、晓妮、晓晓、晓伊。中文名是本服务显示标签，官方ID不变；实际可选项以启动校验成功后的`GET /v1/voices`为准。发布身份和真实合成证据见 [VALIDATION.md](VALIDATION.md)，增加音色不代表用户认可自然度。

当前服务已部署在 K8s namespace `speech-service`、节点 `orangepi5-max-server1`。原版视频 SpeechClient 的 base URL 填 `http://speech-service.speech-service.svc.cluster.local/v1`，model 为 `kokoro-rk3588`，voice 为 `zm_yunjian`。客户端 Pod 需带 `speech-client=true` 标签，并以受管理方式挂载 Bearer 凭据；服务无出站网络。发布身份、设备插件及操作步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。

一次201字符完整技术文稿实联已通过：34.912秒生成42秒、24kHz/mono/PCM16 WAV；无凭据401、错误模型422。未标记客户端4秒网络超时，标记后健康200。重建Pod后，自动预加载、Ready恢复、镜像身份和实际PID1能力复核均通过，客户端经集群DNS健康200，未额外合成。完整文稿听感仍待用户确认。

## 管理员固定配置

| 环境变量 | 值 |
| --- | --- |
| `SPEECH_BACKEND` | `kokoro_convonly` |
| `SPEECH_MODEL` | 管理员固定的模型别名，例如`kokoro-rk3588` |
| `SPEECH_VOICE` | `zm_yunjian` |
| `SPEECH_VOICES` | 明确启用的ID，例如`zm_yunjian,zm_yunxi,zm_yunxia,zm_yunyang,zf_xiaobei,zf_xiaoni,zf_xiaoxiao,zf_xiaoyi`；省略则仅启用`SPEECH_VOICE` |
| `KOKORO_CONVONLY_ROOT` | 已校验的原RK3588 bundle绝对路径 |
| `SPEECH_VOICE_ROOT` | 独立`models/voices`绝对路径 |
| `TOKEN_FILE` | 仅管理员可读的凭据文件绝对路径 |

先单独准备固定版本源码、完整bundle、依赖与官方私有运行库。八个音色使用官方Kokoro v1.0固定revision，不改变原bundle；下载脚本保留历史文件名：

```bash
.venv/bin/python scripts/download_male_voices.py \
  --destination "$PWD/models/voices" --endpoint https://hf-mirror.com
```

每个原始音色约0.5MiB，八个`.pt`合计约4MiB，另需派生`.bin`和receipt空间；转换不安装/导入Torch，不执行pickle，只接受已审查的descriptor及little-endian float32 `(510,1,256)`。启动时从固定`.pt`重解，核对`.bin`与receipt，避免同时改bin和receipt绕过校验。所有配置声线（包括晓贝）共享这条校验及只读style加载路径。任何明确启用的音色缺失或校验失败，服务初始化失败；不会跳过该音色并声称完整可用。

Linux实验启动方式（从本目录运行，预先注入上表环境变量）：

```bash
.venv/bin/python scripts/with_private_runtime.py --root "$PWD" -- \
  .venv/bin/python -m speech_service --host 127.0.0.1 --port 8092
```

私有库脚本仅用于 Linux/root 实验，改变子进程 mount namespace，实验由有限时长的 systemd unit 管理。K8s 镜像已经把固定运行库放在容器内，模型只读挂载，宿主库保持原状。单进程、单HTTP worker、单原生合成；不能用多个Uvicorn worker扩大并发。当前请求1CPU/3GiB、限制2CPU/4GiB，本次 cgroup 峰值约2.89GiB，未发生 OOM。

K8s Pod 未启用 `privileged`，但 root 引导阶段需要 `SYS_ADMIN` 和 `SETPCAP`，在私有挂载命名空间提供 SDK 所需的兼容信息。隔离 Python 引导完成后清空全部能力和 bounding 集合，再启动应用；真实应用 PID 1 已验证五组能力全0、`NoNewPrivs=1`、固件视图只读。不要用直接运行的调试命令绕过镜像 ENTRYPOINT；具体权限边界见部署文档。

## 协议与限制

`POST /v1/audio/speech`需要Bearer鉴权及JSON：

```json
{"model":"kokoro-rk3588","input":"欢迎来到视频工作台。","voice":"zm_yunjian","speed":1.0,"response_format":"wav"}
```

模型必须匹配管理员固定别名。`voice`必须是当前已启用且校验成功的ID；省略时采用`SPEECH_VOICE`，明确传入未知、未启用或null音色返回422，绝不静默改用默认声线。输入限64KiB JSON、2000字符/16KiB文本、速度0.5–2.0；输出为完整、非全零PCM16 WAV，限32MiB/300秒，带准确Content-Length，不压缩、不重定向。K8s Service 对内使用80端口，Pod监听8092；实验时直接访问Pod或回环服务才使用`:8092/v1`。

`GET /v1/voices`同样需要Bearer鉴权；未Ready返回503，不执行合成。八音色全部启用并校验成功时返回：

```json
{"object":"list","model":"kokoro-rk3588","default_voice":"zm_yunjian","data":[{"id":"zm_yunjian","name":"云健","language":"zh-CN","gender":"male","default":true},{"id":"zm_yunxi","name":"云希","language":"zh-CN","gender":"male","default":false},{"id":"zm_yunxia","name":"云夏","language":"zh-CN","gender":"male","default":false},{"id":"zm_yunyang","name":"云扬","language":"zh-CN","gender":"male","default":false},{"id":"zf_xiaobei","name":"晓贝","language":"zh-CN","gender":"female","default":false},{"id":"zf_xiaoni","name":"晓妮","language":"zh-CN","gender":"female","default":false},{"id":"zf_xiaoxiao","name":"晓晓","language":"zh-CN","gender":"female","default":false},{"id":"zf_xiaoyi","name":"晓伊","language":"zh-CN","gender":"female","default":false}]}
```

目录只描述实际启用资产，不承诺情绪控制或自然度。上层工作台按项目统一选择声线，然后将同一项目声线用于每次配音请求；语音服务本身不存储项目状态。

`GET /health/live`不调用模型；`GET /health/ready`在预加载完成后通过，均不暴露路径、文稿或凭据。错误为固定代码：401鉴权、413/422输入、429忙、502无效音频、503后端失败、504等待超时。body等待10秒、合成等待120秒；没有自动重试或换模型。

超时、取消或断连只结束HTTP等待，槽位必须等原生任务结束后才释放；cleanup在同一执行线程排到推理之后。不同声线也共享这一槽位，不会因切换音色绕过忙状态。中文数字规则保留，英文词独立转音素，大写缩写按字母读，不删未知词冒充成功。所有声线共享同一份模型，只在启动时预载只读style表；适配器锁和线程绑定覆盖声线选择、时长预测、完整推理与metadata校验，成功或失败后均清除当前声线。metadata保留原模型身份并逐segment核对实际voice ID；不改vendor、全局VOICES或原manifest。

CPU生成器profile在渲染前拒绝；一些短文本可能落在不支持的NPU时长范围，需后续改进。K8s 内部部署、真实合成与Pod重建恢复已通过，后续继续验证长期运行、不同长度文稿、完整技术文稿听感及线上业务接入。
