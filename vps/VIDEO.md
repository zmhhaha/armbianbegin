# 视频工作台 VPS 入口

`video-service.panghuer.top` 使用现有 VPS `62.234.50.20` 的 Nginx/frps 和集群 frpc，
继续经过 `oauth2-proxy-video-workbench.oauth.svc.cluster.local:4180` 登录代理。
工作台、Redis、数据 PVC、Casdoor 应用与回调地址均沿用现有配置。

```text
浏览器 → VPS:443 Nginx → 127.0.0.1:8080 frps → 集群 frpc
       → OAuth:4180 → video-workbench:8089
```

配置文件：

- [Nginx 专用站点](nginx/video-service.conf.template)：精确域名、全路径 `no-store`、保留 HTTPS/Host、Cookie、WebSocket 和流式响应，不注入备案页脚，不记录 OAuth 查询串。
- [frpc 路由片段](k8s/routes/video-service.toml)：只转发到现有 OAuth 代理。
- [OAuth 入站规则](k8s/video-service-ingress.yaml)：仅允许 `frpc` 命名空间的 `app=frpc` 访问指定代理 TCP4180。

## 部署顺序

1. 保存当前 DNS、目标 Nginx 站点、frpc Secret 和相关策略的私有备份，确认没有同名/同域 FRP 代理或精确 Nginx server 冲突。凭据和完整 Secret 不进入终端输出或 Git。
2. 应用 `k8s/video-service-ingress.yaml`。现有 frpc 公共出口已允许 `oauth` 的 TCP4180；核对实际策略即可，无需替换共享策略。新增窄规则不会收紧其他规则，因为 NetworkPolicy 取并集。
3. 将 `k8s/routes/video-service.toml` 合并进现有 `frpc/frpc-config` 的 `frpc.toml`，完整保留 server/auth/TLS 和其他代理；同条目已存在时校对后跳过，禁止重复追加。先用现有 frpc 的 `verify -c /dev/stdin` 校验候选配置，再通过带 UID/resourceVersion 条件的更新写入 Secret。等待投影更新并再次校验后，重启单副本 Recreate 的 frpc。此步骤会短暂重连共享隧道。
4. 安装专用 Nginx 站点，校验现有通配符证书覆盖该域名且有效，`nginx -t` 通过后仅 reload Nginx。沿用 HTTP80 的 HTTPS 跳转。只替换 `${BASE_DOMAIN}` 和 `${HTTPS_PORT}`，其余 `$host`、`$http_cookie` 等变量必须原样保留。首次完整安装可设 `VIDEO_VPS_ENABLED=1 bash vps/install.sh stage2`；该入口还会执行共享 frps/证书/站点安装流程。已有 VPS 发布本次模板时，应单独受限渲染到 `/etc/nginx/sites-available/video-service.conf` 并建立同名启用链接，避免重跑整个 stage2。
5. 从 VPS 用正确 Host/SNI 验证 Nginx→FRP→OAuth 后，由用户在 Cloudflare Dashboard 手动将该域名 DNS 切为 `A 62.234.50.20`、DNS only。同名 Tunnel CNAME 不得并存。保留原 TunnelRoute 作为回退，不修改其对象以免重启共享 cloudflared。部署脚本不修改 DNS；Casdoor 配置也由用户手动管理。

## 验证

- `nginx -t` 和 `frpc verify` 通过；证书域名/有效期正确，HTTP 跳 HTTPS。
- 匿名访问首页、API、预览和导出仍需登录；不能通过伪造身份头获得业务内容。响应包含 `Cache-Control: no-store`，无共享缓存命中。
- 已有登录会话能读取原项目，采用版本和 ZIP 导出可用。已登录读取某个真实私有产物后，无 Cookie 客户端访问相同 URL 仍被拒绝。
- FRP 代理列表除视频新增条目外保持不变；scientific-agent、ppt-service 和现有业务入口可达。
- 用公网 DNS 或 VPS 核对 A 记录；家中 Clash 的合成 IP 不能证明公网路由。应用检查使用普通读取，不创建新 Agent/模型任务。

## 回退

先确认原 Tunnel 路径可用，再由用户在 Cloudflare Dashboard 手动将该域名恢复成备份里的 Tunnel CNAME、代理状态和 TTL。
等待客户端 DNS 缓存过渡期间，保留视频专用 Nginx 和 FRP 路由。
如需移除新增资源，只移除视频 FRP 条目及 `frpc-video-service-ingress`，保留其他路由、凭据和策略。
专用 Nginx 配置不得在域名仍走 VPS 时先删掉，否则请求会落回通配符静态缓存。
回退不删除工作台、Redis、项目数据或 PVC，也不更改 Casdoor 回调。

## 当前部署记录（2026-10-30）

配置提交为 `2f534adfdd887b12056f856b0319fd93dcab2d66`，部署仅新增视频入口。
原有 34 条 FRP 代理和 server/auth/TLS 设置全部保留，新增后为 35 条。
新 frpc Pod `frpc-5fbbc76b8f-8482q` Ready，视频代理启动成功；原网络策略和工作台 Deployment 未改。
VPS 已安装精确域名站点并在 `nginx -t` 成功后 reload，原有四份站点文件摘要不变，frps 未重启。

本次首次 DNS 切换已完成，当前为 `A 62.234.50.20`、DNS only，公网 DNS 和正常域名 HTTPS 请求均已核对。
用户随后明确后续 DNS 切换及回退由其在 Dashboard 手动操作，不再由 Agent 写 DNS。
原 Tunnel 配置及 Casdoor 保留。

严格 TLS、HTTP→HTTPS、首页/API/静态路径/既有私有预览与导出匿名拒绝、伪造身份头拒绝和全路径 `no-store` 均通过。
科研与 PPT 的 VPS 登录跳转正常，其 DNS 记录未变。
浏览器重新加载后保留原会话并成功读取现有项目和分镜；本次接入没有提交 Agent 或模型任务。
此次浏览器会话中没有可用的已采用素材，未重新声称已登录私有素材下载及 ZIP 导出已实测。

本地 `bash -n`、受限 `envsubst`、TOML/YAML 配置检查及原 PPT 入口 7 项回归通过。
非敏感回执见 [部署摘要](evidence/video-vps-20261030.json)；完整回执和私有备份位于集群管理机及 VPS 的 `/root/video-vps-ingress-20261030/`，不进入 Git。
