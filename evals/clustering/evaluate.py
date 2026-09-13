"""Evaluate same-event pair decisions on the labeled set; fit the logistic scorer.

    uv run python evals/clustering/evaluate.py [--write-scorer config/cluster_scorer.json]

Methodology
- Features are rebuilt from the database with the production code paths (MinHasher,
  Gazetteer, version_tokens), so evaluation cannot silently diverge from serving.
- Every method is evaluated out-of-fold: 5-fold stratified CV repeated 20 times. Tuned
  thresholds and fitted weights never see the fold they are scored on. The prior scorer
  has nothing to fit and is scored directly.
- Two views of each metric:
    sample:     over the labeled pairs as drawn (hard cases are over-represented)
    population: each pair weighted by stratum_size / stratum_sample_size, estimating
                precision/recall over ALL within-window pairs with cosine >= 0.70
                (pairs below 0.70 are assumed negative and not sampled)
- 95% bootstrap CIs over pairs (2,000 resamples) for F1.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RepeatedStratifiedKFold
from sqlalchemy import create_engine, text

from xm_cluster.entities import Gazetteer
from xm_cluster.minhash import MinHasher
from xm_cluster.scoring import FEATURE_NAMES, LogisticScorer, PairFeatures
from xm_cluster.text import content_tokens, shingles, version_tokens
from xm_core.settings import get_settings

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


@dataclass
class Pair:
    pair_id: str
    stratum: str
    label: int
    confidence: str
    features: PairFeatures


def _jac(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def load_pairs(dataset: Path) -> list[Pair]:
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = sorted({r["a"]["id"] for r in rows} | {r["b"]["id"] for r in rows})
    engine = create_engine(get_settings().database_url.get_secret_value())
    with engine.connect() as conn:
        db = {
            r[0]: r
            for r in conn.execute(
                text(
                    "SELECT id, title, lede, source_id, discovered_at, embedding::text "
                    "FROM articles WHERE id = ANY(:ids)"
                ),
                {"ids": ids},
            )
        }
    missing = [i for i in ids if i not in db]
    if missing:
        raise SystemExit(f"{len(missing)} labeled articles missing from the database (wrong snapshot?)")

    hasher = MinHasher()
    gazetteer = Gazetteer.load(ROOT / "config" / "entities.yaml")
    cache: dict[str, dict[str, object]] = {}

    def prepared(aid: str) -> dict[str, object]:
        if aid not in cache:
            _, title, lede, source, discovered, emb = db[aid]
            vec = np.array([float(x) for x in emb.strip("[]").split(",")], dtype=np.float32)
            body = f"{title}\n{lede}"
            cache[aid] = {
                "title": title,
                "source": source,
                "t": discovered,
                "vec": vec / np.linalg.norm(vec),
                "sig": hasher.signature(shingles(body)),
                "ents": gazetteer.extract(body),
                "title_toks": set(content_tokens(title)),
                "versions": version_tokens(title),
            }
        return cache[aid]

    pairs: list[Pair] = []
    for r in rows:
        a, b = prepared(r["a"]["id"]), prepared(r["b"]["id"])
        cos = float(a["vec"] @ b["vec"])  # type: ignore[operator]
        va, vb = a["versions"], b["versions"]
        feats = PairFeatures(
            max_member_cosine=cos,
            centroid_cosine=cos,
            minhash_jaccard=hasher.estimate_jaccard(a["sig"], b["sig"]),  # type: ignore[arg-type]
            title_jaccard=_jac(a["title_toks"], b["title_toks"]),  # type: ignore[arg-type]
            entity_jaccard=_jac(a["ents"], b["ents"]),  # type: ignore[arg-type]
            hours_gap=abs((a["t"] - b["t"]).total_seconds()) / 3600.0,  # type: ignore[operator]
            same_source=a["source"] == b["source"],
            version_conflict=bool(va) and bool(vb) and not (va & vb),  # type: ignore[operator]
        )
        label = int(r["human_label"]) if r.get("human_audited") else int(r["label"])
        pairs.append(Pair(r["pair_id"], r["stratum"], label, r["confidence"], feats))
    return pairs


def design_weights(pairs: list[Pair], meta: dict[str, object]) -> np.ndarray:
    strata: dict[str, int] = meta["strata"]  # type: ignore[assignment]
    sampled: dict[str, int] = {}
    for p in pairs:
        sampled[p.stratum] = sampled.get(p.stratum, 0) + 1
    return np.array([strata[p.stratum] / sampled[p.stratum] for p in pairs], dtype=float)


def prf(y: np.ndarray, pred: np.ndarray, w: np.ndarray | None = None) -> tuple[float, float, float]:
    w = np.ones_like(y, dtype=float) if w is None else w
    tp = float(np.sum(w * (pred == 1) * (y == 1)))
    fp = float(np.sum(w * (pred == 1) * (y == 0)))
    fn = float(np.sum(w * (pred == 0) * (y == 1)))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def best_threshold(scores: np.ndarray, y: np.ndarray) -> float:
    candidates = np.unique(np.round(scores, 4))
    best_t, best_f1 = 0.5, -1.0
    for t in candidates:
        f1 = prf(y, (scores >= t).astype(int))[2]
        if f1 > best_f1:
            best_t, best_f1 = float(t), f1
    return best_t


def threshold_for_precision(scores: np.ndarray, y: np.ndarray, target: float) -> float:
    """Highest-recall threshold whose precision meets `target`; falls back to max precision.

    Product rationale: merging two different events hides news (costly and invisible), while
    a missed merge only shows a duplicate card (visible and mild), so precision is the
    constraint and recall is maximized under it.
    """
    best_t, best_recall, fallback_t, fallback_p = None, -1.0, 0.5, -1.0
    for t in np.unique(np.round(scores, 4)):
        precision, recall, _ = prf(y, (scores >= t).astype(int))
        if precision >= target and recall > best_recall:
            best_t, best_recall = float(t), recall
        if precision > fallback_p:
            fallback_t, fallback_p = float(t), precision
    return best_t if best_t is not None else fallback_t


def bootstrap_f1(y: np.ndarray, pred: np.ndarray, w: np.ndarray | None, n: int = 2000, seed: int = 7):
    rng = np.random.default_rng(seed)
    idx = np.arange(len(y))
    values = []
    for _ in range(n):
        s = rng.choice(idx, size=len(idx), replace=True)
        values.append(prf(y[s], pred[s], None if w is None else w[s])[2])
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def to_matrix(pairs: list[Pair]) -> np.ndarray:
    return np.array([p.features.as_vector() for p in pairs], dtype=float)


def fit_logistic(
    x: np.ndarray, y: np.ndarray, c: float = 1.0
) -> tuple[LogisticRegression, np.ndarray, np.ndarray]:
    mean, std = x.mean(axis=0), x.std(axis=0)
    std[std == 0] = 1.0
    model = LogisticRegression(C=c, max_iter=5000)
    model.fit((x - mean) / std, y)
    return model, mean, std


def logistic_to_scorer(
    model: LogisticRegression, mean: np.ndarray, std: np.ndarray, threshold: float
) -> LogisticScorer:
    """Convert standardized sklearn weights into the serving LogisticScorer form."""
    coef = np.asarray(model.coef_, dtype=float).ravel()
    bias = float(np.asarray(model.intercept_, dtype=float).ravel()[0])
    raw_w = coef / std
    raw_b = bias - float(np.sum(coef * mean / std))
    weights = dict(zip(FEATURE_NAMES, (float(w) for w in raw_w), strict=True))
    center = LogisticScorer().cosine_center
    # serving form subtracts cosine_center from both cosine features
    intercept = raw_b + weights["max_member_cosine"] * center + weights["centroid_cosine"] * center
    return LogisticScorer(
        version=f"fitted-{datetime.now(UTC):%Y%m%d}",
        intercept=intercept,
        cosine_center=center,
        weights=weights,
        threshold=threshold,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=HERE / "pairs_v1.jsonl")
    parser.add_argument("--write-scorer", type=Path)
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "reports" / "clustering-pairs-v1.md")
    args = parser.parse_args()

    pairs = load_pairs(args.dataset)
    meta = json.loads((HERE / "pairs_v1.meta.json").read_text(encoding="utf-8"))
    y = np.array([p.label for p in pairs])
    w_pop = design_weights(pairs, meta)
    x = to_matrix(pairs)
    cos = x[:, 0]
    title_j = x[:, 3]
    prior = LogisticScorer()

    oof: dict[str, list[np.ndarray]] = {
        "cosine_threshold": [],
        "title_jaccard_threshold": [],
        "logistic_fitted": [],
        "logistic_fitted_p80": [],
    }
    splitter = RepeatedStratifiedKFold(n_splits=5, n_repeats=20, random_state=13)
    for train, test in splitter.split(x, y):
        preds = {name: np.zeros(len(y), dtype=int) - 1 for name in oof}
        t_cos = best_threshold(cos[train], y[train])
        preds["cosine_threshold"][test] = (cos[test] >= t_cos).astype(int)
        t_title = best_threshold(title_j[train], y[train])
        preds["title_jaccard_threshold"][test] = (title_j[test] >= t_title).astype(int)
        model, mean, std = fit_logistic(x[train], y[train])
        train_scores = model.predict_proba((x[train] - mean) / std)[:, 1]
        t_lr = best_threshold(train_scores, y[train])
        test_scores = model.predict_proba((x[test] - mean) / std)[:, 1]
        preds["logistic_fitted"][test] = (test_scores >= t_lr).astype(int)
        t_p80 = threshold_for_precision(train_scores, y[train], 0.8)
        preds["logistic_fitted_p80"][test] = (test_scores >= t_p80).astype(int)
        for name in oof:
            oof[name].append(preds[name])

    prior_pred = np.array([int(prior.probability(p.features) >= prior.threshold) for p in pairs])
    results: dict[str, dict[str, object]] = {}

    def summarize(name: str, fold_preds: list[np.ndarray] | None, single: np.ndarray | None = None) -> None:
        if single is not None:
            p_s, r_s, f_s = prf(y, single)
            p_p, r_p, f_p = prf(y, single, w_pop)
            ci_s, ci_p = bootstrap_f1(y, single, None), bootstrap_f1(y, single, w_pop)
        else:
            assert fold_preds is not None
            # average metrics over repeats: each repeat is a full out-of-fold prediction
            repeats = [np.max(np.stack(fold_preds[i : i + 5]), axis=0) for i in range(0, len(fold_preds), 5)]
            ms = np.array([prf(y, r) for r in repeats])
            mp = np.array([prf(y, r, w_pop) for r in repeats])
            p_s, r_s, f_s = ms.mean(axis=0)
            p_p, r_p, f_p = mp.mean(axis=0)
            ci_s = bootstrap_f1(y, repeats[0], None)
            ci_p = bootstrap_f1(y, repeats[0], w_pop)
        results[name] = {
            "sample": {
                "precision": round(p_s, 3),
                "recall": round(r_s, 3),
                "f1": round(f_s, 3),
                "f1_ci95": [round(v, 3) for v in ci_s],
            },
            "population": {
                "precision": round(p_p, 3),
                "recall": round(r_p, 3),
                "f1": round(f_p, 3),
                "f1_ci95": [round(v, 3) for v in ci_p],
            },
        }

    summarize("prior_scorer (no fitting)", None, prior_pred)
    for name, fold_preds in oof.items():
        summarize(name, fold_preds)

    # Final model on all labeled pairs (for serving), with its threshold tuned in-sample.
    model, mean, std = fit_logistic(x, y)
    final_scores = model.predict_proba((x - mean) / std)[:, 1]
    # Serving operating point: precision-constrained (see threshold_for_precision).
    fitted = logistic_to_scorer(model, mean, std, threshold_for_precision(final_scores, y, 0.8))
    check = np.array([fitted.probability(p.features) for p in pairs])
    assert np.allclose(check, final_scores, atol=1e-6), "serving conversion does not reproduce sklearn scores"

    high = np.array([p.confidence != "low" for p in pairs])
    report = {
        "dataset": str(args.dataset.relative_to(ROOT)),
        "pairs": len(pairs),
        "positives": int(y.sum()),
        "low_confidence": int((~high).sum()),
        "human_audited": False,
        "results": results,
        "fitted_scorer": {
            "weights": {k: round(v, 3) for k, v in fitted.weights.items()},
            "intercept": round(fitted.intercept, 3),
            "threshold": round(fitted.threshold, 3),
        },
        "prior_errors": [
            {"pair_id": p.pair_id, "label": p.label, "prob": round(prior.probability(p.features), 3)}
            for p, pred in zip(pairs, prior_pred, strict=True)
            if pred != p.label
        ],
    }
    (HERE / "results_v1.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.write_scorer:
        fitted.to_file(args.write_scorer)
    write_markdown(report, args.report)
    print(json.dumps(report["results"], indent=2))
    print("fitted:", report["fitted_scorer"])


def write_markdown(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Clustering pair evaluation (v1)",
        "",
        f"- Dataset: `{report['dataset']}`, {report['pairs']} pairs ({report['positives']} same-event), "
        f"{report['low_confidence']} marked low-confidence",
        "- Labels: first pass by an AI assistant under the written policy; **not yet human-audited**, "
        "so these numbers are provisional",
        "- Protocol: out-of-fold, 5-fold stratified CV x 20 repeats; population metrics use stratum "
        "design weights",
        "- Reproduce: `uv run python evals/clustering/evaluate.py`",
        "",
        "| Method | Sample P | Sample R | Sample F1 [95% CI] "
        "| Population P | Population R | Population F1 [95% CI] |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, r in report["results"].items():  # type: ignore[union-attr]
        s, p = r["sample"], r["population"]
        lines.append(
            f"| {name} | {s['precision']} | {s['recall']} | {s['f1']} {s['f1_ci95']} | "
            f"{p['precision']} | {p['recall']} | {p['f1']} {p['f1_ci95']} |"
        )
    lines += ["", "Fitted scorer (all pairs): `" + json.dumps(report["fitted_scorer"]) + "`", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
