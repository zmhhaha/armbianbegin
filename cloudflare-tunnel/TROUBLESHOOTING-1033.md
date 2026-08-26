# Cloudflare Tunnel 1033 排障记录

> 适用场景：从外网访问 `*.panghuer.top` 报 Cloudflare Tunnel 错误（Error 1033 / Ray ID），Cloudflare 无法解析隧道主机。
> 2026-08-26 排查记录，供后续复用。

---

## 1. 问题现象

- 从外网访问隧道域名（如 `panghuer.top`、`hublog.panghuer.top`）返回 **Error 1033**：

  > Cloudflare 当前无法解析该主机。确保 cloudflared 正在运行且可以连接到网络。

- 集群内 `cf-tunnel-main` Pod 运行中，但 cloudflared 日志反复报错：

  ```
  ERR Failed to dial a quic connection error="failed to dial to edge with quic: timeout: no recent network activity"
  ERR Connection terminated error="there are no free edge addresses left to resolve to"
  ERR Failed to refresh DNS local resolver error="lookup region1.v2.argotunnel.com: i/o timeout"
  ```
---

## 2. 根因

**软路由 OpenClash 配置有误**，导致全网 DNS 与路由异常：

1. **OpenClash 的 fake-ip DNS 把所有域名解析成假 IP**（`198.18.0.0/15` 段，如 `region1.v2.argotunnel.com → 198.18.0.x`）。
   - cloudflared 拿到 fake-ip 后，QUIC（UDP/7844）连接经过 OpenClash TUN 转发，**时通时断**，无法稳定注册隧道 → Cloudflare 边缘认为隧道离线 → 1033。
2. **OpenClash 规则配置错误**（多条 `MATCH` 兜底规则顺序问题），导致非预期流量（Cloudflare、YouTube 等）走了代理，而该直连的流量（中转站等）又连不上。
3. 上述异常级联到 k8s 集群的 DNS 链路（`coredns → systemd-resolved → 软路由 DNS`），表现为集群 Pod 外部域名解析 SERVFAIL，加剧了 cloudflared 无法解析边缘地址。

> 注：排查过程中曾尝试临时把 coredns 的 `forward` 指到软路由（`192.168.137.1`）作为绕行，但这只是治标；软路由 OpenClash 修正后，coredns 已回滚为原始配置 `forward . /etc/resolv.conf`，无需保留该改动。

---

## 3. 解决方案

按顺序执行：

### 3.1 修正软路由 OpenClash 配置

- 检查 **规则（rules）**：确认只有预期流量走代理（如 GitHub 相关域名），其余按需 DIRECT；避免多条 `MATCH` 兜底导致规则顺序错乱。

### 3.2 重启软路由

重启 OpenClash / 软路由，让 DNS 与路由规则生效。

### 3.3 彻底重启 cloudflared 服务（关键，最后一步）

> **改完 OpenClash 并重启路由器后，必须彻底重启 cloudflared，隧道才会最终生效。**

```bash
kubectl rollout restart deployment/cf-tunnel-main -n default
kubectl rollout status deployment/cf-tunnel-main -n default --timeout=120s
```

重启原因是：cloudflared Pod 会缓存旧的边缘地址解析与连接状态，不重启会继续用旧连接反复重试，即使网络已恢复也无法自动稳定。

---

## 4. 验证

1. **连接状态**：两个 Pod 应各有 4 条就绪连接，且连接到**真实** Cloudflare 边缘 IP（`198.41.x.x`，而非 fake-ip `198.18.x.x`）：

   ```bash
   for p in $(kubectl get pods -n default -l tunnel=main -o jsonpath='{.items[*].metadata.name}'); do
     echo "$p: $(kubectl exec -n default $p -- sh -c 'wget -qO- http://localhost:20241/ready 2>/dev/null')"
   done
   # 期望输出: {"status":200,"readyConnections":4,...}
   ```

2. **日志确认**：出现 `Registered tunnel connection ... protocol=quic` 且后续无 `no recent network activity` 报错。

   ```bash
   kubectl logs -n default deployment/cf-tunnel-main --tail=20
   ```

3. **端到端访问**：

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' https://panghuer.top    # 期望 200
   curl -s -o /dev/null -w '%{http_code}\n' https://hublog.panghuer.top  # 期望 302（oauth2 跳转）
   ```

---

## 5. 排查参考命令（下次直接复用）

| 目的 | 命令 |
|---|---|
| 看 cloudflared 日志 | `kubectl logs -n default deployment/cf-tunnel-main --tail=50` |
| 看连接就绪数 | `kubectl exec -n default <pod> -- sh -c 'wget -qO- http://localhost:20241/ready'` |
| 从 Pod 里查隧道域名 DNS | `kubectl exec -n default <pod> -- nslookup region1.v2.argotunnel.com` |
| 查 coredns 上游配置 | `kubectl get cm -n kube-system coredns -o jsonpath='{.data.Corefile}'` |
| 判断 DNS 是否 fake-ip | 解析结果落在 `198.18.0.0/15` = OpenClash fake-ip 在劫持 |
| 重启 cloudflared | `kubectl rollout restart deployment/cf-tunnel-main -n default` |

---

## 6. 关键教训

- **1033 ≠ cloudflared 进程挂了**：Pod 可能一直 Running，实际是连不上边缘（网络/DNS 层问题）。
- **fake-ip 是头号嫌疑**：任何域名解析出 `198.18.0.0/15` 段地址，说明 OpenClash fake-ip 在劫持 DNS，隧道类 UDP 连接最容易受害。
- **改网络出口配置（OpenClash）后，一定要重启软路由 + 重启 cloudflared**，两者缺一不可。