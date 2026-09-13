"""Lexical pain cues: interpretable features and the rule baseline for the classifier.

Each cue group is a small set of phrases people use when they describe one kind of pain.
They are hand-written from the labeling guidelines (evals/problems/GUIDELINES.md), not
mined from the labeled set, so the rule baseline is not fitted to the data it is scored on.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

LABELS = (
    "bug_or_reliability",
    "cost_or_performance",
    "missing_capability",
    "workflow_friction",
    "how_to_question",
    "not_a_problem",
)
PROBLEM_LABELS = frozenset(LABELS[:4])

_GROUPS: dict[str, str] = {
    "bug": (
        r"\b(error|exception|traceback|crash(es|ed|ing)?|segfault|panic(ked)?|fails?|failed|failing"
        r"|failure|broken|bug|regression|hangs?|hanging|stuck|doesn'?t work|not working|stopped working"
        r"|wrong result|incorrect|corrupt(ed|ion)?|data loss|outage|is down|status code 5\d\d)\b"
    ),
    "cost_perf": (
        r"\b(slow(er|ness)?|latency|expensive|costs?|costly|pricing|price|bill(ing)?|too much memory"
        r"|memory usage|oom(killed)?|out of memory|throughput|bottleneck|takes (forever|hours|minutes)"
        r"|burn(s|ing|ed)? (through )?(tokens|credits|money)|faster)\b"
    ),
    "missing": (
        r"(\bfeature request\b|\badd support\b|\bsupport for\b|\bwould be (nice|great|useful)\b|\bi wish\b"
        r"|\bis there (a|an|any)\b|\bplease add\b|\ballow (users|us|me)?\s*to\b|\bability to\b"
        r"|\bno way to\b|\bcurrently (not|no) (possible|supported)\b|\balternatives? to\b|\bnot supported\b)"
    ),
    "friction": (
        r"\b(tedious|painful|pain point|nightmare|annoying|frustrat\w*|manual(ly)?|workaround|drives me nuts"
        r"|hard to|difficult to|confusing|struggl\w*|cumbersome|boilerplate|toil|every time i)\b"
    ),
    "how_to": (
        r"(^|\b)(how (do|can|should|would) (i|we|you)|how to|what is the best way|best practices?"
        r"|any (advice|recommendations|suggestions)|what should i use)\b"
    ),
    "praise_or_chat": (
        r"\b(great (post|read|article|writeup|work)|thanks for sharing|love (this|it)|very cool|nice work"
        r"|congrat\w*|i built|show hn|what are you (working on|doing))\b"
    ),
}
CUE_NAMES = tuple(_GROUPS)
_COMPILED = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in _GROUPS.items()}
# Any edit to a pattern changes this digest, which invalidates trained classifier artifacts.
CUES_DIGEST = hashlib.sha256("\n".join(f"{k}={v}" for k, v in _GROUPS.items()).encode()).hexdigest()


@dataclass(frozen=True)
class CueHits:
    counts: dict[str, int]

    def vector(self) -> list[float]:
        """log1p-scaled match counts in CUE_NAMES order (keeps long issues from dominating)."""
        return [math.log1p(self.counts[name]) for name in CUE_NAMES]


def cue_hits(text: str) -> CueHits:
    return CueHits({name: len(rx.findall(text)) for name, rx in _COMPILED.items()})


def rule_label(text: str) -> str:
    """Baseline: the first cue group that fires, in the guidelines' precedence order."""
    counts = cue_hits(text).counts
    if counts["praise_or_chat"] and not (counts["bug"] or counts["missing"]):
        return "not_a_problem"
    for group, label in (
        ("bug", "bug_or_reliability"),
        ("cost_perf", "cost_or_performance"),
        ("missing", "missing_capability"),
        ("friction", "workflow_friction"),
        ("how_to", "how_to_question"),
    ):
        if counts[group]:
            return label
    return "not_a_problem"
