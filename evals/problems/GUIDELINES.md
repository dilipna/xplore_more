# Pain-point labeling guidelines (labels_v1)

**Question for every item:** *Does this text describe a pain that a product, tool or service could address, and if so, what kind?* Label the author's **own** situation or a pain they clearly report others having. Do not label the topic of the thread.

Pick exactly one label. When two apply, use the precedence order below (first match wins).

| Label | Use when | Examples |
|---|---|---|
| `bug_or_reliability` | Something that exists behaves wrongly: crashes, errors, regressions, flaky or silent failures, data loss, security defects. | "vLLM 0.9 OOMs on startup with tp=2"; "sync silently drops rows after a schema change" |
| `cost_or_performance` | It works, but it is too slow, too expensive, uses too much memory, or does not scale. | "inference costs are killing our margins"; "pgvector index build takes 9 hours" |
| `missing_capability` | A needed feature or tool does not exist, or the author asks whether one exists. Feature requests belong here. | "support for reranking models"; "is there a tool that diffs two RAG indexes?" |
| `workflow_friction` | Everything technically works, but the process is tedious, manual, confusing or error-prone: developer experience, integration toil, fragmented tooling, hard-to-follow docs, operational toil. | "keeping prompts in sync across 5 services is a nightmare"; "every upgrade needs a day of manual config edits" |
| `how_to_question` | Asks how to do something, without reporting that tools are missing or broken. | "How do I stream tool calls with the Python SDK?" |
| `not_a_problem` | Opinion, news reaction, show-and-tell, praise, jokes, meta discussion, hiring posts, or a personal/career/life question that no software product would plausibly address. | "Great writeup!"; "Ask HN: What are you working on?"; "Should I take the job offer?" |

**Precedence** when more than one fits: `bug_or_reliability` > `cost_or_performance` > `missing_capability` > `workflow_friction` > `how_to_question` > `not_a_problem`.

**Edge rules**
1. **Comments that argue** about a problem someone else raised count only if the comment itself describes the pain (for example "we hit the same thing: ..."). Pure agreement or disagreement is `not_a_problem`.
2. **Ask HN "how do you handle X?"** counts as `workflow_friction` when the post says the current approach hurts. Otherwise it is `how_to_question`.
3. **GitHub issue templates:** judge the substance, not the template headings. A feature request is `missing_capability` even when filed under a bug template.
4. **Career, health, money and relationship questions** are `not_a_problem` unless they describe a tooling pain (for example "no job board lets me filter by visa sponsorship" is `missing_capability`).
5. **Truncated text** (the stored excerpt is at most 1,000 characters): label what is visible, and lower the confidence.

**Confidence:** `high` means clear-cut; `medium` means a plausible second label exists; `low` means ambiguous or truncated.

**Binary target used for the precision goal:** `is_problem = label in {bug_or_reliability, cost_or_performance, missing_capability, workflow_friction}`. `how_to_question` is kept separate: it signals demand for knowledge more than a product gap, and the evaluation reports both views.

**Content and privacy:** each row stores an excerpt (≤ 1,000 characters) of a public post and a link to its source. No usernames or author hashes are stored. Stack Exchange excerpts are licensed CC BY-SA 4.0 and attributed by their `url`. The excerpts exist only to make the evaluation reproducible.

**Provenance:** the first pass is by an AI assistant (`labeler: assistant`, `human_audited: false`), so these labels and every metric computed from them are **provisional** until a human audits them with `evals/problems/audit.py`.
