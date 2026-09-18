# DSH route

`dsh-route.yaml` 是待上线的单服务路由备份，不代表已经在 Cloudflare 生效。
沿用现有远程管理 `main` Tunnel，不新增 Tunnel token，不切换到本地 ingress 配置，也不覆盖已有域名列表。

部署顺序：

1. 先部署 DSH，确认单用户 OAuth 代理就绪。
2. 给现有 cloudflared Deployment 的 Pod 模板添加 `dsh-ingress: "true"`。
   当前 main 命名可先在集群核对，再由管理员执行：
   `kubectl -n default patch deployment cf-tunnel-main --type=merge -p '{"spec":{"template":{"metadata":{"labels":{"dsh-ingress":"true"}}}}}'`
   这会滚动现有 Tunnel；保留原标签和 replicas，并在维护窗口关注其他域名连接。
   注意：**这一步要保留既有标签**（已有 `hermes-ingress: "true"`），merge patch 只增不删，但仍应在执行前核对当前标签集。
3. 在 Cloudflare Tunnel 的 Published application 中增加 hostname `dsh.panghuer.top`，
   service `http://dsh-web.dsh.svc.cluster.local:4180`。不设置 HTTP Host Header 覆盖，**不转发到 3080**。
4. 如修改 hostname，同步 `oauth/k8s/dsh-proxy-configmap.yaml`、Casdoor callback 和此备份。

## 日志与 launch token

DSH 首次登录会用一个进程 launch token 访问一个已认证的 HTTPS 根 URL。该 token **不得出现在路由配置、访问日志或查询串日志中**。

配置本条路由时确认：Cloudflare 侧不开启带 query 的完整 URL 记录，代理侧不记录完整请求行。不要为了排查方便临时打开完整 URL 日志。

Cloudflare Access 可另加 Self-hosted application 与精确邮箱 Allow 策略，其他身份默认拒绝。
它是可选的第二层认证，不替代已实现的 oauth2-proxy。无需关闭 origin TLS 验证；当前内部 service 使用 HTTP。

现有 operator 不持久管理上述额外 Pod 标签，重建 Deployment 可能丢失标签；丢失后 NetworkPolicy 会拒绝连接，
应恢复标签**而不是放宽整个集群访问**。未自动修改共享 operator，以免影响已有服务。

回滚时先在 Cloudflare 仅移除 DSH 路由，再停止 DSH；不要删除共享 main Tunnel 或覆盖其他 Public Hostname。

**本次没有修改远端路由、标签或 Access 策略。**
