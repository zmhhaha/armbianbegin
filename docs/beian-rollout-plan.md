# 备案通过后的服务搬迁与合规改造计划

> 状态：**规划中**（2026-10-12 17:30 制定）。正式执行安排在 **18:00 之后**（避开高峰计费时段）。
> 相关文档：`vps-ingress-design.md`（VPS 入口的设计与运维）、`../vps/README.md`（操作手册）。

## 0. 背景与实测判据

```
走 Cloudflare Tunnel 的服务，从外部（腾讯云 VPS）量的首字节：
  auth 1.51s   dsh 1.48s   hermes 1.40s   guanliao 1.52s   chat 1.49s
  game 1.38s   tool 1.36s  obsidian 1.53s  agent 1.29s      ← 全部 1.3~1.5s ✗
同一服务在集群内部（VPS → frps → 隧道 → 家）只需 13ms ✓
```

结论：**慢不是应用的问题** ✓，而是两件事叠加 ✗ ——
1. **跨境绕行**：国内用户 → Cloudflare 境外边缘 → 绕回你家 ✗
2. **你家 ~1.6 Mbps 上行**：任何响应都要先从你家上行出去 ✗（846KB 的 JS 就要 ~4.3s ✗）

备案已通过 ✓ → 可以把域名指向腾讯云 VPS（443）✓，绕开第 1 条；第 2 条需要靠**缓存**解决 ✓。

## 1. 任务一：统一展示备案号

**目标**：所有从大陆实例（VPS）对外服务的可交互站点，页脚统一展示备案号 + 链接 `beian.miit.gov.cn`。

**方案（推荐：一处配置，不改各应用代码 ✓）**
- 在 VPS 的 nginx 上做**统一注入**：一份共享 snippet，用 `sub_filter` 在 `</body>` 前插入固定 footer；
- `sub_filter` 要求上游不压缩 ✓ → 对 HTML 位置加 `proxy_set_header Accept-Encoding "";`
- **只对 `text/html`、非 API/SSE/WebSocket 路径生效** ✓（避免破坏 JSON 接口与流式响应 ✗）
- 备选：若某应用本身有页脚，优先在该应用里展示 ✓（更"原生" ✓）

**验收**：`curl https://<服务>/` 的 HTML 里出现备案号 ✓；浏览器可见且不遮挡交互 ✓。
**待确认**：备案号具体值；是否所有子域都需展示（以腾讯云/工信部口径为准 ✓）。

## 2. 任务二：搬迁高延迟服务

**排序依据**：首屏负载大小 × 使用频率（当前 TTFB 大家都一样 ✗，所以看**负载** ✓）。

- **Step 0（测量）**：逐个服务记录 ① 首页 TTFB ② 首屏资源总量 ③ 是否登录门 ④ 是否含 WebSocket
- **Step 1**：`dsh` —— 已就绪 ✓，只差：控制台放行 443 ✓ + CF 记录改 A/灰云 ✓
- **Step 2**：`auth`（Casdoor）★ 收益最大（846KB JS + 66KB CSS 全走跨境 ✗）
- **Step 3**：各 Web 门户（chat / game / tool / agent-portal、guanliao、hermes、obsidian …）
- **Step 4**：VPS 侧开 `proxy_cache` ✓ —— 静态资源由腾讯云直接发，**不再经你家上行** ✓✓

**每个服务的搬迁固定三步**（详见 `vps-ingress-design.md` §7）：
```
① frpc 的 Secret 里加一条 [[proxies]]（customDomains + localIP/localPort）→ rollout restart deploy/frpc
② 目标命名空间若是 default-deny → 加一条 frpc-ingress（照 hermes/k8s/frpc-ingress.yaml 抄）
③ Cloudflare 把该记录改成 A → 62.234.50.20，代理状态 = DNS only（灰云 ✗ 不能橙云）
```
nginx 与证书**零改动** ✓（`*.panghuer.top` 通配符 + 按 Host 分流 ✓）。
**回滚**：把记录改回 `CNAME → <tunnel-id>.cfargotunnel.com` + 橙云 ✓（秒级 ✓）。

## 3. 任务三：搬迁对外网访问的影响（分析）

| 用户 | 现在（走 CF） | 搬迁后 | 判断 |
|---|---|---|---|
| **国内** | 1.3–1.5 s ✗ | **20–40 ms** ✓✓ | 大幅改善 ✓ |
| **国外** | 就近 CF 边缘（~20ms）+ 跨境回中国 ✗ | 直接跨境到中国 ✗ | **不会更快** ✗，可能略降 ✗ |

原因：**源站仍在家里** ✓ —— 国外用户无论如何都要跨境到中国才能拿到内容 ✓。
若将来要兼顾国外 ✓：
1. 静态资源缓存在 VPS ✓（两边都快 ✓）
2. 重服务（如 RAG/索引/大文件）**放到 VPS 上**，不回家 ✓✓
3. 迁 NS 到 DNSPod 后可做**境内/境外线路分流** ✓（CF 免费版 DNS 没有地域分流 ✗）

## 4. 任务四：写入 OpenSpec 与文档

- **文档**：本文件；执行过程中更新 `vps-ingress-design.md` §10 与 `vps/README.md`
- **OpenSpec**：项目 `ec663f5a-53d3-4a0e-9037-933eb788d183`（owner `openspec-service` / repo `armbianbegin`）
  - ⚠️ 2026-10-12 17:35 发现 `openspec.panghuer.top` 返回 **502** ✗ → MCP 断开 ✗ → **先修服务再建 change**
  - change 内容：proposal（本计划）/ tasks（可勾选步骤）/ specs（页脚注入的行为约定）

## 5. 任务五：时间与执行窗口

```
17:30–18:00  规划：确认判据、排序、写文档（本轮 ✓，不动生产 ✓）
18:00 之后   Step 0 测量 → 任务一（备案号注入）→ dsh 切换 → auth 迁移 → Step 4 缓存 → 其余服务
```

**每步原则** ✓：先验证再下一步 ✓；每步都可回滚 ✓；不在生产链路上做"顺手改" ✗。
## 6. ★ 前置任务（2026-10-12 发现，必须先做）

**Vault 处于 sealed 状态已 3.5 天** ✗ → 全集群 **60 个 ExternalSecret 全部同步失败**（0 成功 ✗）：

```
Vault:      Sealed = true ✗   Unseal Progress 0/3（阈值 3/5 ✓）
起点:       约 3d8h 前（Vault Pod 在 3d5h 前重启过 ✗ —— 与上次断电时间吻合 ✓）
影响:       ① 密钥无法轮换/新增 ✗  ② 依赖"新值"的服务会陆续失效 ✗
            （openspec.panghuer.top 502 + MCP 断连就是这个 ✗）
好消息:     已同步的 Secret 对象仍在 ✓（DeletionPolicy: Retain ✓）
            → 重启 Pod **不会丢密钥** ✓，只是拿到旧值 ✓
修法:       kubectl -n vault exec vault-0 -- vault operator unseal   ×3（用 5 份 key 中的 3 份 ✓）
            解封后确认：kubectl get externalsecret -A → 全部回到 SecretSynced ✓
注意:       密钥由你保管 ✓，我不接触 ✓；解封前不要重启依赖新密钥的服务 ✗