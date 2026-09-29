"""Evaluate story search on the judged query set and train the LambdaMART reranker.

    uv run python evals/search/evaluate.py      # no DB needed: reads the frozen snapshot

Methodology
- Data: 62 queries (queries_v1.jsonl), graded qrels (qrels_v1.jsonl, assistant-judged,
  human_audited=false, see GUIDELINES.md), and snapshot_v1.json.gz, which froze each
  query's serving-path candidate lists (Postgres FTS top 200, pgvector top 200) and the
  reranker signals for the hybrid top 50.
- Systems (every ranking is recomputed here from the frozen lists):
    fts            Postgres FTS alone, collapsed to stories (serving code, dense list empty)
    bm25           offline Okapi BM25 over title x2 + lede (the baseline docs/search.md names)
    dense          pgvector cosine alone, collapsed to stories
    hybrid         RRF(k=60) of FTS + dense, collapsed: what /v1/search serves today
    rrf_bm25_dense RRF of BM25 + dense at story level: "what if FTS were replaced by BM25"
    rerank         LightGBM LambdaMART reordering the hybrid top 50
- The reranker is only ever scored out-of-fold: grouped 5-fold CV by query, repeated 5
  times with different query shuffles; each query's metric is its mean over the 5 repeats.
  Hyperparameters were fixed before the first run (PARAMS below) and not tuned on these
  results; there is no inner selection loop to leak through.
- Reranking cannot change which 50 stories are candidates, so rerank's Recall@50 equals
  hybrid's by construction and is reported only for completeness.
- 95% CIs: percentile bootstrap over queries (10,000 resamples). System comparisons use a
  paired bootstrap on per-query differences.
- The final model is refit on all queries and exported as a LightGBM dump; the export is
  checked against LightGBM's own predictions through the pure-Python serving evaluator.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
from metrics import bootstrap_ci, paired_bootstrap, query_metrics
from pool import load_snapshot, system_runs

from xm_cluster.entities import Gazetteer
from xm_search.fusion import rrf
from xm_search.query import parse_query
from xm_search.rerank import FEATURE_NAMES, FEATURE_VERSION, CandidateSignals, TreeEnsemble, features

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
MODEL_OUT = ROOT / "config" / "search_reranker.v1.json"
RESULTS = HERE / "results_v1.json"
BASELINE = HERE / "baseline_v1.json"
REPORT = ROOT / "docs" / "reports" / "search-eval-v1.md"

FOLDS, REPEATS = 5, 5
PARAMS: dict[str, Any] = {
    "objective": "lambdarank",
    "n_estimators": 200,
    "learning_rate": 0.05,
    "num_leaves": 7,
    "min_child_samples": 20,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "lambdarank_truncation_level": 20,
    "random_state": 17,
    "deterministic": True,
    "force_row_wise": True,
    "n_jobs": 1,
    "verbose": -1,
}
SYSTEMS = ["fts", "bm25", "dense", "hybrid", "rrf_bm25_dense", "rerank"]
METRICS = ["ndcg@10", "recall@10", "recall@50", "mrr"]
_TREE_KEYS = {
    "split_feature",
    "threshold",
    "decision_type",
    "default_left",
    "missing_type",
    "left_child",
    "right_child",
    "leaf_value",
}


def load_qrels() -> dict[str, dict[int, int]]:
    grades: dict[str, dict[int, int]] = defaultdict(dict)
    for line in (HERE / "qrels_v1.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        grades[r["qid"]][int(r["story_id"])] = int(r["grade"])
    return grades


def baseline_runs(snap: dict[str, Any], qid: str) -> dict[str, list[int]]:
    runs = system_runs(snap, qid)
    fused = rrf([runs["bm25"], runs["dense"]])
    runs["rrf_bm25_dense"] = sorted(fused, key=lambda s: (-fused[s], s))[:100]  # type: ignore[arg-type]
    return runs


def feature_matrix(snap: dict[str, Any], gazetteer: Gazetteer) -> dict[str, tuple[list[int], np.ndarray]]:
    out: dict[str, tuple[list[int], np.ndarray]] = {}
    for qid, q in snap["queries"].items():
        parsed = parse_query(q["query"], gazetteer)
        cands = [CandidateSignals.from_json(c) for c in q["candidates"]]
        out[qid] = ([c.story_id for c in cands], np.array([features(parsed, c) for c in cands], dtype=float))
    return out


def _stack(
    qids: list[str], feats: dict[str, tuple[list[int], np.ndarray]], grades: dict[str, dict[int, int]]
):
    xs, ys, groups = [], [], []
    for qid in qids:
        sids, x = feats[qid]
        xs.append(x)
        ys.append(np.array([grades[qid].get(s, 0) for s in sids], dtype=int))
        groups.append(len(sids))
    return np.vstack(xs), np.concatenate(ys), groups


def _fit(qids: list[str], feats, grades) -> lgb.LGBMRanker:
    x, y, groups = _stack(qids, feats, grades)
    model = lgb.LGBMRanker(**PARAMS)
    model.fit(x, y, group=groups, feature_name=list(FEATURE_NAMES))
    return model


def features_fingerprint(qids: list[str], feats: dict[str, tuple[list[int], np.ndarray]]) -> str:
    """sha256 of the rounded feature matrix: the model is only valid for the features it was fit on."""
    h = hashlib.sha256()
    for qid in sorted(qids):
        sids, x = feats[qid]
        h.update(qid.encode())
        h.update(np.asarray(sids, dtype=np.int64).tobytes())
        h.update(np.round(x, 6).tobytes())
    return h.hexdigest()


def _order(sids: list[int], scores: np.ndarray, rrf_scores: np.ndarray) -> list[int]:
    idx = sorted(range(len(sids)), key=lambda i: (-scores[i], -rrf_scores[i], sids[i]))
    return [sids[i] for i in idx]


def cross_validated(
    qids: list[str], feats, grades
) -> tuple[dict[str, dict[str, float]], list[float], dict[str, float]]:
    """Per-query out-of-fold metrics (mean over repeats), per-repeat mean nDCG@10, gain importances."""
    per_repeat: list[dict[str, dict[str, float]]] = []
    importance: dict[str, float] = defaultdict(float)
    rrf_col = FEATURE_NAMES.index("rrf")
    for r in range(REPEATS):
        order = list(qids)
        np.random.default_rng(1000 + r).shuffle(order)
        folds = [order[i::FOLDS] for i in range(FOLDS)]
        metrics: dict[str, dict[str, float]] = {}
        for k, test in enumerate(folds):
            train = [q for j, fold in enumerate(folds) if j != k for q in fold]
            model = _fit(train, feats, grades)
            for name, gain in zip(
                FEATURE_NAMES, model.booster_.feature_importance(importance_type="gain"), strict=True
            ):
                importance[name] += float(gain)
            for qid in test:
                sids, x = feats[qid]
                ranked = _order(sids, np.asarray(model.booster_.predict(x), dtype=float), x[:, rrf_col])
                metrics[qid] = query_metrics(ranked, grades[qid])
        per_repeat.append(metrics)
    mean = {q: {m: float(np.mean([rep[q][m] for rep in per_repeat])) for m in METRICS} for q in qids}
    repeat_ndcg = [float(np.mean([rep[q]["ndcg@10"] for q in qids])) for rep in per_repeat]
    total = sum(importance.values()) or 1.0
    return mean, repeat_ndcg, {k: v / total for k, v in sorted(importance.items(), key=lambda kv: -kv[1])}


def _compact(node: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in node.items() if k in _TREE_KEYS}
    for side in ("left_child", "right_child"):
        if side in out:
            out[side] = _compact(out[side])
    return out


def export_model(qids: list[str], feats, grades, cv_summary: dict[str, Any]) -> dict[str, Any]:
    model = _fit(qids, feats, grades)
    dump = model.booster_.dump_model()
    compact = {
        "feature_names": dump["feature_names"],
        "tree_info": [{"tree_structure": _compact(t["tree_structure"])} for t in dump["tree_info"]],
        "xm_meta": {
            "model": "lightgbm-lambdamart",
            "feature_version": FEATURE_VERSION,
            "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "train_queries": len(qids),
            "params": PARAMS,
            "lightgbm_version": lgb.__version__,
            "qrels": "evals/search/qrels_v1.jsonl (assistant, human_audited=false)",
            "cv": cv_summary,
        },
    }
    x, _, _ = _stack(qids, feats, grades)
    ours = np.array(TreeEnsemble(compact).predict(x.tolist()))
    diff = float(np.max(np.abs(ours - model.booster_.predict(x))))
    if diff > 1e-9:
        raise SystemExit(f"pure-Python evaluator disagrees with LightGBM by {diff}")
    MODEL_OUT.write_text(json.dumps(compact, separators=(",", ":")), encoding="utf-8")
    compact["xm_meta"]["max_abs_diff_vs_lightgbm"] = diff
    return compact


def summarise(per_query: dict[str, dict[str, dict[str, float]]], qids: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for system in SYSTEMS:
        out[system] = {}
        for m in METRICS:
            mean, lo, hi = bootstrap_ci([per_query[system][q][m] for q in qids])
            out[system][m] = {"mean": mean, "lo": lo, "hi": hi}
    return out


def fmt(cell: dict[str, float]) -> str:
    return f"{cell['mean']:.3f} [{cell['lo']:.3f}, {cell['hi']:.3f}]"


def fmt_delta(d: dict[str, float]) -> str:
    return f"{d['delta']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}]"


def main() -> None:
    snap = load_snapshot()
    grades = load_qrels()
    queries = {
        r["qid"]: r
        for r in map(json.loads, (HERE / "queries_v1.jsonl").read_text(encoding="utf-8").splitlines())
    }
    qids = [q for q in snap["queries"] if any(g >= 2 for g in grades[q].values())]
    dropped = sorted(set(snap["queries"]) - set(qids))
    gazetteer = Gazetteer.load(ROOT / "config" / "entities.yaml")
    feats = feature_matrix(snap, gazetteer)

    per_query: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    for qid in qids:
        for system, ranked in baseline_runs(snap, qid).items():
            per_query[system][qid] = query_metrics(ranked, grades[qid])
    cv, repeat_ndcg, importance = cross_validated(qids, feats, grades)
    per_query["rerank"] = cv

    summary = summarise(per_query, qids)
    comparisons = {
        f"{a}_vs_{b}": {
            m: paired_bootstrap([per_query[a][q][m] for q in qids], [per_query[b][q][m] for q in qids])
            for m in METRICS
        }
        for a, b in [
            ("hybrid", "fts"),
            ("hybrid", "dense"),
            ("bm25", "fts"),
            ("rrf_bm25_dense", "hybrid"),
            ("rerank", "hybrid"),
        ]
    }
    by_type: dict[str, dict[str, float]] = defaultdict(dict)
    for t in sorted({queries[q]["type"] for q in qids}):
        tq = [q for q in qids if queries[q]["type"] == t]
        for system in SYSTEMS:
            by_type[t][system] = float(np.mean([per_query[system][q]["ndcg@10"] for q in tq]))
        by_type[t]["n"] = len(tq)
    lexical_zero = [q for q in qids if not snap["queries"][q]["lexical"]]
    lexical_hits = {q: len(snap["queries"][q]["lexical"]) for q in qids}
    # How much of hybrid's gain over FTS comes from queries where FTS finds fewer than 10 articles.
    thin = [q for q in qids if lexical_hits[q] < 10]
    gain = {q: per_query["hybrid"][q]["ndcg@10"] - per_query["fts"][q]["ndcg@10"] for q in qids}
    thin_share = sum(gain[q] for q in thin) / (sum(gain.values()) or 1.0)

    cv_summary = {
        "ndcg@10_oof": summary["rerank"]["ndcg@10"],
        "ndcg@10_per_repeat": repeat_ndcg,
        "delta_vs_hybrid": comparisons["rerank_vs_hybrid"]["ndcg@10"],
    }
    model = export_model(qids, feats, grades, cv_summary)

    # In-sample numbers for the CI gate only (the shipped model on the data it was fit on);
    # never reported as a quality estimate.
    ens = TreeEnsemble(model)
    rrf_col = FEATURE_NAMES.index("rrf")
    gate_rerank = []
    for qid in qids:
        sids, x = feats[qid]
        gate_rerank.append(
            query_metrics(_order(sids, np.array(ens.predict(x.tolist())), x[:, rrf_col]), grades[qid])[
                "ndcg@10"
            ]
        )
    baseline = {
        "note": "Recorded by evals/search/evaluate.py. The CI gate (evals/search/test_gate.py) fails when a "
        "metric drops more than `tolerance` below these values on the frozen snapshot.",
        "tolerance": 0.01,
        "queries": len(qids),
        "hybrid": {m: summary["hybrid"][m]["mean"] for m in METRICS},
        "rerank_in_sample": {"ndcg@10": float(np.mean(gate_rerank))},
        "features_sha256": features_fingerprint(qids, feats),
    }
    BASELINE.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")

    n_judged = sum(len(g) for g in grades.values())
    n_rel = sum(1 for g in grades.values() for v in g.values() if v >= 2)
    n_manual = sum(
        1
        for line in (HERE / "qrels_v1.jsonl").read_text(encoding="utf-8").splitlines()
        if not json.loads(line)["in_pool"]
    )
    results = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "snapshot": {
            k: snap[k] for k in ("created_at", "as_of", "embedding_model", "corpus", "feature_version")
        },
        "queries": len(qids),
        "dropped_no_relevant": dropped,
        "judgments": {"total": n_judged, "relevant": n_rel, "manual_additions": n_manual},
        "lexical_zero_hit_queries": lexical_zero,
        "lexical_hits": {
            "median": float(np.median(list(lexical_hits.values()))),
            "queries_under_10": len(thin),
            "share_of_hybrid_gain_over_fts_from_them": thin_share,
        },
        "summary": summary,
        "comparisons": comparisons,
        "ndcg@10_by_query_type": by_type,
        "rerank": {
            "params": PARAMS,
            "folds": FOLDS,
            "repeats": REPEATS,
            "ndcg@10_per_repeat": repeat_ndcg,
            "feature_importance_gain": importance,
            "export_max_abs_diff": model["xm_meta"]["max_abs_diff_vs_lightgbm"],
            "trees": len(model["tree_info"]),
        },
        "per_query": {s: per_query[s] for s in SYSTEMS},
    }
    RESULTS.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render_report(results, queries), encoding="utf-8")
    print(f"wrote {RESULTS.name}, {BASELINE.name}, {MODEL_OUT.relative_to(ROOT)}, {REPORT.relative_to(ROOT)}")
    for system in SYSTEMS:
        print(f"{system:15s} " + "  ".join(f"{m}={fmt(summary[system][m])}" for m in METRICS))
    for name, c in comparisons.items():
        print(f"{name:25s} ndcg@10 {fmt_delta(c['ndcg@10'])}  p(<=0)={c['ndcg@10']['p_le_0']:.3f}")


def render_report(r: dict[str, Any], queries: dict[str, dict[str, Any]]) -> str:
    s, c = r["summary"], r["comparisons"]
    label = {
        "fts": "Postgres FTS only",
        "bm25": "BM25 (offline)",
        "dense": "Dense (bge-small) only",
        "hybrid": "**Hybrid RRF (serving today)**",
        "rrf_bm25_dense": "RRF(BM25, dense)",
        "rerank": "**Hybrid + LambdaMART (out-of-fold)**",
    }
    lines = [
        "# Search evaluation v1: lexical vs dense vs hybrid, and a LambdaMART reranker",
        "",
        f"_Generated by `evals/search/evaluate.py` on {r['generated_at']}. Every number below is recomputed from "
        "committed files (`snapshot_v1.json.gz`, `qrels_v1.jsonl`); no database is needed to reproduce it._",
        "",
        "> **Provisional labels.** Relevance judgments are an AI assistant's first pass (`human_audited: false`). "
        "Treat every number here as provisional until a human audits `evals/search/qrels_v1.jsonl`. "
        "See `evals/search/GUIDELINES.md` for the grading scale and the known biases.",
        "",
        "## Setup",
        "",
        f"- **Corpus:** {r['snapshot']['corpus']['articles']:,} articles in {r['snapshot']['corpus']['stories']:,} stories "
        f"(dev DB, frozen {r['snapshot']['as_of']}). The unit retrieved and judged is a story.",
        f"- **Queries:** {r['queries']} (entity {r['ndcg@10_by_query_type'].get('entity', {}).get('n', 0)}, "
        f"topical {r['ndcg@10_by_query_type'].get('topical', {}).get('n', 0)}, "
        f"natural-language question {r['ndcg@10_by_query_type'].get('question', {}).get('n', 0)}, "
        f"news event {r['ndcg@10_by_query_type'].get('event', {}).get('n', 0)}, "
        f"tail {r['ndcg@10_by_query_type'].get('tail', {}).get('n', 0)}), each with a written relevance narrative.",
        f"- **Judgments:** {r['judgments']['total']:,} graded (0-3) query-story pairs from TREC-style pooling "
        f"(hybrid top 50 + FTS/dense/BM25 top 20, shown blind to system), {r['judgments']['relevant']} relevant (grade ≥ 2), "
        f"{r['judgments']['manual_additions']} added manually for stories no system pooled.",
        "- **Metrics:** nDCG@10 (graded, gain 2^g-1), Recall@10/@50 and MRR (grade ≥ 2). "
        "95% CIs are percentile bootstraps over queries (10,000 resamples); deltas use a paired bootstrap.",
        "",
        "## Results",
        "",
        "| System | nDCG@10 | Recall@10 | Recall@50 | MRR |",
        "|---|---|---|---|---|",
    ]
    for sys_ in SYSTEMS:
        lines.append(f"| {label[sys_]} | " + " | ".join(fmt(s[sys_][m]) for m in METRICS) + " |")
    lines += [
        "",
        "Reranking only reorders the hybrid top 50, so its Recall@50 equals hybrid's by construction.",
        "",
        "### Paired differences (nDCG@10 unless stated)",
        "",
        "| Comparison | ΔnDCG@10 [95% CI] | ΔRecall@50 [95% CI] | share of resamples ≤ 0 |",
        "|---|---|---|---|",
    ]
    names = {
        "hybrid_vs_fts": "Hybrid - FTS",
        "hybrid_vs_dense": "Hybrid - dense",
        "bm25_vs_fts": "BM25 - Postgres FTS",
        "rrf_bm25_dense_vs_hybrid": "RRF(BM25, dense) - hybrid",
        "rerank_vs_hybrid": "LambdaMART - hybrid",
    }
    for k, v in c.items():
        lines.append(
            f"| {names[k]} | {fmt_delta(v['ndcg@10'])} | {fmt_delta(v['recall@50'])} | {v['ndcg@10']['p_le_0']:.3f} |"
        )
    lines += [
        "",
        "### nDCG@10 by query type",
        "",
        "| Type | n | " + " | ".join(SYSTEMS) + " |",
        "|---|---|" + "---|" * len(SYSTEMS),
    ]
    for t, row in r["ndcg@10_by_query_type"].items():
        lines.append(f"| {t} | {int(row['n'])} | " + " | ".join(f"{row[x]:.3f}" for x in SYSTEMS) + " |")
    zero, lh = r["lexical_zero_hit_queries"], r["lexical_hits"]
    lines += [
        "",
        f"**Why FTS alone recalls so little:** `websearch_to_tsquery` requires every query term, so FTS returned a median of "
        f"{lh['median']:.0f} articles per query, fewer than 10 for {lh['queries_under_10']} of {r['queries']} queries, and none "
        f"for {len(zero)} (" + ", ".join(f"`{queries[q]['query']}`" for q in zero) + "). "
        f"Those {lh['queries_under_10']} thin-lexical queries account for {lh['share_of_hybrid_gain_over_fts_from_them']:.0%} "
        "of hybrid's nDCG@10 gain over FTS; the dense list fills the gap. BM25's OR semantics are the other half of the same story.",
        "",
        "## Reranker",
        "",
        f"- LightGBM LambdaMART, {r['rerank']['trees']} trees, parameters fixed before the first run: "
        f"`num_leaves={PARAMS['num_leaves']}`, `learning_rate={PARAMS['learning_rate']}`, `min_child_samples={PARAMS['min_child_samples']}`, "
        f"`lambdarank_truncation_level={PARAMS['lambdarank_truncation_level']}`.",
        f"- Scored only out-of-fold: grouped {r['rerank']['folds']}-fold CV by query, repeated {r['rerank']['repeats']} times. "
        "nDCG@10 per repeat: " + ", ".join(f"{x:.3f}" for x in r["rerank"]["ndcg@10_per_repeat"]) + ".",
        f"- {len(FEATURE_NAMES)} features, one definition shared by training, the CI gate and serving (`xm_search.rerank.features`). "
        "Top features by share of split gain:",
        "",
        "| Feature | Gain share |",
        "|---|---|",
    ]
    for name, share in list(r["rerank"]["feature_importance_gain"].items())[:8]:
        lines.append(f"| `{name}` | {share:.3f} |")
    lines += [
        "",
        f"- The shipped model (`config/search_reranker.v1.json`) is refit on all {r['queries']} queries and evaluated in "
        "serving by a pure-Python tree walker, so the API image carries no LightGBM/OpenMP dependency. Its predictions "
        f"match LightGBM's to {r['rerank']['export_max_abs_diff']:.1e}.",
    ]

    def verdict(key: str) -> str:
        d = c[key]["ndcg@10"]
        if d["lo"] > 0:
            return f"better (ΔnDCG@10 {fmt_delta(d)}, CI excludes 0)"
        if d["hi"] < 0:
            return f"worse (ΔnDCG@10 {fmt_delta(d)}, CI excludes 0)"
        return f"not distinguishable (ΔnDCG@10 {fmt_delta(d)}, CI includes 0)"

    lines += [
        "",
        "## Conclusions",
        "",
        f"1. **Keep hybrid RRF as the serving retriever.** Against FTS alone it is {verdict('hybrid_vs_fts')}; "
        f"against dense alone it is {verdict('hybrid_vs_dense')}.",
        f"2. **Postgres FTS is the weak leg, but swapping it for BM25 inside RRF does not help here.** BM25 alone vs "
        f"FTS alone: {verdict('bm25_vs_fts')}. RRF(BM25, dense) vs today's hybrid: {verdict('rrf_bm25_dense_vs_hybrid')}. "
        "The cheaper next step is relaxing FTS to OR semantics with a match-count feature, measured the same way.",
        f"3. **Do not turn the reranker on by default yet.** Out-of-fold, LambdaMART vs hybrid: "
        f"{verdict('rerank_vs_hybrid')}; MRR moves {s['hybrid']['mrr']['mean']:.3f} → {s['rerank']['mrr']['mean']:.3f}. "
        "The model, features and serving evaluator ship and are pinned by the CI gate, so enabling it is a config change "
        "once a larger, human-audited query set shows a gain whose CI excludes zero.",
        "",
        "## Limitations",
        "",
        "1. **One judge, and it is an AI.** No inter-annotator agreement; grades 0 vs 1 on long-form posts are the least reliable.",
        "2. **Query selection bias.** Queries were written after reading the corpus, so they favour topics it covers well.",
        f"3. **Small sample.** {r['queries']} queries; CIs are wide and they are the honest summary, not the point estimates.",
        "4. **Pool bias.** Unjudged stories count as non-relevant. Pooling four systems plus manual additions limits, "
        "but does not remove, the bias against a system that finds relevant stories nobody else ranked.",
        "5. **Snapshot, not live.** Freshness features are computed as of the snapshot time; a live index drifts from it.",
        "6. **The reranker was trained on these same 62 queries** (out-of-fold for every number above). A new query set is needed "
        "before claiming the gain generalises.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "uv run python evals/search/snapshot.py        # needs the dev DB; refreezes candidates (only when the corpus changes)",
        "uv run python evals/search/pool.py            # needs the dev DB; judging pool, blind to system",
        "uv run python evals/search/apply_judgments.py # judgments -> qrels_v1.jsonl",
        "uv run python evals/search/evaluate.py        # this report, results_v1.json, baseline_v1.json, the model",
        "uv run pytest evals/search -q                 # the CI regression gate",
        "```",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
