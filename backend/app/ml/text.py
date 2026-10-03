"""Turning customer-written text into numbers a model can use."""

import re
from collections import Counter
from collections.abc import Iterable

_WORD = re.compile(r"[a-z0-9']+")
UNKNOWN = "<unk>"


def tokenize(text: str) -> list[str]:
    """Lowercase words plus adjacent word pairs ("arrived_broken").

    Word pairs capture short phrases whose meaning differs from the words alone,
    e.g. "money_back" or "wrong_item".
    """
    words = _WORD.findall(text.lower())
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]


class Vocabulary:
    """Maps each known token to an integer id. Id 0 is reserved for unknown tokens."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self._index = {token: i for i, token in enumerate(tokens)}

    @classmethod
    def build(cls, texts: Iterable[str], min_count: int = 2) -> "Vocabulary":
        counts = Counter(token for text in texts for token in tokenize(text))
        # Rare tokens are dropped: they'd mostly teach the model to memorize typos.
        kept = sorted(token for token, n in counts.items() if n >= min_count)
        return cls([UNKNOWN, *kept])

    def encode(self, text: str) -> list[int]:
        ids = [self._index.get(token, 0) for token in tokenize(text)]
        return ids or [0]

    def __len__(self) -> int:
        return len(self.tokens)
