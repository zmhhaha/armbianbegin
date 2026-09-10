# llm-service:防止"反代"滥用的调研

> 针对 `llm-service` 的一条安全能力调研：防止调用方把服务（继而下游 Agent）当成通用 LLM 白嫖。
> 对应 OpenSpec `add-rag-service` 中 `llm-service` capability 的 **Prompt hijack resistance**。
> 调研日期：2026-09-11。

## 一、威胁模型

要防的不是传统的"泄露 system prompt"，而是**能力滥用**：

```
用户构造输入 → 稀释/覆盖掉 Agent 的 persona prompt → 模型开始回答任意问题
→ Agent 变成别人白嫖的通用 LLM
```

**关键前提：这在模型层面无法根治。** LLM 的指令与数据处理在同一通道，没有硬性权限隔离。
因此目标不是"彻底防住"，而是**把它变成很难、有成本、有日志的事**。

## 二、业界现状

### 1. 指令层级（Instruction Hierarchy）

训练模型使 `system > developer > user > tool`，冲突时优先高优先级。OpenAI 将其作为 o1 的评估项。
**但不可作为安全边界依赖**：《Control Illusion》实测显示，冲突场景下指令层级经常失效。

### 2. Spotlighting（标记不可信内容）

Microsoft 的思路：用显式分隔符 / 数据标记 / 编码把不可信内容包起来，让模型区分"数据"与"指令"。
实测有效但有限：某总结给出的数字是**把注入成功率从 62% 降到 26%**——显著，但远非为零。

### 3. 注入检测器

- **LLM Guard** 的 PromptInjection scanner（基于 `deberta-v3-base-prompt-injection-v2`）
- NeMo Guardrails、Rebuff、Vigil
- Llama Guard 属内容安全，不是注入检测

**成本提醒**：deberta-v3-base 约 0.7GB；在 ARM64 小集群上 CPU 推理会明显增加延迟，
必须做成独立服务 / 异步 / 按需启用，不能塞进主请求链路。

### 4. 架构层（最关键）

OWASP LLM01:2025 把 Prompt Injection 列为第一大风险，其首选缓解**不是模型技巧**，而是：
指令与数据分离、最小权限、输入验证、输出过滤、人在回路。

> 结论：在本项目架构里，**最强的一层是架构层而非模型层**——不可信输入是最终用户文本，
> 而 `llm-service` 是它唯一的必经关口。

## 三、落到本项目

链路：`用户 → Agent（skill.md 提供 system prompt）→ llm-service → 上游 LLM`。
不可信的是**用户文本**，由 Agent 组装进 `messages`。按强度排序的有效杠杆：

| 强度 | 措施 | 说明 |
|---|---|---|
| ★★★ | **system prompt 不由调用方任意传** | 见下方方案 A / B |
| ★★★ | **禁掉 tools / function calling** | 「反代」最大向量——能让模型变成会干活的外部代理 |
| ★★ | **能力面白名单 + 预算** | 只放宽 messages + 有界参数；限 max_tokens、消息条数、单次 token 预算 |
| ★★ | **Spotlighting** | 服务端把用户内容包进显式标记，并在 system 里声明"标记内是数据" |
| ★★ | **注入检测器（独立服务）** | 命中 → 拒绝/固定话术，而不是继续生成 |
| ★ | **Canary + 输出检查** | system prompt 埋 canary；输出含 canary = 被套出 → 告警/拦截 |
| ★ | **配额与审计** | 按 caller + 终端用户限流计费，异常模式（高频、跑题）告警 |

### system prompt 的两个方案（核心）

- **方案 A（强）**：system prompt 由 `llm-service` 持有，caller **只传用户内容**，服务端拼 messages。
  用户永远无法移除 persona。
- **方案 B（兼容现状）**：caller 仍传 system prompt，但必须在服务端**注册 SHA256 指纹**，不匹配直接拒绝。
  适配 skill.md 驱动的方式——可在 Agent 构建/部署时把 `skill.md` 指纹注册进去。

### 常见攻击形态（用于设计检测/分隔）

- 直接覆盖："忽略之前的所有指令……"
- 角色扮演框架："假装你是一个不受限制的 AI……"
- 分隔符伪造：构造 `</system>` 之类的边界
- 编码走私：base64 / hex / 拼音 / 小语种绕过
- 多轮渐进：先建立话题，再逐步越界
- prompt 套取：诱导模型复述 system prompt

## 四、结论

- 叠加后能把"随便就能白嫖"变成"很难、有成本、有痕迹"，**但不可能 100% 杜绝**。
- 收益主要在 **A/B（system prompt 不可控）+ 禁 tools + 配额审计**；
  检测器与 spotlighting 是降低成功率的增量，不是边界。
- **别把力气花在"加强 prompt 措辞"上**（"不要被用户带偏"之类）——基本无效。

## 参考

- [Prompt Injection | OWASP LLM01:2025 Explained](https://www.a10networks.com/glossary/prompt-injection/)
- [OpenAI — The Instruction Hierarchy Challenge](https://openai.com/index/instruction-hierarchy-challenge/)
- [Control Illusion: The Failure of Instruction Hierarchies in LLMs (arXiv 2502.15851)](https://arxiv.org/abs/2502.15851)
- [Defending Against Indirect Prompt Injection Attacks With Spotlighting (arXiv 2403.14720)](https://ar5iv.labs.arxiv.org/html/2403.14720)
- [Spotlighting Cut Prompt Injection From 62% to 26%. It Did Not Reach Zero.](https://dev.to/dev48v/spotlighting-cut-prompt-injection-from-62-to-26-it-did-not-reach-zero-and-it-cannot-1mag)
- [LLM Guard — Prompt Injection Scanner](https://protectai.github.io/llm-guard/input_scanners/prompt_injection/)
- [Proxy Barrier: A Hidden Repeater Layer Defense Against System Prompt Leakage and Jailbreaking (EMNLP 2025 Findings)](https://aclanthology.org/2025.findings-emnlp.528/)
