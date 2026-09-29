# Search relevance judging guidelines (qrels_v1)

**Unit judged:** a *story* (a cluster of articles about one event), as `/v1/search` returns stories. The judge sees the story title and the first ~110 characters of its representative article, plus the query and its narrative in `queries_v1.jsonl`.

**Question for every pair:** *How useful is this story to someone who typed this query, given the narrative?*

| Grade | Meaning |
|---|---|
| 3 | Highly relevant: the story's main subject is exactly the query's need. |
| 2 | Relevant: substantially about the need, or a direct instance/subtopic of it. |
| 1 | Marginal: mentions or touches the need (a roundup with one related item, a neighbouring topic, a different version of the named thing). |
| 0 | Not relevant. |

**Binary relevance** for Recall@k and MRR: grade ≥ 2. nDCG@10 uses the graded labels with gain `2^grade − 1`.

**Pooling (TREC-style):** for each query the pool is the hybrid top 50 (the reranker's candidate set, judged in full so learning-to-rank trains on complete labels) plus the FTS-only, dense-only and offline-BM25 top 20. Pool rows were shown sorted by story id, so the judge could not see which system ranked what. Unjudged stories count as non-relevant.

**Manual additions:** while judging, the judge had also read every story title in the corpus (1,301 stories) and could add a relevant story that no system pooled. These are rows with `in_pool: false`. They make recall estimates honest for stories every system missed; they are a small minority (listed per query in the report).

**Provenance:** judged by an AI assistant (`labeler: assistant`, `human_audited: false`). Every metric computed from these labels is **provisional** until a human audits them. The raw judgment file is `assistant_judgments_v1.txt` (one line per query; only non-zero grades are written, every other pooled story is grade 0; a leading `+` marks a manual addition).

**Known biases, stated up front:**
1. The queries were written by the same assistant after reading the corpus, so they skew towards topics the corpus covers well (few zero-result queries). This favours recall numbers.
2. Judging used titles and a short excerpt, not full text. Grades 1 vs 0 on long-form posts are the least reliable.
3. One judge, no inter-annotator agreement.
