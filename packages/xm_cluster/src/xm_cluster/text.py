"""Text normalization shared by MinHash shingling and title-similarity features."""

from __future__ import annotations

import re
import unicodedata

_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")

# Words that carry no event identity in tech headlines.
_STOPWORD_TEXT = """
    a an and are as at be by for from has have how in into is it its new of on or our that the
    this to was we what when why will with you your via after over about now more than just
    announces announced launches launched introduces introducing releases released unveils
    unveiled says said today update updates report reports
"""
STOPWORDS = frozenset(_STOPWORD_TEXT.split())

_RIGHT_SINGLE_QUOTE = "\u2019"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return text.replace(_RIGHT_SINGLE_QUOTE, "'")


def tokens(text: str) -> list[str]:
    """Lowercase tokens; version-like tokens such as 'gpt-5.1' and 'v0.29.0' stay whole."""
    return _TOKEN.findall(normalize(text))


def content_tokens(text: str) -> list[str]:
    return [t for t in tokens(text) if t not in STOPWORDS and len(t) > 1]


def shingles(text: str, size: int = 3) -> set[str]:
    """Word n-gram shingles over content tokens; short texts fall back to unigrams."""
    toks = content_tokens(text)
    if len(toks) < size:
        return set(toks)
    return {" ".join(toks[i : i + size]) for i in range(len(toks) - size + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
