# Scope

This brief asks what two early studies report about retrieval-augmented generation (RAG) and reduced language-model hallucination. It uses at most two arXiv abstracts, with Crossref metadata for bibliographic matching and available DOI verification. Searches were performed on 22 October 2026, with no publication-date filter. The included studies date from 2020 and 2021. This is a targeted brief, not a systematic review or a survey of current models.

# Methods

Four exact queries were issued through the academic search tool:

| Provider | Exact query | Limit | Observed returned rows |
| --- | --- | ---: | ---: |
| arxiv | `ti:"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"` | 1 | 1 |
| crossref | `Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks` | 2 | 2 |
| arxiv | `ti:"Retrieval Augmentation Reduces Hallucination in Conversation"` | 1 | 1 |
| crossref | `Retrieval Augmentation Reduces Hallucination in Conversation` | 1 | 1 |

These were purposive title searches, not a broad discovery search. All four requests succeeded; no source errors were returned. The five returned rows are observed adapter results, not database totals. The Crossref and arXiv dialogue records were merged by identical title and authors, retaining both sources and the Crossref DOI. This left four unique records: two included, two excluded, and none uncertain. Every unique record has a screening decision in screening.jsonl.

Inclusion required direct relevance to retrieval augmentation and factuality or hallucination, plus an acquired arXiv abstract describing an evaluated method. At most two abstracts were used. The two metadata-only Crossref records returned for the foundational-paper query were excluded: *Retrieval‐Augmented Generation* (2026; DOI 10.1002/9781394374717.ch03) and *Advanced Retrieval‐Augmented Generation* (2026; DOI 10.1002/9781394374717.fmatter). They were not exact matches to that study and supplied no acquired abstract for scientific extraction. No findings were inferred from their metadata or referenced works.

All three observed DOIs were looked up through Crossref and returned the same identifiers at 2026-10-22T09:08:42Z; their lookup sources and timestamps are retained in papers.jsonl. The included dialogue paper has verified DOI 10.18653/v1/2021.findings-emnlp.320. The foundational paper has no DOI or PMID in the retrieved record; its identifier verification remains unknown. The available verification command supports DOI and PMID, so its arXiv identifier was not independently verified. DOI verification confirms identifier metadata only and does not validate scientific findings or establish peer-review status.

# Findings

<!-- claim:C1 -->
Lewis and colleagues describe RAG as a pretrained sequence-to-sequence generator coupled to a dense Wikipedia index accessed through a neural retriever. Their two formulations condition on retrieved passages either across a whole output sequence or separately per token. The abstract reports more specific, diverse and factual generated language than a parametric-only sequence-to-sequence baseline. This supports a qualitative, author-reported factuality benefit in their evaluated setting; the abstract supplies no numerical hallucination-rate reduction. [1]

<!-- claim:C2 -->
Shuster and colleagues address knowledge-grounded dialogue using architectures comprising retrievers, rankers and encoder-decoders. Their abstract reports state-of-the-art performance on two conversational tasks and a substantial reduction in knowledge hallucination according to human evaluations. This is direct abstract-level evidence of an author-reported hallucination benefit, but the abstract does not state its magnitude or enough evaluation detail to independently assess that benefit. [2]

<!-- claim:C3 -->
Together, the abstracts provide favorable reports for retrieval-augmented generation in the studied generation and dialogue settings. Insufficient evidence is available to estimate a pooled reduction in hallucination, conclude that retrieval eliminates hallucinations, or generalize these findings to current models and other domains. The factuality comparison in the first abstract and the human-evaluated hallucination claim in the second are different outcomes; they cannot be treated as a common numerical endpoint. No contradictory result appears in these two acquired abstracts, but the targeted search cannot establish agreement across the wider literature. [1] [2]

# Limitations

Only two abstracts were acquired; no full text was downloaded or read. Every paper therefore has full_text.available=false and full_text_path=null. The extracted findings are located in the saved abstracts, and Crossref metadata was used only for bibliographic purposes. Source URLs and DOI landing pages do not constitute full-text access. The author lists are retained as supplied by the adapters; the foundational paper's returned list may be incomplete, so its bibliography uses “et al.”

<!-- claim:C4 -->
The acquired abstracts do not supply numerical factuality or hallucination effects, uncertainty estimates, detailed evaluation rubrics, or sample sizes. The dialogue abstract mentions human evaluation without providing its protocol or annotator agreement. Neither abstract supplies enough component-level comparison detail to isolate retrieval's contribution from other architectural or training choices. Consequently, this brief cannot assess statistical reliability, conduct a full risk-of-bias appraisal, or determine which RAG design most reliably reduces hallucination. [1] [2]

The two-paper cap, purposive title queries and small return limits sharply restrict coverage. No later studies or adverse-result searches were included. There were no failed lookup requests, but verification of the foundational paper remains unknown. Verification of the other records must not be read as stronger scientific evidence. The conclusions should be revisited using full texts and a broader search before making deployment decisions.

# References

[1] Lewis, Patrick, et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. arXiv:2005.11401v4. http://arxiv.org/abs/2005.11401v4. Evidence accessed: arXiv abstract only; DOI/PMID unavailable in the retrieved record; independent identifier verification unknown.

[2] Shuster, Kurt; Poff, Spencer; Chen, Moya; Kiela, Douwe; Weston, Jason (2021). *Retrieval Augmentation Reduces Hallucination in Conversation*. arXiv:2104.07567v1. http://arxiv.org/abs/2104.07567v1. DOI: 10.18653/v1/2021.findings-emnlp.320; https://doi.org/10.18653/v1/2021.findings-emnlp.320. Evidence accessed: arXiv abstract only; publication metadata and DOI verification from Crossref. The shared title and authors support the record merge; full-text equivalence between versions was not assessed.
