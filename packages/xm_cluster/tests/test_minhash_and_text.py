from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from xm_cluster.entities import Gazetteer
from xm_cluster.minhash import MinHasher
from xm_cluster.text import jaccard, shingles, tokens

ROOT = Path(__file__).resolve().parents[3]


def _set_with_jaccard(target: float, size: int = 400, seed: int = 0) -> tuple[set[str], set[str]]:
    rng = random.Random(seed)
    shared = int(round(2 * size * target / (1 + target)))
    common = {f"c{i}" for i in range(shared)}
    a = common | {f"a{i}" for i in range(size - shared)}
    b = common | {f"b{i}" for i in range(size - shared)}
    assert abs(jaccard(a, b) - target) < 0.01
    rng.shuffle(list(a))
    return a, b


@pytest.mark.parametrize("target", [0.1, 0.3, 0.5, 0.8])
def test_signature_estimates_jaccard(target: float) -> None:
    mh = MinHasher(num_perm=256, bands=16)  # more permutations -> tighter estimate for the test
    a, b = _set_with_jaccard(target)
    est = mh.estimate_jaccard(mh.signature(a), mh.signature(b))
    # Standard error sqrt(J(1-J)/k) <= 0.032 at k=256; allow ~3 sigma.
    assert abs(est - target) < 0.1, (target, est)


def test_signature_is_deterministic_and_serializable() -> None:
    mh = MinHasher()
    s = shingles("OpenAI releases GPT-5.1 with better reasoning and lower latency for developers")
    sig = mh.signature(s)
    assert np.array_equal(sig, MinHasher().signature(s))
    assert np.array_equal(MinHasher.from_bytes(MinHasher.to_bytes(sig)), sig)
    assert len(MinHasher.to_bytes(sig)) == 256


def test_identical_text_shares_every_band_and_unrelated_text_shares_none() -> None:
    mh = MinHasher()
    a = shingles("Kubernetes 1.40 released with in-place pod resizing generally available")
    b = shingles("Kubernetes 1.40 released with in-place pod resizing generally available")
    c = shingles("Stripe acquires a stablecoin startup to expand payments in Latin America")
    ka, kb, kc = mh.band_keys(mh.signature(a)), mh.band_keys(mh.signature(b)), mh.band_keys(mh.signature(c))
    assert ka == kb
    assert not set(ka) & set(kc)


def test_band_collision_probability_matches_theory() -> None:
    mh = MinHasher()  # 16 bands x 4 rows
    trials, hits = 300, 0
    for seed in range(trials):
        a, b = _set_with_jaccard(0.5, size=200, seed=seed)
        # vary the universe so trials are independent
        a = {f"{seed}:{x}" for x in a}
        b = {f"{seed}:{x}" for x in b}
        hits += bool(set(mh.band_keys(mh.signature(a))) & set(mh.band_keys(mh.signature(b))))
    expected = 1 - (1 - 0.5**4) ** 16  # ~0.64
    assert abs(hits / trials - expected) < 0.1


@given(st.text(min_size=0, max_size=300))
@settings(max_examples=200)
def test_tokens_never_crash_and_are_lowercase(text: str) -> None:
    for t in tokens(text):
        assert t == t.lower()


def test_version_tokens_stay_whole() -> None:
    assert "gpt-5.1" in tokens("OpenAI ships GPT-5.1 today")
    assert "v0.29.0" in tokens("vLLM v0.29.0 is out")


def test_gazetteer_matches_longest_alias_and_respects_case() -> None:
    gz = Gazetteer.load(ROOT / "config" / "entities.yaml")
    found = gz.extract("Google DeepMind and Hugging Face released Gemma; GitHub Copilot adds MCP support")
    assert {"google-deepmind", "huggingface", "gemma", "copilot", "mcp"} <= found
    # Case-sensitive short aliases must not match common words.
    assert "go-lang" not in gz.extract("we will go to the store")
    assert "rust" not in gz.extract("rust on the bike chain")
    assert "rust" in gz.extract("Rust 1.90 improves compile times")
    # Word boundaries: 'Metadata' is not Meta, 'gemini-like' still counts only as a word.
    assert "meta" not in gz.extract("metadata catalog improvements")
