独立科学审阅结论：**通过，无阻断项。** 本次审阅针对生产专用 canary 任务 `fd86d43c-13f1-5766-a8d1-bcff2fcc9d1b` 的“局限”章节修订。逐句阅读了原稿、候选、两篇实际保存的摘要、E1/E2、原/候选 claims、references、revision_output 与 comparison；未运行模型、访问全文、重新检索或直接读写数据库。

第一条新 claim `revision_limits_1` 准确保留 Lewis 等摘要的“RAG 与维基百科稠密索引结合、相对纯参数基线提高事实性”，以及 Asai 等摘要的“固定检索忽略必要性/相关性可能生成无帮助回答、按需检索和反思相结合后相对其指定基线改善长文本事实性及引用准确性”。候选明确各自报告范围，没有把 Self-RAG 对 ChatGPT/检索增强 Llama2-chat 的摘要结果转述为对 Lewis RAG 的直接胜出。“检索内容及其使用方式值得共同考察”是有限的综合建议，紧接着声明不足以确立跨研究改善幅度。

第二条新 claim `revision_limits_2` 对应 E1 缺少事实性评估细节、效应量和统计不确定性，以及 E2 缺少具体数值、误差和控制实验。它将缺口明确归于“固定证据”，没有断言原论文全文也缺少这些内容。候选拒绝从两份摘要推断 Self-RAG 优于 Lewis RAG、分离检索与反思的独立贡献、推广到所有场景或保证消除事实错误，并说明全文核验及进一步控制实验仍有必要。此限定与实际取得的摘要层级相符。

两条新 claim 都保持 `assessment=insufficient`，证据集合为 E1/E2，明确沿用原 C3 的不足判断，未提高支持强度。未改的 C1/C2 仍分别引用 E1/E2、保持 supported 及原 explanation。引用 [1] 对应 Lewis 等 *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*（arXiv:2005.11401v4），[2] 对应 Asai 等 *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*（arXiv:2310.11511v1），paper_id 关联正确；两篇均仅取得摘要，标识符独立核验仍 unknown。新正文没有性能数字或新文献，也没有本次已读全文或完成新检索的表述。

独立字节/关联检查结果：

- 原稿 1524 字节，SHA-256 `3442677c39a8a26cca304d483c2b1e97b0dcce3ad81062a1f3d30e3f6258407d`；候选 2376 字节，SHA-256 `4952c189cf72f72acc54ea66acfbf117581bedb8271305b02ed659212749f8ed`，分别与 receipt/comparison 的 parent/candidate 摘要一致。
- 原目标范围 `[907,1207)`，300 字节；新目标范围 `[907,2059)`，1152 字节。前 907 字节、后 317 字节完全保持；候选目标与 candidate-section、comparison.after、revision_output.section_markdown 完全一致。
- 候选章节 SHA-256 `48d05a1178ba6028574b127e610a81194370f5d589f817d28697f7b513646e73`；标题“局限”保持。papers、evidence、references 原/候选逐字节一致；外部 C1/C2 记录一致。

生产 API receipt 另记录同意图 start 重放仍是同一任务、显式采用及采用幂等恢复成功，selection_revision 从 0 变为 1，采用 ID `c3cce5ba-9487-55f3-bd56-8d732a2c0ecd`；原件下载保持、版本精确下载和匿名/外部身份隔离通过。这些是 API 运行证据，实际 worker/model provenance 由另一项独立审计确认，不由本次文章阅读反推。

首次任务 `6402d618-747c-580a-8e90-cf49ab96ae58` 的 `unsupported_assessment_upgrade` 拒绝保留为真实失败及保守校验证据，不能称为瞬时错误。现存材料不足以确定当时触发的是相同 claim ID 子集还是完整不确定证据集合分支。本次使用根提交 `f9f13893754b79697deb94571c6cc793e6fde9e6` 的独立新意图，明确保留不确定判断；未放宽 runtime 或科学校验。

非阻断的文字改善：第一段重述了一部分“发现”章节，今后可在保持限定的前提下缩短重复内容。不过本次修订的目标是明确摘要比较局限，现有两段达成目标，不需要重跑。

通过范围为本次专用 canary 新写的章节、证据与不变量；不推广为两篇论文的全文质量评价，也不表示 RAG 与 Self-RAG 的独立对照实验已经完成。
