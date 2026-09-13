"""Sample article pairs from the live corpus for same-event labeling.

Stratified by embedding cosine and by same/cross source, so the set contains hard
negatives (similar topic, different event) and hard positives (rewrites), not only easy
extremes. A purely random sample would be ~99.9% trivial negatives.

    uv run python evals/clustering/sample_pairs.py --out evals/clustering/pairs_v1.candidates.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import create_engine, text

from xm_core.settings import get_settings

WINDOW = timedelta(hours=72)
# (low, high, per-stratum cap) over cosine, applied separately to cross- and same-source pairs.
BINS = [
    (0.70, 0.78, 25),
    (0.78, 0.82, 30),
    (0.82, 0.85, 40),
    (0.85, 0.88, 45),
    (0.88, 0.92, 45),
    (0.92, 1.01, 40),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    engine = create_engine(get_settings().database_url.get_secret_value())
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, source_id, title, left(lede, 300), discovered_at, embedding::text "
                "FROM articles WHERE embedding IS NOT NULL ORDER BY id"
            )
        ).all()
    vecs = np.array([[float(x) for x in r[5].strip("[]").split(",")] for r in rows], dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    sims = vecs @ vecs.T
    times = [r[4] for r in rows]

    strata: dict[tuple[bool, int], list[tuple[int, int]]] = {}
    n = len(rows)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(times[i] - times[j]) > WINDOW:
                continue
            s = float(sims[i, j])
            for b, (lo, hi, _) in enumerate(BINS):
                if lo <= s < hi:
                    strata.setdefault((rows[i][1] == rows[j][1], b), []).append((i, j))
                    break

    chosen: list[tuple[int, int, str]] = []
    for (same_source, b), pairs in sorted(strata.items()):
        cap = BINS[b][2] if not same_source else BINS[b][2] // 3
        for i, j in rng.sample(pairs, min(cap, len(pairs))):
            chosen.append(
                (i, j, f"{'same' if same_source else 'cross'}-source cos[{BINS[b][0]},{BINS[b][1]})")
            )
    rng.shuffle(chosen)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for k, (i, j, stratum) in enumerate(chosen):
            a, b = rows[i], rows[j]
            fh.write(
                json.dumps(
                    {
                        "pair_id": f"p{k:04d}",
                        "stratum": stratum,
                        "cosine": round(float(sims[i, j]), 4),
                        "a": {"id": a[0], "source": a[1], "title": a[2], "lede": a[3]},
                        "b": {"id": b[0], "source": b[1], "title": b[2], "lede": b[3]},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    meta = {
        "seed": args.seed,
        "articles": n,
        "window_hours": WINDOW.total_seconds() / 3600,
        "bins": BINS,
        # population size per stratum, needed for design-weighted (population) metrics
        "strata": {
            f"{'same' if same else 'cross'}-source cos[{BINS[b][0]},{BINS[b][1]})": len(pairs)
            for (same, b), pairs in sorted(strata.items())
        },
    }
    meta_path = args.out.parent / args.out.name.replace(".candidates.jsonl", ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"articles={n} candidate_pairs={len(chosen)} strata={meta['strata']}")


if __name__ == "__main__":
    main()
