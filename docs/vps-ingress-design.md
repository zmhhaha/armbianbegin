# 国内 VPS 入口（替代 Cloudflare Tunnel 的直连方案）设计文档

> 记录时间：2026-10-07
> 涉及：腾讯云轻量 `62.234.50.20`（Ubuntu）、家里 k8s 集群、Cloudflare（`panghuer.top`）
> 状态：**阶段 1/2 已就绪，卡在 VPS 侧端口未放行**（见文末"当前进度"）

---

## 0. 一句话总结

把"外网访问家里服务"的入口从 **Cloudflare（美国边缘 ✗）** 换成 **自己买的国内 VPS**，
让手机（联通/移动）和所有外网用户走 **国内线路** 直达，延迟从**秒级降到几十毫秒**；
并且做成**可无限加服务**的结构——以后新增一个站点只要改两处（一条隧道配置 + 一条 DNS）。

---

## 1. 问题：现在为什么这么慢

### 1.1 现在的路径

```
手机/电脑 ──► 家里路由器(Clash 透明代理) ──► Cloudflare 边缘(美国 DFW/SEA ✗)
                                                     │
                                                     ▼
                                           Cloudflare Tunnel
                                                     │
                                                     ▼
                            家里 k8s 里的 cloudflared pods ──► 各服务
```

### 1.2 实测数据（2026-10-07）

| 目标 | 实测 | 说明 |
|---|---|---|
| 应用自身（容器内直连 DSH 的 3080） | **9–11 ms** ✓ | **服务本身一点都不慢** |
| 服务器 → baidu.com | ttfb **0.090 s** ✓ | 家宽出口带宽正常 |
| 服务器 → github.com（走代理 ✓） | tls 0.30 s / ttfb **0.49 s** ✓ | 走代理反而快 |
| `dsh.panghuer.top`（直连真实 CF IP ✗） | tls **1.6 / 3.2 / 3.3 / 12.8 s**，ttfb **1.5 / 2.6 / 16.3 / 19.4 s** | ✗✗ 秒级，还超时 |
| 隧道自身 → 自己的公网地址 | **10.5 s 超时** / 3.1 s / 0.34 s | ✗ 隧道那一腿也慢 |
| `cf-ray` 响应头（落哪个边缘） | **-DFW（达拉斯）/ -SEA（西雅图）** | ✗ 被甩到美国 |

### 1.3 根因（两层，都要解决）

1. **Cloudflare 在中国大陆没有免费节点** ✗
   China Network 需要**企业版 + 域名备案**；免费/普通套餐的流量会走到**境外边缘**，
   叠加联通/移动国际出口的拥塞与 QoS → 秒级延迟、偶发超时。
2. **更要命的是：源站在你家里** ✗
   每个请求都要 `用户 → CF 边缘(美国) → 隧道 → 你家 → 再原路返回`，
   **CDN 缓存完全帮不上忙**（DSH 是动态应用 + WebSocket）。
   所以即使 CF 在国内有节点，也得跨两次国境。

> 附带发现：家里路由器的 Clash 会**透明代理所有设备的出站连接**（DNS 返回 `198.18.x.x` fake-IP ✓），
> 连"直连真实 CF IP"也会被路由器本地接走（实测 `connect 0.000936s` ✗）。
> **后果：在家里做的任何端口/延迟测试都不可信**，判据必须在 VPS 上执行。

---

## 2. 目标

| 目标 | 判据 |
|---|---|
| 联通/移动用户直连，延迟可用 | 首字节 **< 100 ms**（现在是 1.5–19 s ✗） |
| 支持**多个**服务（现在 35+ 域名，以后还会加） | 新增服务 **≤ 3 步**，不动 nginx/证书 |
| WebSocket 正常（DSH 界面依赖） | 连续操作数分钟不断线 |
| 登录链路不变（oauth2-proxy + Casdoor） | 回调成功，无需改应用配置 |
| 可回滚 | 任何一步失败都能在 **1 分钟**内退回现状 |
| 合规 | 域名 + 80/443 在**腾讯云**侧完成 ICP 备案 |

---

## 3. 目标架构

```
   手机 / 外网用户（联通·移动·电信）
        │  HTTPS 443（域名：xxx.panghuer.top）
        ▼
┌─────────────────────────────────────────────────────────────┐
│  腾讯云轻量 VPS  62.234.50.20   （备案挂在这台机器上）        │
│                                                             │
│   nginx ── 443，通配符证书 *.panghuer.top                    │
│     │        只有一个 server 块：                            │
│     │        proxy_pass http://127.0.0.1:8080（保留 Host）    │
│     ▼                                                        │
│   frps ── bindPort 7000（认证 token + TLS）                  │
│           vhostHTTPPort 8080 ← 按 Host 自动分流到各服务       │
│           proxyBindAddr 127.0.0.1 ← 公网唯一入口只有 nginx   │
└─────────────────────────────────────────────────────────────┘
        ▲
        │  一条 frp 隧道（家里**主动往外连** ✓ 不需要公网 IP、不用开入站端口）
        │
┌───────┴─────────────────────────────────────────────────────┐
│  家里 k8s 集群（namespace: dsh）                             │
│                                                             │
│   Deployment frpc（1 副本，非 root、只读根、drop ALL）        │
│     ├─ proxy "dsh-web"     → dsh-web.dsh.svc:4180            │
│     ├─ proxy "hermes-web"  → hermes-web.hermes.svc:4180      │
│     └─ proxy "……"          → 以后每加一个服务加一条           │
│                                                             │
│   NetworkPolicy：frpc-egress（能出去）+ 各目标命名空间的      │
│                  frpc-ingress（允许 frpc 进来）              │
└─────────────────────────────────────────────────────────────┘
```

### 一次请求的完整旅程（目标态）

```
① 手机解析 xxx.panghuer.top      → VPS IP（Cloudflare 里一条 A 记录，DNS only ✓）
② 手机 → VPS:443                 → 国内线路，20–40 ms ✓
③ nginx 终止 TLS（通配符证书）    → 带 X-Forwarded-Proto: https 转发到 127.0.0.1:8080
④ frps 按 Host 找对应 proxy      → 通过已有隧道把请求送给家里的 frpc
⑤ frpc 转发到服务 ClusterIP       → dsh-web:4180（oauth2-proxy）
⑥ 响应原路返回
```

**全程不出国** ✓（预估端到端 **20–60 ms**，届时实测）。

---

## 4. 关键设计决策（为什么这么做）

### 4.1 为什么用 frp，而不是 WireGuard？

| | frp（本方案 ✓） | WireGuard |
|---|---|---|
| 家里那侧 | **一个普通 Pod** ✓ 用户态、纯出站、不需要特权 ✓ | 需要 NET_ADMIN 特权 Pod 或改宿主机 ✗ |
| 与现有安全策略 | 契合（NetworkPolicy 逐条放行 ✓） | 要额外处理路由与策略 ✗ |
| 加服务 | 加一条配置 ✓ | 加一条 nginx 配置 ✓ |

结论：**frp 作为主方案** ✓；WireGuard 留作以后"个人设备 VPN 直连家里"的备选 ✓（两者不冲突）。

### 4.2 为什么用 frp 的 HTTP vhost 模式，而不是"一服务一端口"？

你现在有 **35+ 个公开域名**（全部记在 `cloudflare-tunnel/operator/*.yaml` ✓）。
一服务一端口意味着：每个服务要分配端口 + 一条 DNS + 一份证书条目 ✗ → 不可持续。

HTTP vhost 模式：所有域名**共用 frps 的 8080 端口**，按 `Host` 头自动分流 ✓✓。

### 4.3 为什么用一张通配符证书？

`*.panghuer.top` 的 Let's Encrypt 通配符证书（DNS-01，走 Cloudflare API 自动续期 ✓）
**一次覆盖全部子域** ✓ → 以后加服务**不用再签证书、不用改 nginx** ✓✓。

### 4.4 为什么 `proxyBindAddr = 127.0.0.1`？

让 frps 的所有代理端口**只绑本机** ✓ —— 公网唯一入口只有 nginx 的 443 ✓，
隧道端口（18080/8080…）在外面完全不可见 ✓（少一个攻击面）。

### 4.5 为什么 Target 命名空间要加一条 NetworkPolicy？

你的集群是 **default-deny** ✓：每个命名空间只放行"隧道入口"的 Pod。
现有惯例是各命名空间的 `tunnel-ingress` 放行 **Cloudflare 的 cloudflared Pod** ✓
（例：`hermes/tunnel-ingress` → `app=cloudflared, tunnel=main` → 端口 4180）。
所以新入口必须**照同样的写法**再加一条 `frpc-ingress`（放行 `dsh/app=frpc`）✓ —— 这是**每个命名空间一次性**的工作。

### 4.6 备案与 80/443

- 备案绑定的是**域名 + 接入商**；你家宽带**不能备案** ✗（运营商不提供接入、家宽 80/443 被封），
  但**源站在家里不需要备案** ✓ —— 备案是给**腾讯云这台 VPS** 的 ✓。
- **审核期间 80/443 不能用** ✗（腾讯云会拦截）→ 所以先在 8080/18080 上把链路跑通 ✓，
  备案通过后再签证书、开 443 ✓。
- 你的域名条件已经满足 ✓：注册商是**阿里云**（工信部批准 ✓）、有效期到 2036 ✓、NS 在 Cloudflare（不影响备案 ✓）。

---

### 4.7 安全模型：知道 IP 和端口 ≠ 能进来

| 层 | 保护什么 | 强度 |
|---|---|---|
| **`auth.token`** | 谁能向 frps **注册代理** | **192 位随机**（48 位十六进制）。没有 token，攻击者**注册不了任何代理** ✗ |
| `transport.tls` | 隧道内容加密 | TLS ✓（默认**不校验服务端证书** ✗，见下面的加固项） |
| 端口本身 | —— | 知道 `62.234.50.20:7000` **不能登录** ✗，最多是"敲门" |

**公网暴露面只有两个**：

```
7000/tcp      隧道控制端口 —— 唯一对公网开放的隧道端口，token 保护 ✓
443/tcp       nginx —— 唯一的服务入口 ✓；后面每个服务仍用它自己的登录
              （oauth2-proxy + Casdoor + 邮箱白名单 ✓）→ 从 CF 迁到 VPS **不降低认证强度** ✓
──────────────────────────────────────────────────────────────
8080 / 18080+ 被 proxyBindAddr 钉在 127.0.0.1 ✓ → 公网连连接都建立不了 ✓
```

**攻击者实际能做的**：对 7000 刷连接（DoS ✗）—— 任何公网端口都有这个通用风险。
缓解手段：`fail2ban` ✓、把 `bindPort` 换成高位随机端口 ✓。

**可选加固**（按需要选）：

1. `bindPort` 改为高位随机端口（减少扫描噪声）；
2. 安装 `fail2ban`；
3. 让客户端**校验服务端证书**（frp 的 `transport.tls` 系参数；采用前按 0.71 文档确认参数名与用法）；
4. 若想彻底"零监听服务端口"：改用 **WireGuard**（UDP + Curve25519 认证，VPS 上不存在可被扫描的服务端口 ✓✓）——
   代价是家里要引入特权 Pod 或改宿主机 ✗，见 §4.1 的对比。

**凭据卫生（重要）**：

- token 只存在于两处：集群 Secret `frpc-config` ✓、服务器 `/root/frp-token.txt`（权限 600 ✓）；
- **绝不写进 git** ✗ —— 本文档中的 token 一律是占位符；
- 取用方式：
  ```bash
  kubectl -n dsh get secret frpc-config -o jsonpath='{.data.frpc\.toml}' | base64 -d | grep '^auth.token' | cut -d'"' -f2
  ```
- 怀疑泄露时的轮换步骤：重新生成 → 更新 Secret → `kubectl -n dsh rollout restart deployment/frpc`
  → 同步更新 VPS 的 `/etc/frp/frps.toml` → `sudo systemctl restart frps` ✓

## 5. 组件清单

| 位置 | 组件 | 作用 | 状态 |
|---|---|---|---|
| VPS | `frps` + systemd | 隧道服务端、按 Host 分流 | ⏳ 待确认（端口未通） |
| VPS | `nginx` | 终止 TLS、唯一公网入口 | ⏳ 备案后 |
| VPS | `certbot` + Cloudflare DNS 插件 | 自动签发/续期 `*.panghuer.top` | ⏳ 备案后 |
| k8s `dsh` | Deployment `frpc` | 隧道客户端（出站） | ✅ 已部署 |
| k8s `dsh` | Secret `frpc-config` | 隧道配置（含 token） | ✅ 已部署 |
| k8s `dsh` | NetworkPolicy `frpc-egress` | 让 frpc 能出去（VPS:7000 + DNS + 各服务端口） | ✅ 已部署 |
| k8s `dsh` | NetworkPolicy `frpc-web-ingress` | 允许 frpc 进 dsh-web:4180 | ✅ 已部署 |
| k8s `hermes` | NetworkPolicy `frpc-ingress` | 允许 frpc 进 hermes-web:4180 | ✅ 已部署 |
| Cloudflare | 每条域名的 A 记录 | 指向 VPS IP（DNS only） | ⏳ 备案后逐条切换 |

**集群侧已部署的 frpc 关键配置**（`Secret frpc-config` → `/etc/frp/frpc.toml`）：

```toml
serverAddr = "62.234.50.20"
serverPort = 7000
auth.method = "token"
auth.token = "<48 位随机 token，见集群 Secret>"
transport.tls.enable = true
loginFailExit = false          # ★ 必须：否则首次连不上就退出 → k8s 里变 CrashLoopBackOff
log.to = "console"

# ── 目标态用 HTTP vhost 模式；下面两条现在写成 TCP，切模式时改 type/customDomains ──
[[proxies]]
name = "dsh-web"
type = "http"                       # 现在: tcp + remotePort=18080
customDomains = ["dsh.panghuer.top"]
localIP = "dsh-web.dsh.svc.cluster.local"
localPort = 4180

[[proxies]]
name = "hermes-web"
type = "http"                       # 现在: tcp + remotePort=18081
customDomains = ["hermes.panghuer.top"]
localIP = "hermes-web.hermes.svc.cluster.local"
localPort = 4180
```

**部署 frpc 时踩过、必须记住的两个坑**：

1. `loginFailExit = false` ✗→✓ —— frp 默认首次登录失败就**退出**，在 k8s 里表现为
   `CrashLoopBackOff`（日志原话：*With loginFailExit enabled, no additional retries will be attempted*）。
2. `strategy: Recreate` ✗→✓ —— `dsh` 命名空间的配额 `dsh-web-budget` 只允许 **2 个 Pod**；
   RollingUpdate 需要"旧 Pod + 新 Pod"同时存在 → **死锁**（`FailedCreate: exceeded quota`）。
   frpc 用掉的就是那个预留的空位。

---

## 6. 实施阶段

| 阶段 | 内容 | 判据 | 状态 |
|---|---|---|---|
| **0** | 提交 ICP 备案（腾讯云控制台） | 受理 | ✅ 已提交，等管局 1–3 周 |
| **1** | VPS：装 frps、注册 systemd | `systemctl is-active frps` + `ss -ltnp \| grep 7000` | ⏳ 待确认 |
| **2** | 家里 k8s：frpc + 策略 | Pod `1/1 Running`；frps 日志出现 `login to server success` | ✅ 已部署（等 1 完成才通） |
| **3** | VPS：nginx + 通配符证书 | `curl -k https://127.0.0.1 -H 'Host: dsh.panghuer.top'` 返回 302 | ⏳ 备案后 |
| **4** | Cloudflare：逐条改 A 记录（DNS only → VPS IP） | 手机访问 `https://dsh.panghuer.top` 正常登录 | ⏳ 备案后 |
| **5** | 验证 | 联通/移动各测一次；连续操作数分钟不断线 | ⏳ |

**阶段 1/2 的脚本已经纳入仓库** ✓ —— 见 [`../vps/install.sh`](../vps/install.sh) 与 [`../vps/README.md`](../vps/README.md)（幂等、可重跑、不含任何密钥）：

```bash
git clone <本仓库> && cd armbianbegin/vps
sudo bash install.sh stage1     # 装 frps（备案审核期间就能跑 ✓，不碰 80/443）
sudo bash install.sh stage2     # 装 nginx + 申请通配符证书 + 启用站点（备案通过后 ✓）
```

下面这段内联脚本**仅作历史留档**，实际执行请以 `vps/install.sh` 为准 ✓。

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
FRP_VER="0.71.0"
# token 绝不写进 git ✓ —— 用下面这条命令从集群里取：
#   kubectl -n dsh get secret frpc-config -o jsonpath='{.data.frpc\.toml}' | base64 -d | grep '^auth.token' | cut -d'"' -f2
# （服务器上也有 root-only 的副本：/root/frp-token.txt，权限 600）
TOKEN="在此填入取到的 48 位十六进制 token"

case "$(uname -m)" in
  x86_64|amd64) FRP_ARCH=amd64 ;;
  aarch64|arm64) FRP_ARCH=arm64 ;;
  *) echo "不支持的架构: $(uname -m)"; exit 1 ;;
esac

TMP=$(mktemp -d)
curl -fL "https://github.com/fatedier/frp/releases/download/v${FRP_VER}/frp_${FRP_VER}_linux_${FRP_ARCH}.tar.gz" -o "$TMP/frp.tgz"
tar -xzf "$TMP/frp.tgz" -C "$TMP"
sudo install -m 0755 "$TMP/frp_${FRP_VER}_linux_${FRP_ARCH}/frps" /usr/local/bin/frps
sudo mkdir -p /etc/frp

sudo tee /etc/frp/frps.toml >/dev/null <<EOF
bindPort = 7000

auth.method = "token"
auth.token = "${TOKEN}"

transport.tls.force = true

# 只允许这段端口做 TCP 代理（HTTP vhost 模式不需要端口）
allowPorts = [{ start = 18080, end = 18100 }]

# HTTP vhost：所有域名共用一个端口，按 Host 分流
vhostHTTPPort = 8080

# 加固：代理端口只绑本机，公网唯一入口是 nginx
proxyBindAddr = "127.0.0.1"

log.to = "console"
log.level = "info"
EOF

sudo tee /etc/systemd/system/frps.service >/dev/null <<'EOF'
[Unit]
Description=frp server
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=always
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now frps
sleep 2

sudo systemctl is-active frps >/dev/null && echo "frps: active ✓" || { sudo journalctl -u frps -n 30 --no-pager; exit 1; }
ss -ltnp | grep -q ':7000' && echo "监听 7000 ✓"
if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q active; then sudo ufw allow 7000/tcp; fi
```

> ⚠️ **同时在腾讯云控制台放行** `TCP 7000`（轻量应用服务器 → 防火墙）。
> 备案通过后还要放行 `80`、`443`（`8080` 与 `18080` 段**不要**放行 ✓ 它们只走本机）。

---

## 7. 以后新增一个服务（标准动作）

以新增 `foo.panghuer.top` 为例（假设它跑在 namespace `foo`，Service `foo-web`，端口 4180）：

**① 隧道加一条**（改 Secret，加一段 `[[proxies]]`）

```toml
[[proxies]]
name = "foo-web"
type = "http"
customDomains = ["foo.panghuer.top"]
localIP = "foo-web.foo.svc.cluster.local"
localPort = 4180
```

```bash
# 应用并重载
kubectl -n dsh create secret generic frpc-config --from-file=frpc.toml=./frpc.toml \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n dsh rollout restart deployment/frpc      # Recreate 策略，秒级
```

**② 让那个命名空间接受 frpc**（一次性；照它现有 `tunnel-ingress` 的 podSelector 写）

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: frpc-ingress
  namespace: foo
spec:
  podSelector:
    matchLabels:
      role: web            # ← 用该命名空间现有 tunnel-ingress 里的同一个选择器
  policyTypes: ["Ingress"]
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: dsh
      podSelector:
        matchLabels:
          app: frpc
    ports:
    - port: 4180
      protocol: TCP
```

**③ Cloudflare 加一条 DNS**

```
类型 A   名称 foo   内容 62.234.50.20   代理状态：DNS only（灰云）
```

**完成** ✓ —— nginx、证书、端口都不用动 ✓。

> 若新服务是非 HTTP（SSH、数据库…），改用 TCP 模式：
> `type = "tcp"` + `remotePort = 1809x`（落在 `allowPorts` 段内）+ nginx 里加 `stream` 转发 ✓。

---

## 8. 回滚手册（按层）

| 层级 | 回滚动作 | 生效时间 |
|---|---|---|
| 单条域名（最常用 ✓） | Cloudflare 把该 A 记录改回 **CNAME → `<uuid>.cfargotunnel.com` + 橙色云** | 秒级（DNS TTL） |
| 全部域名 | 同上，逐条改回 | 分钟级 |
| k8s 侧隧道 | `kubectl -n dsh delete deploy/frpc secret/frpc-config netpol/frpc-egress netpol/frpc-web-ingress`（+ 各命名空间的 `frpc-ingress`） | 秒级 |
| VPS 侧 | `sudo systemctl disable --now frps`（nginx 同理） | 秒级 |

**关键点**：CF Tunnel 与 Cloudflare zone **始终保持原样** ✓ —— 切换只在 DNS 记录这一层 ✓，
所以回滚永远不会牵动应用、证书或集群里的东西 ✓。

---

## 9. 已知限制与风险

| 项 | 说明 | 对策 |
|---|---|---|
| **家宽上行**是回程瓶颈 ✗ | "给别人访问"时所有数据都从你家上传 | 部署后实测上行；不够就限制并发或把静态内容放 VPS |
| **VPS 是单点** | 这台挂了 → 外网入口断（CF 已被 DNS 绕开 ✗） | 记录回滚步骤（第 8 节）；必要时再买一台做备用 |
| 本地测不准 ✗ | 家里路由器 Clash 透明代理 → 任何端口/延迟测试都失真 | **判据一律在 VPS 上执行** |
| 备案期间不能开 443 ✗ | 腾讯云拦截未备案域名的 80/443 | 先在 8080/18080 验证链路；备案后再开 |
| 35 条 DNS 逐条切换 | 工作量大 | 可脚本化（Cloudflare API）；先切 dsh + hermes 试水 |
| `dsh` 命名空间配额 = 2 Pod ✗ | frpc 用掉了预留位；再加边车会再次 `FailedCreate` | 需要时提配额（`dsh-web-budget`） |
| frp 隧道层加密 | `transport.tls` 用自签证书，仅保护隧道层 | 公网侧由 nginx 的 LE 证书保护 ✓ |

---

## 10. 当前进度与下一步

### 已完成 ✅

- 家里 k8s：`frpc` Deployment（Recreate 策略、非 root、只读根、drop ALL）+ `frpc-config` Secret
  + `frpc-egress` / `frpc-web-ingress` / `hermes/frpc-ingress` 三条策略
- 两条代理：`dsh-web → 4180`、`hermes-web → 4180`
- 镜像 `arm-cluster-master:5000/frpc:v0.71.0` 已推入本地 registry

### 卡在这里 ⏳

frpc 日志持续报：

```
connect to server error: session shutdown
```

说明**还没连上 VPS**。请在 VPS 上确认：

```bash
systemctl is-active frps                # 应为 active
sudo ss -ltnp | grep ':7000'            # 应看到 frps 监听
sudo journalctl -u frps -n 20 --no-pager
```

并确认**腾讯云控制台防火墙已放行 TCP 7000** ✓（最常见的原因 ✗）。
一旦通，frpc 日志会出现 `login to server success`，随后 VPS 上
`curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/ -H 'Host: dsh.panghuer.top'`
应返回 **302**（DSH 的登录跳转 ✓）。

### 待办（备案通过后）

1. VPS：`apt install nginx certbot python3-certbot-dns-cloudflare` → 通配符证书 → 单一 server 块
2. frpc 两条代理从 `tcp` 改成 `http` + `customDomains`
3. Cloudflare 逐条改 A 记录（先 `dsh` + `hermes`）
4. 联通/移动各测一次 + WebSocket 连续操作验证

---

## 附录 A：命令速查

```bash
# —— VPS ——
systemctl status frps --no-pager
sudo journalctl -u frps -f
ss -ltnp | grep -E ':(7000|8080)'

# —— 家里 k8s ——
kubectl -n dsh get pod -l app=frpc -o wide
kubectl -n dsh logs -l app=frpc -c frpc --tail=20 -f
kubectl -n dsh get secret frpc-config -o jsonpath='{.data.frpc\.toml}' | base64 -d
kubectl get pods -A -l role=web            # 现在能走隧道的服务

# —— 端到端（在 VPS 上执行！家里测不准 ✗）——
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/ -H 'Host: dsh.panghuer.top'
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/ -H 'Host: hermes.panghuer.top'
```

## 附录 B：实测数据留档（2026-10-07）

```
应用自身（容器内）          9–11 ms      ✓
服务器 → baidu               90 ms        ✓
服务器 → github（走代理）     490 ms       ✓
服务器 → CF 真实 IP（直连）   1.5–19.4 s   ✗（含超时）
隧道 → 自公网地址            0.34–10.5 s  ✗
cf-ray                       -DFW / -SEA  ✗（美国边缘）
VPS 22 端口（本机直连）       72 ms        ✓（唯一可信的家测结果）
其余端口（本机测试）          0 ms         ✗ 被 Clash 本地接走，无效
```
