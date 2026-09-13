"""MinHash signatures and LSH band keys for near-duplicate candidate retrieval.

With b bands of r hashes each, two documents with Jaccard similarity s share at least one
band with probability 1 - (1 - s^r)^b. For r=4, b=16:
    s=0.3 -> 0.12,  s=0.5 -> 0.64,  s=0.7 -> 0.98
so syndicated copies and light rewrites are recalled, while unrelated articles rarely
collide. Band hits are only *candidates*; the pair scorer makes the decision.

Hashing is deterministic across processes and versions (blake2b + fixed seeds), which is
required because signatures and band keys are persisted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


def _shingle_hash(shingle: str) -> int:
    return int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")


@dataclass(frozen=True)
class MinHasher:
    num_perm: int = 64
    bands: int = 16
    seed: int = 20260913

    def __post_init__(self) -> None:
        if self.num_perm % self.bands != 0:
            raise ValueError("num_perm must be divisible by bands")

    @property
    def rows_per_band(self) -> int:
        return self.num_perm // self.bands

    def _params(self) -> tuple[npt.NDArray[np.uint64], npt.NDArray[np.uint64]]:
        rng = np.random.default_rng(self.seed)
        a = rng.integers(0, np.iinfo(np.uint64).max, size=self.num_perm, dtype=np.uint64, endpoint=True)
        b = rng.integers(0, np.iinfo(np.uint64).max, size=self.num_perm, dtype=np.uint64, endpoint=True)
        return a | np.uint64(1), b  # multiply-shift requires odd multipliers

    def signature(self, shingles: set[str]) -> npt.NDArray[np.uint32]:
        """Min over multiply-shift hashes h(x) = ((a*x + b) mod 2^64) >> 32.

        Wrap-around at 2^64 is the definition of the multiply-shift family (Dietzfelbinger),
        not an accident: uint64 arithmetic implements the modulus for free.
        """
        if not shingles:
            return np.full(self.num_perm, np.iinfo(np.uint32).max, dtype=np.uint32)
        a, b = self._params()
        hashes = np.array([_shingle_hash(s) for s in shingles], dtype=np.uint64)
        with np.errstate(over="ignore"):
            permuted = (hashes[:, None] * a[None, :] + b[None, :]) >> np.uint64(32)
        return np.min(permuted, axis=0).astype(np.uint32)

    def band_keys(self, signature: npt.NDArray[np.uint32]) -> list[int]:
        """One signed 64-bit key per band (Postgres BIGINT), prefixed by band index."""
        keys: list[int] = []
        r = self.rows_per_band
        for band in range(self.bands):
            chunk = signature[band * r : (band + 1) * r].tobytes()
            digest = hashlib.blake2b(bytes([band]) + chunk, digest_size=8).digest()
            keys.append(int.from_bytes(digest, "big", signed=True))
        return keys

    @staticmethod
    def estimate_jaccard(sig_a: npt.NDArray[np.uint32], sig_b: npt.NDArray[np.uint32]) -> float:
        return float(np.mean(sig_a == sig_b))

    @staticmethod
    def to_bytes(signature: npt.NDArray[np.uint32]) -> bytes:
        return signature.astype("<u4").tobytes()

    @staticmethod
    def from_bytes(raw: bytes) -> npt.NDArray[np.uint32]:
        return np.frombuffer(raw, dtype="<u4").astype(np.uint32)
