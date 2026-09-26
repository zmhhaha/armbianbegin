# metrics-server —— 让 `kubectl top` 可用

**集群此前没有 Metrics Server**，所以 `kubectl top` 不可用、**只能看到 requests 看不到实际用量**（[../panghu_chat/docs/infrastructure-assessment.md:63](../panghu_chat/docs/infrastructure-assessment.md)）。装上它，Metrics API 才存在，`kubectl top nodes` / `kubectl top pods -A` 才可用。

- 锁定版本：**metrics-server v0.8.1**
- 上游：<https://github.com/kubernetes-sigs/metrics-server>
- 清单来源：上游 HA 清单 `high-availability-1.21+.yaml`，**语义上只做四处改动**（见下）

> ### 怎么核对"只改了四处"：用**语义** diff，不要用行 diff
>
> `deploy.sh` 用 `python3 + PyYAML` 加载并重写清单（与 `network-policy/calico/install.sh` 同一手法），而 **PyYAML 往返一圈会把整个文件的格式重排**——键序、引号、`---` 位置都变。所以 `diff upstream.yaml rendered.yaml` 会把**每一行**都标成改动，那个输出没有信息量。
>
> 正确做法是比对**解析后的结构**（逐键递归）。2026-09-27 实测结果，全部 10 个文档**只有 4 处**差异，且正好是下面这四处：
>
> ```text
> Deployment/metrics-server —— 4 处差异：
>   ...containers[0].args: 列表长度 5 -> 6
>   ...containers[0].image: 'registry.k8s.io/metrics-server/metrics-server:v0.8.1'
>                        -> 'arm-cluster-master:5000/metrics-server/metrics-server:v0.8.1'
>   ...containers[0].resources.limits: 新增 = {'cpu': '500m', 'memory': '300Mi'}
>   ...spec.nodeSelector.kubernetes.io/arch: 新增 = 'arm64'
> ```

---

## ⚠️ 先读这一条：它解决的是「看得见」，不是「调得动」

**调度器依据的是 `requests`，而本集群的 Pod 几乎都不写 requests**（`cluster_config.sh` 的注释：master 上 12 个 Pod 合计 0.23 GiB，三台 NanoPC 上 calico-node 只有 cpu，kube-proxy 和 CSI 全是空的）。

于是装上 metrics-server 之后：

- ✅ 你会**第一次看到真实用量**——这是本次的全部目的
- ❌ **该 Pending 的还是会 Pending**。把观测到的用量**回填成 requests** 才是改善调度的那一步，那是另一件事

**它也不是监控系统**：没有历史、没有告警、重启即丢。它回答"现在多少"，不回答"趋势如何"。`infrastructure-assessment.md` 里那些"没有 Prometheus / Grafana / 不可观测"的结论**装着不动**——本仓库的监控缺口不是这一步能补的。

---

## 版本为什么是 v0.8.1

上游 README 的兼容矩阵（2026-09-27 取自上游）：

| metrics-server | 支持的 Kubernetes |
|---|---|
| 0.9.x | **1.34+** |
| **0.8.x** | **1.31+** |
| 0.7.x | 1.27+ |

本集群是 **v1.31.2**（`cluster_config.sh`）→ 只有 0.8.x 这一线合适，v0.8.1 是它的最新补丁。**不要"顺手升级"到 0.9.x，它要求 1.34+，在这台集群上跑不起来。**

---

## 与上游的四点差异

镜像地址由 `mirror.sh` 改（它只做 `sed`，不改结构）；其余三处由 `deploy.sh` 在渲染时改。两个脚本的头部注释都写了理由，**核对方式见上面的语义 diff 说明**。

### 1. 镜像改到私有 registry（`mirror.sh`）

`registry.k8s.io/metrics-server/metrics-server:v0.8.1` → `arm-cluster-master:5000/metrics-server/metrics-server:v0.8.1`，并**断言架构是 arm64** 之后才推。

镜像源按顺序试：`MS_MIRROR`（可选）→ `registry.k8s.io` → 阿里云两个镜像站。**registry.k8s.io 在本网络上慢或不通**——`debian_begin.sh` 拉 kubeadm 镜像时也是走阿里云，同理。架构断言是这份回退列表敢一路试下去的原因：不管从哪来，不是 arm64 就停。

### 2. `--kubelet-insecure-tls`（`deploy.sh`）

**上游清单里没有这一条，这个集群必须有。** 原因链条：

- `kubeadm init` 默认**不启用 `serverTLSBootstrap`**（`debian_begin.sh` 全文没有这个设置）
- 于是 kubelet 的 serving 证书是**自签的**，metrics-server 用系统信任库验不过去
- 结果是 scrape 全部失败、Metrics API 空转

**它的代价要说清楚，不能只写"加上就好"**：metrics-server 因此**不校验 kubelet 的身份**——一个被攻陷的节点可以喂假指标。影响有限（只读指标、单租户集群），但这是**明示的取舍**，不是默认无害。

> **更严格的路（本次不做，备查）**：kubelet 开 `serverTLSBootstrap: true`，逐个批准 CSR，然后去掉这个 flag。代价是全节点重启 kubelet + CSR 批准流程，收益是 metrics-server 能验 kubelet 身份。

### 3. 补 `resources.limits`（`deploy.sh`）

上游只写 requests（`cpu 100m / memory 200Mi`）。[../docs/platform-k8s-conventions.md](../docs/platform-k8s-conventions.md) §九.9 要求显式 requests **和** limits，所以补 `limits: cpu 500m / memory 300Mi`。

整份开销：**2 replica × (100m / 200Mi) = 集群 200m / 400Mi**，落在该文件记载的"常驻轻服务 50–200m / 64–256Mi"档位内。

### 4. `nodeSelector: kubernetes.io/arch: arm64`（`deploy.sh`）

上游只钉 `kubernetes.io/os: linux`；本仓库统一用 arch 钉架构。

---

## 两处**有意**偏离本仓库约定

看起来像疏忽，其实是刻意的，写在这里免得日后被人"修正"回去：

| 约定 | 出处 | 这里怎么做 | 为什么 |
|---|---|---|---|
| `automountServiceAccountToken: false` | `platform-k8s-conventions.md` §九.8 | **保持 `true`（上游默认）** | 它就是靠 SA token 跟 kubelet 与 apiserver 说话——这是它的职责本体，不是放松 |
| 基础设施放 `data` namespace | 同上 §九.3 | 放 **`kube-system`** | APIService 走聚合层，metrics-server 在 kube-system 是上游与生态惯例 |

**`securityContext` 三件套不用改**——上游清单已经满足（`runAsNonRoot`、`runAsUser: 1000`、`readOnlyRootFilesystem`、`drop: [ALL]`、`allowPrivilegeEscalation: false`、`seccompProfile: RuntimeDefault`）。

---

## 两个容易踩的点

### 🔴 不要加 `hostNetwork`

`--secure-port=10250` 是 **Pod 内**端口，与 kubelet 的 10250 不在同一个 netns，**不冲突**。一旦加上 `hostNetwork: true` 才会真冲突（抢 kubelet 的端口）。

### 🔴 不要加 tolerations

上游清单**没有** tolerations，三台 NanoPC 带静态污点 `memory.guard/over-80:NoSchedule`，所以 replica 只能落在**未打污点的两台**：`arm-cluster-master` 与 `orangepi5-max-server1`（master 的 control-plane 污点已于 2026-09-22 摘除，见 `platform-k8s-conventions.md` §8.1）。

> ⚠️ **候选只有两台，而 `replicas: 2` + `required` 反亲和正好把两台都用满。** 2026-09-27 实测确认落在两个不同节点上。**任一台变得不可调度时，另一个 replica 会 Pending**——服务不中断（一个 replica 足够提供 Metrics API），但冗余就没了。
>
> ⚠️ **集群里没有 `orangepi5-plus-server1`。** `cluster_config.sh` 的 `ALL_NODES` 列了 6 个名字，但 `kubectl get nodes` 只有 **5** 台。这条是 2026-09-27 跑 metrics-server 时才被发现的（早先的推断写反了：错的是 `cluster_config.sh`，不是 `platform-k8s-conventions.md` 的节点表）。

**为了"跑起来"而加 tolerations，等于把 metrics-server 塞进三台 3.66 GiB 的机器**——而那正是 `resource_scheduler/` 那套守卫要挡的方向。

反亲和是 `requiredDuringScheduling`（两个 replica 必须不同节点）。**若第二个 replica 长期 Pending**，把渲染出的 `podAntiAffinity` 由 `required` 改成 `preferred`。

---

## 部署

```sh
bash mirror.sh            # 镜像进私有 registry + 渲染清单（不碰集群）
bash deploy.sh --dry-run  # 先看渲染结果（前 60 行）
bash deploy.sh            # apply + 等 rollout + 等 APIService Available
bash verify.sh            # 验收，退出码 0 才算过
```

**通过条件**：

| 步骤 | 通过条件 |
|---|---|
| `mirror.sh` | `rendered/` 里清单存在；自查输出显示镜像指向私有 registry、**无 `registry.k8s.io` 残留**；架构断言通过 |
| `deploy.sh` | 脚本自己打印「✓ 三处改动都已落地」；`metrics-server 2/2 Ready`；APIService `Available=True` |
| `verify.sh` | **退出码 0**；`kubectl top nodes` 与 `kubectl top pods -A` 都返回真实数字 |

> **首次可用有 15–75 秒延迟**：`--metric-resolution=15s` 才产生第一个指标点，聚合层还要等后端就绪。这期间 `kubectl top` 会显示 `<unknown>`——那是正常的，`verify.sh` 把它算**警告**而不是失败，等一会儿重跑即可。

### 验收记录（2026-09-27，通过）

`verify.sh` **退出码 0**：

| 检查 | 结果 |
|---|---|
| Deployment | `metrics-server 2/2 Ready` |
| 反亲和 | 2 个 replica 在 2 个不同节点上 |
| APIService | `v1beta1.metrics.k8s.io` `Available=True` |
| Metrics API | 返回 **5** 个节点的指标（集群共 5 台） |
| `kubectl top nodes` / `kubectl top pods -A` | 均可用（后者 164 行） |

> ### 🔴 读 `kubectl top nodes` 必看：三台 NanoPC 的 `MEMORY%` 长期 >100%
>
> 验收当天原样输出：
>
> ```text
> NAME                    CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
> arm-cluster-master      1044m        13%    5866Mi          54%
> nanopct4-server1        485m         8%     2755Mi          278%
> nanopct4-server2        580m         9%     2022Mi          204%
> nanopct4-server3        457m         7%     1796Mi          181%
> orangepi5-max-server1   2780m        34%    13200Mi         83%
> ```
>
> **278% / 204% / 181% 不是异常，也不是 bug。** 百分比的分母是 **allocatable**，而 `cluster_config.sh` **刻意**把这三台 3.66 GiB 机器的 allocatable 压到约 **1.06 GiB**（`NANOPC_SYSTEM_RESERVED=2.2Gi` + `NANOPC_KUBE_RESERVED=0.5Gi`）——目的是给 `kubepods.slice` 一个内核层面的硬顶，超了先杀 Pod，而不是像 2026-09-21 那样杀掉宿主机的 mysqld 连带 40 个 oauth2-proxy。
>
> ⇒ **这三行的百分比按定义就不可能低于 100%**：实际占用 2.7 / 2.0 / 1.8 GiB，分母约 1.06 GiB。
>
> ⇒ **不要拿它当容量指标读。** 它的正确读法是"宿主机上用了多少"，不是"Kubernetes 还剩多少"。判断这三台还能不能放东西，看 `resource_scheduler/README.md` 那套硬顶逻辑，不是看这个百分比。

---

## 回退

```sh
kubectl delete -f rendered/metrics-server-deploy.yaml
```

删除会一并带走 Deployment、Service、PDB、APIService 与全套 RBAC。**没有持久化数据**，回退就是删掉，不留痕。

若只想临时停掉指标而不删：`kubectl -n kube-system scale deploy/metrics-server --replicas=0`（APIService 会转成不可用，`kubectl top` 报错）。

---

## 排障

| 症状 | 看哪里 |
|---|---|
| replica 一直 Pending | 反亲和要求第二个节点。`kubectl -n kube-system describe pod -l k8s-app=metrics-server` 看 Events；确认三台 NanoPC 的污点还在（那是**应该**在的），必要时改 `preferred` |
| `ImagePullBackOff` | 私有 registry 里没有镜像，或架构不对。重跑 `mirror.sh`；必要时 `MS_MIRROR=<可达前缀> bash mirror.sh` |
| APIService 一直不 Available | 后端没就绪。`kubectl -n kube-system logs deploy/metrics-server`——**scrape kubelet 失败通常会在这里显形**（TLS、10250 不可达、kubelet webhook 认证被改过） |
| `kubectl top` 全部 `<unknown>` | 等 30–60 秒。若持续如此，看日志里有没有 `unable to fetch metrics from node` 之类的行 |
| 指标只有部分节点 | `--kubelet-preferred-address-types` 的第一项是 `InternalIP`，本集群是**多网卡主机**，**不要动它的顺序**——Calico 那次 `IP=autodetect` 选错网卡断了两个小时（`network-policy/calico/README.md` 阶段 0 表格第 3 条） |

---

## 本方案不做的事

- **不引入 Prometheus / Grafana / kube-prometheus-stack。** `infrastructure-assessment.md:291` 把"安装 Metrics Server"与"扩展监控覆盖 K8s/PG/Redis/Ingress/业务指标"并列成一条，那是**两件事**，本次只做前半。
- **不改 kubelet 配置。** 所以用 `--kubelet-insecure-tls` 而不是 `serverTLSBootstrap` + CSR。
- **不动 `resource_scheduler/`。** 守卫仍是宿主机 `/proc` 那一套。
- **不设 HPA。** Metrics API 就位后 HPA 才可用，那是新需求。

---

## 部署之后要改的文档

**验证通过之后**再改——现在这些地方还都是真的。它们分两类，**不要一起改**：

**A 类：装上就过期**（说的是"没有 Metrics Server / `kubectl top` 不可用 / 只能看 requests"）

`panghu_chat/docs/infrastructure-assessment.md` 的 `:22`、`:63`、`:155`、`:263`；`docs/rag-service-spike.md:25`；`docs/platform-k8s-conventions.md:228`；`openspec_service/DEVELOPMENT_BACKLOG.md:89`；`Resourcetolerate.md:149`（那条 `kubectl top nodes` 的验证步骤现在才真的能跑）。

**B 类：依然成立，只做补充不改结论**（说的是"没有监控 / 不可观测"）

`infrastructure-assessment.md` 的 `:153`、`:187`、`:291`、`:312`；`DEVELOPMENT_BACKLOG.md:139`、`:153`。

> ⚠️ **不要把 B 类改成"已解决"。** metrics-server 给的是瞬时用量，不是监控。

## 文件

| 文件 | 作用 |
|---|---|
| `mirror.sh` | 抓上游 HA 清单、改镜像地址、镜像进私有 registry（断言 arm64），渲染到 `rendered/` |
| `deploy.sh` | 渲染三处改动 → `rendered/metrics-server-deploy.yaml` → apply → 等 rollout 与 APIService；带 `--dry-run` |
| `verify.sh` | 验收：Deployment、反亲和、APIService、Metrics API 真在返回数据、`kubectl top` 两条命令 |
| `.gitignore` | 忽略 `rendered/`（**每个目录各自 ignore，根 `.gitignore` 不管这个**） |
