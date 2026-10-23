# PPT 的 Cloudflare Tunnel 接入

PPT 站点域名为 `ppt.panghuer.top`。由管理员在 Cloudflare 后台配置域名/Tunnel，
Casdoor 应用也由管理员在后台配置。

## Public Hostname

在能够访问集群 Service 的现有 Tunnel 中增加一条 Public Hostname：

| 字段 | 值 |
| --- | --- |
| Public hostname | `ppt.panghuer.top` |
| Service type | `HTTP` |
| Service URL | `ppt-site.ppt-service.svc.cluster.local:4180` |
| HTTP Host Header | `ppt.panghuer.top` |

对应的非敏感配置片段见 [public-hostname.json](ppt/public-hostname.json)。
这份片段不是整条Tunnel配置，不能覆盖现有Public Hostname列表。
域名应按Cloudflare为该Tunnel生成的记录路由；不要同时给同一个主机名保留VPS的A记录。
仓库的 `TunnelRoute` 只是备份，不能代替后台配置，原因见 [路由权威来源](README.md#路由的权威来源重要)。

```text
浏览器 → HTTPS Cloudflare → cloudflared
      → http://ppt-site.ppt-service.svc.cluster.local:4180
      → 同 Pod OAuth 代理 → http://127.0.0.1:8000 PPT
```

源站必须指向OAuth代理4180，业务8000没有Service端口，不得另建绕过OAuth的入口。
保留原Host/Origin、Authorization、Cookie和CSRF头；oauth2-proxy使用固定HTTPS回调。

## 网络规则

PPT namespace默认拒绝，既要放行网站入口，也要检查cloudflared所在namespace的出口：

- PPT入口：来源**实际**cloudflared namespace与Pod标签同时匹配，目的仅网站Pod的TCP4180。
- Connector出口：目的namespace `ppt-service`与Pod标签 `app.kubernetes.io/name=ppt-site`
  同时匹配，仅TCP4180；不得放开整个PPT namespace的8000/5432。
- Connector连接Cloudflare和DNS的原有规则保留，网站无需访问Tunnel token或Cloudflare管理API。

[connector-egress.yaml.template](ppt/connector-egress.yaml.template) 和
[site-ingress.yaml.template](ppt/site-ingress.yaml.template) 是两端待填的独立策略模板，
不能直接apply。分别复制为部署用YAML，**在两份文件中填入同一个真实Connector namespace，
并把占位matchLabels整体替换成同一组完整的精确Pod标签**，再同时应用。
两端必须使用相同身份，不需要业务部署渲染器；Connector出口的namespace写在metadata，
同一值在PPT入口写入来源namespaceSelector。
Kubernetes策略取并集：如果Connector已有广泛出口，新增窄策略不会自动收窄它，
须检查现有策略的有效许可，不能据新增文件声称出口已经隔离。

仓库中有两种不同的定义，仅供确认现场时对照，**不是当前在线状态的证明**：

| 部署方式 | namespace | Connector Pod标签 |
| --- | --- | --- |
| operator正式 `Tunnel/main` | `default` | `app=cloudflared,tunnel=main` |
| `manual/deployment.yaml` | `cloudflare-tunnel` | `app.kubernetes.io/name=cloudflared,app.kubernetes.io/component=tunnel` |

`cf-tunnel-operator` 是控制器自己的namespace，不能用它代替Connector身份。
可用只读 `kubectl get pods -A --show-labels` 确认实际Connector，读取标签不需要读取Tunnel Secret。

## 缓存与验收

在Cloudflare为精确主机名 `ppt.panghuer.top` 设置Cache Rule：
表达式 `http.host eq "ppt.panghuer.top"`，动作 **Bypass cache**，覆盖该站所有路径。
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

## 可选的 VPS 入口

如以后选择国内VPS，使用 [VPS PPT配置](../vps/PPT.md)：
`A ppt → 62.234.50.20`、DNS only，启用专用不缓存nginx站点及frpc路由。
同一时刻为该主机名选择一条入口链；切换入口不会替代专用OAuth与Vault配置。
