# News ↔ problem links (F2), v1: measured, not shipped

**Idea.** On a story, show "problems people report about this" (and the reverse), linked by embedding similarity: the story's representative-article embedding compared with each problem's centroid (`bge-small-en-v1.5`, cosine). No LLM involved.

**Ship bar:** at least 70% of the links shown should be relevant at some similarity floor. (No floor reached even 30%, so the exact bar does not change the decision.)

## Method

- `evals/links/pool.py`: as of `2026-09-29T02:33:41Z`, each story from the previous 14 days is paired with its nearest problem (problems seen in the previous 45 days).
- 48 pairs, 12 per cosine bin (0.70–0.74, 0.74–0.77, 0.77–0.80, ≥ 0.80), sampled with a fixed seed.
- Across the 687 stories, the best-match cosine had a 10th percentile of 0.63 and a median of 0.716 (measured by a direct SQL query over the same window, relative to query time rather than the fixed as_of). Only 12 stories reached 0.80, so the top bin holds all of them.
- **Judge:** the assistant (Claude), `human_audited: false`. A pair is relevant if a reader of the story would find the problem to be about the same technology *and* the same concern. Labels and one-line reasons are in `evals/links/judgments_v1.txt`.
- `evals/links/evaluate.py` computes precision with Wilson 95% intervals and writes `evals/links/results_v1.json`.

## Result

| Similarity floor | Relevant / judged | Precision | 95% CI |
|---|---|---|---|
| ≥ 0.70 | 7 / 48 | 15% | 7–27% |
| ≥ 0.74 | 7 / 36 | 19% | 10–35% |
| ≥ 0.77 | 5 / 24 | 21% | 9–41% |
| ≥ 0.80 | 3 / 12 | 25% | 9–53% |

**Decision: not shipped.** No floor gets near the 70% bar. Raising the floor further leaves almost nothing to link, since only 12 of 687 stories reach 0.80.

## What the failures look like

The good links share a specific product and concern:
- a PyTorch release adding MPS comparison ops ↔ the MPS operator-coverage issue;
- NVIDIA's agent runtime controls ↔ "how do you gate a coding agent's shell access";
- a voice-call app for coding agents ↔ people asking about dictation with coding agents.

Most misses match only a broad area. A few problem centroids ("SGLang simulator roadmap", "OpenAI billing complaint") act as hubs that sit near many unrelated stories. A single cosine from a small general-purpose embedding can't tell "same topic" from "same concern".

## What could work next (not built)

- A pair classifier like the one used for problem clustering: cosine plus shared named entities (product, repo, model), plus a hub penalty for centroids that are nearest to many stories. Trained and evaluated on a larger judged set.
- Per-member matching (nearest problem *post*, not centroid), so broad problems stop acting as hubs.
- A human audit of these 48 labels before any threshold is trusted.
