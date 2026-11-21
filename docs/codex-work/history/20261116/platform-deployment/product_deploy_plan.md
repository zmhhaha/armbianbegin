> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`archives/video-service/20261116/c-rendered/feedback-20261106/animation-lab/agent-creation-phase1/creation-product-r1/product_deploy_plan.md`；正文 SHA-256：`88871f8b2f9b1e9450f85c7496e3c146dae42667abed611d330c0e99955c22e6`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# 私有制作执行器与原 Lab 接线方案（待根任务实施）

本文件和 `product_deploy_server.py` 仅准备与离线核对，没有据此访问服务器、构建、部署或提交模型。实际执行由根任务分阶段完成，以下数字是验收上限，不能记作已完成结果。

## 固定身份与最小资源

产品源码固定为 `3c187fc0843a3adcaa74804e416c429e8f5bb357`。Lab 与 executor 镜像分别读取服务器阶段根的 `product-lab-image.json` 和 `product-executor-image.json`，要求 `video.animation-product-image-build.v1`、对应 component、相同 revision 与源归档摘要、ARM64，以及没有部署/模型任务的构建回执；不把 mutable `latest` 当成发布身份。

渲染镜像固定为 `arm-cluster-master:5000/video-motion-renderer:latest@sha256:744b62419edefee38c243bce8fbb581797487990b0dc02909f7a7a6eb89433da`。必须在 master 的 **Docker daemon** 中实际 `image inspect` 可见；kubelet/containerd 已拉取不能代替这个条件，子容器使用 `--pull=never`。

| 范围 | 新建或修改 | 保留边界 |
|---|---|---|
| `video-animation-creation` namespace | 新建 1 Namespace、1 Deployment、1 ClusterIP Service、1 NetworkPolicy、2 ExternalSecret/Secret | 不创建 Ingress、SA/RBAC、集群权限或 PVC |
| 原 `video-workbench/video-animation-lab` | 原 Deployment 仅替换固定摘要镜像、追加 `--creation-url/--creation-token-file`、追加单键只读 Secret 挂载；在 deployment metadata 与 Pod template 同步更新标准 revision/digest/ref.name 和 release annotation | 旧完整参数、其余 annotation/labels、开发者 allowlist、proxy 模式、Service、selector、卷/PVC/数据目录全部保留 |
| 原 Lab NetworkPolicy | 仅把原空 egress 改为集群 DNS 及所选 executor Pod 的 TCP8767 | 原 ingress、Pod selector 及其余 spec 保留 |
| 原 Lab namespace | 新增 Lab caller 的 1 ExternalSecret/Secret | 不挂 Agent 凭据、Docker socket、共享运行根 |
| 共享 Agent | 使用已完成的两条 v2 路由与独立 caller；检查先前新增的 ingress | 本操作器不再修改 Agent 路由、UID、DB、公共配置或 deployment |
| 普通 `video-workbench` | 只记录并核对 UID/完整 spec | 不重新部署、不切换整片业务工作流 |

执行器固定 `arm-cluster-master` / ARM64，root controller 只恢复 `CHOWN/FOWNER`，持有 Docker socket，明确属于可信控制器。数据目录 **host 与容器均为 `/var/lib/video-animation-creation`**；仅挂这个专用目录和 `/var/run/docker.sock`。initContainer 仅有 FOWNER，将数据根设为0700，不挂 socket 或凭据。生成场景仍在 uid10001、`--network=none`、只读根、drop ALL、无凭据/socket 的既有子容器中执行。

prepare 和 apply 都要求这个新数据根不存在或为空，且现有父目录为 root 所有且不可由组/其他人写入；不清空已有目录。如果发现旧 pending 账本，停下核对，避免新进程的恢复 pump 自动接续旧任务、误消耗本轮预算。

## 两个不同 token、三条投影

权威 Vault KV 为 `secret/agent-service/runtime`；ESO 使用已存在的 `ClusterSecretStore/vault-backend`，remoteRef 路径 `secret/data/agent-service/runtime`。不输出 token，不放进命令参数、浏览器、Git 或部署资源 JSON。

| 权威 property | 接收 namespace/Secret | 单键与进程挂载 | 权限 |
|---|---|---|---|
| **已有** `ANIMATION_CREATION_SEQUENCE_TOKEN` | `video-animation-creation/animation-creation-agent` | `token` → `/run/secrets/animation-creation-agent/token`，0400 | 共享 Agent caller `video-animation-creation-sequence`，仅 `video.animation-create.v2`、`video.animation-review.v2` |
| **新建一次** `ANIMATION_CREATION_LAB_TOKEN` | `video-animation-creation/animation-creation-lab` | `token` → `/run/secrets/animation-creation-lab/token`，0400 | 私有 executor bearer；不可用于 Agent |
| 同一个 `ANIMATION_CREATION_LAB_TOKEN` | `video-workbench/animation-creation-lab` | `token` → `/run/secrets/animation-creation/token`，0440 | Lab → executor；与上一行是同一条链的两端 |

`credentials --execute` 以完整旧 KV 的版本做一次 CAS，仅追加 Lab property，保留所有原字段；Agent token 从已启用的权威 property 读取，不能新生成或换用旧 Lab/业务 caller。三个 Secret 各只投影 `token`，不复制整个 Agent `secrets.json`。新 ExternalSecret 的 API 默认字段先核对包含计划，再保存实际完整 spec/UID；之后按实际冻结值核对，避免 CRD defaulting 误报。

## 精确网络方向

1. 已有 OAuth2 proxy 的原路径继续把 `https://video-service.panghuer.top/dev/animations/` 转到原 Lab:8766；原 Casdoor、域名、代理配置不变。
2. Lab 使用 `http://video-animation-creation.video-animation-creation.svc.cluster.local:8767`。Lab egress 和 executor ingress 同时限定 namespace 与 Pod selector `app.kubernetes.io/name=video-animation-creation` / 原 Lab selector；不是 namespace 与 Pod 两个 OR peer。
3. executor 使用 `http://agent-service.agent-service.svc.cluster.local:8080`。egress 使用实际 `agent-service-api.spec.selector.matchLabels`；至少应包含 `app.kubernetes.io/name=agent-execution-service,component=api`。
4. 共享 Agent 已加的 `agent-service/video-animation-creation-to-agent-api` ingress 必须选择这个**实际 API deployment selector**，仅允许新 executor namespace+Pod selector TCP8080。本操作器只核对它，不自行覆盖共享 Agent policy。
5. executor 只额外允许 `kube-system/k8s-app=kube-dns` TCP/UDP53；不开放外网、API server、数据库、TTS 或 LLM 直连。

## 原 Lab 历史保留与备份

原两 PVC 的实际名字从 deployment 读取，记录 UID/完整 spec 与 Bound 状态；不按默认名字重建，不改 storageClass/capacity，不删除/移动/替换 PVC。原 `/data/animation-lab.db`、`/data/animation-experiments.db` 和 `/evaluations` 在原挂载位置继续使用。

prepare 在原 Pod 中以 SQLite `mode=ro` 读取，在内存中做 SQLite backup，然后将压缩后的数据库副本存入服务器本次0700目录下0600文件；不向原 Pod 写备份、不直接复制可能未合并 WAL 的 `.db`。SQLite 的内存序列化副本可能保留WAL头，因此仅在**备份副本**中将第18/19字节规范化为独立数据库的1/1，同时记录原序列化摘要/原头；不改原数据库。服务器以内存反序列化及 `integrity_check` 验证备份可独立还原，真实本地WAL夹具已核对BLOB/浮点值恢复。逐表保存 schema/列与每条 typed row 的摘要计数，另对历史普通媒体文件存字节数/SHA256；WAL/SHM/journal 辅助文件不当作业务媒体。apply 前再次要求与基线完全一致；若用户这期间添加标注，停下重新准备，不能覆盖新数据。新版本启动后要求所有原行多重集、原 schema/列及历史媒体保持，可另增新版本正常注册的记录。

新制作记录从一开始就放在专用根：`creation-service.sqlite3`、`creation-polish.sqlite3`、`creation-runs/`、`renders/`；不混进旧 Lab SQLite，也不搬入普通工作台 DB 或原候选导入账本。保留失败现场和 once 标记，不自动回滚、重试付费操作或清理 UID/隔离记录。

## 分步执行示例

服务器固定阶段根：

```bash
cd /root/video-process-20261105/feedback-20261106/animation-capability-redesign/agent-creation-phase1/creation-product-r1
python3 -B product_deploy_server.py prepare
python3 -B product_deploy_server.py credentials --execute
python3 -B product_deploy_server.py apply --execute
python3 -B product_deploy_server.py verify
```

这些是供根任务审查的调用示例；本文件没有执行。prepare 必须在产品两镜像回执和共享 Agent v2 实际能力/ingress 就绪之后执行。单独 `credentials` / `apply` 不带 `--execute` 只返回未请求执行；每个执行阶段先创建独占 once 文件，失败后没有自动重跑。prepare 的 `plan-files.json` 和操作器/源码哈希会冻结输入，之后改操作器应使用新的 plan 目录。

操作器依赖原控制源码校验与修复后的 `activation_server_v2.py`；冻结并复核这个文件与 `build_product_server.py` 的字节摘要，不覆盖/隐式继续原失败的 activation 文件或 plan。使用前由根任务核对 v2 已完成修复并上传。

verify 只做就绪、实际镜像、投影、历史数据/媒体保留、Lab→executor 的真实鉴权 GET 和入口接线检查；它不会点击按钮或 POST 制作，不能据此宣布完整付费链完成。

## 本轮真实端到端验收预算与调用

旧 p1/r2 候选预算已耗尽且收尾，不能借用。根任务如决定开启**本次独立正式 HTTP 产品验收**，建议只开启 **1 个新 run**：初作最多1个 Agent job、独立 v2 审阅最多1个 job；只在有适用问题时创作者修订最多1个 job；原作/修订隔离渲染各最多1次，共最多2次。参考观察0次、TTS0次、第二次审阅0次、重试新任务0次。失败即保留原 run 查账，不换 UUID 重做；需要故障恢复时 GET 只读取/核对同一请求。

每个 Agent job 的 Pi 工具往返可产生多次模型 HTTP 请求，不能把3个 job写成3次模型请求。现用公开拓扑显示代理 `max_calls_per_attempt=128`，若实际共享配置仍为此值，理论上界最多384次请求；产品操作器不修改共享上限。应在运行前核对实际上限与任务 timeout，实际数从 `agent_model_requests` 及图片输入传输表核对。本产品 run 总 deadline3600秒，单次既有渲染timeout180秒；这不是成本报价或实际耗时保证。

开发者浏览器以原登录身份打开 `/dev/animations/`，在已有能力目标的 development 输入上只点一次“制作并打磨一轮”。选一个已准入 HTML/SVG、8秒、24fps目标；不同时试遍样例，也不宣称 Canvas/Three.js 自由源码已经准入。按钮会先持久保存 UUID，再发唯一POST；记录实际 request/run/job/operation identities。

底层同源接口的准确 body 是：

```json
{
  "request_id": "<一次生成并持久保存的 UUID>",
  "experiment_id": "<当前已登记能力目标 id>",
  "definition_identity": "<该目标的实际 64 位 identity>",
  "input_role": "development"
}
```

读取 `GET /dev/animations/api/experiments` 取得目标 identity 与 `csrf_token`；提交 `POST /dev/animations/api/creation-runs`，JSON Content-Type，`Origin: https://video-service.panghuer.top`，`X-Animation-Lab-Token: <csrf_token>`，使用现有登录 cookie。身份由原 proxy 的 `X-Forwarded-User` 提供，不能从浏览器 body 自报 owner。轮询只用 `GET /dev/animations/api/creation-runs/<run_id>`，刷新/离页回来仍只GET。取消是显式 `POST .../<run_id>/cancel`，body `{}`，消耗的额度保持。

播放器/下载使用该 run 返回的同源 `versions/original|revised/media`，验证实际播放、Range206及下载字节摘要；`.../source` 只返回JSON，不作为可执行页面打开。逐项核对：初作真实 MP4、实际独立审阅图片传输、可用时一次修订MP4、技术复验、页面刷新恢复、旧标注/旧媒体可读取、已创建子容器停止清理。技术完成、模型发现问题、人类欣赏效果和正式采用分别记结论；没有用户试听或认可就不写为已认可。新闭环不自动发布效果包、不改正式视频制作流程、不合主线。
