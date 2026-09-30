"""A 2-D map of stories and problems by meaning.

numpy only and deterministic: t-SNE (exact gradients, fine for the ~1k points a week holds) lays
out the embeddings, k-means finds islands in the layout, and each island is labelled with its
most distinctive title words (class-based TF-IDF). Nothing is generated: labels are words that
appear in the titles.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

_WORD = re.compile(r"[a-z][a-z0-9.+#-]{2,}")
_STOPWORD_TEXT = (
    "the and for with from that this your you are was were will can not but its into over about "
    "how why what when who new now just more than all our out has have had use using used via "
    "ask show tell github com www http https release releases introducing announcing launch "
    "launches launched says said make makes made get gets based one two first after before "
    "without while their they them his her it's i'm don't isn't we're you're here there where "
    "which also some any may might should would could does did doing done very much many most "
    "other another such only own same then too ever still even back off like want need "
)
# Publisher names and issue-tracker boilerplate say nothing about what an island is about.
_NOISE = (
    "techcrunch blog verge register amazon web services aws nvidia technical source support add file "
    "feature request issue update version latest"
)
STOPWORDS = frozenset(_STOPWORD_TEXT.split()) | frozenset(_NOISE.split())


def _pca(x: np.ndarray, k: int) -> np.ndarray:
    centered = x - x.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ vt[:k].T


def _sq_dists(y: np.ndarray) -> np.ndarray:
    s = np.sum(y * y, axis=1)
    return np.maximum(s[:, None] + s[None, :] - 2.0 * (y @ y.T), 0.0)


def _affinities(d2: np.ndarray, perplexity: float) -> np.ndarray:
    """Row-wise Gaussian affinities whose entropy matches log(perplexity) (binary search on beta)."""
    n = d2.shape[0]
    target = math.log(perplexity)
    p = np.zeros((n, n))
    for i in range(n):
        di = np.delete(d2[i], i)
        lo, hi, beta = 0.0, np.inf, 1.0
        w = np.exp(-(di - di.min()) * beta)
        sw = float(w.sum())
        for _ in range(64):
            w = np.exp(-(di - di.min()) * beta)
            sw = float(w.sum())
            h = math.log(sw) + beta * float((di - di.min()) @ w) / sw
            if abs(h - target) < 1e-5:
                break
            if h > target:
                lo, beta = beta, beta * 2 if hi == np.inf else (beta + hi) / 2
            else:
                hi, beta = beta, (beta + lo) / 2
        p[i, np.arange(n) != i] = w / sw
    return p


def tsne(x: np.ndarray, *, perplexity: float = 30.0, iters: int = 400) -> np.ndarray:
    """Deterministic t-SNE to 2-D (PCA initialisation, no random numbers)."""
    n = x.shape[0]
    if n < 5:
        out = np.zeros((n, 2))
        if n > 1:
            out[:, : min(2, n - 1)] = _pca(x, min(2, n - 1))
        return out
    x = _pca(x.astype(np.float64), min(50, x.shape[1], n - 1))  # denoise and speed up distances
    perplexity = min(perplexity, (n - 1) / 3.0)
    p = _affinities(_sq_dists(x), perplexity)
    p = np.maximum((p + p.T) / (2.0 * n), 1e-12)
    y = _pca(x, 2)
    y = y / (np.std(y[:, 0]) + 1e-12) * 1e-4
    velocity = np.zeros_like(y)
    gains = np.ones_like(y)
    lr = max(n / 12.0 / 4.0, 50.0)
    for it in range(iters):
        exaggeration, momentum = (12.0, 0.5) if it < 150 else (1.0, 0.8)
        num = 1.0 / (1.0 + _sq_dists(y))
        np.fill_diagonal(num, 0.0)
        q = np.maximum(num / num.sum(), 1e-12)
        pq = (exaggeration * p - q) * num
        grad = 4.0 * (pq.sum(axis=1)[:, None] * y - pq @ y)
        gains = np.where(np.sign(grad) != np.sign(velocity), gains + 0.2, gains * 0.8).clip(min=0.01)
        velocity = momentum * velocity - lr * gains * grad
        y = y + velocity
        y = y - y.mean(axis=0)
    return y


def kmeans(y: np.ndarray, k: int, *, iters: int = 50) -> np.ndarray:
    """Deterministic k-means. Initial centres: farthest-point picks among points in dense regions
    (5th-neighbour radius at or below the median), so lone outliers never seed an island."""
    n = y.shape[0]
    k = max(1, min(k, n))
    d2 = _sq_dists(y)
    radius = np.sort(d2, axis=1)[:, min(5, n - 1)]
    dense = y[radius <= np.median(radius)]
    centers = [dense[int(np.argmin(np.sum((dense - y.mean(axis=0)) ** 2, axis=1)))]]
    for _ in range(1, k):
        d = np.min(np.stack([np.sum((dense - c) ** 2, axis=1) for c in centers]), axis=0)
        centers.append(dense[int(np.argmax(d))])
    c = np.array(centers)
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        labels = np.argmin(((y[:, None, :] - c[None, :, :]) ** 2).sum(axis=2), axis=1)
        new = np.array([y[labels == j].mean(axis=0) if np.any(labels == j) else c[j] for j in range(k)])
        if np.allclose(new, c):
            break
        c = new
    return labels


def tokens(title: str) -> list[str]:
    return [
        w.strip(".-")
        for w in _WORD.findall(title.lower())
        if w.strip(".-") not in STOPWORDS and len(w.strip(".-")) > 2
    ]


def island_labels(titles: list[str], labels: np.ndarray, top: int = 3) -> dict[int, list[str]]:
    """Class-based TF-IDF: words frequent in one island and rare in the others."""
    per: dict[int, Counter[str]] = {}
    for title, lab in zip(titles, labels, strict=True):
        per.setdefault(int(lab), Counter()).update(set(tokens(title)))
    k = len(per)
    df = Counter(w for c in per.values() for w in c)
    out: dict[int, list[str]] = {}
    for lab, counts in per.items():
        scored = sorted(
            ((cnt * math.log(1 + k / df[w]), w) for w, cnt in counts.items() if cnt >= 2),
            key=lambda t: (-t[0], t[1]),
        )
        out[lab] = [w for _, w in scored[:top]]
    return out


@dataclass(frozen=True)
class Layout:
    xy: np.ndarray  # (n, 2), scaled to [-1, 1]
    islands: np.ndarray  # (n,)
    labels: dict[int, list[str]]


def layout(vectors: np.ndarray, titles: list[str], *, k: int = 10) -> Layout:
    y = tsne(vectors)
    if len(y):
        y = y - y.mean(axis=0)
        span = float(np.abs(y).max()) or 1.0
        y = y / span
    islands = kmeans(y, k) if len(y) else np.zeros(0, dtype=int)
    return Layout(xy=y, islands=islands, labels=island_labels(titles, islands) if len(y) else {})
