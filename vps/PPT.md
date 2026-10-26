# PPT 站点入口

`ppt-service.panghuer.top` 按已确认方案接入 VPS/nginx/frp：安装专用 nginx 站点，
合并 frpc 路由，并保留现有 OAuth 代理和 namespace `ppt-service`。
[Cloudflare Tunnel](../cloudflare-tunnel/PPT.md) 配置保留为可选路线；公网 DNS 切换与入口部署分别核对。

| 配置 | 文件 | 作用 |
| --- | --- | --- |
| 精确域名 nginx server | [ppt-service.conf.template](nginx/ppt-service.conf.template) | TLS 终止，原 Host 转发到 frps，全路径不缓存 |
| 公共 nginx 安装入口 | [install.sh](install.sh) 的 stage2 | 显式设 `PPT_VPS_ENABLED=1` 时渲染并启用，`nginx -t` 后 reload |
| 非敏感 frpc 路由片段 | [ppt-service.toml](k8s/routes/ppt-service.toml) | `ppt-service.panghuer.top` → `ppt-site.ppt-service.svc.cluster.local:4180` |
| frpc 公共出口 | [frpc.yaml](k8s/frpc.yaml) | 旧 Web 广泛规则排除 PPT namespace，其他 namespace 保持原规则 |
| PPT 精确出口 | [ppt-service-egress.yaml](k8s/ppt-service-egress.yaml) | 仅 `frpc/app=frpc` → `ppt-service/app.kubernetes.io/name=ppt-site` 的 TCP4180 |
| 公网 DNS | Cloudflare DNS 后台 | `A ppt-service → 62.234.50.20`、DNS only；不得与同名 Tunnel CNAME 并存 |
| 可选 Tunnel 路线 | [Cloudflare PPT](../cloudflare-tunnel/PPT.md) | 保留配置，切换时同步调整同主机名 DNS 和入口 |

## 为什么使用专用 nginx server

公共通配符站点会缓存 `/assets/`，并忽略上游 `Cache-Control`。PPT 的 HTML、静态资源、
API、预览和下载都必须经过认证，因此精确 `server_name ppt-service.${BASE_DOMAIN}` 的模板覆盖该主机，
关闭缓存读取与写入，统一回传 `Cache-Control: no-store`，不继承公共静态 location 或 HTML 改写。
其他域名继续使用现有通配符站点。HTTP80仍使用既有跳转规则。

模板仅替换 `BASE_DOMAIN` 和 `HTTPS_PORT`，保留 nginx 的 `$host`、`$http_authorization`、
`$http_cookie` 等运行时变量。它沿用通配符证书，并保持 Host、Authorization、Cookie、Origin、
CSRF 头和 WebSocket/SSE；26 MiB入口请求上限配合应用的25 MiB文件及26 MiB multipart限制。
入口只能通向 OAuth 代理4180，业务8000继续仅监听同 Pod loopback。

## 启用顺序

1. 按 [OAuth PPT](../oauth/k8s/PPT.md)、[Vault PPT](../vault/inventory/PPT-SERVICE.md)
   和 [PPT K8s部署说明](../panghu_agent/ppt_service/deploy/k8s/README.md) 完成专用客户端、邀请名单、
   Secret同步、镜像/存储/数据库及站点就绪。
2. 同时应用更新后的 `vps/k8s/frpc.yaml` 和 `vps/k8s/ppt-service-egress.yaml`。
   前者从旧广泛规则排除新namespace；后者给精确网站Pod4180加回许可。
   PPT namespace还须保留自己的 `frpc-ingress` 规则，要求来源namespace与Pod标签同时匹配。
3. 在受保护的管理流程中，把 `k8s/routes/ppt-service.toml` **合并**到现有 frpc 配置。
   保留全部其他代理和 server/auth/TLS 设置；若同名/同域条目已存在，先核对再更新，禁止重复追加。
   使用 frpc 自带配置校验后，再按共享网关维护流程更新和重启。
   本片段没有token，不能单独替换 `frpc-config` Secret；不要把整个真实配置输出到终端或Git。
4. 运行 `sudo env PPT_VPS_ENABLED=1 bash vps/install.sh stage2`，
   安装专用站点并在 `nginx -t` 通过后加载。默认不安装PPT站点，已有文件也不会自动删除。
   这是共享网关安装操作，会执行脚本既有系统/证书/frps步骤；若只发布这次模板更新，
   管理员也可按相同受限变量渲染，安装到 `/etc/nginx/sites-available/ppt-service.conf`，
   在 `sites-enabled` 建同名链接，校验后只reload nginx。不得直接把未渲染模板放入生效目录。
5. 入口准备就绪后，核对 Cloudflare 中该主机名的实际记录，再将公网 DNS 切换为
   `A ppt-service → 62.234.50.20`、DNS only，移除同名 Tunnel CNAME 并停用其公开路由。
   同一主机名只使用一条公网入口链；nginx/frpc 已配置不代表 DNS 已切换。

## 入口验收

- TLS域名/证书正确，HTTP跳转至HTTPS；匿名HTML/asset/API无法读取业务内容。
- 登录并成功读取某个实际 `/assets/` 文件后，使用无cookie的新客户端访问相同URL，仍被拒绝/重定向，
  不得得到之前缓存的200；响应应含 `Cache-Control: no-store`。
- 已登录用户只能使用自己的项目，未邀请用户不得进入；Bearer伪造或丢失不能靠转发头绕过。
- 对应的上传、CSRF、SSE、退出与大cookie行为通过；无缓存命中或跨用户响应复用。
- 从frpc实际探针能连网站4180，不能连PPT的8000、数据库5432或其他Pod；
  CNI实测与仓库策略静态校验分别记录，不能把渲染成功当作网络隔离已通过。

## 本地配置校验

在仓库根目录运行：

```bash
python -m unittest discover -s vps/tests -p test_ppt_route.py -v
bash -n vps/install.sh
bash -n vps/install-frpc.sh
```

2026-10-23本地7项契约校验通过，真实`envsubst`验证仅替换允许的变量，
并检验frpc策略并集不会给PPT的8000/5432或其他Pod放行。
此结果不包含实际`nginx -t`、Cloudflare配置、CNI数据平面或登录往返；
这些由部署方在自己的环境验收，不需要为代码校验连接公共服务或读取任何token。

## 回退

先停用该域名入口/移除对应frpc代理，其他代理和token保持原值。
PPT停止公开服务后可禁用专用nginx站点；不要只删专用server并继续保留域名/frpc路由，
否则会落回有静态缓存的通配符server。策略回退须同步恢复两份frpc清单，避免规则并集放宽访问。
此入口操作不删除PPT数据库、数据PVC或Vault记录。
若切回 Tunnel，先确认其配置仍指向 `ppt-site.ppt-service.svc.cluster.local:4180`，
再用该 Tunnel 的 CNAME 替换 VPS A 记录；不得给同一主机名同时保留两种记录。
