# 网络策略引擎选型与启用清单

**结论：集群当前没有任何 NetworkPolicy 生效。**

> ## 🔴 2026-09-21 更正：**kube-router 是被误判的，真正的原因是策略里的一条 CIDR**
>
> 本文档这一节之前写着"kube-router 不支持 `ipBlock` 的 `except` 列表"，并据此改用完整 Calico。**该结论错误，特此更正。**
>
> **真正的原因**：DSH 的 `runner-egress` 策略在 except 列表里写了 **`198.18.0.0/15`**（大概是当成 RFC 2544 基准测试保留段加的）。但**本网络的软路由跑 OpenClash fake-ip DNS，把所有外部域名都解析成 `198.18.x.x`**——这一条等于**把整个公网排除了**。仓库里 [../cloudflare-tunnel/TROUBLESHOOTING-1033.md](../cloudflare-tunnel/TROUBLESHOOTING-1033.md) 早就记录过这个 fake-ip 行为。
>
> 实测（2026-09-21，同一 Pod、同一策略、只改这一条）：
>
> | except 列表 | 内网 | 公网 |
> |---|---|---|
> | 13 条（含 `198.18.0.0/15`） | 断 ✅ | **断 ❌** |
> | 12 条（去掉它） | 断 ✅ | **通 ✅** |
>
> **kube-router 与 Calico 的 `except` 实现都是正确的。** 我最初的 `probe-matrix.sh` 场景复刻了同一条错误的 except 列表，于是"验证"出了一个不存在的引擎缺陷，并据此做了一次不必要的换 CNI 手术。
>
> **当前状态**：集群已在 Calico 上且工作正常（迁移本身完成了，Calico 也更能兑现 NetworkPolicy）。**不回滚**——它现在提供的能力是 flannel 从来没有的。策略侧的真问题已在 [../panghu_chat/dsh/k8s/networkpolicies.yaml](../panghu_chat/dsh/k8s/networkpolicies.yaml) 修掉（删除该 CIDR 并加注说明）。
>
> **教训**：`except` 里写"保留段"之前，先确认本网络的 DNS 不做 fake-ip。这个仓库有 fake-ip，而且已经写过一次。
>
> 完整过程见 [calico-migration-run.md](calico-migration-run.md)。
>
> ### 🟡 2026-09-22 状态：三件事要说清
>
> - **Calico 是在位的引擎。** 本文第三节那套 kube-router `--run-firewall` 方案**已不适用**。kube-router 的目录与脚本按所有者 2026-09-22 的决定**保留作历史记录与备用路线**（`network-policy/k8s/20-kube-router.yaml`、`deploy.sh`、`build.sh`），**不是当前选型**：它的 `--enable-cni=false` 和 `br_netfilter` 前提都建立在"flannel 继续做数据面"之上，而在 Calico 底下再叠一个写 iptables 的策略组件正是 2026-09-21 踩过的坑（当时 kube-router 与 Calico 并行写 iptables）。
> - **DSH 边界尚未复验。** 引擎到位、策略已修，但端到端复验还没跑过。执行材料：[../panghu_chat/dsh/verify-network-boundary.sh](../panghu_chat/dsh/verify-network-boundary.sh)（从**真实项目容器**里探测）；判据与期望值见 [../panghu_chat/dsh/docs/boundaries.md](../panghu_chat/dsh/docs/boundaries.md) 末节。
> - 所以**本文第一行「集群当前没有任何 NetworkPolicy 生效」请按「截至 2026-09-20」读**，不要当作今天的结论。同理，[infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) 第 8.0 节与第 11 节那条验收项也还是未通过状态。
>
> ### ⚠️ 另一个读数陷阱：本网络对任意公网地址都回 CONNECTED（实测 2026-09-23）
>
> 这是**第二个会把网络测量读歪**的本网络特性，和上面的 fake-ip 同源（都在软路由那一层）。
>
> 实测：TCP 连 `192.0.2.1`、`198.51.100.7`、`203.0.113.55`（RFC 5737 的三个不可路由测试段）**全部 CONNECTED**，端口换 80 / 81 / 1234 / 9999 都一样。`curl http://192.0.2.1/` 拿不到 HTTP 响应（`http_code=000`）但 TCP 握手成功。软路由在做**透明代理**，任何目标都由它先应答。
>
> **影响**：任何"可达性"测量里，**REACHABLE 这一侧的证据是弱的**——它只证明包离开了 Pod、策略放行了它，**不证明对端真的应答了**。
>
> **不受影响**：**DENY 这一侧仍然是硬的**。NetworkPolicy 的丢弃发生在节点上、包还没离开节点，代理根本看不到它，所以**造不出假的可达**。反过来也成立：如果被策略拦掉的目标显示了 CONNECTED，那一定是策略没生效，不是代理的锅。
>
> ⇒ 写验收脚本时把**"必须被拒"当主判据**，"必须可达"只当烟雾测试。两份真实负载的验收脚本都按这个原则写了并就地注明：[../panghu_chat/dsh/verify-network-boundary.sh](../panghu_chat/dsh/verify-network-boundary.sh)（公网那组期望**可达**，证据弱）与 [../panghu_chat/hermes/verify-network-boundary.sh](../panghu_chat/hermes/verify-network-boundary.sh)（公网那组期望**被拒**，证据硬）。

- 调查日期：2026-09-20
- 调查方式：SSH 到 `arm-cluster-master` 只读查询 + 从 `dsh-runner` 容器内 TCP 探测
- 起因：复核 [infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) 时发现 DSH 的网络边界不成立

## 一、问题

集群 CNI 是 **`kube-flannel`**（5 节点各一个 DaemonSet）。`kube-system` 里除 `kube-proxy` 外没有其他 DaemonSet，**无 Calico / Cilium / kube-router / antrea，也无任何策略相关 CRD**。

**flannel 不实现 NetworkPolicy**。因此集群中现存的 **13 个 NetworkPolicy 对象全部空转**。

实测证据——从 `dsh-runner-armbianbegin` 容器内 TCP 探测（该容器的策略明确声称拒绝内网）：

| 目标 | 策略声称 | 实测 |
|---|---|---|
| `llm-service.llm.svc:80` | 拒绝 | **CONNECTED** |
| `rag-service.data.svc:8080` | 拒绝 | **CONNECTED** |
| `embedding-service.data.svc:8080` | 拒绝 | **CONNECTED** |
| `postgres.data.svc:5432` | 拒绝 | **CONNECTED** |
| `redis.data.svc:6379` | 拒绝 | **CONNECTED** |
| `kubernetes.default.svc:443` | 拒绝 | **CONNECTED** |
| `vault.vault.svc:8200` | 拒绝 | **CONNECTED** |
| `registry.npmmirror.com:443`（对照） | 放行 | CONNECTED |

**受影响范围**（13 个策略分布）：

| 命名空间 | 策略 |
|---|---|
| `dsh` | `default-deny`、`tunnel-ingress`、`web-egress` |
| `dsh-runners` | `default-deny`、`runner-ingress`、`runner-egress` |
| `hermes` | `default-deny`、`tunnel-ingress`、`research-egress`、`hublog-publisher` |
| `data` | `embedding-service`、`rag-service` |
| `llm` | `llm-service` |

## 二、选型

### ❌ Calico 策略-only —— 官方不支持

最初的首选，查证后**排除**。[projectcalico/calico#8866](https://github.com/projectcalico/calico/issues/8866) 中维护者的明确答复：

> "For using calico policy only mode with flannel, **it is not possible to install calico on a cluster that already has flannel installed.**"

> "we do not have any official method for installing policy-only Calico on a cluster with a pre-existing Flannel overlay... **some configurations of Flannel are completely incompatible with how Calico enforces policy, e.g, Flannel bridges break Calico policy between pods on the same node.**"

提问者自行 patch ClusterRole 让 `calico-policy-only.yaml` 跑起来了，官方回复仍是不支持、不推荐。**不要从这里试起。**

### ⚠️ Canal（`canal.yaml`）—— 可行，但等于换 CNI

Calico 官方唯一的 flannel 组合，是一次性安装 flannel + Calico。**这意味着替换现有 flannel**：

- 需改每节点 kubelet 的 CNI 配置
- kube-router 的文档把代价写得很直白：**"Switching CNI providers on a running cluster requires re-creating all pods to pick up new pod IPs."**
- 本集群 **164 个 Pod** 需要重建

对本需求（只为挡住 DSH runner）代价过高。保留为 kube-router 验证失败时的退路。

### ✅ kube-router `--run-firewall` 策略-only —— 采用

```sh
kube-router --run-firewall=true --run-router=false --run-service-proxy=false
```

只做网络策略；Pod 网络留给 flannel，Service 留给 kube-proxy。**不装 CNI 插件、不改 kubelet 的 CNI 配置**——这是它与 Canal/Calico 的关键差别，也是**不需要重建 Pod** 的原因。

| 前提 | 状态 |
|---|---|
| 官方文档支持"只跑策略" | ✅ 四个开关 `--run-firewall` / `--run-router` / `--run-service-proxy` / `--run-loadbalancer` 可独立启用 |
| 宿主机 iptables 能看到网桥上的 Pod 流量 | ✅ `br_netfilter` 已加载、`bridge-nf-call-iptables=1`（master / nanopct4-server1 / orangepi5 三台实查） |
| 有 arm64 镜像 | ✅ release 含 `kube-router_2.11.1_linux_arm64.tar.gz`；Makefile 构建 `linux/amd64,linux/arm64,linux/arm,...` |
| 项目活跃 | ✅ v2.11.1（2026-08-17），最近提交 2026-09-13，未归档 |

**风险**：kube-router 是 cloudnativelabs 的第三方项目（约 2.5k stars、19 个 open issue），不是 CNI 厂商主线。

> ⚠️ **本方案有一环未验证**：`br_netfilter=1` 是**必要条件，不是充分条件**。kube-router 直接写宿主机 iptables 的 `KUBE-POD-FW-*` 链，模型与 Calico 不同，因此 Calico 那句"网桥会破坏同节点策略"**不能直接套用**，但也不能反过来假定它一定生效。**必须先做第五节的最小验证。**

## 三、生效范围：只框 dsh + hermes

NetworkPolicy 只影响被其 `podSelector` 选中的 Pod。**其余约 40 个命名空间没有任何策略选中它们 → 默认放行，行为完全不变。**

⚠️ **但生效范围不由"装在哪"决定，而由"谁被选中"决定。** `data/` 和 `llm/` 的 3 个策略已经存在，引擎一开就会一起变成真的。要只框 dsh + hermes，**必须把它们删掉**：

```sh
kubectl -n data delete networkpolicy embedding-service rag-service
kubectl -n llm  delete networkpolicy llm-service
```

保留它们的代价（若日后想全集群收口，这些是要补的）：

| 策略 | 保留后必须补的 |
|---|---|
| `data/embedding-service` | 给 `rag-service` Pod 补 `embedding-client: "true"` 标签——**实测全集群带该标签的 Pod 数量为 0**，而 rag-service 是 embedding-service 唯一的调用方；另需处理其 `egress: []`（连 DNS 都禁） |
| `data/rag-service` | 10 个调用方**均已带** `rag-client: "true"` ✅，无需改动 |
| `llm/llm-service` | 实测 12 个调用方**均已带** `llm-client: "true"` ✅，无需改动 |

**建议：先删，把引擎生效范围严格框在 dsh + hermes。** 全集群收口是一件独立的、可以慢慢做的事。

## 四、启用前必须完成的三件事

以下三处**当前都是坏的**，引擎一开就会立刻暴露：

### 1. cloudflared 的入口标签

`dsh/tunnel-ingress` 与 `hermes/tunnel-ingress` 原本要求来源 Pod 带 `dsh-ingress: "true"` / `hermes-ingress: "true"`。**实测 cloudflared 的标签只有 `{app: cloudflared, tunnel: main, pod-template-hash}`——这两个标签从来不存在。** 直接用现有策略启用引擎，**DSH 和 Hermes 会双双失联**。

**✅ 已在仓库修好**：两个策略改为选择 cloudflared 已有的稳定标签，零改 operator：

```yaml
from:
- namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: default}}
  podSelector: {matchLabels: {app: cloudflared, tunnel: main}}
ports: [{protocol: TCP, port: 4180}]
```

### 2. Hermes → Hublog 的出站端口

`hublog-publisher` 原只放行 **8080**，而 `HUBLOG_URL` 无端口即 **80**（[hermes-code-review.md](hermes-code-review.md) 的 H1）。

**✅ 已在仓库修好**：同时放行 80 与 8080——具体哪个对取决于 CNI 在 DNAT 前还是后匹配端口，不赌。

### 3. 确认依赖的标签都在

| 依赖 | 状态 |
|---|---|
| cloudflared ← 两个 ingress 策略 | ✅ 改为选现有标签 |
| `hermes-web` Pod `role: web` | ✅ 实测存在 |
| `hermes-collect/report/publish` Pod 的 `role` | ✅ 实测分别为 `collect` / `report` / `publish`，与策略选择器一致 |
| `dsh-web` `role: web`、runner `role: runner` | ✅ 实测存在 |
| runner ↔ web 的 2222 互连 | ✅ 策略两侧一致 |

## 五、最小验证（不要直接上全集群）

**✅ 已落成可执行材料：[`network-policy/`](../network-policy/README.md)。** 本节只讲判断，具体命令与脚本在那个目录里。

> ⚠️ **本节 2026-09-20 更正过一次，方向变了。** 初版写的是"直接调度到 `orangepi5-max-server1` 试"。实测 pod 分布后推翻：
>
> | 节点 | Pod 数 |
> |---|---:|
> | `orangepi5-max-server1` | **94**（全集群 164 的 57%） |
> | `nanopct4-server3` / `-server2` | 32 / 19 |
> | `arm-cluster-master` | 12 |
> | `nanopct4-server1` | **4**（全是 hostNetwork 基础设施） |
>
> 而 kube-router 的失败模式**不是"策略没生效"**（那是 fail-open，不比今天差），**是它改坏宿主机 FORWARD 链导致那台节点的 Pod 掉网**。在一台跑着 94 个 Pod 的节点上冒烟，是在赌整个集群。
>
> 但反过来，`nanopct4-server1` 上**没有任何应用 Pod**，纯在那儿试也证明不了策略生效。所以验证设计成**用一个用完即删的探针 Pod**，既把爆炸半径压到零，又能真正测到 enforcement。

### 三步铺开

```sh
cd network-policy
bash build.sh                      # 同步镜像进私有 registry，固定 digest

bash deploy.sh --dry-run           # 先看渲染
bash deploy.sh                     # 默认钉在 nanopct4-server1（4 个 Pod）
bash verify.sh                     # 三阶段自证

bash deploy.sh --node orangepi5-max-server1   # 真正要紧的那台
bash verify.sh --node orangepi5-max-server1

bash deploy.sh --all-nodes         # 通过后再全量
```

`verify.sh` 的三阶段是**必须**的，因为"流量断了"本身什么都证明不了——可能只是数据面坏了：

| 阶段 | 动作 | 期望 |
|---|---|---|
| A | 无策略时探测 | 全部 `CONNECTED`（基线） |
| B | 给探针 Pod 套 deny-all egress | 全部 `BLOCKED`/`TIMEOUT`（证明在生效） |
| C | 删除该策略再探测 | 全部 `CONNECTED`（证明可逆） |

**C 失败是最危险的信号**——策略可装不可卸，立即停手，不要 `--all-nodes`。

**同节点与跨节点都要测**：网桥问题只在同节点出现。探针目标里已同时包含两类。

### 通过之后、动 orangepi5 之前：两件必做

**`verify.sh` 证明的是引擎能工作，不是你的策略是对的。** 探针只受它自己那条临时策略影响；PASS 不能说明真实策略挂到 94 个真实 Pod 上会怎样。两件事必须先做完：

**① 把已修好的策略 apply 到集群。** 仓库里的修复**提交了 ≠ 集群上是新的**。2026-09-20 实测：集群里 `dsh/tunnel-ingress` 与 `hermes/tunnel-ingress` **仍是旧版**（要求 `dsh-ingress` / `hermes-ingress` 标签，而 cloudflared 从来没这两个标签），`hublog-publisher` 仍只放行 8080。**直接上引擎 = DSH/Hermes 立刻从公网失联、发布断掉。** 核对与 apply 命令见 [network-policy/README.md](../network-policy/README.md)。

**② 删掉范围外的三条策略**（见第三节），否则 `embedding-service` 的入站策略会在 orangepi5 上立刻执行，而实测全集群带 `embedding-client: "true"` 的 Pod 为 0 → **RAG 当场断**。

注意 ① 现在做是**零风险**的：引擎还没生效，改了也没人执行。

## 六、启用后仍需注意

> ### 🔴 2026-09-20 首次铺开 orangepi5 失败并回滚，根因已定位
>
> `dsh-runner` 的出网被**整个掐断**，包括 `runner-egress` 用 `ipBlock 0.0.0.0/0` + 13 条 `except` 明确放行的公网。已回滚，服务恢复。
>
> **`verify.sh` 当时 PASS——因为它只测过「无策略」和「deny-all」，从未测过带 `ipBlock` allow 规则的策略。** 那次 PASS 完全不能预测真实策略的行为。这是本节最该记住的一句。
>
> **根因（`probe-matrix.sh` 实测，一次只动一个变量）**：`ipBlock` 的 **`except` 列表**。同样写 `ipBlock: 0.0.0.0/0`，**不加 `except` 全通，加上 `except` 就变成全断**。「策略叠加」假设已被推翻——空 `default-deny` 叠加不改变结果。
>
> **这是结构性问题，不是调参能绕过的。** NetworkPolicy 没有取反表达，「公网放行 + 内网拒绝」唯一的写法就是 `ipBlock 0.0.0.0/0` + `except`。
>
> > **⇒ 如果 kube-router 不支持 `except`，本文档第三节设计的整个内网边界在 kube-router 上根本表达不出来。选型需要重新评估（可能回到 Canal / 完整 Calico，即接受换 CNI、重建 Pod）。**
>
> 上游线索 [#1617](https://github.com/cloudnativelabs/kube-router/issues/1617) 结构完全一致，但它的解法（显式 `--service-cluster-ip-range`）对本集群无效——默认值恰是我们的 Service CIDR。
>
> 完整矩阵与记录见 [network-policy/README.md](../network-policy/README.md)。

- **存量 Pod 是否被 kube-router 纳管**：策略-only 模式不装 CNI 插件，理论上能接管已存在的 Pod，但**未验证**。最小验证里若内网仍连通，先排查这一条再否定整个方案。
- **IPv6 未覆盖**：`ipBlock` 只有 IPv4，全仓无 IPv6 处理。需确认节点无 IPv6 出口（见 [../panghu_chat/dsh/docs/boundaries.md](../panghu_chat/dsh/docs/boundaries.md)）。
- **`calico-node` 不适用**：若最终转 Canal，注意其 `calico-node` 需要 privileged，可参考本仓库 `kube-flannel` 命名空间已有的 `pod-security=privileged` 做法。
- **不要把网络隔离计入任何已完成的验收**：在最小验证通过之前，[infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) 第 11 节那条"集群网络隔离实际生效"保持不通过。
