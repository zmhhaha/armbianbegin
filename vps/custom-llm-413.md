# DSH 长对话触发模型代理 413

记录日期：2026-10-21。线上修复和验证已完成。

## 现象与原因

DSH 使用 `custom-llm`，长对话反复出现：

```text
本轮运行失败
custom-llm API error (413): 413 Request Entity Too Large
nginx/1.28.3 (Ubuntu)
```

请求链路为 DSH → `custom-llm-proxy.panghuer.top`（VPS Nginx）→ `jingsi.asia:9080`。
VPS 的 `/var/log/nginx/error.log` 确认拒绝发生在本站模型代理：

```text
client intended to send too large body: 1060272 bytes,
server: custom-llm-proxy.panghuer.top,
request: "POST /v1/responses HTTP/1.1"
```

该站点原先没有显式设置 `client_max_body_size`，生效的默认上限为 1 MiB（1,048,576 字节）。
对话历史增长后，请求刚超过此上限就被拒绝。`proxy_request_buffering off` 不会取消请求体大小限制。
这个错误本身不能证明已超过模型的 token 上下文窗口。

DSH 已安装压缩组件，支持在会话空闲时执行 `/compact`。其自动压缩依据上下文预算触发，
与 Nginx 的字节限制不同，因此可能先遇到 413；压缩过程自身的模型请求也可能超限。

## 修复配置

在模型代理的 `location /v1/` 内增加：

```nginx
client_max_body_size 32m;
```

配置只作用于此站点的模型 API 路径。仓库源文件为
[`nginx/custom-llm-proxy.conf.template`](nginx/custom-llm-proxy.conf.template)，
部署文件为 `/etc/nginx/sites-available/custom-llm-proxy.conf`，
由 `sites-enabled` 的同名链接启用。模板也已同步，后续 `install.sh stage2` 渲染不会丢失修复。

本次先备份线上配置，再修改、校验并平滑重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl is-active nginx
```

备份路径：`/etc/nginx/sites-available/custom-llm-proxy.conf.bak-20261021-135559`。
文件名中的时间为 VPS 生成的时间，不作为北京时间记录。
语法检查通过，重载后服务状态为 `active`。

## 验证结果与范围

向公网 `/v1/responses` 发送了 2,097,194 字节（约 2 MiB）的 JSON 请求，未携带 API Key。
返回 HTTP 401，响应包含 `API_KEY_REQUIRED`，证明大请求已通过代理并到达上游鉴权，
不再被本站 Nginx 以 413 拒绝。此探测没有进行模型推理。

本次未代替用户重放原 DSH 会话；原会话的完整模型回复仍需用户重试确认。
32 MiB 只提高传输层上限，模型上下文窗口和上游请求限制仍各自生效。
长对话可先执行 `/compact`；若仍出现 413，应重新检查本站日志并区分是否由上游返回。

## 登录与回滚

本机 SSH 已有 `tencent` 别名，实际账户是 `ubuntu`，私钥路径为
`~/.ssh/tencent_vps.pem`（不是 `tencent_ssh.pem`），可用：

```bash
ssh tencent
```

私钥内容不进入仓库。需要回滚本次线上配置时，在 VPS 执行：

```bash
sudo cp /etc/nginx/sites-available/custom-llm-proxy.conf.bak-20261021-135559 /etc/nginx/sites-available/custom-llm-proxy.conf
sudo nginx -t && sudo systemctl reload nginx
```

回滚会恢复原有请求体限制；若决定长期回滚，也应同步修改仓库模板。
