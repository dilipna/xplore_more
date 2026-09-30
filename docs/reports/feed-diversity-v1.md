# Feed source diversity, v1

**Question:** does one source dominate the top of the news feed (`/v1/feed`), and does a simple cap fix it?

**Setup.** Everything is computed as of a fixed time, `2026-09-29T02:33:41Z` (the newest article in the local database), with the serving code's own functions (`evals/feed/diversity.py`, raw output in `evals/feed/results_v1.json`). A story's *lead source* is the source of its representative article, which is the source a story card shows first. Search is not touched.

## Result

Top 20 of the feed, 24-hour window (332 candidate stories):

| | Stories from the most common lead source | Distinct lead sources |
|---|---|---|
| Before (heuristic only) | **19 of 20 (95%), Hacker News** | 2 |
| After (heuristic + source cap) | **3 of 20 (15%)** | 11 |

The 72-hour (385 candidates) and 7-day (500 candidates) windows give the same top 20. Older stories are already decayed by the 18-hour freshness half-life, so the wider windows don't change the head.

After the cap, the top 20 leads with Hacker News 3, PyTorch releases 3, TechCrunch AI 3, Ars Technica 3, Simon Willison 2, and one each from The Verge, OpenAI News, Ollama releases, Microsoft Research, AWS ML Blog and llama.cpp releases.

## Why Hacker News dominated, and why the weights were left alone

Only Hacker News articles carry community points, so it's tempting to blame the `hn_points` term (`0.35 × log1p(points)`, already log-scaled). A diagnostic run with that weight set to **0** and no cap still gives Hacker News **13 of 20 (65%)**. So most of the skew is volume, not points: Hacker News is the lead source of 131 of the 332 candidates in the window, more than any other source. Retuning weights without a relevance label set would be guesswork. A structural cap directly targets what was measured.

## The rule (`xm_rank.features.diversify`)

At most **2 stories per lead source in the top 10**, and **3 in the top 20**. Each position takes the highest-ranked remaining story whose source is still under every cap that covers that position. Past position 20 the heuristic order continues unchanged. Stories are only moved down, never dropped. If too few distinct sources exist, the rule relaxes to the original order. The `ranker` field in the response is now `heuristic/story-features-v1+source-cap-v1`.

## Other fixes made alongside

- **The candidate pool was an arbitrary cut.** It was a `SELECT DISTINCT ... LIMIT 500` with no `ORDER BY`, and the 7-day window holds 574 stories. It is now newest-first, so the cut drops the oldest stories.
- **The "lead" source shown on cards was alphabetical.** The API sorted `sources` by id, so `hacker-news` was shown ahead of `the-verge` on a story both covered. The representative article's source now comes first.

## Caveats

- One snapshot of one local corpus. The shares will move as the corpus changes; rerun the script on the live database to re-measure.
- This measures **source concentration only**, not whether the stories are good or on topic. With no relevance labels for the feed, no claim is made that the new order is "better" beyond being less concentrated. Automated release tags (for example PyTorch `trunk/<hash>` releases) now reach the top 10, which is a source-quality issue left for follow-up.
