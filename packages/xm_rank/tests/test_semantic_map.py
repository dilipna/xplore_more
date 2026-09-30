from __future__ import annotations

import numpy as np

from xm_rank.semantic_map import island_labels, kmeans, layout, tokens, tsne


def blobs(n_per: int = 30, dim: int = 16) -> np.ndarray:
    rng = np.random.default_rng(7)
    centers = np.eye(dim)[:3] * 10
    return np.vstack([c + rng.normal(0, 0.3, (n_per, dim)) for c in centers])


def test_tsne_is_deterministic_and_2d() -> None:
    x = blobs()
    a, b = tsne(x, iters=300), tsne(x, iters=300)
    assert a.shape == (90, 2)
    assert np.array_equal(a, b)


def test_tsne_keeps_neighbours_together() -> None:
    y = tsne(blobs(), iters=300)
    groups = [y[i * 30 : (i + 1) * 30] for i in range(3)]
    within = max(float(np.linalg.norm(g - g.mean(axis=0), axis=1).mean()) for g in groups)
    between = min(
        float(np.linalg.norm(groups[i].mean(axis=0) - groups[j].mean(axis=0)))
        for i in range(3)
        for j in range(i + 1, 3)
    )
    assert between > 3 * within


def test_kmeans_recovers_separated_islands() -> None:
    y = tsne(blobs(), iters=300)
    labels = kmeans(y, 3)
    majorities = [int(np.bincount(labels[i * 30 : (i + 1) * 30]).argmax()) for i in range(3)]
    assert len(set(majorities)) == 3  # each blob gets its own island
    # t-SNE can strand a few noisy points away from their group; islands stay at least 90% pure.
    for i, m in enumerate(majorities):
        assert int((labels[i * 30 : (i + 1) * 30] == m).sum()) >= 27


def test_labels_are_words_from_the_titles() -> None:
    titles = [
        "vLLM speculative decoding",
        "vLLM decoding speedups",
        "Kubernetes pod resizing",
        "Kubernetes pod limits",
    ]
    labels = island_labels(titles, np.array([0, 0, 1, 1]))
    assert labels[0][0] in {"vllm", "decoding"} and labels[1][0] in {"kubernetes", "pod"}
    vocab = {w for t in titles for w in tokens(t)}
    assert all(w in vocab for words in labels.values() for w in words)


def test_publisher_names_are_not_labels() -> None:
    assert "techcrunch" not in tokens("OpenAI ships a model | TechCrunch")


def test_layout_scales_to_unit_box_and_handles_tiny_inputs() -> None:
    lay = layout(blobs(), [f"title {i}" for i in range(90)], k=3)
    assert float(np.abs(lay.xy).max()) <= 1.0 + 1e-9
    tiny = layout(np.eye(3), ["a", "b", "c"], k=3)
    assert tiny.xy.shape == (3, 2)
