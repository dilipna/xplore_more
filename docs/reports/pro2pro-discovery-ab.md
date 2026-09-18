# Discovery A/B: XploreMore-sourced vs HN/web-sourced (P6)

**Status: the run is in progress. No results are recorded here yet.** This file currently
holds only the method and the known limitations, both fixed before any trial ran. The results
table is generated from the committed raw data, never typed by hand.

## Question

Pro2Pro's Research Agent can discover problems from XploreMore's clustered, demand-ranked
problem API, or from its own Hacker News and web search. Does the XploreMore source produce
better discovery for the same budget?

## Design

One trial = one topic, one arm, running the **real** Research Agent and the **real** Analyst
(guardrails → dedupe → conviction score). 8 topics × 2 arms = 16 trials.

- **`xploremore` arm:** `XPLOREMORE_API_URL` set, so `find_problems`/`get_problem` are bound
  alongside the HN/web tools, with the XploreMore prompt.
- **`baseline` arm:** `XPLOREMORE_API_URL` unset, so exactly the pre-existing HN/web toolset
  and prompt.

Held equal across arms: provider and model, `max_tokens`, guardrails, the Analyst prompt and
its shortlist threshold, the research step ceiling (both arms get 22, so the baseline is never
cut short where the XploreMore arm would not be), the turn timeout, the per-call retry policy,
and a 65 s pause before every trial so each one starts with a fresh tokens-per-minute window.

Arm order alternates by topic, so any drift in provider latency or rate-limit state does not
systematically favour one arm. Each arm keeps its own dedupe memory, so "dedupe-new" means new
relative to that arm's own earlier trials. No trial writes to the application database and no
review email is sent.

**Topics** (`evals/pro2pro/topics_v1.txt`) were fixed before the first trial and were not
tuned on results.

## Statistics

- Proportions over trials (for example "research turn completed") use a Wilson 95% interval.
- Idea-level metrics (guardrail pass rate, dedupe-new rate, shortlisted share, conviction,
  tokens per shortlisted idea) use a **cluster bootstrap that resamples whole trials**, because
  ideas from one research turn are not independent of each other.
- Differences between arms are computed **paired by topic**, bootstrapped over topics.
- 10,000 resamples, seed 7, so the intervals are reproducible.

## What this cannot tell you

- **Sample size is small** (8 topics per arm). Intervals will be wide; treat anything whose
  interval spans zero as "not distinguished by this experiment".
- **The Analyst is an LLM, not ground truth.** Conviction and shortlisting measure what the
  Analyst thinks, which is what actually gates Pro2Pro's pipeline, but it is not a measure of
  real-world problem quality.
- **Approval share and human quality ratings are not measured**, because they need a human.
  They are reported as "not measured" rather than replaced with a proxy.
- LLM output is stochastic and each cell here is one run per topic, so re-running will not
  reproduce the numbers exactly. The raw per-trial data is committed so any claim can be
  recomputed.
- XploreMore's side is a **one-day dev corpus snapshot** whose classifier and clustering
  quality are themselves provisional and assistant-audited (see `docs/problems.md`). The
  baseline arm searches the live web. This is a comparison of two discovery paths on this
  corpus, not a general claim about either source.
- Both arms ran on Groq's 8,000 TPM tier, where a turn can spend minutes waiting out rate
  limits. Wall-time differences mostly reflect that ceiling, not the sources.

## Reproduce

```bash
# XploreMore API with a key, from the xplore_more repo
PORT=8765 uv run xm-api
uv run xm-api keys create --name pro2pro-local --rate 600

# from the p2pagent repo (commit cbdf5ab)
XPLOREMORE_API_URL=http://127.0.0.1:8765 XPLOREMORE_API_KEY=<key> \
  uv run p2pops-discovery-ab run \
    --topics-file ../xplore_more/evals/pro2pro/topics_v1.txt \
    --out ../xplore_more/evals/pro2pro/ab_v1.jsonl --data-dir <scratch dir>
uv run p2pops-discovery-ab report --in ../xplore_more/evals/pro2pro/ab_v1.jsonl
```

Raw per-trial data: `evals/pro2pro/ab_v1.jsonl` (one JSON object per trial: tools bound, every
tool call, XploreMore availability and any outage, each idea with its status, score and
provenance, token counts, rate-limit retries, wall time).

## Results

_Pending: written from `evals/pro2pro/ab_v1.jsonl` when the run finishes._
