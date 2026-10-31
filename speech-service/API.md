# 内部语音 API 原型

用户选定继续调整的中文男声为云健`zm_yunjian`；云希保留对比，小贝女声未获采用。视频业务的配音候选、字幕和MP4尚未接通。

## 管理员固定配置

| 环境变量 | 值 |
| --- | --- |
| `SPEECH_BACKEND` | `kokoro_convonly` |
| `SPEECH_MODEL` | 管理员固定的模型别名，例如`kokoro-rk3588` |
| `SPEECH_VOICE` | `zm_yunjian` |
| `KOKORO_CONVONLY_ROOT` | 已校验的原RK3588 bundle绝对路径 |
| `SPEECH_VOICE_ROOT` | 独立`models/voices`绝对路径 |
| `TOKEN_FILE` | 仅管理员可读的凭据文件绝对路径 |

先单独准备固定版本源码、完整bundle、依赖与官方私有运行库。男声音色使用官方Kokoro v1.0固定revision，不改变原bundle：

```bash
.venv/bin/python scripts/download_male_voices.py \
  --destination "$PWD/models/voices" --endpoint https://hf-mirror.com
```

仅下载约1MiB音色；转换不安装/导入Torch，不执行pickle，只接受已审查的descriptor及little-endian float32 `(510,1,256)`。启动时从固定`.pt`重解，核对`.bin`与receipt，避免同时改bin和receipt绕过校验。

Linux实验启动方式（从本目录运行，预先注入上表环境变量）：

```bash
.venv/bin/python scripts/with_private_runtime.py --root "$PWD" -- \
  .venv/bin/python -m speech_service --host 127.0.0.1 --port 8092
```

私有库脚本需要Linux/root，只改变子进程mount namespace。实验由有限时长的systemd unit管理整个进程组；未来容器可把库放在容器内，无需改宿主库。单进程、单HTTP worker、单原生合成；不能用多个Uvicorn worker扩大并发。男声实验限制2核CPU/4GiB内存；先前女声长文峰值约2.85GiB，常驻部署需保留余量。

## 协议与限制

`POST /v1/audio/speech`需要Bearer鉴权及JSON：

```json
{"model":"kokoro-rk3588","input":"欢迎来到视频工作台。","voice":"zm_yunjian","speed":1.0,"response_format":"wav"}
```

模型与音色必须匹配管理员配置。输入限64KiB JSON、2000字符/16KiB文本、速度0.5–2.0；输出为完整、非全零PCM16 WAV，限32MiB/300秒，带准确Content-Length，不压缩、不重定向。视频原版SpeechClient的base URL填`http://<internal-service>:8092/v1`。

`GET /health/live`不调用模型；`GET /health/ready`在预加载完成后通过，均不暴露路径、文稿或凭据。错误为固定代码：401鉴权、413/422输入、429忙、502无效音频、503后端失败、504等待超时。body等待10秒、合成等待120秒；没有自动重试或换模型。

超时、取消或断连只结束HTTP等待，槽位必须等原生任务结束后才释放；cleanup在同一执行线程排到推理之后。中文数字规则保留，英文词独立转音素，大写缩写按字母读，不删未知词冒充成功。男声style在时长预测前选择，metadata返回实际voice ID；不改vendor、全局VOICES或原manifest。

CPU生成器profile在渲染前拒绝；一些短文本可能落在不支持的NPU时长范围，需后续改进。常驻部署、云健完整技术文稿试听及线上业务接入仍按验证结果推进。
