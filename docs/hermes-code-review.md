# Hermes 代码评审

> 评审时间：2026-09-16；**2026-09-17 修订**（代码在评审后大幅改动，且已部署）。
> 评审对象：`panghu_chat/hermes/`（子模块）+ `oauth/k8s/hermes-*`、`vault/inventory/hermes-*`、`cloudflare-tunnel/operator/hermes-*`。
> 配套：[hermes-intelligence-review.md](hermes-intelligence-review.md)（方案层评审）、[platform-auth-ingress-survey.md](platform-auth-ingress-survey.md)、[platform-k8s-conventions.md](platform-k8s-conventions.md)。

## 修订记录（2026-09-17）

代码在评审后做了结构性调整，且 Hermes 已部署。变化与相应处置：

| 变化 | 对评审的影响 |
|---|---|
| `scripts/render.py` + `deployment.example.yaml` → `k8s/core.yaml`（静态清单）+ `config/build.example.env` | 清单不再由脚本渲染，直接可读、可 `kubectl diff`。**这是改进** |
| `build.sh` 现在会 pull → 断言 `Architecture == arm64` → 解析 digest → 用 digest 构建，并写入 `rendered/upstream-image.txt` | **H2 的镜像部分已解决**（见下） |
| oauth2-proxy 从 container 模板（`hermes-proxy-container.yaml`）→ ConfigMap `hermes-oauth`（INI 格式），容器定义进 `core.yaml` | 我此前引用的行号失效，结论不变 |
| 新增**双层认证**：外层 oauth2-proxy + Hermes dashboard 自身 OIDC | 新增内容，见第三节 |
| 研究配置从 Secret 改为 ConfigMap（`k8s/research-configmap.yaml`） | 合理，非敏感配置不该进 Vault |
| Hublog 凭据改为 `secret/hermes/auth` 的 `HUBLOG_SERVICE_TOKENS` 信封 | 代码已同步（`pipeline.py:191-199` 解析信封），**一致** |
| 已部署 | ARM64 与 CLI 契约在事实上跑通了 |

**仍未解决的高危只剩一条：H1。**

## 一、高危（仍存在）

### H1. Hublog 出站端口不一致：NetworkPolicy 8080 vs 实际连接 80

> 🔴 **2026-09-20 双重状态更新：**
> 1. **清单层已修**：`hublog-publisher` 现在同时放行 **80 与 8080**，不再赌 CNI 在 DNAT 前还是后匹配端口。
> 2. **但本条从未"发作"过，因为策略根本没生效**：集群 CNI 是 `kube-flannel`，不实现 NetworkPolicy。下面"Hublog 发布会被拦"的推论**在当时的集群上不成立**（发布任务实际跑过并 Completed）。
>
> 所以这条的准确定性是**清单内部不一致**，不是一次实际故障。它仍然值得修——策略引擎一旦启用，它就是第一个会炸的点。见 [network-policy-engine.md](network-policy-engine.md)。

修改后**两处都变明确**了，但方向相反：

| 位置 | 值 |
|---|---|
| `panghu_chat/hermes/k8s/core.yaml` | `hublog-publisher` NetworkPolicy ~~只放行 `port: 8080`~~ → **2026-09-20 已改为同时放行 80 与 8080** |
| `panghu_chat/hermes/k8s/core.yaml:49` | `HUBLOG_URL: http://hublog-api.hublog.svc.cluster.local` —— **无端口，即 80** |
| `panghu_chat/hermes/app/pipeline.py:211` | `cls(part.hostname, part.port, ...)` → `part.port` 为 `None` → **80** |

而实际 Service 是：`panghu_chat/hublog/k8s/api-deployment.yaml:59` —— `ports: [{name: http, port: 80, targetPort: http}]`（容器端口 8080）。**Service 只有 80 这一个端口。**

**关键结论：把 `HUBLOG_URL` 改成 `:8080` 是错的** —— Service 上没有 8080，会直接 connection refused。修法只能是让 NetworkPolicy 匹配实际连接。

但具体填哪个值取决于 CNI 在 DNAT 前还是后匹配 egress 端口：

- **DNAT 前匹配**（egress 在源 Pod netns 评估，看到 Service port 80）→ 规则必须是 `80`；现在写 8080 = **发布静默失败**
- **DNAT 后匹配**（看到 targetPort 8080）→ 现在的 8080 能通，改成 80 反而会坏

仓库里**没有先例可抄**：现存三个 NetworkPolicy 里，llm-service 的 egress 只涉及 DNS 与外部 443，embedding-service 的 egress 是空的，rag-service 根本没有 egress 规则。这是仓库第一次出现"egress 指向一个 port≠targetPort 的内部 Service"。

**建议（二选一）**：

1. **稳妥做法**：该规则同时放行 80 和 8080。目标是已经限定到 `hublog` namespace 的 `app: hublog-api` Pod，多放一个端口的安全代价可忽略，但能一次消除不确定性。
2. **精确做法**：实测后只留一个。测试方法见下。

**实测方法**（部署后 30 秒可判定）：起一个带 `role: publish` 标签的 Pod，让它落到 `hublog-publisher` 这条规则上，直接连 80 端口：

```bash
kubectl -n hermes run hermes-netcheck --rm -it --restart=Never \
  --labels='role=publish' \
  --image=arm-cluster-master:5000/hermes-intelligence:latest \
  --command -- /opt/hermes/.venv/bin/python -c \
  "import socket; socket.create_connection(('hublog-api.hublog.svc.cluster.local',80),5).close(); print('port 80 OK')"
```

通了 → 规则改成 80（或保留两者）。超时 → 当前 CNI 是 DNAT 后匹配，现规则可用。

> ⚠️ 时序：这三个 CronJob 初始全部 `suspend: true`，所以**发布路径至今没有被执行过**。这条必须在启用 `hermes-publish` 之前解决，否则第一次发布会在 20:10 静默失败，而失败要等 `failedJobsHistoryLimit` 里看到 Job 才知道。

### H2. CLI 契约 —— 镜像部分已解决，契约部分仍无门禁

`build.sh` 现在做了三件对的事：

```bash
docker pull --platform linux/arm64 "$HERMES_IMAGE"
arch="$(docker image inspect "$HERMES_IMAGE" --format '{{.Architecture}}')"
[[ "$arch" == arm64 ]] || { echo "Expected arm64, got $arch" >&2; exit 1; }
upstream_digest="$(docker image inspect "$HERMES_IMAGE" --format '{{index .RepoDigests 0}}')"
HERMES_IMAGE="$upstream_digest"   # 之后一律用 digest 构建
```

并写入 `rendered/upstream-image.txt` 记录实际用了哪个 digest。**这比之前的"人工检查 manifest"强得多**，而且已部署 = 事实上通过了。

仍有两个小口子：

- **默认从 `:latest` 解析**（`HERMES_IMAGE` 未设时）。重跑 build 会拉到新的上游版本，CLI 契约可能漂移。`config/build.example.env` 里已经给了 `HERMES_IMAGE=...@sha256:ACTUAL_DIGEST` 的写法 —— 建议把实际 digest 写进 `build.local.env` 固化。
- **`core.yaml` 用的是 `:latest` + `imagePullPolicy: Always`**（与仓库其他服务一致）。配合上面那条，一次 `rollout restart` 就可能换到未经验证的镜像。仓库惯例如此，但 Hermes 是交互式 agent，比 llm-service 这类纯转发服务更依赖 CLI 契约，值得用 `rendered/image.txt` 的 tag 钉住。

## 二、中危（沿用 09-16 评审，未变动）

以下均未修改，逐条见下。**其中 M3 因为双层认证的加入而更需要确认。**

**M1. `collect()` 的 `count` 语义误导**（`pipeline.py:107-110`）：`INSERT OR IGNORE` 后无条件 `count += 1`，记的是"feed 里看到的条目数"而非"新增数"。collect 每 3 小时重读同样 60 条，count 几乎不变，而报告附录直接印 `源名: N 条`。

**M2. 文件锁按 action 分文件**（`pipeline.py:239`）：`collect.lock`/`report.lock`/`publish.lock` 三把无关的锁，挡不住跨 CronJob 并发开同一个 sqlite。注释承诺的功能没兑现。

**M3. 发布内容零净化**（`pipeline.py:180-181`）：`content = report + appendix` 直接发。report 是模型输出，prompt 里写了"不使用 HTML"但无强制。**现在多了一层关注点**：Hermes dashboard 自身的会话/模板是否可能把内容带进报告，确认 Hublog 前端转义与否。

**M4. `clean()` 顺序反了**（`pipeline.py:89`）：先剥标签再 `html.unescape`，`&lt;script&gt;` 剥不掉、unescape 后变成真标签。进的是 prompt 不是发布内容，一行可改。

**M5. `public_get` 只连解析出的第一个地址**（`pipeline.py:59`，字典序最小），无轮换无回退。README 自称"部分来源在国内可能不可达"——那种源会每次记 error，永不尝试其它 A/AAAA 记录。

**M6. oauth2-proxy 用 httpGet 探针，而 `default-deny` 关了全部 Ingress**（`core.yaml:196-204` vs `:517-523`）。dashboard 用 exec 探针（绑 127.0.0.1，免疫），proxy 用 httpGet。**已部署 → 事实上没被拦**，这条可以销案，但它说明这个集群的 CNI 放行 kubelet 探针流量，值得记进 [platform-k8s-conventions.md](platform-k8s-conventions.md)。

## 三、新增：双层认证

`oauth/k8s/HERMES.md` 记录：上游 dashboard 对**公开域名强制原生认证**，不能只靠外层代理。于是形成：

```
Cloudflare → oauth2-proxy（精确邮箱白名单，__Host-hermes）→ Hermes dashboard 原生 OIDC → 应用
```

Casdoor 同一应用登记两个回调：`/oauth2/callback`（外层）与 `/auth/callback`（Hermes 自身）。

**这是对的**，两点值得肯定：

1. **不绕过上游认证**。README 明确写"不要改写 Host/Origin 或关闭检查来绕过原生认证"——面对"上游强制认证导致部署麻烦"这种压力，没有选择关掉它，方向正确。
2. **`WEBSOCKETS_MAX_LINE_LENGTH: '32768'` 加得漂亮**（`oauth/k8s/hermes-proxy-configmap.yaml:11`）。注释写明原因是"OIDC cookies 会超过 websockets 默认 8 KiB 握手行上限"。这是个不实测根本发现不了的坑，说明真跑过。

需要留意的一点：**dashboard 容器现在持有 OIDC 客户端凭据**（`core.yaml:119-128`，从 `hermes-oidc` 注入 `HERMES_DASHBOARD_OIDC_CLIENT_ID/SECRET`）。这是原生 OIDC 的必然代价，且与 `hermes-oidc` 里给外层代理的是**同一个** Casdoor 应用凭据。securityContext 侧 dashboard 仍是 root（见 L1），所以"web 容器持有可完成外层代理流程的凭据"这件事，是在 dashboard 无法降权的前提下接受的。记一笔，等上游支持非 root 启动时再收。

## 四、低危 / 建议（沿用，暂未变动）

**L1. dashboard 容器是真的 root**（`core.yaml:143-155`），`capabilities.add: [CHOWN, FOWNER, DAC_OVERRIDE, SETUID, SETGID]`。README 明确不声称满足 Pod Security restricted、不改成 privileged，态度对。与 oauth2-proxy 同 Pod 共享 netns，是上游 s6 入口的结构性约束。

**L2. Dockerfile 的 `A && B || C` 会掩盖 pip 真实失败**：`pip install` 失败会静默转去 `uv pip install`。建议拆成显式 if/else。

**L3. `publish()` 对 2xx 响应体缺字段无防御**（`pipeline.py:219-220`）：`json.loads(data)["id"]`，结构变化时报 `KeyError`。有幂等键兜底不会重复发文，但错误难懂。

**L4. `Namespace` 被创建两次**（`deploy.sh` 与 `core.yaml:1-4`）。无害。

**L5. `deploy.sh` 只 `kubectl apply`，无 server-side dry-run**。

## 五、部署后新增关注点

### 5.1 节点容量：Hermes 钉在和 ES 同一台

`core.yaml:94,263,344,454` 全部 `kubernetes.io/hostname: orangepi5-max-server1` —— 也就是 ES / PostgreSQL / Redis / embedding-service 所在的那台 8C/15.5G 节点。

加上 Hermes 之后的 **limits 合计**：ES 2C/4Gi + embedding 4C/1Gi + PG 1C/2Gi + Redis 0.5C/1Gi + hermes-web 1C/2Gi + report 1C/2Gi + collect 1C/0.5Gi + publish 1C/0.5Gi ≈ **11.5 核 / 13 GiB**，对一台 8 核 / 15.5 GiB 的机器。

limits 只在争抢时生效，requests 合计约 5.5 GiB 调度上没问题。但**内存余量只剩约 2.5 GiB**，而这台机器还带 RK3588 的 NPU 相关工作。建议：

- 观察 `report`（2Gi limit）与 `hermes-web` 同时活跃时的节点内存
- 如果吃紧，`report` 是更适合下调 limit 的那个（它只在 20:00 跑，且 pipeline 有 `activeDeadlineSeconds: 1200` 兜底）

### 5.2 `HUBLOG_URL` 写死在 ConfigMap，不再是代码默认值

`core.yaml:49` 把 `HUBLOG_URL` 显式写进了 `hermes-runtime`。这本身是好事（可发现、可改），但它也让 H1 变成**纯清单层的不一致**，不再有"也许 env 会覆盖"的可能性。改 NetworkPolicy 时注意 `hermes-runtime` 是被三个 CronJob 共享的 `envFrom`，别顺手改动影响到 collect/report。

## 六、与方案层评审的关系

[hermes-intelligence-review.md](hermes-intelligence-review.md) 里几条针对"现网无先例"的批评已被这份代码解决：

| 方案层评审当时说的 | 现在 |
|---|---|
| 单用户白名单在现网无先例（`--email-domain=*`） | 已用 `authenticated_emails_file` 实现，是仓库首份 |
| 独立 cookie 需覆盖 cookie-name + domain，属新设计 | `cookie_name = "__Host-hermes"` 且不设 domain，`__Host-` 三条约束都满足 |
| MFA 零痕迹 | 交给 Casdoor 侧配置，方向正确 |
| ARM64 前提未验证 | 已部署，且 `build.sh` 会断言 arm64 并固定 digest |

仍未解决的（非代码问题）：

- **H1** —— 启用 publish 前必须处理
- **成本记账**：`MAX_DAILY_ATTEMPTS=2`（`core.yaml:48`）限的是**模型调用次数**，不是金额。README 也承认"Token 轮数限制不等于金额硬上限"，需确保供应商侧真设了每日额度
- **"看到第一份产出"的路径**：三个 CronJob 仍全部 suspend，需先完成验收清单
