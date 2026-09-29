# OAuth 代理合并：八个二级域名共用一个 oauth2-proxy

> **需求（2026-09-28，所有者提出）**：八个人格原本每个二级域名一个 oauth2-proxy，缩成八域名共用一个。
>
> 落地时间线：**2026-09-28 部署共享实例** → **2026-09-29 修正回调生成方式**（`182a78c`）。
> 本文记录**最终落地的形态**；曾经提出但未采用的那套做法见 §六 —— **那段很重要，别误用**。

## 结论摘要（TL;DR）

| | 合并前 | 合并后 |
|---|---|---|
| oauth2-proxy Deployment | 8 | **1**（`oauth2-proxy-baijiazhengming`） |
| oauth2-proxy Pod | 16 | **2** |
| oauth ConfigMap | 8 | **1** |
| Cloudflare Public Hostname | 8 | 8，但 **backend 全部改成指向共享实例** |
| Casdoor 回调 | 8 条 | **仍是 8 条，且都在用**（见 §二） |
| UI / API 代码 | — | **零改动** |

代价：**认证层成为单点**（影响面 1 → 8 个域名）；八个旧代理留着当退路但零流量。

## 一、最终形态

```text
八条 Public Hostname（*-agent.panghuer.top）
  → Cloudflare Tunnel：backend 全部 = oauth2-proxy-baijiazhengming.oauth.svc:4180
  → oauth2-proxy-baijiazhengming（1 个 Deployment，2 副本）
  → baijiazhengming-ui.baijiazhengming.svc:7860
  → baijiazhengming-api
```

部署方式（**只有一个入口**）：

```bash
bash oauth/k8s/deploy-agent-proxy.sh baijiazhengming \
  http://baijiazhengming-ui.baijiazhengming.svc.cluster.local:7860
```

`panghu_agent/baijiazhengming/deploy.sh` 的第 4 步就是这么调的（`3f3fd2d` 起只渲染这一个，
不再循环那八个）。八个旧的 `oauth2-proxy-<slug>-agent` 仍留在 ns `oauth` 里、**零流量**，
作为"回退到单域名"的退路，但**不再由日常部署渲染/重启** —— 之前循环渲染它们，导致真正在用的
共享实例反倒不会被更新（改了 ConfigMap 却不重启它，是个更隐蔽的"改了不生效"）。

## 二、回调怎么生成（本文最关键的一条）

共享实例**不写 `--redirect-url`**，只给 `--whitelist-domain=.panghuer.top`，由 oauth2-proxy
**按请求的 Host 生成回调**。于是：

- 从哪个域名登录，就用那个域名的 `/oauth2/callback`，**跳回原域名**；
- **不存在 canonical 域名**，八条 Casdoor 回调**每条都在用**；
- 实现位置：[`proxy-deployment.yaml`](../oauth/k8s/proxy-deployment.yaml) 把该行抽成占位符
  `__CALLBACK_ARG__`，由 [`deploy-agent-proxy.sh`](../oauth/k8s/deploy-agent-proxy.sh) 按 target 渲染：

| target | 渲染出的参数 |
|---|---|
| `baijiazhengming`（多域名共享实例） | `--whitelist-domain=.panghuer.top` |
| 其余按服务的代理 | `--redirect-url=https://<target>.panghuer.top/oauth2/callback`（与改动前逐字相同） |

> ⚠️ **为什么不能写死**：一个实例服务八个域名时，写死 `--redirect-url` 会让**从其它域名首次登录**
> 的人被绕到被写死的那个域名的回调上（已登录的人无感，因为 cookie 是 `.panghuer.top` 全域的）。
> 2026-09-29 实际踩过这个坑，`182a78c` 就是修它。

## 三、人格怎么选（应用零改动）

| 机制 | 作用 |
|---|---|
| `passHostHeader: true` | 原始 `Host` 透传给 UI → `_resolve()` 继续按域名查 registry 白名单选出人格 |
| `--cookie-domain=.panghuer.top` + 共享 `oauth2-proxy-secret` | 会话跨子域通用 → 在任一域名登录后，访问其余七个**免登录** |
| `injectRequestHeaders`（`X-Forwarded-User`/`Email`/`Preferred-Username`） | 注入的是**登录用户身份**，八个域名完全相同；区分人格的**只有 `Host`** |

## 四、验证清单

1. 八个域名逐个访问，**各显示各自的人格品牌与文案**（这一条同时证明 `Host` 被正确透传）；
2. 从 A 域名登录后直接访问 B 域名 → **免登录**；
3. 从**未登录状态**在不同的域名分别登录 → 都应停在该域名，**不应被绕到别的域名**（§二 的回归点）；
4. `kubectl -n oauth get deploy oauth2-proxy-baijiazhengming` 应为 2/2。

## 五、回滚到单域名：**不再是一条命令**

八个旧代理还在（零流量），但**旧的 api/ui 服务已被 `scripts/retire-legacy-personas.sh` 删除**，
所以回退得先把它们重建起来：

```bash
# 用 scripts/deploy-{api,ui}.sh 重建某个域名的旧服务，再把隧道 backend 指回去
```

（口径见 `panghu_agent` 的 `3f3fd2d` 提交信息。）

## 六、⚠️ 未采用的历史方案（别执行）

2026-09-28 曾提交过**另一套**做法，最终**没有采用**：

| 文件 | 当时的思路 |
|---|---|
| [`shared-agent-proxy.yaml`](../oauth/k8s/shared-agent-proxy.yaml) | 保留 8 个 `<slug>-agent` Service 当"壳"，只改 `selector` 指向共享 Pod，声称"隧道 backend 字符串零改动" |
| [`deploy-shared-agent-proxy.sh`](../oauth/k8s/deploy-shared-agent-proxy.sh) | 上述方案的部署/回滚脚本，并把 `--redirect-url` 写死成一个 canonical 域名 |

**为什么没用**：

1. 实际落地时隧道**改成了直接指向共享实例**，所以根本不需要"壳"Service；
2. 那套把 `--redirect-url` 写死成 canonical —— 正是 `182a78c` 要修的问题。

🔴 **不要执行 `deploy-shared-agent-proxy.sh`**：它与 `deploy-agent-proxy.sh` 渲染的是**同名
Deployment**（`oauth2-proxy-baijiazhengming`），一旦执行就会把线上实例覆盖成**写死回调**的版本，
把 `182a78c` 修好的坑重新挖开。

## 七、当前仍存在的风险

| 风险 | 说明 |
|---|---|
| **认证层单点** | 1 个 Deployment、2 副本；它挂了八个域名一起挂。业务层（UI/API）本来就是共享的，所以没有引入新的**业务**单点 |
| **没有 PodDisruptionBudget** | 未采用的那份清单里带了一个 PDB，因此**线上是否有限制未确认** —— 节点驱逐时可能同时带走两个副本 |
| **八个旧代理零流量但仍在** | 占资源；确认不再需要"单域名回退"后应删除 |

## 八、未验证项（诚实记录）

| 项 | 状态 |
|---|---|
| 隧道 backend 的实际指向 | **未验证**（Cloudflare 后台才是权威来源，operator 那份 YAML 只是备份）。本文依据是 `3f3fd2d` 与 `182a78c` 两条提交信息里的"隧道只喂它"，以及 `deploy-agent-proxy.sh` 的 `baijiazhengming` 特例 |
| 线上是否有 PDB / 副本数 | **未验证**（本机无 kubectl） |
| `--redirect-url` 省略时按 Host 生成回调 | **未在本机验证**；这是 `182a78c` 的既定行为，上线后靠 §四 第 3 条回归 |
