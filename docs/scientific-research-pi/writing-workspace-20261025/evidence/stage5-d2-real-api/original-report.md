# 范围
仅对照Lewis等2020年RAG与Asai等2023年Self-RAG原始研究，讨论检索如何影响事实性；检索于2026年10月23日完成，不扩展至其他研究。

# 方法
以两篇arXiv编号精确检索，各返回1条；去重后筛选2篇，均纳入，无排除。仅取得摘要，未读全文；无来源错误，标识符未独立核验，验证状态未知。

# 发现
<!-- claim:C1 -->
RAG将生成模型与维基百科稠密索引结合。Lewis等摘要报告，相比纯参数生成基线，输出更具体、多样且更具事实性，支持外部检索可改善事实表达的有限结论。[1]

<!-- claim:C2 -->
Self-RAG摘要指出，忽略检索必要性及段落相关性的固定检索可能产生无帮助回答。其用反思标记按需检索并评议段落与生成，报告长文本事实性及引用准确性优于其比较的ChatGPT和检索增强Llama2-chat。[2]

# 局限
<!-- claim:C3 -->
两篇摘要提示，应结合检索内容与使用方式理解事实性改善；但缺少全文指标、误差及控制实验，证据不足以量化两者差距、分离检索与反思贡献，或保证消除错误。本简报仅作两篇摘要的定性对照。[1] [2]

# 参考文献
[1] Lewis等（2020）. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. arXiv:2005.11401v4. http://arxiv.org/abs/2005.11401v4

[2] Asai等（2023）. Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. arXiv:2310.11511v1. http://arxiv.org/abs/2310.11511v1
