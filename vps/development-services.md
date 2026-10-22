# OpenSpec、Gitea、Drone 的 VPS 入口

这三个服务的公网入口使用 VPS `62.234.50.20`。应用和数据仍在 Kubernetes，域名、OAuth 回调、Git 仓库 URL 和 Drone webhook 地址保持不变，无需迁移数据库或数据卷。

## 访问路径与 DNS

```text
客户端 HTTPS :443
  → VPS Nginx（TLS 终止）
  → 127.0.0.1:8080 frps（按 Host 路由）
  → 集群中现有 frpc
  → Kubernetes Service
```

| 公网域名 | 集群目标 | Cloudflare DNS |
| --- | --- | --- |
| `openspec.panghuer.top` | `openspec-service.openspec.svc.cluster.local:8080` | A → `62.234.50.20`，灰云 |
| `gitea.panghuer.top` | `gitea.gitops.svc.cluster.local:3000` | A → `62.234.50.20`，灰云 |
| `drone.panghuer.top` | `drone-server.gitops.svc.cluster.local:8080` | A → `62.234.50.20`，灰云 |

2026-10-22，用户已将上述三条记录改为 A 记录并关闭 Cloudflare 代理；已通过 Cloudflare API 核对。灰云表示客户端直接连接 VPS，HTTPS 由 VPS 的有效证书提供。DNS 生效后应继续完成下述协议检查。

三条 FRP 路由已存在，不需要重建或重启 frpc、frps。OpenSpec 和 Drone 使用现有通配域名 Nginx 配置；Gitea 使用专用配置，允许最大 512 MiB 请求体，并关闭请求及响应缓冲，支持 Git HTTP、LFS 和附件传输。应用本身的大小限制仍然有效。

## 部署 Gitea 的 Nginx 配置

在 VPS 的仓库目录执行：

```bash
sudo bash vps/deploy-gitea-nginx.sh
```

脚本从 `vps/nginx/gitea.conf.template` 生成站点配置，保留既有 HTTPS 转发头、WebSocket 设置及备案页脚。它只更新 Gitea 站点，保存仅 root 可读的备份，执行 `nginx -t` 后 reload Nginx。记录脚本输出的备份路径，便于恢复。

本次入口迁移使用这个专用脚本，不需要执行全量 `install.sh` 的 stage2；全量安装会涉及 frps 等共享组件。

## 验证

从外部网络检查 DNS、证书及服务健康状态：

```bash
dig +short openspec.panghuer.top A
dig +short gitea.panghuer.top A
dig +short drone.panghuer.top A

curl --fail --show-error https://openspec.panghuer.top/readyz
curl --fail --show-error https://gitea.panghuer.top/api/healthz
curl --fail --show-error https://drone.panghuer.top/healthz
```

三个 A 记录应解析到 `62.234.50.20`，健康检查应返回 HTTP 200。若本地代理或路由器返回合成 IP，请使用不经过该代理的公网 DNS 或从 VPS 检查。不要用 `curl -k` 跳过证书检查。

DNS 尚在传播时，可以在 VPS 强制通过本机 Nginx 检查指定域名：

```bash
curl --fail --show-error --resolve openspec.panghuer.top:443:127.0.0.1 https://openspec.panghuer.top/readyz
curl --fail --show-error --resolve gitea.panghuer.top:443:127.0.0.1 https://gitea.panghuer.top/api/healthz
curl --fail --show-error --resolve drone.panghuer.top:443:127.0.0.1 https://drone.panghuer.top/healthz
```

健康检查通过后，还需验证实际使用路径：

- **OpenSpec：** MCP 地址仍为 `https://openspec.panghuer.top/mcp`。使用正常 OAuth 登录的客户端执行一次项目读取。根路径 `/` 返回 401 属于鉴权行为，不能据此认定服务故障。
- **Gitea：** 打开网页并验证登录，使用已有授权凭据对现有仓库执行 `git ls-remote <仓库 HTTPS URL> HEAD`。健康接口正常不代表已验证 Git 协议。不要把 token 放进 URL、命令行或文档。
- **Drone：** 打开网页并验证经 Gitea 登录的跳转，确认返回 `https://drone.panghuer.top/login`，检查已有构建页面及 runner 状态。

OpenSpec 客户端使用的 `localhost`／`127.0.0.1` OAuth 回调是客户端本机接收授权结果的地址，与服务公网入口独立。迁移到 VPS 不会自动修复客户端回调监听或 Casdoor 回调白名单问题；服务域名未变，也不需要因此改动现有回调。

## 回滚

旧 Cloudflare TunnelRoute 保留，供入口回滚使用。不要为这次迁移编辑或删除这些对象：当前控制器可能因此重建共享配置并重启 cloudflared，影响其他服务。保留它们不会把 DNS 自动改回 Tunnel。

需要回滚公网入口时，将受影响域名在 Cloudflare 恢复为：

```text
类型：CNAME
目标：e04e40cb-4290-4725-b9e2-7f8a344104a5.cfargotunnel.com
代理状态：已代理（橙云）
TTL：自动
```

回滚前先确认旧 Tunnel 通道可用；DNS 缓存可能使一部分客户端暂时仍走 VPS。Gitea 的专用 Nginx 配置可以保留，不影响 DNS 回滚。若需要恢复该配置，使用部署脚本记录的备份，执行 `nginx -t` 成功后再 reload。
