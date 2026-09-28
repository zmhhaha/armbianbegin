# OAuth 代理合并：八个二级域名共用一个 oauth2-proxy

> **需求（2026-09-28，所有者提出）**：八个人格现在是「每个二级域名一个 oauth2-proxy」，
> 想缩成「八个域名共用一个」，**但 Cloudflare 隧道不动**。
>
> 材料：[shared-agent-proxy.yaml](../oauth/k8s/shared-agent-proxy.yaml)（清单）、
> [deploy-shared-agent-proxy.sh](../oauth/k8s/deploy-shared-agent-proxy.sh)（部署/回滚脚本）。
>
> 本文是方案与决策记录，不是实现规格。

## 结论摘要（TL;DR）

**可行，而且隧道、Casdoor、UI/API 代码三者都不用动** —— 只需集群侧的 oauth 资源。

| | 现在 | 合并后 |
|---|---|---|
| oauth2-proxy Deployment | 8 | **1** |
| oauth2-proxy Pod | 16（8 × 2 副本） | **2** |
| oauth ConfigMap | 8 | **1** |
| Cloudflare Public Hostname | 8 | **8（不变）** |
| Casdoor 回调 | 8 | **8（不变，实际只用 1 条）** |
| UI / API 代码 | — | **零改动** |

代价是两条：**认证层变成单点**（影响面从 1 个域名变 8 个），以及 **canonical 回调只能是八个域名之一**（见 §四）。

## 一、为什么"隧道不动"也能合并

四条机制凑在一起，缺任何一条这个方案都不成立：

| 机制 | 作用 |
|---|---|
| **Service 是 label selector 间接层** | 隧道 backend 是 `oauth2-proxy-<slug>-agent.oauth.svc:4180`。**保留这 8 个 Service 名**，只改它们的 `spec.selector` 指向共享 Pod —— 隧道的 backend 字符串一个字都不用改 |
| **`--redirect-url` 只能填一个值** | 用**现有八个域名之一**做 canonical，而 Casdoor 里那条回调**早就注册过**了（八个代理各注册过一条）→ 认证侧零改动 |
| **`--whitelist-domain=.panghuer.top`** | 让登录后能跳回**原始**域名。`--redirect-url` 默认只允许跳回它自己的 host，不配这条就会出现「在 A 域名登录却落在 B 域名」 |
| **`passHostHeader: true` + `--cookie-domain=.panghuer.top`** | 原始 Host 透传给 UI → `_resolve()` 继续有效，**应用零改动**；cookie 跨子域通用 → 用户**不需要重新登录** |

> 注意区分两种头：**区分人格的是 `Host`**（浏览器按域名自动带，八域名八种值）；
> oauth2-proxy 注入的 `X-Forwarded-User` / `X-Forwarded-Email` /
> `X-Forwarded-Preferred-Username` 是**登录用户身份**，八个域名下完全相同，与人无关。

## 二、请求链路（每一跳看到什么）

```text
浏览器      https://daofaziran-agent.panghuer.top/
   │        Host: daofaziran-agent.panghuer.top        ← 浏览器自动带
   ▼
cloudflared 按 hostname 查路由（分流发生在隧道这一层）
   │        同一个 Host 原样转发
   ▼
Service oauth2-proxy-daofaziran-agent.oauth.svc:4180   ← "壳"：只是 DNS 名 + selector
   │        不解析、不改写，纯粹把流量送给同一组 Pod
   ▼
oauth2-proxy（唯一实例）  认证 + 注入三个身份头
   │        Host 原样透传（passHostHeader: true）
   ▼
Service baijiazhengming-ui.baijiazhengming.svc:7860
   ▼
UI 的 _resolve()：先看 X-Forwarded-Host、没有就看 Host
   → 查 registry 的 host 白名单 → 选中对应人格
```

`_resolve()`（`panghu_agent/baijiazhengming/ui.py`）优先取 `X-Forwarded-Host`，而代理并没有
注入它，所以实际生效的是 `Host` —— 链路能走通本身就证明其中一个是对的。

## 三、改了什么、没改什么

**改（都在 `oauth/` 下）**：

1. 新增 ConfigMap `oauth2-proxy-config-baijiazhengming`：单份 alpha-config，upstream 指向共享 UI；
2. 新增 Deployment `oauth2-proxy-baijiazhengming`：2 副本，`--whitelist-domain` 是相对旧模板唯一新增的参数；
3. 新增同名 Service（供直连/排障）与一个 PodDisruptionBudget（`minAvailable: 1`，缓解单点；不需要可删）；
4. **8 个原有 Service 只改 `spec.selector`**（名字、端口、metadata.labels 都不动）。

**不改**：Cloudflare 隧道路由、Casdoor 回调列表、`baijiazhengming` 的 UI/API 代码与清单、
`registry.yaml`、其它代理（research / scientific / game-review / literature-downloader / txt2img）。

## 四、唯一的不对称：canonical 回调

`--redirect-url` 只有一个值，所以必须从八个域名里选一个当 OAuth 往返的中转，默认取
`bingbichunqiu-agent.panghuer.top`（最早迁移、最"中性"的一个）。

- 从**其它七个**域名登录时，会先经 canonical 完成回调，再靠 `--whitelist-domain` 跳回原域名；
- 地址栏会**短暂**出现 canonical 域名（302，用户基本无感），但最终回到原域名；
- 想用一个**专用** canonical 域名（如 `baijiazhengming.panghuer.top`）就得在隧道里加一条路由
  并去 Casdoor 注册回调 —— 那超出了"隧道不动"的约束，属于另一件事。

⚠️ **`--whitelist-domain` 是本方案最容易漏的一条**，症状就是「在 A 登录却落在 B」。

## 五、迁移步骤

```bash
# 0. 先核对隧道 backend（后台才是权威来源，operator 那份 YAML 只是备份）
#    Cloudflare 后台 → 该 tunnel 的 Public Hostname → 八条路由的 backend 应是
#    oauth2-proxy-<slug>-agent.oauth.svc.cluster.local:4180
kubectl get svc -n oauth | grep 'oauth2-proxy-.*-agent'   # 名字要对得上

# 1. 服务端预演（不改任何东西）
bash oauth/k8s/deploy-shared-agent-proxy.sh --dry-run

# 2. 上线：部署共享代理 + 把 8 个 Service 的 selector 指过去；旧代理仍在跑
bash oauth/k8s/deploy-shared-agent-proxy.sh

# 3. 逐个域名验证（见 §六）
# 4. 稳定几天后缩容旧代理
bash oauth/k8s/deploy-shared-agent-proxy.sh --retire-old
```

脚本内置两道前置校验：canonical 必须是那八个域名之一（否则 Casdoor 回调对不上），
以及 8 个"壳"Service 必须已存在（否则说明隧道 backend 的名字与预期不符）。

**新参数与旧模板的全部差异**（便于 review）：

| 参数 | 旧（每域名一个） | 新（共享） |
|---|---|---|
| `--redirect-url` | `https://<target>.panghuer.top/oauth2/callback` | 固定一个 canonical |
| `--whitelist-domain` | 无（默认只允许自己） | `.panghuer.top` |
| upstream `uri` | 已经都指向共享 UI | 不变 |
| 其余 15 个参数 | — | 逐条相同 |

## 六、验证清单

1. 八个域名逐个访问，**各显示各自的人格品牌与文案** —— 这一条同时证明了 Host 被正确透传；
2. 从 A 域名登录后直接访问 B 域名 → **应当免登录**（`cookie-domain=.panghuer.top` 生效）；
3. 登录往返后**回到原来访问的域名**（不回到 canonical）→ 证明 `--whitelist-domain` 生效；
4. `kubectl -n oauth get pods | grep baijiazhengming` 应有 2 个 Running；
5. `kubectl -n oauth get endpoints oauth2-proxy-<slug>-agent` 八个壳都应指向那 2 个 Pod。

## 七、回滚

```bash
bash oauth/k8s/deploy-shared-agent-proxy.sh --rollback
```

它会为八个 target 重跑 `deploy-agent-proxy.sh`（各自的 ConfigMap / Deployment / Service 与
2 副本一起恢复），再把共享代理缩到 0。共享代理的 ConfigMap/Service/PDB 保留不删，便于再切回来。

回滚窗口期：`--retire-old` 之前旧 Pod 一直在跑，`--rollback` 基本是秒级；缩容之后再回滚要等
8 个 Deployment 重新拉起。

## 八、风险与代价

| 风险 | 说明 | 缓解 |
|---|---|---|
| **认证层单点** | 影响面从 1 个域名变成 8 个 | 2 副本 + PDB；业务层（UI/API）本来就是共享的，没有引入新的业务单点 |
| **canonical 不对称** | 七个人格域名的登录回跳经 canonical | 仅影响地址栏瞬时显示；`--whitelist-domain` 保证跳回原域名 |
| **`--whitelist-domain` 漏配** | 「在 A 登录却落在 B」 | §六 第 3 条专门验它 |
| **误伤其它代理** | `deploy-agent-proxy.sh` 是通用脚本，还服务 research / scientific / game-review / literature-downloader / txt2img | 本方案只动八个人格那 8 个 Service 与新增的共享代理，脚本里 `AGENTS` 数组限定范围 |
| **隧道与 YAML 不一致** | 后台改了但 `tunnel-routes.yaml` 没同步（踩过） | 本方案**不需要**改路由，反而少一处不一致的来源 |

## 九、未在本机验证的部分（诚实记录）

| 项 | 状态 |
|---|---|
| 清单 YAML 合法性 | ✅ 本机用 PyYAML 解析校验（12 个文档；8 个壳的名字与 selector 逐个断言） |
| 脚本语法与参数守卫 | ✅ `bash -n` 通过；非法 canonical、未知参数两条路径已实测 |
| **集群路径（apply / scale / rollback）** | ❌ **本机没有 kubectl，无法实跑** —— 需在有 kubectl 的机器上先跑 `--dry-run` |
| **`passHostHeader` 是否被 oauth2-proxy v7.8.0 的 alpha-config 支持** | ⚠️ **未验证**（镜像拉不到）。但**不影响方案成立**：共享代理的配置与拆分时逐条相同，承载域名的头（`Host` 或 `X-Forwarded-Host`）行为一致，只是实例数从 8 变 1。§六 第 1 条会顺带验出来 |
| 八个域名的端到端登录 | ❌ 需在集群侧按 §六 执行 |

## 附：如果哪天要连隧道也缩成一个域名

那时的形态是「一个域名 + 路径分段（`/daofaziran`）」，需要**同时**动三处：
Cloudflare 路由与 301 跳转、Casdoor 回调、以及 UI 的 `_resolve()`（Host 不再能区分人格）。
那是另一个方案，与本篇互不替代。
