"""Attach same-event labels to sampled candidate pairs -> pairs_v1.jsonl.

Labeling policy (docs/clustering.md): label 1 when both items report or directly respond to
the SAME real-world event or announcement (including an outlet's rewrite, a commentator's
link post about that announcement, and multiple posts a company publishes for one launch).
Label 0 for related-but-distinct items: different versions or releases, series parts,
partner-availability posts, customer case studies, roundups and newsletters, and topical
essays.

Provenance: first-pass labels were assigned by an AI assistant (Claude Opus 5) reading
titles and ledes, recorded as `labeler`. Pairs marked `confidence: low` are ambiguous and
are reported separately. A human audit is required before these labels support any public
claim (`human_audited: false`).
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

POSITIVE = {
    "p0003", "p0019", "p0023", "p0026", "p0036", "p0043", "p0047", "p0048", "p0050", "p0051",
    "p0060", "p0063", "p0070", "p0078", "p0088", "p0098", "p0102", "p0105", "p0112", "p0115",
    "p0127", "p0133", "p0144", "p0158", "p0171", "p0173", "p0177",
}  # fmt: skip

CONFIDENCE = {
    # low: genuinely ambiguous under the policy
    "p0016": "low", "p0023": "low", "p0026": "low", "p0051": "low", "p0073": "low",
    "p0088": "low", "p0094": "low", "p0105": "low", "p0112": "low", "p0114": "low",
    "p0152": "low", "p0153": "low", "p0165": "low",
    # medium: commentary/reaction pieces judged to cover the same event
    "p0019": "medium", "p0036": "medium", "p0102": "medium", "p0115": "medium",
    "p0144": "medium", "p0173": "medium",
}  # fmt: skip

NOTES = {
    "p0004": "partner availability (Bedrock) is a distinct announcement",
    "p0012": "different Kubernetes patch versions released the same day",
    "p0051": "datasette 0.65.4 and 1.0a39: one coordinated security release across two branches",
    "p0073": "transformers release adding launch-day support vs the model launch post",
    "p0105": "safety overview and capability assessment published for the same launch",
    "p0112": "two robotics models, likely announced together",
    "p0144": "two outlets on the same Anthropic threat report",
    "p0173": "commentary on a specific blog post",
}


def main() -> None:
    src = HERE / "pairs_v1.candidates.jsonl"
    dst = HERE / "pairs_v1.jsonl"
    rows = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    with dst.open("w", encoding="utf-8") as fh:
        for r in rows:
            pid = r["pair_id"]
            r["label"] = 1 if pid in POSITIVE else 0
            r["confidence"] = CONFIDENCE.get(pid, "high")
            r["note"] = NOTES.get(pid)
            r["labeler"] = "assistant:claude-opus-5"
            r["human_audited"] = False
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    pos = sum(1 for r in rows if r["pair_id"] in POSITIVE)
    print(f"labeled {len(rows)} pairs: {pos} positive, {len(rows) - pos} negative")


if __name__ == "__main__":
    main()
