# PPT 的 Cloudflare Tunnel 接入

PPT 站点域名为 `ppt-service.panghuer.top`，与正式 namespace `ppt-service` 保持一致。
当前按已确认方案接入 [VPS/nginx/frp](../vps/PPT.md)，本文保留 Cloudflare Tunnel 的可选路线。
VPS 公网 DNS 使用 `A ppt-service → 62.234.50.20`、DNS only，不与同名 Tunnel CNAME 并存。
域名、Tunnel 和 Casdoor 应用由管理员在各自后台维护；实际 DNS 切换需单独核对。

## Public Hostname

选择 Tunnel 作为公网入口时，在能够访问集群 Service 的现有 Tunnel 中配置一条 Public Hostname：

| 字段 | 值 |
| --- | --- |
| Public hostname | `ppt-service.panghuer.top` |
| Service type | `HTTP` |
| Service URL | `ppt-site.ppt-service.svc.cluster.local:4180` |
| HTTP Host Header | `ppt-service.panghuer.top` |

正式部署的namespace固定为 `ppt-service`。如果后台还保留旧源站
`ppt-site.ppt-service-test.svc.cluster.local:4180`，请编辑原有Public Hostname，
把它改为上表地址并保存；只部署正式Service不会自动更新Cloudflare后台，旧地址会继续返回502。

本次旧源站导致502、入口策略修复及公网恢复的实际结果见
[2026-10-24 部署排障记录](../panghu_agent/ppt_service/deploy/k8s/TROUBLESHOOTING.md)。

对应的非敏感配置片段见 [public-hostname.json](ppt-service/public-hostname.json)。
这份片段不是整条Tunnel配置，不能覆盖现有Public Hostname列表。
切换到 Tunnel 时，用 Cloudflare 为该 Tunnel 生成的 CNAME 替换 VPS A 记录；
同一个主机名不同时保留 Tunnel CNAME 和 VPS A 记录。使用 VPS 时保留本文配置供以后切换，不发布同名 Tunnel 入口。
仓库的 `TunnelRoute` 只是备份，不能代替后台配置，原因见 [路由权威来源](README.md#路由的权威来源重要)。

```text
浏览器 → HTTPS Cloudflare → cloudflared
      → http://ppt-site.ppt-service.svc.cluster.local:4180
      → 同 Pod OAuth 代理 → http://127.0.0.1:8000 PPT
```

源站必须指向OAuth代理4180，业务8000没有Service端口，不得另建绕过OAuth的入口。
保留原Host/Origin、Authorization、Cookie和CSRF头；oauth2-proxy使用固定HTTPS回调。

## 网络规则

PPT namespace默认拒绝入口。2026-10-24已确认实际Connector为
`default/cf-tunnel-main`，Pod标签同时包含 `app=cloudflared,tunnel=main`。
[site-ingress.yaml](ppt-service/site-ingress.yaml) 使用这组身份，仅允许访问
`ppt-service` 中 `app.kubernetes.io/name=ppt-site` 的TCP4180。
在仓库根目录部署这条规则：

```bash
kubectl apply -f cloudflare-tunnel/ppt-service/site-ingress.yaml
```

`deploy.sh` 的基线仅包含frpc入口许可，使用Tunnel时还须应用以上Cloudflare入口规则。
业务8000仅监听同Pod loopback，数据库5432也不向Connector放行。

同日确认Connector所在的 `default` namespace没有NetworkPolicy，当前未隔离其出口，
因此此次只需添加PPT入口许可。**不要单独应用只允许PPT4180的Connector出口策略**：
首条Egress策略会使被选中的Connector进入出口隔离，可能同时切断Cloudflare连接、DNS
和其他现有站点。将来收紧出口时，应先收集并保留Cloudflare、DNS及全部现有服务所需的
完整规则，再统一部署和验证；PPT的新增目标应同时匹配namespace `ppt-service` 和Pod标签
`app.kubernetes.io/name=ppt-site`，仅允许TCP4180。

[connector-egress.yaml.template](ppt-service/connector-egress.yaml.template) 和
[site-ingress.yaml.template](ppt-service/site-ingress.yaml.template) 保留供其他Connector部署使用，
不能直接apply。使用前须填写同一个真实Connector namespace，并把两份文件中的占位
matchLabels整体替换成同一组完整的精确Pod标签；出口模板须纳入上述完整出口方案。
Kubernetes策略取并集：若Connector已有广泛出口，新增窄策略不会自动收窄它，
须检查所有策略的有效许可。

仓库中两种Connector定义如下；切换部署方式后须重新核对现场身份并调整入口规则：

| 部署方式 | namespace | Connector Pod标签 |
| --- | --- | --- |
| operator正式 `Tunnel/main` | `default` | `app=cloudflared,tunnel=main` |
| `manual/deployment.yaml` | `cloudflare-tunnel` | `app.kubernetes.io/name=cloudflared,app.kubernetes.io/component=tunnel` |

`cf-tunnel-operator` 是控制器自己的namespace，不能用它代替Connector身份。
可用只读 `kubectl get pods -A --show-labels` 确认实际Connector，读取标签不需要读取Tunnel Secret。

## 缓存与验收

在Cloudflare为精确主机名 `ppt-service.panghuer.top` 设置Cache Rule：
表达式 `http.host eq "ppt-service.panghuer.top"`，动作 **Bypass cache**，覆盖该站所有路径。
保留上游的 `Cache-Control: no-store`，不得对assets、预览、下载或API套用Cache Everything，
也不要给本应用启用HTML/JS改写来绕过CSP。

启用后必须验证：HTTPS回调完成；邮箱白名单以外的用户和未验证邮箱无法进入；匿名HTML/asset/API没有业务内容；
已登录读过某个实际asset后，清空cookie再请求同一URL仍被拒绝/重定向，不得命中之前的200；
文件上传、CSRF、SSE及退出有效。实际CNI网络探针与配置静态校验分别记录。

OAuth配置见 [OAuth PPT](../oauth/k8s/PPT.md)，精确邮箱名单独立维护在
[ppt-owner-configmap.yaml](../oauth/k8s/ppt-owner-configmap.yaml) 的 `ppt-owner.data.emails`，
每行一个邮箱，不需要配置 `sub`；凭据见
[Vault PPT](../vault/inventory/PPT-SERVICE.md)，业务配置见
[PPT K8s部署说明](../panghu_agent/ppt_service/deploy/k8s/README.md)。

## 当前 VPS 接入方案

按 [VPS PPT配置](../vps/PPT.md) 启用专用不缓存 nginx 站点及 frpc 路由。
入口准备就绪后，核对并切换为 `A ppt-service → 62.234.50.20`、DNS only，移除同名 Tunnel CNAME 并停用其公开路由。
公网 DNS 与服务器配置分别记录；同一时刻为该主机名选择一条入口链，切换入口不会替代专用 OAuth 与 Vault 配置。
