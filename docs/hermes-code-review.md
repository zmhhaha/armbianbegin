# Hermes 代码评审

> 评审时间：2026-09-16，代码基准 HEAD `3dd4128` + 未提交工作区（Hermes 相关文件全部 untracked）。
> 评审对象：`panghu_chat/hermes/`（子模块）+ `oauth/k8s/hermes-*`、`vault/inventory/hermes-*`、`cloudflare-tunnel/operator/hermes-*`。
> 配套：[hermes-intelligence-review.md](hermes-intelligence-review.md)（方案层评审）、[platform-auth-ingress-survey.md](platform-auth-ingress-survey.md)、[platform-k8s-conventions.md](platform-k8s-conventions.md)。
> 作者自述状态：**未运行测试、未构建镜像、未部署**（`panghu_chat/hermes/README.md` 首段）。

## 结论摘要（TL;DR）

工程质量明显高于同仓库的平均水平——SSRF 防护、凭据最小权限分离、失败时拒绝编造，这三处做得很扎实，值得作为后续服务的参考实现。

发现 **2 个会导致功能不工作的高危问题**，都是"未执行测试"最典型的漏项：

1. **Hublog 出站 NetworkPolicy 写的是 8080，而代码默认连的是 80**，且仓库里另一个消费方走的就是 80。是否真被拦取决于 CNI 在 DNAT 前还是后匹配端口 —— 必须实测。
2. **写死的 Hermes CLI 参数（`chat --query-file --oneshot --run-budget` 等）尚未与固定的镜像摘要对过**，不匹配的话要到运行期才报错。

另有 6 个中危、5 个低危，见下。

## 一、先说做得好的（不是客套，是有具体理由的）

**1. SSRF 防护是仓库里最认真的一处**（`app/pipeline.py:40-77`）

- scheme 必须是 https；拒绝内嵌凭据；只允许 443
- 解析出的**全部**地址都要 `is_global`，任一为私网就拒绝
- 校验后**钉住 IP 连接**，同时保留 SNI/证书校验主机名（`PinnedHTTPS`）——这正是防 DNS rebinding 的正确写法
- 每次重定向**重新走一遍完整校验**（循环重入），最多 5 跳
- `Accept-Encoding: identity` 避免压缩炸弹，2 MB 上限作用在原始字节上

**2. 凭据最小权限分离是真的做到了**

- **只有 publish 容器挂 Hublog token**（`scripts/render.py:87-89`），report 和 collect 都不挂
- 并且在 `app/pipeline.py:157` 显式 `env.pop("HUBLOG_SERVICE_TOKEN", None)` 兜底
- 私人网页和研究 job 用**两个不同的 PVC**（`hermes-web` vs `hermes-reports`），`HERMES_HOME` 也分开（`/opt/data` vs `/reports/agent`）——README 声称的"私人会话历史不进入报告 job"是有结构保证的，不只是靠自觉

**3. 失败时拒绝编造**

- `if not rows: raise RuntimeError("no collected evidence; refusing to invent a report")`（`pipeline.py:146-147`）
- 报告必须有 `BEGIN_REPORT`/`END_REPORT` 标记，且有长度上下界（`pipeline.py:172-177`）
- `MAX_DAILY_ATTEMPTS` **先占额度再启动**，崩溃也消耗预算（`pipeline.py:153-154`）——这个顺序是对的
- CronJob `backoffLimit: 0`，失败不自动重试

**4. 与仓库既有约定一致**

CronJob 是唯一调度源（明确不启用 Hermes 内建 cron）、`timeZone: Asia/Shanghai`、label-based NetworkPolicy、Vault + ExternalSecret、`--platform linux/arm64` + 摘要固定、`suspend: True` 默认暂停。这些都对齐了 [platform-k8s-conventions.md](platform-k8s-conventions.md)。

**5. oauth2-proxy 的配置正好补上了平台空白**

`oauth/k8s/hermes-proxy-container.yaml` 用了 `--authenticated-emails-file=/owner/emails`（精确单邮箱）而不是现网的 `--email-domain=*`，cookie 用 `--cookie-name=__Host-hermes` 且不设 domain。**这是仓库里第一份 per-user 白名单 + 独立 cookie 的配置**，此前 [platform-auth-ingress-survey.md](platform-auth-ingress-survey.md) 记录的"现网无先例"说的就是这块空白。

`__Host-` 前缀要求 Secure + Path=/ + 无 Domain 三条同时成立，这里 `--cookie-secure=true`、`--cookie-path=/`、未设 `--cookie-domain`，**三条都满足**。MFA 交给 Casdoor，方向也对（oauth2-proxy 自己不提供 MFA）。

## 二、高危

### H1. Hublog 出站端口不一致：NetworkPolicy 8080 vs 代码默认 80

三处证据：

| 位置 | 内容 |
|---|---|
| `scripts/render.py:101` | `hublog-publisher` NetworkPolicy 只放行 `port: 8080` |
| `app/pipeline.py:187` | `os.getenv("HUBLOG_URL", "http://hublog-api.hublog.svc.cluster.local")` —— **无端口，即 80** |
| `scripts/render.py:87-89` | publish 容器**没有设置 `HUBLOG_URL` 环境变量**，所以一定走默认值 |

而实际 Service 是：`panghu_chat/hublog/k8s/api-deployment.yaml:59` —— `ports: [{name: http, port: 80, targetPort: http}]`（容器端口 8080）。

**仓库里另一个消费方走的是 80**：`oauth/k8s/hublog-proxy-configmap.yaml:26` —— `uri: http://hublog-api.hublog.svc.cluster.local:80`。所以 8080 这个写法在仓库里是**孤例**。

**会不会真被拦，取决于 CNI 在 DNAT 前还是后匹配 NetworkPolicy 端口**：

- 若在 DNAT **后**匹配（看到的是 targetPort 8080）→ 命中，能通
- 若在 DNAT **前**匹配（egress 在源 Pod netns 评估，看到的是 Service port 80）→ 被 `default-deny` 拦掉，发布静默失败

README 自己在网络那节已经提示"请核对 CNI 对 Service DNAT 的处理"，但那条是写给 OIDC/内网服务的，没意识到 Hublog 这条本身就有这个不一致。

**修法（二选一，然后实测）**：把 NetworkPolicy 改成 `port: 80`，或在 `render.py` 里给 publish 容器显式设 `HUBLOG_URL=...:8080`。选 80 与仓库既有写法一致。

### H2. 写死的 Hermes CLI 参数尚未与镜像摘要对齐

`app/pipeline.py:158-159` 写死了：

```
/opt/hermes/.venv/bin/hermes chat --query-file ... --oneshot --quiet \
    --toolsets web --max-turns 6 --run-budget 900
```

`render.py:51` 同样写死了 `dashboard --host 127.0.0.1 --no-open`。

README 自己说了前提是"先选择包含 `dashboard`、`chat --query-file --oneshot --run-budget` 的上游版本，检查其 ARM64 manifest，然后固定摘要"。但**这个前提没有落到任何可验证的地方**——`render.py` 只校验了 `image` 字段含有 `@sha256:`，不校验 CLI 契约。

不匹配的后果是运行期才暴露：`subprocess` 返回非 0 → `RuntimeError("Hermes exited with code N; check model configuration")`，错误信息还会把人往"模型配置"方向引。

这正是 [hermes-intelligence-review.md](hermes-intelligence-review.md) 第一节说的"ARM64 是单点前提"的**具体形式**：现在门禁只剩"镜像有 arm64 manifest"，但真正的门禁是"镜像里的 CLI 契约对得上"。建议加一个 spike 脚本，把这两个命令对着摘要实跑一次语义检查，作为构建前的门禁。

## 三、中危

### M1. `collect()` 的 `count` 语义与实际不符，会误导报告读者

`app/pipeline.py:107-110`：

```python
db.execute("INSERT OR IGNORE INTO items VALUES (?,?,?,?,?,?,?,?)", (...))
count += 1
```

`count` 无条件自增，**不管 INSERT 是否被 IGNORE**。所以 `coverage.count` 是"本次 feed 里看到的条目数"，不是"新入库条目数"。

更要紧的是 collect 每 3 小时重读同样的 `feed.entries[:60]`，**count 会几乎不变**。而报告附录直接印 `{source}: {count} 条`（`pipeline.py:178-179`），读者会理解成"这次采到 60 条新资料"。

建议：用 `db.total_changes` 前后差值取真实新增数，或把字段/文案改成明确的"feed 条目数"。

### M2. 文件锁按 action 分文件，挡不住 collect 与 report 并发

`app/pipeline.py:231`：锁文件是 `ROOT / (action + ".lock")` —— `collect.lock`、`report.lock`、`publish.lock` 是三把**互不相干**的锁。

注释写的是"File lock supplements CronJob Forbid for manually created jobs on the same PVC"，但 `concurrencyPolicy: Forbid` 只在**单个 CronJob 内**生效，跨 CronJob 的 collect/report 并发它管不着。而两者都开同一个 `sources.sqlite`。

实际风险不高（collect 在每 3 小时的 :15，report 在 20:00，正常不重叠），但既然设计意图是"防止同一 PVC 上的并发写入"，就该用一把共享锁，否则这行注释承诺的东西没有兑现。

### M3. 发布内容不经过任何净化

`app/pipeline.py:180-181`：`content = report + appendix` 直接发出去。`report` 是模型输出——prompt 里写了"不使用 Markdown 表格或 HTML"（`config/report-prompt.txt:14`），但**没有任何强制**。

如果 Hublog 前端渲染 HTML，模型输出里的标签会被渲染。`appendix` 是程序生成的（只含源名、计数、异常类型名），安全。

**需要确认 Hublog 侧是否转义**。若转义，这条降为提示。

### M4. `clean()` 先剥标签后 unescape，实体可以重新变成标签

`app/pipeline.py:89`：

```python
html.unescape(re.sub(r"<[^>]+>", " ", str(text)))[:limit]
```

顺序反了。`&lt;script&gt;` 在剥标签阶段不是标签（剥不掉），unescape 之后才变成 `<script>`。正确顺序是先 unescape 再剥。

影响面有限（进的是 prompt，不是最终发布内容，且 prompt 明确声明来源不可信），但改起来是一行。

### M5. `public_get` 只连解析出的第一个地址，无回退

`app/pipeline.py:59`：`PinnedHTTPS(part.hostname, sorted(addresses)[0])`。

取的是**字典序最小**的地址，不轮换、失败不回退。README 自己说"部分来源在国内可能不可达"——如果某个源的第一个地址恰好在黑洞里，这个源会**每次采集都记一条 error**，永远不尝试其它可用地址（比如同一个域的 IPv6 或其它 A 记录）。

建议按顺序逐个尝试，全部失败才算该源失败。

### M6. oauth2-proxy 用 httpGet 探针，但 `default-deny` 关掉了全部 Ingress

`render.py:99` 的 `default-deny` 对所有 Pod 同时关闭 Ingress 和 Egress。同一个 Pod 里：

- dashboard 用 **exec** 探针（`render.py:56-57`）—— 不受 NetworkPolicy 影响
- oauth2-proxy 模板用 **httpGet** 探针（`oauth/k8s/hermes-proxy-container.yaml` 的 `/ping`）—— 流量来自 kubelet

kubelet 探针流量通常来自节点而非 Pod，多数 CNI 默认放行；但**不是所有 CNI 都这样**，被拦时表现为 Pod 永远不 Ready。

顺便：同一个 Pod 里两种探针风格，容易让人以为是随手写的。建议加注释说明 dashboard 用 exec 是因为它绑了 `127.0.0.1` 而非 0.0.0.0。

## 四、低危 / 建议

**L1. dashboard 容器是真的 root。** `render.py:55` 给它加了 `capabilities.add: [CHOWN, FOWNER, DAC_OVERRIDE, SETUID, SETGID]`。README 明确写"当前不声称满足 Pod Security restricted"、不改成 privileged，态度是对的。但**它和 oauth2-proxy 同 Pod**，共享 network namespace——root 的 dashboard 可以访问 Pod 内所有地址。这是上游 s6 入口的结构性约束，不是代码问题；记一笔，将来上游支持非 root 启动时应收回到 restricted。

**L2. Dockerfile 的 `A && B || C` 会掩盖 pip 的真实失败。** `Dockerfile:6-8` 里 `pip install` 失败会静默转去 `uv pip install`。两者对同一 requirements 的行为未必一致，构建结果不可预期。建议拆成显式 if/else 并把错误打出来。

**L3. `publish()` 对 2xx 响应体缺字段没有防御。** `app/pipeline.py:211-212`：`post = json.loads(data)` 后直接 `post["id"]`。Hublog 返回 2xx 但结构变化时会 `KeyError`，报错信息很难懂。有幂等键兜底不会重复发文，但建议显式校验字段并抛清晰错误。

**L4. `Namespace` 被创建两次**（`deploy.sh:11` 与 `render.py:24`）。无害。

**L5. `deploy.sh` 只做 `kubectl apply`，没有 server-side dry-run。** `render.py` 已经校验了占位符和摘要，够用；可选用 `--dry-run=server` 提前暴露 schema 问题。

## 五、需要实测确认的清单

代码里已经写好、但**必须上服务器验证**的项（README 的验收清单已覆盖大部分，这里补上本次评审新增的）：

| 项 | 为什么 |
|---|---|
| Hublog 出站能否连通 | H1，取决于 CNI 的 DNAT 匹配时机 |
| Hermes CLI 参数与镜像摘要在语义上匹配 | H2，不匹配要运行期才发现 |
| oauth2-proxy 的 httpGet 探针是否被 NetworkPolicy 拦 | M6 |
| Hublog 渲染是否转义 HTML | M3 |
| `coverage.count` 在报告里读起来是否会被误解 | M1，看第一份 `payload.json` 时留意 |

## 六、与方案层评审的关系

[hermes-intelligence-review.md](hermes-intelligence-review.md) 里几条针对"现网无先例"的批评，**已经被这份代码解决了**：

| 方案层评审当时说的 | 现在 |
|---|---|
| 「单用户白名单在现网无先例，oauth2-proxy 是 `--email-domain=*`」 | 已用 `--authenticated-emails-file` 实现，是仓库首份 |
| 「独立 cookie 需要覆盖 cookie-name + domain，属新设计」 | 已用 `__Host-hermes` 且不设 domain，三条前缀约束都满足 |
| 「MFA 零痕迹」 | 交给 Casdoor 侧配置，方向正确 |

仍未解决的（与代码无关，是排期问题）：

- **ARM64 + ARM64 内 CLI 契约** 仍未实测 → 这就是 H2
- **「看到第一份产出」的路径仍偏长**：初始 CronJob 全部 `suspend: True`，且要先完成 README 的 14 项验收清单
- **成本记账**：`MAX_DAILY_ATTEMPTS` 限的是**模型调用次数**（默认 2 次/天），不是金额。README 也承认"Token 轮数限制不等于金额硬上限，供应商账户应另设每日费用额度"。这与我此前指出的"没有持久化账本"一致，目前靠供应商侧额度兜底——可以接受，但要确保在供应商侧真的设了。
