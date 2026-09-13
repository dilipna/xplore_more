"""Evaluate pain-point classifiers on labels_v1 and train the serving artifact.

    uv run python evals/problems/evaluate.py            # evaluate, write results + report + artifact

Methodology
- Dataset: evals/problems/labels_v1.jsonl (485 discussion docs, stratified by source).
  Labels are the assistant's first pass (human_audited=false) unless a human audit
  supplied human_label, which then wins. Every number is provisional until audited.
- Features are built with the serving code (xm_problems.classifier.build_features) from
  real bge-small embeddings of "title\\nlede", the same input the indexer embeds.
- Methods:
    rules              hand-written cue groups in precedence order (nothing fitted)
    zero_shot          cosine to embedded label descriptions (nothing fitted)
    logreg_embedding   multinomial logistic regression on the embedding only
    logreg_full        embedding + cue counts + is_comment + platform one-hot
- Every fitted number is out-of-fold: 5-fold stratified CV repeated 10 times. C is chosen by
  an inner 3-fold CV on each outer training fold (macro-F1), and the decision threshold on
  p_problem is chosen on that inner out-of-fold output (highest recall with precision >=
  target), then applied unchanged to the outer test fold.
- Binary target: is_problem = label in {bug_or_reliability, cost_or_performance,
  missing_capability, workflow_friction}. how_to_question counts as not a problem here.
- Two views: "sample" (rows as drawn; small strata are over-represented) and "population"
  (each row weighted by stratum_size / stratum_sample_size).
- 95% CIs: percentile bootstrap over items (2,000 resamples) on repeat 0's predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold
from sklearn.preprocessing import StandardScaler

from xm_core.settings import get_settings
from xm_embed.embedder import FastEmbedEmbedder
from xm_problems.classifier import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    PainClassifier,
    build_features,
    cue_text,
    embedding_text,
    feature_schema,
    schema_hash,
)
from xm_problems.cues import LABELS, PROBLEM_LABELS, rule_label

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRECISION_TARGET = 0.80
# First run used 0.003..0.3 and picked the 0.003 edge most often, so the grid extends lower.
C_GRID = (0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3)
SEED = 13
REPEATS = 10
FOLDS = 5
BOOTSTRAP = 2000

LABEL_DESCRIPTIONS = {
    "bug_or_reliability": "Something is broken: an error, crash, regression, failure or data loss.",
    "cost_or_performance": "It works but is too slow, too expensive, uses too much memory or does not scale.",
    "missing_capability": "A needed feature or tool does not exist; a feature request or asking if a tool exists.",
    "workflow_friction": "The process is tedious, manual, confusing or painful even though it technically works.",
    "how_to_question": "Asking how to do something or for advice on the right approach.",
    "not_a_problem": "Opinion, news reaction, praise, a joke, show and tell, or a personal life question.",
}


# --- data -----------------------------------------------------------------------------


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in rows:
        r["gold"] = r["human_label"] if r.get("human_audited") and r.get("human_label") else r["label"]
    return rows


def embed_rows(rows: list[dict[str, Any]]) -> np.ndarray:
    texts = [embedding_text(r["title"], r["text"]) for r in rows]
    digest = hashlib.sha256("\x1e".join(texts).encode()).hexdigest()[:16]
    cache = HERE / ".cache" / f"embeddings-{digest}.npy"
    if cache.exists():
        return np.load(cache)
    settings = get_settings()
    embedder = FastEmbedEmbedder(EMBEDDING_MODEL, EMBEDDING_DIM, settings.embedding_cache_dir)
    vectors = np.asarray(embedder.embed(texts), dtype=np.float64)
    cache.parent.mkdir(exist_ok=True)
    np.save(cache, vectors)
    return vectors


def full_features(rows: list[dict[str, Any]], emb: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            build_features(e, r["title"], r["text"], r["platform"], r["is_comment"])
            for r, e in zip(rows, emb, strict=True)
        ]
    )


# --- metrics --------------------------------------------------------------------------


def prf(tp: float, fp: float, fn: float) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0}


def binary(y_true: np.ndarray, y_pred: np.ndarray, w: np.ndarray | None = None) -> dict[str, float]:
    w = np.ones(len(y_true)) if w is None else w
    return prf(
        float(w[y_true & y_pred].sum()), float(w[~y_true & y_pred].sum()), float(w[y_true & ~y_pred].sum())
    )


def multiclass(gold: list[str], pred: list[str]) -> dict[str, Any]:
    per_class = {}
    for label in LABELS:
        tp = sum(g == label and p == label for g, p in zip(gold, pred, strict=True))
        fp = sum(g != label and p == label for g, p in zip(gold, pred, strict=True))
        fn = sum(g == label and p != label for g, p in zip(gold, pred, strict=True))
        per_class[label] = {**prf(tp, fp, fn), "support": sum(g == label for g in gold)}
    return {
        "accuracy": float(np.mean([g == p for g, p in zip(gold, pred, strict=True)])),
        "macro_f1": float(np.mean([m["f1"] for m in per_class.values()])),
        "per_class": per_class,
    }


def bootstrap_ci(y_true: np.ndarray, y_pred: np.ndarray, rng: np.random.Generator) -> dict[str, list[float]]:
    n = len(y_true)
    stats = {"precision": [], "recall": [], "f1": []}
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, n, n)
        m = binary(y_true[idx], y_pred[idx])
        for k in stats:
            stats[k].append(m[k])
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in stats.items()}


def choose_threshold(y_true: np.ndarray, p_problem: np.ndarray) -> float:
    """Highest recall with precision >= target; falls back to the most precise threshold."""
    best_t, best_recall, fallback_t, fallback_p = 0.5, -1.0, 0.5, -1.0
    for t in np.unique(np.round(p_problem, 6)):
        m = binary(y_true, p_problem >= t)
        if m["precision"] >= PRECISION_TARGET and m["recall"] > best_recall:
            best_t, best_recall = float(t), m["recall"]
        if m["precision"] > fallback_p:
            fallback_t, fallback_p = float(t), m["precision"]
    return best_t if best_recall >= 0 else fallback_t


# --- models ---------------------------------------------------------------------------


def fit_lr(x: np.ndarray, y: np.ndarray, c: float) -> tuple[StandardScaler, LogisticRegression]:
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=c, max_iter=5000, class_weight="balanced")
    model.fit(scaler.transform(x), y)
    return scaler, model


def proba_in_label_order(scaler: StandardScaler, model: LogisticRegression, x: np.ndarray) -> np.ndarray:
    raw = model.predict_proba(scaler.transform(x))
    out = np.zeros((len(x), len(LABELS)))
    for j, cls in enumerate(model.classes_):
        out[:, LABELS.index(cls)] = raw[:, j]
    return out


PROBLEM_MASK = np.array([label in PROBLEM_LABELS for label in LABELS])


def decide(proba: np.ndarray, threshold: float) -> tuple[list[str], np.ndarray]:
    p_problem = proba[:, PROBLEM_MASK].sum(axis=1)
    is_problem = p_problem >= threshold
    labels = []
    for row, positive in zip(proba, is_problem, strict=True):
        side = PROBLEM_MASK if positive else ~PROBLEM_MASK
        labels.append(LABELS[int(np.where(side, row, -1.0).argmax())])
    return labels, is_problem


def inner_select(x: np.ndarray, y: np.ndarray, seed: int) -> tuple[float, float]:
    """Pick C by inner-CV macro-F1, then the threshold on that C's inner out-of-fold output."""
    inner = StratifiedKFold(n_splits=3, shuffle=True, random_state=seed)
    best: tuple[float, float, np.ndarray] | None = None
    for c in C_GRID:
        oof = np.zeros((len(x), len(LABELS)))
        for tr, te in inner.split(x, y):
            scaler, model = fit_lr(x[tr], y[tr], c)
            oof[te] = proba_in_label_order(scaler, model, x[te])
        f1 = multiclass(list(y), [LABELS[i] for i in oof.argmax(axis=1)])["macro_f1"]
        if best is None or f1 > best[1]:
            best = (c, f1, oof)
    assert best is not None
    c, _, oof = best
    y_problem = np.isin(y, list(PROBLEM_LABELS))
    return c, choose_threshold(y_problem, oof[:, PROBLEM_MASK].sum(axis=1))


def evaluate_lr(name: str, x: np.ndarray, rows: list[dict[str, Any]]) -> dict[str, Any]:
    y = np.array([r["gold"] for r in rows])
    cv = RepeatedStratifiedKFold(n_splits=FOLDS, n_repeats=REPEATS, random_state=SEED)
    preds = np.empty((REPEATS, len(rows)), dtype=object)
    decisions = np.zeros((REPEATS, len(rows)), dtype=bool)
    argmax_problem = np.zeros((REPEATS, len(rows)), dtype=bool)
    chosen_c: list[float] = []
    thresholds: list[float] = []
    for fold, (tr, te) in enumerate(cv.split(x, y)):
        repeat = fold // FOLDS
        c, t = inner_select(x[tr], y[tr], seed=SEED + fold)
        chosen_c.append(c)
        thresholds.append(t)
        scaler, model = fit_lr(x[tr], y[tr], c)
        proba = proba_in_label_order(scaler, model, x[te])
        labels, is_problem = decide(proba, t)
        preds[repeat, te] = labels
        decisions[repeat, te] = is_problem
        argmax_problem[repeat, te] = PROBLEM_MASK[proba.argmax(axis=1)]
        if (fold + 1) % FOLDS == 0:
            print(f"  {name}: repeat {repeat + 1}/{REPEATS} done")
    return summarize(name, rows, preds, decisions, argmax_problem, chosen_c, thresholds)


def evaluate_static(name: str, labels: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    preds = np.array([labels] * REPEATS, dtype=object)
    decisions = np.array([[label in PROBLEM_LABELS for label in labels]] * REPEATS)
    return summarize(name, rows, preds, decisions, decisions, [], [])


def summarize(
    name: str,
    rows: list[dict[str, Any]],
    preds: np.ndarray,
    decisions: np.ndarray,
    argmax_problem: np.ndarray,
    chosen_c: list[float],
    thresholds: list[float],
) -> dict[str, Any]:
    gold = [r["gold"] for r in rows]
    y_problem = np.array([g in PROBLEM_LABELS for g in gold])
    weights = np.array([r["stratum_size"] / r["stratum_sample_size"] for r in rows])
    high = np.array([r["confidence"] == "high" for r in rows])
    pooled_gold = gold * REPEATS
    pooled_pred = [p for rep in preds for p in rep]
    per_repeat = [binary(y_problem, decisions[k]) for k in range(REPEATS)]
    per_repeat_mc = [multiclass(gold, list(preds[k])) for k in range(REPEATS)]
    by_stratum = {}
    for stratum in sorted({r["stratum"] for r in rows}):
        mask = np.array([r["stratum"] == stratum for r in rows])
        by_stratum[stratum] = {
            **binary(np.tile(y_problem[mask], REPEATS), decisions[:, mask].reshape(-1)),
            "n": int(mask.sum()),
            "positives": int(y_problem[mask].sum()),
        }
    rng = np.random.default_rng(SEED)
    discussion = np.array([r["platform"] != "github" for r in rows])
    return {
        "method": name,
        "multiclass_pooled": multiclass(pooled_gold, pooled_pred),
        "macro_f1_mean": float(np.mean([m["macro_f1"] for m in per_repeat_mc])),
        "macro_f1_std": float(np.std([m["macro_f1"] for m in per_repeat_mc])),
        "binary_operating": {
            "sample": binary(np.tile(y_problem, REPEATS), decisions.reshape(-1)),
            "population": binary(
                np.tile(y_problem, REPEATS), decisions.reshape(-1), np.tile(weights, REPEATS)
            ),
            "high_confidence_labels": binary(
                np.tile(y_problem[high], REPEATS), decisions[:, high].reshape(-1)
            ),
            "precision_std_over_repeats": float(np.std([m["precision"] for m in per_repeat])),
            "recall_std_over_repeats": float(np.std([m["recall"] for m in per_repeat])),
            "ci95_repeat0": bootstrap_ci(y_problem, decisions[0], rng),
            "by_stratum": by_stratum,
            "excluding_github": {
                **binary(np.tile(y_problem[discussion], REPEATS), decisions[:, discussion].reshape(-1)),
                "n": int(discussion.sum()),
                "positives": int(y_problem[discussion].sum()),
            },
        },
        "binary_argmax": binary(np.tile(y_problem, REPEATS), argmax_problem.reshape(-1)),
        "chosen_C": dict(Counter(chosen_c)),
        "threshold_mean": float(np.mean(thresholds)) if thresholds else None,
        "threshold_std": float(np.std(thresholds)) if thresholds else None,
    }


def zero_shot_labels(emb: np.ndarray) -> list[str]:
    settings = get_settings()
    embedder = FastEmbedEmbedder(EMBEDDING_MODEL, EMBEDDING_DIM, settings.embedding_cache_dir)
    anchors = np.asarray([embedder.embed_query(LABEL_DESCRIPTIONS[label]) for label in LABELS])
    anchors /= np.linalg.norm(anchors, axis=1, keepdims=True)
    docs = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    return [LABELS[i] for i in (docs @ anchors.T).argmax(axis=1)]


# --- artifact -------------------------------------------------------------------------


def train_artifact(x: np.ndarray, rows: list[dict[str, Any]], result: dict[str, Any], dataset: Path) -> dict:
    y = np.array([r["gold"] for r in rows])
    c = Counter(result["chosen_C"]).most_common(1)[0][0]
    # Threshold for the shipped model: out-of-fold p_problem averaged over repeats at that C.
    cv = RepeatedStratifiedKFold(n_splits=FOLDS, n_repeats=REPEATS, random_state=SEED + 1)
    p_sum, counts = np.zeros(len(rows)), np.zeros(len(rows))
    for tr, te in cv.split(x, y):
        scaler, model = fit_lr(x[tr], y[tr], c)
        p_sum[te] += proba_in_label_order(scaler, model, x[te])[:, PROBLEM_MASK].sum(axis=1)
        counts[te] += 1
    y_problem = np.isin(y, list(PROBLEM_LABELS))
    threshold = choose_threshold(y_problem, p_sum / counts)

    scaler, model = fit_lr(x, y, c)
    order = [list(model.classes_).index(label) for label in LABELS]
    schema = feature_schema()
    artifact = {
        "version": "pain-v1-" + datetime.now(UTC).strftime("%Y%m%d"),
        "labels": list(LABELS),
        "feature_schema": schema,
        "feature_schema_hash": schema_hash(schema),
        "threshold": round(threshold, 6),
        "precision_target": PRECISION_TARGET,
        "C": c,
        "feature_mean": [round(float(v), 8) for v in np.asarray(scaler.mean_)],
        "feature_scale": [round(float(v), 8) for v in np.asarray(scaler.scale_)],
        "coef": [[round(float(v), 8) for v in np.asarray(model.coef_)[i]] for i in order],
        "intercept": [round(float(np.asarray(model.intercept_)[i]), 8) for i in order],
        "training": {
            "dataset": str(dataset.relative_to(ROOT)).replace("\\", "/"),
            "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "rows": len(rows),
            "human_audited_rows": sum(bool(r.get("human_audited")) for r in rows),
            "labels_provisional": not all(r.get("human_audited") for r in rows),
        },
    }
    # Parity: the numpy serving path must reproduce sklearn's probabilities.
    served = PainClassifier(artifact).predict_proba(x)
    reference = proba_in_label_order(scaler, model, x)
    max_diff = float(np.abs(served - reference).max())
    if max_diff > 1e-5:
        raise SystemExit(f"serving parity failed: max |p_served - p_sklearn| = {max_diff}")
    artifact["training"]["serving_parity_max_abs_diff"] = max_diff
    return artifact


# --- report ---------------------------------------------------------------------------


def pct(v: float) -> str:
    return f"{100 * v:.1f}%"


def write_report(results: dict[str, Any], path: Path) -> None:
    methods = results["methods"]
    lines = [
        "# Pain-point classifier v1: evaluation report",
        "",
        f"> Generated by `uv run python evals/problems/evaluate.py` on {results['created_at']}. "
        "Do not edit numbers by hand; re-run the script.",
        "",
        "## Read this first",
        "",
        f"- **Labels are provisional.** {results['dataset']['rows']} items labeled by an AI assistant "
        f"(`human_audited: false`; {results['dataset']['human_audited_rows']} audited so far). "
        "The metrics measure agreement with those labels, not verified truth. "
        "Audit with `uv run python evals/problems/audit.py`.",
        f"- **Small minority classes.** Supports: {results['dataset']['label_counts']}. "
        "Per-class numbers for classes under 30 items are unstable; the binary view is the decision that matters.",
        "- All fitted numbers are out-of-fold (5-fold stratified CV x 10 repeats, nested selection of C and threshold).",
        "",
        f"## Binary: is this a problem? (operating point, precision target {pct(PRECISION_TARGET)})",
        "",
        "| Method | Precision | Recall | F1 | Precision (population) | Recall (population) | 95% CI precision | 95% CI recall |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in methods:
        b = m["binary_operating"]
        ci = b["ci95_repeat0"]
        lines.append(
            f"| {m['method']} | {pct(b['sample']['precision'])} | {pct(b['sample']['recall'])} | "
            f"{pct(b['sample']['f1'])} | {pct(b['population']['precision'])} | {pct(b['population']['recall'])} | "
            f"{pct(ci['precision'][0])} to {pct(ci['precision'][1])} | "
            f"{pct(ci['recall'][0])} to {pct(ci['recall'][1])} |"
        )
    lines += [
        "",
        "Rules and zero-shot have no threshold, so their operating point is their argmax label.",
        "",
        "## Six-way category",
        "",
        "| Method | Accuracy (pooled) | Macro-F1 (mean ± sd over repeats) |",
        "|---|---|---|",
    ]
    for m in methods:
        lines.append(
            f"| {m['method']} | {pct(m['multiclass_pooled']['accuracy'])} | "
            f"{m['macro_f1_mean']:.3f} ± {m['macro_f1_std']:.3f} |"
        )
    best = results["selected_method"]
    sel = next(m for m in methods if m["method"] == best)
    lines += [
        "",
        f"### Per class: `{best}` (pooled out-of-fold)",
        "",
        "| Label | Support | Precision | Recall | F1 |",
        "|---|---|---|---|---|",
    ]
    for label, v in sel["multiclass_pooled"]["per_class"].items():
        lines.append(
            f"| {label} | {v['support'] // REPEATS} | {pct(v['precision'])} | {pct(v['recall'])} | {pct(v['f1'])} |"
        )
    lines += [
        "",
        f"### By source: `{best}` binary operating point",
        "",
        "| Stratum | n | Problems (gold) | Precision | Recall |",
        "|---|---|---|---|---|",
    ]
    for stratum, v in sel["binary_operating"]["by_stratum"].items():
        lines.append(
            f"| {stratum} | {v['n']} | {v['positives']} | {pct(v['precision'])} | {pct(v['recall'])} |"
        )
    art = results["artifact"]
    hc = sel["binary_operating"]["high_confidence_labels"]
    ex = sel["binary_operating"]["excluding_github"]
    pop = sel["binary_operating"]["population"]
    gh = sel["binary_operating"]["by_stratum"].get("github-issues-ai", {})
    rules_ex = next(m for m in methods if m["method"] == "rules")["binary_operating"]["excluding_github"]
    lines += [
        "",
        "## Findings",
        "",
        f"1. **The headline precision is carried by GitHub issues.** GitHub items are {gh.get('positives', 0)} "
        f"problems out of {gh.get('n', 0)}, and `{best}` gets them right "
        f"(P {pct(gh.get('precision', 0))}, R {pct(gh.get('recall', 0))}). On the other platforms "
        f"({ex['n']} items, {ex['positives']} problems) it reaches only P {pct(ex['precision'])}, "
        f"R {pct(ex['recall'])} (rules: P {pct(rules_ex['precision'])}, R {pct(rules_ex['recall'])}). "
        "Finding problems inside open discussion is the hard part, and v1 does not solve it yet.",
        f"2. **The precision target is met on the sample, not on the population.** Population-weighted "
        f"precision is {pct(pop['precision'])} because discussion platforms dominate the real stream.",
        "3. **Minority categories are not learned.** `workflow_friction` and `cost_or_performance` have 18 "
        "examples each; their F1 is far below the other classes. Category is a hint, not a fact, in v1.",
        "4. **Consequences for P3 (problem clustering):** use `p_problem` as a soft weight rather than a hard "
        "filter, require several independent voices before a cluster is ranked, and keep platform in the "
        "demand score's evidence so a reader can see that a problem is GitHub-only.",
        "5. **Next data step:** a v2 set with active sampling (high-`p_problem` HN/Lobsters items, "
        "where positives are rare) and a human audit of the low- and medium-confidence labels first.",
        "",
        "## Shipped artifact",
        "",
        f"- `config/problem_classifier.v1.json`, version `{art['version']}`, method `{best}`, "
        f"C = {art['C']}, threshold on p_problem = {art['threshold']:.3f}.",
        f"- Feature schema hash `{art['feature_schema_hash'][:16]}…`; loading refuses a mismatched schema.",
        f"- Serving parity: numpy path vs sklearn max |Δp| = {art['serving_parity_max_abs_diff']:.2e}.",
        f"- Sensitivity: on high-confidence labels only, precision {pct(hc['precision'])}, recall {pct(hc['recall'])}.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "uv run python evals/problems/evaluate.py",
        "```",
        "",
        "Embeddings are cached in `evals/problems/.cache/` (gitignored) keyed by a hash of the input texts.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=HERE / "labels_v1.jsonl")
    args = parser.parse_args()

    rows = load_rows(args.dataset)
    emb = embed_rows(rows)
    x_full = full_features(rows, emb)
    print(f"{len(rows)} rows, {x_full.shape[1]} features")

    methods = [
        evaluate_static(
            "rules", [rule_label(cue_text(r["title"], r["text"], r["is_comment"])) for r in rows], rows
        ),
        evaluate_static("zero_shot", zero_shot_labels(emb), rows),
        evaluate_lr("logreg_embedding", emb, rows),
        evaluate_lr("logreg_full", x_full, rows),
    ]
    fitted = [m for m in methods if m["method"].startswith("logreg")]
    selected = max(fitted, key=lambda m: m["binary_operating"]["sample"]["f1"])
    x_selected = x_full if selected["method"] == "logreg_full" else None
    if x_selected is None:
        raise SystemExit("serving supports logreg_full features only; embedding-only won, revisit")
    artifact = train_artifact(x_selected, rows, selected, args.dataset)
    (ROOT / "config" / "problem_classifier.v1.json").write_text(json.dumps(artifact) + "\n", encoding="utf-8")

    results = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": {
            "path": artifact["training"]["dataset"],
            "sha256": artifact["training"]["dataset_sha256"],
            "rows": len(rows),
            "human_audited_rows": artifact["training"]["human_audited_rows"],
            "label_counts": dict(Counter(r["gold"] for r in rows).most_common()),
        },
        "protocol": {
            "folds": FOLDS,
            "repeats": REPEATS,
            "seed": SEED,
            "C_grid": C_GRID,
            "precision_target": PRECISION_TARGET,
            "bootstrap": BOOTSTRAP,
        },
        "methods": methods,
        "selected_method": selected["method"],
        "artifact": {k: artifact[k] for k in ("version", "C", "threshold", "feature_schema_hash")}
        | {"serving_parity_max_abs_diff": artifact["training"]["serving_parity_max_abs_diff"]},
    }
    (HERE / "results_v1.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    write_report(results, ROOT / "docs" / "reports" / "problem-classifier-v1.md")
    for m in methods:
        b = m["binary_operating"]["sample"]
        print(
            f"{m['method']:18s} P={b['precision']:.3f} R={b['recall']:.3f} F1={b['f1']:.3f} "
            f"macroF1={m['macro_f1_mean']:.3f}"
        )


if __name__ == "__main__":
    main()
