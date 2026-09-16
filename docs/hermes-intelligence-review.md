# Hermes 情报助手方案评审（`add-hermes-geopolitical-intelligence`）

> 评审时间：2026-09-16。**同日两次修订**，见「修订记录」。
> 评审对象：OpenSpec store 中未归档 change `add-hermes-geopolitical-intelligence`（项目 `armbianbegin`）。
> 本文不改动该 change。tasks.md / proposal 维持原样，本文作为决策记录。
> 配套阅读：[platform-auth-ingress-survey.md](platform-auth-ingress-survey.md)、[platform-k8s-conventions.md](platform-k8s-conventions.md)、[platform-reusable-capabilities.md](platform-reusable-capabilities.md)。

## 已定的前提（本文按此评审）

1. **Hermes 是独立服务，有自己的 LLM 接入方式**，不跟 `llm-service` 走统一接入。
2. **只服务所有者一人。**
3. **程序员就业采集是给 Hermes 的一个新任务**，不影响现有服务。**目的是看效果**——做得好再谈后续。

> ⚠️ 第 3 条的含义：这是**评估性任务**，不是交付项目，更不是接替工程。**不要**为它设计并行期、判定矩阵、退役流程——那是过度设计。

## 结论摘要（TL;DR）

主要问题不在方向，而在**执行前提没验证、任务不可验收、以及"看效果"这条路径太长**：

1. **ARM64 是单点前提，却被降级成第 1 条普通 task**，且没有失败退路。这条不落实，后面 15 条全部空转。
2. **16 条 task 里，"看到第一份产出"排在最末尾**（一周 shadow 测试是第 14 条）。评估任务应该反着排——最短路径先出结果，再迭代。
3. **没有说清"看效果"看什么**。一周后如果只有一堆报告，看不出 Hermes 好在哪。
4. **design 要求的"单用户白名单 + MFA + 独立 cookie"在现网没有先例**，oauth2-proxy 现状是放行任何 Casdoor 用户。
5. **"Configure Cloudflare Tunnel routing" 是手工控制台操作**，不可提交、不可回滚审计。

## 修订记录（2026-09-16）

本文初版两侧判断都错了，均已撤回：

| 初版判断 | 处置 | 依据 |
|---|---|---|
| 「程序员就业采集与 `programmer_jobs_agent` 重复，是重复建设」 | **撤回** | 该采集是 Hermes 侧的新任务，是刻意的新工作 |
| 「Hermes 应走 `llm-service` 统一接入」 | **撤回** | Hermes 自带 LLM 接入是已定决策 |
| 「这是接替项目，需要并行期 / 判定标准 / 退役动作」 | **撤回** | 用户明确：不是接替，就是个新任务，主要看效果 |

第三条尤其值得记一笔：**初版把"如果做得好可能替代现有服务"放大成了"接替工程"**，为它设计了并行期、判定矩阵和退役流程——这正是本文批评 proposal 的同一个毛病（把简单目标复杂化）。评估任务就该以评估的方式做。

## 一、ARM64 是单点前提，被降级成了普通 task

tasks.md 第 1 条是 "Confirm the Hermes image version, ARM64 support, startup command, web port, and persistent data paths"。

上游情况（**我未能直接核实，见第六节**）：搜索结果显示存在 issue #3913「Docker images for linux/arm64 missing」、issue #5554「Is there any plan to support ARM64/v8 for this Docker image?」，以及一个「fix(ci): build and push multi-arch Docker image (amd64 + arm64)」的 CI 修复 PR —— 说明 **arm64 镜像是后来才补上的**，必须钉死在那个提交之后的版本。

而且"上游不给我就自己 build"在这个仓库里不是一条免费退路：**全仓没有 amd64 构建目标、没有 buildx manifest list**，全部是 `docker build --platform linux/arm64` 单平台（见 [platform-k8s-conventions.md](platform-k8s-conventions.md) 第六节）。

**这条不落实，后面 15 条全部空转。** 应该是前置门禁（时间盒 spike），不是 task 1。

> ✅ **已澄清（2026-09-16 晚）**：Hermes 相关代码**已经写好了**（`panghu_chat/hermes/` + `oauth/`、`vault/`、`cloudflare-tunnel/` 下的 `hermes-*`，全部未提交），但**尚未构建镜像、未部署**。此前"store 里 16 条 task 全未勾选、仓库内 `grep hermes` 零命中"的观察，是因为代码在该时点之后才写出来。
>
> 这意味着本节关注的 ARM64 问题**形式上缓解了**（`build.sh` 强制 `HERMES_IMAGE` 必须带 `@sha256:` 摘要，`render.py:10-12` 也二次校验），但**实质门禁仍在**：镜像里有 arm64 manifest ≠ 镜像里的 CLI 契约对得上。具体见 [hermes-code-review.md](hermes-code-review.md) 的 H2。

## 二、评估任务应该先出产出，而 tasks.md 是反着排的

当前 16 条 task 的顺序大致是：确认镜像 → 建 namespace → 写 manifest → 配 Cloudflare → 配 Casdoor → 配 cookie → 调度器 → **定义五个数据源** → 归一化去重 → 配时间表 → 限流 → 网络限制 → 备份 → **一周 shadow 测试** → 安全验证 → 运维文档。

也就是说：**"看到第一份报告"在第 14 条**，前面 13 条全是基础设施和安全加固。

对交付项目这没问题。但这是个**评估任务**——你要回答的是"Hermes 干这个活行不行"，不是"上线一个生产服务"。评估的最短路径是：

```
能跑起来 → 接一个数据源 → 出一份中文报告 → 你看看 → 再决定加不加后面这些东西
```

按现在的排法，你在投入 13 条基础设施工作之后才能知道 Hermes 到底行不行。**建议把顺序倒过来**：先打通"一个数据源 → 一份报告 → 你能看到"，把认证、网络策略、备份、运维文档都推到确认值得继续之后。

## 三、"看效果"要看什么，没写

一周之后你手上会有 7 份报告。如果事先没定看什么，这 7 份报告说明不了什么。建议先定 3–5 个你能一眼判断的观察点，例如：

- **时效**：当天的事有没有进当天报告，延迟多少
- **覆盖**：漏了什么明显的、多了什么无关的
- **可信**：事实 / 官方表态 / 分析三者的区分做得怎么样，有没有编造
- **可用**：你自己愿意读吗，读完有收获吗
- **成本**：一周烧了多少 token / 多少钱

最后一条尤其要有——见第五节第 1 条，这条**没有现成基础设施兜底**。

### 3.1 现成参照物：`programmer_jobs_agent` 的日报

不用另做基线设计。`programmer_jobs_agent`（`panghu_agent/content_agents/`）**每天 20:00 已经在产出中文招聘日报**（`content_agents/k8s/cronjobs.yaml:89-94`），周报在周日 20:30（`:129`）。

同一个题材、同一天，两边的报告放一起看，Hermes 的差异一眼可见——强在哪、弱在哪、值不值得继续。这是"看效果"最省力的方式，不需要任何并行期机制。

它的数据源调研也已经做完，**不要重做**：

- `programmer_jobs_agent/Reference.md` —— RSS / 公开 API / 开源聚合器分类清单
- `docs/jdwatch-work-research.md` —— `jdwatch.work` 采集方式调研

礼貌抓取（详情页间随机 3–10s、403/429 停手，`main.py:426-447`）和 JSON-LD 解析（`main.py:85-140,378-393`）都有现成写法可参考。

> 💡 评估期建议：**先只产出给你看的报告，不要往 Hublog 发布**。这样输出干净、便于对比，也不会和现有 agent 的内容混在一起。

## 四、认证设计与现网的差距

design.md 的 Safety and Isolation 要求 exact user allowlist + MFA + 独立安全 cookie + 保留 WebSocket/streaming。实际情况（详见 [platform-auth-ingress-survey.md](platform-auth-ingress-survey.md)）：

| design 要求 | 现网状况 |
|---|---|
| exactly the owner's account | oauth2-proxy 是 `--email-domain=*`，**放行任何 Casdoor 用户**（`oauth/k8s/secret.yaml:21`）。全仓无 `--authenticated-emails-file` / `--allowed-group` |
| require MFA | **全仓零痕迹**。grep `mfa\|totp\|2fa\|two-factor` 无有效匹配 |
| 独立的 secure cookie | 所有 oauth2-proxy **共用一份 cookie secret、同名 cookie `_oauth2_proxy`、domain `.panghuer.top`**（`oauth/k8s/proxy-deployment.yaml:60-78`）。要独立必须覆盖 cookie-name + domain，属新设计 |

**现成的正确做法不是 oauth2-proxy**，而是 `openspec_service` 的模式：直连后端 + 应用内 JWT 鉴权 + 用 JWT `sub` 做单用户白名单：

- `openspec_service/k8s/core.yaml:26` — `BOOTSTRAP_ADMIN_SUBJECTS: "27714443"`
- `openspec_service/src/config.mjs:19`、`rest.mjs:153` — `if(!config.bootstrapSubjects.has(sub)) throw forbidden();`
- 路由先例：`cloudflare-tunnel/operator/openspec-service-route.yaml:10-11` 直连后端、绕过 oauth2-proxy

"只服务一个人"这个前提让这条路更好走——单用户白名单不需要组、角色或成员管理。

> 评估阶段其实可以更省：如果这一周你只是想看效果，先不暴露公网也行（ClusterIP + 内网访问），把整套认证推到确认值得继续之后。这样第二节的"最短路径"又能短一截。

### 4.1 "Configure Cloudflare Tunnel routing" 不是代码任务

实际生效的路由在 **Cloudflare 后台**，仓库里的 `tunnel-routes.yaml` 只是备份，`kubectl apply` 不生效（`cloudflare-tunnel/README.md:79-81`）。

排期含义：这条 task 是**手工控制台操作**，不可提交、不可回滚审计。必须标注。

## 五、独立 LLM 接入带来的两处覆盖缺口

这一节不是对决策的反对，是把后果写清楚以便**有意识地接受**。两处在评估期就会碰到。

**1. 成本没有兜底，而且没有现成账本。** `llm-service` 的 per-caller 限流和 `GET /v1/usage` 都不覆盖 Hermes。而且要注意：`llm-service` 的用量计数器本身是**进程内存态、Pod 重启归零**（`llm-service/app.py:53-56`）——**就算**走统一接入也不能当账本。所以"一周烧了多少"这个数字，Hermes 侧得自己有持久化记账，否则第三节的成本观察点拿不到数。

**2. 已有的注入防护不覆盖 Hermes。** `llm-service/guard.py` 提供 spotlight（不可信内容包裹）、canary（套话检测）、detection（攻击形态正则），当前只作用于走它的调用方。Hermes 每天吞大量抓来的网页，design.md 自己也写了 "Web content is untrusted data and must not become an instruction" —— 这句话要落到实处，需要 Hermes 侧有等价机制，或者明确接受没有。评估期正好可以顺便看看它会不会被网页内容带跑。

## 六、本次评审的证据限制

**我没有能直接读到 Hermes 上游文档。** `github.com`、`hermes-agent.nousresearch.com`、`deepwiki.com` 都被本环境的网络策略拦住了（`WebFetch` 报 "Unable to verify if domain is safe to fetch"）。

因此第一节关于上游的结论，**全部来自搜索结果的标题，不是原文**：issue #3913、#5554、PR #6124 的标题；cron 相关是文档页 "Cron Internals" / "Scheduled Tasks (Cron)" / "Cron Troubleshooting" 的标题，以及 issue #110650 的标题。

**spike 必须实测确认，不能采信本文的推断。** 若 Hermes 已经部署起来，这些自然作废。

仓库内的结论都有 `文件:行号` 证据，基于 HEAD `3dd4128` 的调查；行号会随代码演进漂移，引用前先核对。

## 七、其他 task 层面的问题

| # | 问题 | 说明 |
|---|---|---|
| 1 | **没有一条有验收标准或产出物** | 对比 `add-rag-service` 的 tasks.md：粒度类似，但每条能去代码里找证据，还附了逐条核对的 verification note |
| 2 | **没有依赖顺序和门禁** | ARM64 那条应该前置；现在 16 条是平铺的（见第二节） |
| 3 | **"Define source connectors for 5 areas" 一行 = 五个难度差一个数量级的工作流** | RSS 好办，官方发布要解析，"mainland employment" 实测最难（`docs/jdwatch-work-research.md` 的结论是对方靠浏览器自动化 + 可能有登录态）。评估期建议**先做最简单的那一个** |
| 4 | **没提 robots / 抓取频率 / ToS** | content_agents 的礼貌抓取先例（3–10s 随机、403/429 停手）可直接抄 |
| 5 | **调度归属没选定** | "Only one scheduler may be authoritative" 只是担心，没有机制。仓库既有约定是"周期性任务用 K8s CronJob，应用内不做调度"，但 Hermes 自带原生 cron。走哪条需要**显式选定并写明**，否则就是双调度器 |
| 6 | **备份 task 没有恢复演练** | 没验证过的备份等于没有备份。design 提到 "backup outside Hermes write access" 是对的，task 没体现。评估期优先级不高，可以推后 |

## 八、可立即执行的小事

1. `add-rag-service` 已 42/44 完成，剩两条是明确放弃/延后的，且主 spec 里没有对应 requirement → **可以归档**。
2. `add-project-portal` 已废弃且未归档，其 spec 里的门户与 runner 需求并未实现 → 归档会把未实现需求合进主 specs，**保持未归档是对的**。
3. 若 Hermes 确已部署：tasks.md 的 16 条未勾选状态与实际不符，应据实更新（这正是 `add-rag-service` 遇到过的 taskStatus 滞后问题）。
