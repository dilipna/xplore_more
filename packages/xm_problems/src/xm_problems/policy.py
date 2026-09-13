"""Problem clustering policy: what counts as "the same problem".

A problem is one specific pain that independent people report: "vLLM loses Qwen tool calls
emitted inside <think>" or "no native Azure AI Foundry provider". It is not a topic
("DeepSeek"), and it is not a news event.

Differences from the story policy (xm_cluster.scoring), each from calibration on 528
classifier-admitted live discussions (2026-09-13; see docs/problems.md):
- 30-day window instead of 72 hours: problems persist while news decays.
- Cosine is centered higher (0.84 vs 0.85 with a lower slope). Among admitted docs, unrelated
  pairs have median cosine 0.575 and p99 0.72, but same-topic opinions reach 0.85-0.90, so
  cosine alone cannot separate "same problem" from "same topic".
- Title overlap counts for more, because issue and question titles usually name the pain.
- version_conflict is KEPT. Template feature requests for different models ("support
  Qwen3.8-Flash" / "support GLM5.3") were among the most similar false pairs.
- same_source carries no penalty: duplicate issues in one repository are common and real.
- Time decay is per day, not per hour.
"""

from __future__ import annotations

import re
from datetime import timedelta

from xm_cluster.scoring import LogisticScorer
from xm_cluster.text import content_tokens, version_tokens

PROBLEM_LOCK_KEY = 0x584D50524F424C4D  # "XMPROBLM"
WINDOW = timedelta(days=30)
MAX_DENSE_CANDIDATES = 10
MAX_MEMBERS_COMPARED = 25

# Audit 1 (evals/problems/merge_audits.jsonl): 17/33 joins correct. Fixes, each tied to an
# observed failure:
# - Two distinct issues filed by ONE author were merged twice. Same author_hash lowers the logit.
SAME_AUTHOR_LOGIT = -2.0
# - Template titles ("[Roadmap] ...", "Feature Request: Support X") shared boilerplate tokens,
#   inflating title overlap. Those tokens are ignored for problem headlines.
_TEMPLATE_PREFIX = re.compile(
    r"^\s*(?:\[[^\]]{1,40}\]\s*[:\-—]*\s*)+|^\s*(?:feature request|feat|rfc|bug|proposal|roadmap|"
    r"tracking issue|tell hn|ask hn|show hn)\s*[:\-—]\s*",
    re.IGNORECASE,
)
_BOILERPLATE = frozenset(
    [
        *("feature", "request", "support", "add", "adding", "please", "possible", "allow", "new"),
        *("roadmap", "rfc", "bug", "issue", "tracking", "proposal", "development"),
        *("ask", "tell", "show", "hn"),
    ]
)
# - "Support GLM5.3" vs "support Qwen3.8-Flash" were merged: model versions glued to a name
#   are invisible to the story tokenizer (which is left unchanged; stories were evaluated on it).
_NAMED_VERSION = re.compile(r"(?<![a-z0-9])[a-z][a-z\-]{1,15}?-?\d+(?:\.\d+){0,2}(?![0-9])", re.IGNORECASE)


def headline_tokens(headline: str) -> set[str]:
    return {t for t in content_tokens(_TEMPLATE_PREFIX.sub(" ", headline)) if t not in _BOILERPLATE}


# Number-suffixed tokens that name precisions, GPUs or platforms, not versions (fp8 vs int4
# is not a conflict between two different products).
_NOT_A_VERSION = re.compile(r"^(?:fp|int|uint|bf|q|a|h|b|l|t|v|x|sm|rtx|gtx|m|x86|arm|win|py|cuda)-?\d+$")


def problem_version_tokens(headline: str) -> set[str]:
    named = {
        token
        for m in _NAMED_VERSION.finditer(headline)
        if not _NOT_A_VERSION.match(token := m.group(0).lower())
    }
    return version_tokens(headline) | named


def problem_scorer() -> LogisticScorer:
    return LogisticScorer(
        # c: version_conflict -6 -> -10. On the audit-2 corpus the join set is identical to b.
        version="problem-prior-2026-09-13c",
        intercept=-0.8,
        cosine_center=0.84,
        weights={
            "max_member_cosine": 25.0,
            "centroid_cosine": 0.0,
            "minhash_jaccard": 3.0,
            "title_jaccard": 4.0,
            "entity_jaccard": 2.0,
            "hours_gap": -0.02 / 24.0,  # -0.02 logit per day apart
            "same_source": 0.0,
            # Decisive, unlike the story policy's -6: an integration test showed -6 still merging
            # near-identical "support GLM5.3" / "support Qwen3.8" requests (p 0.62). Trade-off:
            # one bug reported against two different versions stays split into two problems.
            "version_conflict": -10.0,
        },
        # Audit 1: correct joins had probability >= 0.61 except one; raised from 0.5.
        threshold=0.6,
    )
