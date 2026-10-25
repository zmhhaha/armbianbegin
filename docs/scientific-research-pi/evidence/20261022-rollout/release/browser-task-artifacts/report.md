# 检索增强生成如何减少大模型幻觉：摘要证据简报

## 范围（Scope）

本简报关注 RAG 如何改善生成内容的事实性，以及这种改善的边界。采用目的性小样本，最多使用两篇 arXiv 摘要；本次纳入原始 RAG 论文（2020）与 Self-RAG（2023）。不设置发表年份过滤，实际样本年份为 2020、2023；这是简报，不是系统综述，也不代表截至检索日的全部研究。

## 方法（Methods）

实际检索于 2026-10-22（UTC）进行。arXiv 使用以下精确标题查询，各限制返回 1 条：`ti:"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"` 与 `ti:"Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection"`。Crossref 另以这两个完整标题（不含 arXiv 的 ti 语法）分别检索，各限制返回 1 条。四次请求均成功，各观察到 1 条返回记录；没有来源报错。检索记录保存在 searches.jsonl。返回条数是适配器观察到的行数，不是数据库命中总数。

按 DOI、PMID 或标题去重后，实际观察到 4 篇不同作品，逐篇筛选：纳入 2 篇 arXiv 论文，排除 2 篇 Crossref 返回的不同作品，无待定记录。纳入条件为实际取得 arXiv 摘要且直接讨论检索生成及事实性；Crossref 仅用于书目核对，不作为本简报的科学证据。

Crossref 标题检索分别返回《Retrieval‐Augmented Generation》（2026，DOI：10.1002/9781394374717.ch03）和《Learning to Retrieve, Generate, and Compress: A Unified View of Efficient RAG》（2025，DOI：10.20944/preprints202508.1211.v1），均不匹配目标论文。随后对这两个返回 DOI 逐一执行 Crossref 标识符查询，均返回相同 DOI，核对时间分别为 2026-10-22T11:27:58Z、2026-10-22T11:28:10Z。这只确认被排除作品的标识符，不证明其科学结论，也不能把 DOI 移配给目标论文。两篇纳入论文均未获得匹配的 Crossref DOI，其 DOI 保持 null、核验状态为 unknown；有限的检索不能证明它们没有 DOI。完整核验来源与时间保存在 papers.jsonl。

## 发现（Findings）

<!-- claim:C1 -->
RAG 减少事实性错误的一条路径，是让生成过程利用检索得到的外部材料。原始 RAG 摘要中的实现，把预训练 seq2seq 模型与维基百科稠密向量索引结合，由神经检索器提供片段，再以这些片段为条件生成文本。作者报告，在其语言生成任务中，RAG 比所比较的纯参数 seq2seq 基线生成更符合事实的语言；这支持“检索材料可以改善事实性”的有限结论。[1]

<!-- claim:C2 -->
检索材料还需要被恰当地选择和利用。Self-RAG 摘要指出，无视检索是否必要、片段是否相关而固定加入若干片段，可能导致无帮助的回答。其方法按需检索，并使用特殊的反思 token 对检索片段和生成内容进行反思；作者报告，相较所比较模型，长文本生成的事实性与引用准确性有所提升。这提示，减少幻觉需要关注检索的相关性及生成过程对证据的使用。[2]

## 局限（Limitations）

所有科学结论仅依据上述两篇 arXiv 摘要，未获取或阅读全文，也未下载 PDF；full_text.available 均为 false。观察到的 Crossref 摘要不参与科学综合。未评定同行评审状态，未独立复现实验。摘要报告的结果均按作者报告转述，无法核查完整方法、评估协议和失败案例。两个精确标题查询及每次 1 条的返回上限，使样本覆盖很窄，可能漏掉相关研究；没有观察到其他证据，不能据此宣称没有反例或领域争议。

<!-- claim:C3 -->
对于“RAG 能把幻觉降低多少、能否保证回答正确、能否适用于所有领域”，本次证据不足。原始 RAG 摘要未给出事实性改善的数值及完整评估样本数，Self-RAG 摘要也未提供足以统一计算改善幅度的数值和评估细节；两篇结果不能合并成通用的幻觉降低比例，也不能外推为正确性保证。[1] [2]

## 参考文献（References）

[1] Patrick Lewis 等（2020）. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. arXiv:2005.11401v4. http://arxiv.org/abs/2005.11401v4 。证据层级：摘要；匹配的 Crossref DOI 未获得，核验状态 unknown。

[2] Akari Asai, Zeqiu Wu, Yizhong Wang, Avirup Sil, Hannaneh Hajishirzi（2023）. *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*. arXiv:2310.11511v1. http://arxiv.org/abs/2310.11511v1 。证据层级：摘要；匹配的 Crossref DOI 未获得，核验状态 unknown。
