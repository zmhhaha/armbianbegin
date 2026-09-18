# docs/ 索引

本目录是设计与调研笔记。**实现规格以 OpenSpec store 为准**（`armbianbegin` 项目，见仓库根的 `.openspec-project.json` 与 `AGENTS.md`）；这里放的是过程材料、现状调查和决策记录。

## 平台现状调查（动手前先读）

2026-09-16 的一次全仓库调查，代码基准 HEAD `3dd4128`。**目标是回答"新服务该怎么做"，并列出"哪些东西已经有了、别重复造"。** 行号会随代码演进漂移，引用前先核对。

| 文档 | 回答什么问题 |
|---|---|
| [platform-auth-ingress-survey.md](platform-auth-ingress-survey.md) | 要把内部 web 服务暴露到公网并做认证，该怎么做？现网的单用户白名单、MFA、会话 cookie 是什么状态？WebSocket/SSE 怎么配？ |
| [platform-k8s-conventions.md](platform-k8s-conventions.md) | 新增一个服务，manifest / namespace / 存储 / 镜像 / 资源 / 定时任务按什么约定写？集群有多大？ |
| [platform-reusable-capabilities.md](platform-reusable-capabilities.md) | 集群里已经有哪些可复用能力（LLM 网关、RAG、embedding、ES、邮件、定时采集框架）？哪些东西容易被重复造？ |

三份合起来的要点：**`content_agents` 已是一套完整的定时采集→中文报告框架；`llm-service` 是统一 LLM 入口（14 个消费方已迁移）；RAG/embedding/ES 检索层已建好且可扩展；周期性任务一律用 K8s CronJob。**

## 专题调研

| 文档 | 主题 |
|---|---|
| [rag-service-spike.md](rag-service-spike.md) | RAG 可行性实测（2026-09-10）：ES/embedding 基准数据、索引 schema 草案、容量估算。注意草案里的字段与实际实现的 mapping 有出入，以代码为准 |
| [llm-service-abuse-defense.md](llm-service-abuse-defense.md) | 防止调用方把 llm-service 当通用 LLM 白嫖的调研（2026-09-11）：威胁模型、杠杆排序、落实状态 |
| [jdwatch-work-research.md](jdwatch-work-research.md) | `jdwatch.work` 就业信息采集方式调研（2026-09-04）：结论是职位聚合站 + 自动化爬虫管道 |
| [ARC.md](ARC.md) | Actions Runner Controller 科普与部署指南。与 RAG/情报方向无关 |

## 决策记录

| 文档 | 记录了什么 |
|---|---|
| [hermes-code-review.md](hermes-code-review.md) | 对 Hermes 已写代码的评审（2026-09-16 初评，**2026-09-17 修订**：代码大幅改动且已部署）。当前仍存 1 高危 —— Hublog 出站 NetworkPolicy 写 8080 而实际连 80；另有 6 中危、5 低危。也记录了 SSRF 防护、凭据最小权限分离、双层认证等做得好的地方 |
| [hermes-intelligence-review.md](hermes-intelligence-review.md) | 对 OpenSpec change `add-hermes-geopolitical-intelligence` 的**方案层**评审（2026-09-16，同日两次修订）。**未改动该 change 本身** |
