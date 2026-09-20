# 平台现状调查：Kubernetes 部署约定

> 调查时间：2026-09-16，代码基准 HEAD `3dd4128`。
> 范围：`llm-service/`、`embedding-service/`、`rag-service/`、`es/`、`email-service/`、`openspec_service/`、`panghu_agent/content_agents/`、`base/`、`ceph/`、`nfs/`、`static_resource/`、`resource_scheduler/`。
> 用途：回答"在这个集群里新增一个服务，按什么约定写 manifest"。
> 行号基于该次调查，代码演进后会漂移，引用前先核对。

## 结论摘要（TL;DR）

- **裸 YAML + `build.sh`/`deploy.sh`，没有 Helm**（唯一 Helm 痕迹是 `vault/helm-values/`，只用于 Vault 自身）。Kustomize 只在 2 处，且无 overlay。
- **Namespace 混合**：基础设施共用 `data`，应用各自独立（`llm` / `email-service` / `openspec` / `content-agents` …）。跨 namespace 一律 FQDN。
- **周期性任务用 K8s CronJob，应用内不做调度** —— 重点服务里 `apscheduler`/`node-cron`/`schedule` 全部零命中。这是仓库的硬约定。
- **NetworkPolicy 只有 3 个**，全部集中在 llm / embedding / rag，且是 **label-based 放行**（调用方 Pod 必须自己打 `llm-client: "true"` 之类的标签）。这个坑在仓库里被记录了约 15 次。
- **安全加固只有 3 个服务做全**（llm / embedding / openspec）。rag、postgres、redis、email 都**没有 securityContext**，以镜像默认用户（多为 root）运行。
- **镜像全部自建、单平台 `--platform linux/arm64`**，推私有 registry `arm-cluster-master:5000`。全仓无 amd64 构建目标、无 buildx manifest list。
- **集群很小**：5–6 节点、合计约 34 核 / 44 GiB，其中 3 台 NanoPC 各只有约 4 GiB 且"内存极紧"。

## 一、Manifest 组织与部署工具链

**按服务分目录，目录内是裸 YAML + 脚本。** 两种子布局并存：

- 单文件 `k8s.yaml`：`llm-service/k8s.yaml`、`embedding-service/k8s.yaml`、`rag-service/k8s.yaml`、`postgres/k8s.yaml`、`redis/k8s.yaml`、`email-service/k8s-deployment.yaml`、`sqlite/k8s.yaml`、`portal/k8s.yaml`
- `k8s/` 子目录拆多文件：`es/k8s/{configmap,service,statefulset}.yaml`、`openspec_service/k8s/core.yaml`

**Kustomize 只有 2 处**，且都没有 overlay：

- `openspec_service/k8s/kustomization.yaml`（只有 `resources: [core.yaml]`），由 `openspec_service/scripts/deploy.sh:158,165` 以 `kubectl apply -k` 调用
- `cloudflare-tunnel/manual/kustomization.yaml`

**部署方式：每服务一对 `build.sh` + `deploy.sh`。** 典型流程（`embedding-service/deploy.sh`、`rag-service/deploy.sh`、`es/deploy.sh`）：

1. `kubectl apply` ExternalSecret → 等 secret Ready
2. `kubectl apply -f k8s.yaml`
3. `kubectl set image`
4. `kubectl rollout restart` + `rollout status`

`KUBECONFIG` 默认 `/etc/kubernetes/super-admin.conf`（`llm-service/deploy.sh:5`）。**镜像 tag 用 `latest`，所以必须显式 `rollout restart`**（`llm-service/deploy.sh:32-33`）。部分脚本用 `sed` 在 apply 前替换 registry/tag（`llm-service/deploy.sh:30`、`panghu_agent/content_agents/deploy.sh`）。

**仓库没有集中 CI 部署。** `.drone.yml` 只为 openspec-service 构建并 push 镜像（tags = commit SHA + latest）；注释说明"未接线 Drone 时在 master 上原生 arm64 构建"。

## 二、Namespace 约定

**混合模式：基础设施共用 `data`，应用独立。**

共用 `data`：embedding、rag、es、postgres、redis、sqlite（`embedding-service/k8s.yaml:5`、`rag-service/k8s.yaml:5`、`es/k8s/statefulset.yaml:5`、`postgres/k8s.yaml:11`、`redis/k8s.yaml:11`）。

独立 namespace：llm-service → `llm`（`llm-service/k8s.yaml:4`）、email → `email-service`（`email-service/k8s-deployment.yaml:10`）、openspec → `openspec`（`openspec_service/k8s/core.yaml:4`）、content_agents → `content-agents`、静态资源 PVC → `main-portal`（`static_resource/k8s/static-pvc.yaml:11`）。

跨 namespace 一律用 FQDN：

- `llm-service.llm.svc.cluster.local`（`rag-service/k8s.yaml:83`）
- `elasticsearch.data.svc.cluster.local:9200`（`rag-service/k8s.yaml:43`）
- `postgres.data.svc.cluster.local:5432`（`openspec_service/scripts/deploy.sh:142`）
- `embedding-service.data.svc.cluster.local:8080`（`embedding-service/README.md:28`）

## 三、NetworkPolicy —— 只有 3 个，且是 label-based

全仓库唯一的 3 个 `kind: NetworkPolicy`：

| 文件:行 | namespace | 方向 | 规则 |
|---|---|---|---|
| `llm-service/k8s.yaml:139-161` | `llm` | Ingress + Egress | 入站只放行 `podSelector: {llm-client: "true"}`；出站只放行 DNS(53) + HTTPS(443) |
| `embedding-service/k8s.yaml:54-68` | `data` | Ingress + Egress | 入站只放行 `embedding-client: "true"`；出站 `egress: []`（全禁） |
| `rag-service/k8s.yaml:93-107` | `data` | 仅 Ingress | 入站只放行 `rag-client: "true"`；出站不限制（注释明说不限制） |

**写法特征**：`from: [{namespaceSelector: {}, podSelector: {matchLabels: {...}}}]` —— `namespaceSelector` 为空 `{}` 即"匹配所有 namespace"，靠 **label** 而不是 namespace 做准入。

> ⚠️ **这是本仓库最高频的坑**：调用方 Pod 必须**显式打上** `llm-client: "true"` / `rag-client: "true"` / `embedding-client: "true"` 标签，否则连不上。而且**表现为超时（connection timeout），不是 401** —— 很容易误判成服务挂了。仓库里约 15 处记录了这个坑：`llm-service/INTEGRATION.md:159`、`llm-service/README.md:229`、`rag-service/k8s.yaml:24`、`panghu_game/GuanLiao/deploy/README.md:63`、`panghu_agent/k8s/api-deployment.yaml:21-23` 等。
>
> 🔴 **2026-09-20 更正：以上整段在本集群上没有依据。** 实测确认集群 CNI 是 `kube-flannel`（无 Calico/Cilium/kube-router），**flannel 不实现 NetworkPolicy**，因此这 3 个策略**从未生效**。从 `dsh-runner` 容器直连 `rag-service` / `embedding-service` / `llm-service` 全部 **CONNECTED**。
>
> 打标签仍是**正确的写法**（策略生效后它就是准入条件），但**不要再用"表现为超时"去诊断连通性问题**——现在的超时一定是别的原因。那"约 15 处记录"经查大多是注释与 README 相互引用，**不是本集群的实测经验**。证据见 [../panghu_chat/docs/infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) 第 8.0 节。

`llm-guard-report-agent` 的 CronJob 演示了正确写法（`panghu_agent/content_agents/k8s/cronjobs.yaml:271-273`）。

**其余所有服务都没有 NetworkPolicy** —— postgres、redis、es、email、openspec、portal、各 agent/game。`panghu_chat/docs/infrastructure-assessment.md:160` 把"NetworkPolicy 网络隔离"列为尚缺能力。

## 四、安全上下文与 ServiceAccount

**写了完整容器级加固的只有 3 个服务**：

| 服务 | pod securityContext | container securityContext | 证据 |
|---|---|---|---|
| llm-service | `runAsNonRoot` / `runAsUser:10002` / `runAsGroup:10002` / `seccompProfile:RuntimeDefault` | `allowPrivilegeEscalation:false` + `readOnlyRootFilesystem:true` + `capabilities.drop:[ALL]` | `llm-service/k8s.yaml:92-96`, `:111-114` |
| embedding-service | `runAsNonRoot` / `10001:10001` / `RuntimeDefault` | 同上三件套 | `embedding-service/k8s.yaml:27-31`, `:41-44` |
| openspec-service | `runAsNonRoot` / `10001:10001` / `fsGroup:10001` / `fsGroupChangePolicy:OnRootMismatch` / `RuntimeDefault` | 同上三件套 | `openspec_service/k8s/core.yaml:69`, `:85` |

**部分加固**：es —— pod 级 `runAsUser:1000` / `runAsGroup:0` / `runAsNonRoot:true` / `fsGroup:1000`（`es/k8s/statefulset.yaml:25-30`），但 **initContainer 故意特权** `runAsUser:0` + `privileged:true` 做 `sysctl vm.max_map_count`（同文件 `:35-38`）；容器本身无 `readOnlyRootFilesystem`/`capabilities`。

**完全没有 securityContext 的**（以镜像默认用户跑，通常 root）：`rag-service/k8s.yaml`（整个 Deployment `:10-65`）、`postgres/k8s.yaml`、`redis/k8s.yaml`、`email-service/k8s-deployment.yaml`、`static_resource/k8s/static-pvc.yaml` 的 Job。

**`automountServiceAccountToken: false`**：llm（`:88`）、embedding（`:23`）、rag（`:27`）写了；openspec 用 ServiceAccount 对象承载。

**ServiceAccount 对象**：业务服务里只有 openspec 自建 —— `openspec_service/k8s/core.yaml:50-55`（`kind: ServiceAccount` + `automountServiceAccountToken: false`），Deployment `:70` 引用。其余 ServiceAccount 都是基础设施：`nginx_gateway/nginx-ingress-controller.yaml:12,24`、`cloudflare-tunnel/{operator,manual}/rbac.yaml`、`hadoop_base/fencing.yaml:3`。

**没有业务服务的 RBAC Role/RoleBinding。没有 ResourceQuota / LimitRange（全仓 grep 零命中）。没有 PodSecurityPolicy / Pod Security Admission 标签。**

## 五、持久化存储

三个 StorageClass：

| SC | provisioner | 特性 | 出处 |
|---|---|---|---|
| `ceph-rbd` | `rbd.csi.ceph.com` | **默认 SC**，`reclaimPolicy: Delete`，可扩容，**RWO** | `ceph/ceph-rbd-storageclass.yaml` |
| `ceph-cephfs` | `cephfs.csi.ceph.com` | `fsName: k8s-cephfs`，**RWX** | `ceph/cephfs-storageclass.yaml` |
| `nfs` | 静态 PV | `pv-nfs-master/server1/server2` 各 100Gi，`Retain`，**全部 RWX** | `nfs/pv-nfs.yaml`、`nfs/pvc-nfs.yaml` |

> ⚠️ `nfs/` 目录里的 server 写的是 `nanopct4-master`/`nanopct4-server1/2`，与 `cluster_config.sh` 里实际的 `nanopct4-server1/2/3` 命名对不上 —— 看起来是模板/历史遗留，用之前先核对。

**读写模式惯例**：

- **单 writer → `ceph-rbd` + RWO**
- **需跨 Pod / 跨 Job 共享（CronJob 共享数据卷、静态图）→ `ceph-cephfs` + RWX**

现存 PVC：

| PVC | 文件:行 | SC | 模式 | 容量 |
|---|---|---|---|---|
| postgres-data | `postgres/k8s.yaml:25-35`, `:94-102` | ceph-rbd | RWO | 10Gi |
| redis | `redis/k8s.yaml:140-148` | ceph-rbd | RWO | 5Gi |
| es | `es/k8s/statefulset.yaml:109-120` | ceph-rbd | RWO | 30Gi |
| openspec-workspaces | `openspec_service/k8s/core.yaml:30-39` | ceph-rbd | RWO | 20Gi |
| static-files | `static_resource/k8s/static-pvc.yaml:7-18` | ceph-cephfs | RWX | 50Mi |
| content-agents-data | `panghu_agent/content_agents/k8s/storage.yaml:3-12` | ceph-cephfs | RWX | 1Gi |
| vault | `vault/k8s/pvc.yaml:7-20` | ceph-rbd | RWO | — |

容量约定：有状态基础设施 5–30Gi，工作区/缓存 1–20Gi，静态资源极小（50Mi）。**集群 Ceph 总量约 436 GiB，已用约 5.5 GiB**（`panghu_chat/docs/infrastructure-assessment.md:48`）。

`static_resource` 有个特殊做法：图片不入镜像，`deploy.sh` 先 rsync 到 master 的 `/root/armbianbegin/static_resource`，再由一个 `hostPath` → PVC 的 init Job 拷进 `main-portal`（`static_resource/k8s/static-pvc.yaml:20-53`、`static_resource/deploy.sh:34-46`）。

## 六、镜像与 ARM64 构建

**全部自建镜像，推私有 registry `arm-cluster-master:5000`**（宿主 Docker registry，端口 5000；`cluster_config.sh:11-13`）。

| Dockerfile | FROM | 产物 |
|---|---|---|
| `llm-service/Dockerfile:1` | `python:3.11-slim` | `arm-cluster-master:5000/llm-service:latest`，`USER 10002:10002` |
| `embedding-service/Dockerfile:1` | `python:3.11-slim` | 模型**烘焙进镜像**（`RUN python prepare_model.py` 下 bge-small-zh-v1.5），`USER 10001:10001` |
| `rag-service/Dockerfile:1` | `python:3.11-slim` | 无 USER（root 跑） |
| `es/Dockerfile:2` | `docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}` (8.15.3) | 加装 analysis-ik |
| `email-service/Dockerfile:6` | `${REGISTRY}/base:latest` | — |
| `openspec_service/Dockerfile:1` | `arm64v8/node:22-bookworm-slim` | 装 git，`useradd --uid 10001` |
| `base/Dockerfile:6` | `arm64v8/debian:latest` | 通用工具基础镜像 |

**每个 `build.sh` 都带 `docker build --platform linux/arm64`**：`llm-service/build.sh:39`、`embedding-service/build.sh:52`、`rag-service/build.sh:10`、`es/build.sh:39`；openspec 参数化 `PLATFORM="${PLATFORM:-linux/arm64}"`。

> ⚠️ **全仓没有 amd64 构建目标，没有 buildx manifest list，没有 `docker buildx`**。这意味着：如果某个上游只提供 amd64 镜像，"自己 build 一个 arm64 版"并不是一条免费的退路 —— 得先把多架构基础镜像、原生依赖（Node/Python native module）这条链走通。

K8s 侧用 `nodeSelector: kubernetes.io/arch: arm64` 钉架构（`llm-service/k8s.yaml:91`、`embedding-service/k8s.yaml:26`、`rag-service/k8s.yaml:29`）。

## 七、定时任务：CronJob 是唯一约定

**CronJob（唯一一处，7 个）**：`panghu_agent/content_agents/k8s/cronjobs.yaml`，namespace `content-agents`：

| name | schedule (Asia/Shanghai) | 行 |
|---|---|---|
| `github-trending-agent` | `30 19 * * *` | `:5-44` |
| `finance-news-agent` | `*/30 * * * *` | `:47` |
| `programmer-jobs-agent` | `0 20 * * *` | `:87` |
| `programmer-jobs-weekly-agent` | `30 20 * * 0` | `:129` |
| `international-news-agent` | `30 0,12 * * *` | `:170` |
| `meme-collector-agent` | `0 21 * * *` | `:211` |
| `llm-guard-report-agent` | `15 4 * * *` | `:253` |

**CronJob 约定可以直接照抄**：

```yaml
spec:
  timeZone: Asia/Shanghai
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      ttlSecondsAfterFinished: 3600
      backoffLimit: 2
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: agent
              command: [python, -m, <pkg>.main]
              resources:
                requests: {cpu: 10m, memory: 32Mi}
                limits: {cpu: 500m, memory: 512Mi}
```

数据经共享 RWX PVC `content-agents-data` 挂 `/data`。

**Job 先例**（一次性/迁移）：DB migration Job —— `panghu_chat/hublog/k8s/migration-job.yaml`、`panghu_game/{TaShuo,ShaPan,GuanLiao,QianFu}/deploy/k8s/migration-job.yaml`，约定 `command: [python, -m, app.migrate]`、`ttlSecondsAfterFinished: 3600`（完成后保留 1 小时）。运行期动态创建 Job 的先例：`panghu_agent/scihub_cli/job.yaml:1-2`（"Literature Downloader API creates per-task Jobs at runtime"）。

**应用内调度器：在重点服务里没有。** 对 `apscheduler|APScheduler|BackgroundScheduler|AsyncIOScheduler|node-cron|import schedule` 的全局 grep 在 llm/embedding/rag/es/email 的代码里**零命中**。命中的 `schedule.` 全在游戏引擎里指"角色作息表"（如 `panghu_game/QianFu/packages/core/src/engine.ts:2000`）。宿主机层面只有 `debian_begin.sh:202-203` 给 registry 容器加了 `@reboot` crontab。

> ✅ **约定明确：周期性任务用 K8s CronJob，一次性/迁移任务用 Job，应用内不做调度。** 新服务如果自带调度器（比如引入一个第三方 agent 运行时），要么按这个约定改掉，要么显式说明为什么例外 + 如何防止与 CronJob 重复执行。

另有一个宿主机级定时器作对照：`resource_scheduler/systemd/k8s-node-memory-guard.{service,timer}` —— 1 分钟跑一次读 kubelet `stats/summary`，>80% 给 NanoPC 节点打 `memory.guard/over-80=true:NoSchedule` taint，≤75% 摘除（`resource_scheduler/k8s-node-memory-guard.sh:9-10,89-94`）。

## 八、资源量级与集群规模

**重点服务的 requests/limits**：

| 服务 | requests | limits | 出处 |
|---|---|---|---|
| llm-service | 100m / 128Mi | 1 / 512Mi | `llm-service/k8s.yaml:108-110` |
| embedding-service | **1 / 512Mi** | **4 / 1Gi** | `embedding-service/k8s.yaml:38-40` |
| rag-service | 200m / 256Mi | 1 / 1Gi | `rag-service/k8s.yaml:59-61` |
| es | **1000m / 3Gi** | **2 / 4Gi** | `es/k8s/statefulset.yaml:67-73`（JVM `-Xms2g -Xmx2g`，`:53-54`） |
| postgres | 200m / 512Mi | 1000m / 2Gi | `postgres/k8s.yaml:75-81` |
| redis | 100m / 256Mi | 500m / 1Gi | `redis/k8s.yaml:106-112`（`maxmemory 1gb`，`:37`） |
| email-service | 50m / 64Mi | 200m / 128Mi | `email-service/k8s-deployment.yaml:58-60` |
| openspec-service | 50m / 128Mi | 500m / 512Mi | `openspec_service/k8s/core.yaml:84` |
| CronJob（批处理） | 10m / 32Mi | 200–500m / 256–512Mi | `content_agents/k8s/cronjobs.yaml:39-40` 等 |

量级总结：常驻轻服务 50–200m / 64–256Mi requests；重服务上限 1–4 核 / 1–4Gi；requests:limits 普遍 2–4× 余量。

**集群规模**（ARM64，K8s `v1.31.2`，`cluster_config.sh:31-34`）：

| 节点 | 角色 | CPU | 内存 | SoC | 备注 |
|---|---|---|---|---|---|
| arm-cluster-master | control-plane | 8C | 15.5G | RK35xx | `192.168.137.101` |
| orangepi5-max-server1 | worker | 8C | 15.5G | **RK3588** | ES/PG/Redis 所在，带 NPU |
| nanopct4-server1/2/3 | worker ×3 | 6C | 3.66G | RK3399 | **内存极紧** |

合计约 34 核 / 44 GiB。无 Metrics Server，资源观测需直接 SSH。

调度靠 `nodeSelector` 钉死节点（llm、embedding、es 都钉 `orangepi5-max-server1`；rag 只钉 `kubernetes.io/arch: arm64`）。**没有 tolerations 实际使用**（只在 hadoop/spark 是注释掉的）。低资源节点靠 taint + `resource_scheduler` 守卫。

> ⚠️ 容量现实：ES 一个服务就占 3Gi request / 4Gi limit，而三台 NanoPC 各只有 3.66 GiB 且不适合跑重负载。**新增长驻服务前先做内存估算**，这不是一个能随手加常驻进程的集群。`docs/rag-service-spike.md:18-25` 对节点能力有更细的实测口径。

## 九、新增服务的检查清单

1. 建目录，写 `Dockerfile`（`FROM` 用 arm64 基础镜像）+ `k8s.yaml` + `build.sh` + `deploy.sh`。
2. `docker build --platform linux/arm64`，推 `arm-cluster-master:5000/<name>:latest`。
3. namespace：基础设施放 `data`，应用自建独立 namespace。跨 ns 用 FQDN。
4. 需要被 llm/rag/embedding 调用 → **调用方 Pod 打对应 client 标签**，否则超时。
5. 敏感值走 Vault `secret/data/<ns>/<app>/<key>` + ExternalSecret（`refreshInterval: 1h`、`creationPolicy: Owner`），照抄 `vault/inventory/` 现有写法。
6. 单 writer 用 `ceph-rbd` RWO；跨 Job 共享用 `ceph-cephfs` RWX。
7. 周期性任务写 CronJob，照抄第七节的字段组合；不要在应用内起调度器。
8. 加 securityContext 三件套（`runAsNonRoot` + `readOnlyRootFilesystem` + `drop: [ALL]`）+ `automountServiceAccountToken: false`，对齐 llm/embedding/openspec。
9. 显式设 `resources.requests/limits`（集群没有 ResourceQuota 兜底）。
