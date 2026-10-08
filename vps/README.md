# vps/ —— 国内 VPS 入口机（边缘网关）

> 设计文档：[../docs/vps-ingress-design.md](../docs/vps-ingress-design.md)（为什么这么做、架构图、请求旅程、实测数据）
> 机器：腾讯云轻量 `62.234.50.20`（Ubuntu）· 记录时间：2026-10-07

## 一、它是什么，不是什么

```
公网用户 ──443──► 本机（nginx + frps）══ frp 隧道（集群主动出站 ✓）══► 家里 k8s 里的 frpc → 各服务
```

- **是**：一台边缘网关。跑 `frps`（隧道服务端）+ `nginx`（TLS 终止、唯一公网入口）+ `certbot`（通配符证书）。
- **不是**：**不加入 k8s 集群** ✓ —— 没有 kubelet、不是节点、不碰 Ceph/Calico（跨公网的节点会带来流量费用、网络平面分裂与攻击面问题，见设计文档 §4）。

本目录是这台机器的**唯一事实来源** ✓：换机器时 `git clone` + `bash install.sh` 即可重建。

## 二、前置条件

| 项 | 说明 |
|---|---|
| 腾讯云**控制台防火墙** | stage1 放行 `TCP 7000`；stage2 再放行 `TCP 80`、`TCP 443`。⚠️ **控制台防火墙与系统 ufw 是两套东西**，只开 ufw 没用 ✗ |
| ICP 备案 | 80/443 需要备案通过（stage2 之前必须完成）。stage1 不需要 ✓ |
| 集群侧 | `frpc` Deployment + Secret `frpc-config`（已部署 ✓，见设计文档 §5） |
| Cloudflare API Token | 仅 stage2 需要：`Zone → DNS → Edit` 权限（用于 DNS-01 签通配符证书） |

## 三、部署

```bash
git clone <本仓库> && cd armbianbegin/vps

# 阶段 1：frps（备案审核期间就能跑 ✓，不涉及 80/443）
#   token 从集群 Secret 取（在你家里那台执行取，再粘到 VPS 上）：
#     kubectl -n dsh get secret frpc-config -o jsonpath='{.data.frpc\.toml}' | base64 -d | grep '^auth.token' | cut -d'"' -f2
sudo bash install.sh stage1
#   脚本会安全提示输入 FRP_TOKEN（不进 shell 历史 ✓）

# 阶段 2：nginx + 通配符证书 + 站点（备案通过、80/443 放行后）
sudo bash install.sh stage2
```

**判据**：

```bash
systemctl is-active frps && ss -ltnp | grep ':7000'      # stage1 通过
sudo journalctl -u frps -f                                # 家里 frpc 连上来后会看到登录成功
curl -sk -o /dev/null -w '%{http_code}\n' -H 'Host: dsh.panghuer.top' https://127.0.0.1/   # 302 = 通了 ✓
```

## 四、日常运维

```bash
systemctl status frps nginx --no-pager
journalctl -u frps -n 50 --no-pager          # 隧道日志
tail -f /var/log/nginx/error.log
nginx -t                                     # 改配置后先校验
```

**改配置**：改本目录里的模板 → 重新 `git pull` → 再跑一次对应的 `install.sh` 阶段（幂等 ✓，配置没变就不重启 ✓）。

**换 token**（怀疑泄露时）：

```bash
# 1) 集群侧：更新 Secret 里的 auth.token（改 frpc.toml 后 apply）
# 2) 集群侧：kubectl -n dsh rollout restart deployment/frpc
# 3) VPS：sudo FRP_TOKEN='<新 token>' bash install.sh stage1
```

**新增一个对外域名**：**不需要动本机** ✓ —— 只要在集群的 `frpc` 配置里加一条 `[[proxies]]`，
再到 Cloudflare 加一条 A 记录（DNS only → 本机 IP）✓。通配符证书与 nginx 配置都无需改 ✓。

**证书**：`certbot.timer` 自动续期 ✓。手动检查：

```bash
systemctl list-timers | grep certbot
certbot renew --dry-run
```

## 五、排错对照表

| 现象 | 原因 | 处理 |
|---|---|---|
| frpc 一直 `session shutdown` / 连不上 | 控制台防火墙没放行 7000 ✗ | 控制台 → 防火墙 → 加 `TCP 7000` |
| `frps` 起不来 | token 里的字符或模板渲染问题 | `journalctl -u frps -n 40` 看报错 |
| nginx 502 / 404 | frps 没起，或对应域名没有 `[[proxies]]` | `curl -H 'Host: 域名' http://127.0.0.1:8080/` 在**本机**测（外面测不准 ✗） |
| 浏览器**无限重定向** ✗ | 缺 `X-Forwarded-Proto: https` | 检查 `nginx/default.conf.template` 是否被改坏 |
| 页面能开但**操作卡死** ✗ | WebSocket 头丢失 | 同上，检查 `Upgrade` / `Connection` 两行 |
| 外面测端口"都开着"却连不上 | 家里路由器 Clash 透明代理接了连接 ✗ | 一律**在本机**用 `curl` 判定 ✓ |
| `toml: invalid character in comment` ✗ | frp 的 TOML 解析器**不接受注释里的非 ASCII 字符** ✗ | `frps.toml.template` 必须保持**纯 ASCII**；中文说明写在本文件 ✓ |
| `toml: invalid character at start of key: ï` ✗ | 模板带了 UTF-8 **BOM**（PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写 BOM ✗） | 脚本渲染时会剥掉 BOM 与 CR ✓；改模板请用不带 BOM 的编辑器 ✓ |
| `open /etc/frp/frps.toml: permission denied` ✗ | 调用者 umask 077 → `/etc/frp` 变成 0700 ✗ | 脚本已显式 `umask 022` + `install -d -m 0755` ✓ |
| 下载 frps 卡住 / `curl: (56) unexpected eof` ✗ | 国内直连 GitHub release 资源被掐断 ✗ | 脚本会依次尝试官方源与两个代理 ✓；或用 `FRP_TARBALL_URL` 指定镜像 ✓ |

## 六、回滚

| 层级 | 动作 |
|---|---|
| 单条域名 | Cloudflare 把该 A 记录改回 `CNAME → <uuid>.cfargotunnel.com` + 橙色云（秒级 ✓） |
| 本机入口 | `sudo systemctl disable --now nginx frps` |
| 彻底移除 | 卸载 nginx/frps，或直接销毁这台轻量实例（集群侧 `frpc` 不受影响 ✓） |

**关键**：Cloudflare zone 与 Tunnel **始终保持原样** ✓，切换只发生在 DNS 记录这一层 ✓ —— 回滚永远不会牵动应用或集群 ✓。

## 七、安全注意

- **token 不进 git** ✗ —— 本目录里的模板只有 `${FRP_TOKEN}` 占位符 ✓；取值方式见第三节。
- **公网只暴露两个端口**：`7000`（token 保护 ✓）与 `443`（nginx）✓。
  `8080` 与 `18080+` 被 `proxyBindAddr = "127.0.0.1"` 钉在本机 ✓，外面连不上 ✓。
- 各服务**自己的登录不因此改变** ✓（oauth2-proxy + Casdoor + 邮箱白名单）—— 迁移不降低认证强度 ✓。
- `frps` 以专用用户 `frp` 运行 ✓（非 root、无 capability、系统盘只读）。
- 可选的进一步加固：客户端校验服务端证书、`fail2ban`、把 `bindPort` 换成高位端口 —— 见设计文档 §4.7。

## 把 frpc 加回集群（集群重装后）

`frpc` 的 Deployment 与两条 NetworkPolicy 现在就在 `k8s/frpc.yaml` 里（**不**由 dsh/deploy.sh 应用 ✗），
但 **Secret `frpc-config`（含隧道 token）不在 git 里** ✗，需要单独创建：

```bash
# 1) 准备 token：可以沿用现成的（如果还有），也可以重新生成一把并同时更新 VPS 上的 frps ✓
TOKEN=$(openssl rand -hex 24)

# 2) 写 frpc.toml（注意：loginFailExit = false 是必须的 ✗→✓，否则 k8s 里会 CrashLoopBackOff）
kubectl -n dsh create secret generic frpc-config --from-file=frpc.toml=/dev/stdin <<EOF
serverAddr = "62.234.50.20"
serverPort = 7000
auth.method = "token"
auth.token = "${TOKEN}"
transport.tls.enable = true
loginFailExit = false
log.to = "console"
log.level = "info"

[[proxies]]
name = "dsh-web"
type = "http"
customDomains = ["dsh.panghuer.top"]
localIP = "dsh-web.dsh.svc.cluster.local"
localPort = 4180

[[proxies]]
name = "hermes-web"
type = "http"
customDomains = ["hermes.panghuer.top"]
localIP = "hermes-web.hermes.svc.cluster.local"
localPort = 4180
EOF

# 3) 若 token 是新生成的，记得把同一把 token 写到 VPS 的 /etc/frp/frps.toml 并重启 frps ✓
```

**新增一个对外服务**：在 Secret 的 `frpc.toml` 里再加一段 `[[proxies]]`（`type = "http"` + `customDomains` + `localIP/localPort`）✓，
然后 `kubectl -n dsh rollout restart deployment/frpc` ✓；**nginx 与证书都不用改** ✓✓。
若目标命名空间是 default-deny，再照 `frpc-ingress` 的样子加一条放行 ✓。

### 新增一个对外服务（走国内 VPS）

1. 目标命名空间放行 frpc（**只有 default-deny 的命名空间才需要** ✓）——
   在该应用的清单里加一条，照 dsh/k8s/frpc-ingress.yaml（或 hermes 那份）抄：
   `yaml
   ingress:
   - from:
     - namespaceSelector:
         matchLabels: { kubernetes.io/metadata.name: frpc }
       podSelector:
         matchLabels: { app: frpc }
     ports: [{ port: <目标端口>, protocol: TCP }]
   `
2. 在 Secret rpc/frpc-config 的 frpc.toml 里加一段 proxy，然后重启：
   `	oml
   [[proxies]]
   name = "新服务"
   type = "http"
   customDomains = ["新服务.panghuer.top"]
   localIP = "<svc>.<ns>.svc.cluster.local"
   localPort = <端口>
   `
   `ash
   kubectl -n frpc rollout restart deploy/frpc
   `
3. Cloudflare / DNS：加一条记录指向 VPS ✓。**nginx 与证书都不用改** ✓✓（通配符 + 按 Host 分流）。
