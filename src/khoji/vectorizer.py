from __future__ import annotations

from collections import Counter
from math import log, sqrt

from .normalization import char_ngrams


SparseVector = dict[str, float]


class CharNgramTfidf:
    def __init__(self, min_n: int = 3, max_n: int = 5) -> None:
        self.min_n = min_n
        self.max_n = max_n
        self.idf: dict[str, float] = {}

    def fit(self, documents: list[str]) -> "CharNgramTfidf":
        document_count = len(documents)
        document_frequencies: Counter[str] = Counter()
        for document in documents:
            document_frequencies.update(
                set(char_ngrams(document, self.min_n, self.max_n))
            )

        self.idf = {
            token: log((1 + document_count) / (1 + frequency)) + 1.0
            for token, frequency in document_frequencies.items()
        }
        return self

    def transform_one(self, document: str) -> SparseVector:
        counts = Counter(char_ngrams(document, self.min_n, self.max_n))
        if not counts:
            return {}

        vector = {
            token: count * self.idf.get(token, 0.0)
            for token, count in counts.items()
            if token in self.idf
        }
        norm = sqrt(sum(value * value for value in vector.values()))
        if norm == 0:
            return {}
        return {token: value / norm for token, value in vector.items()}

    def fit_transform(self, documents: list[str]) -> list[SparseVector]:
        self.fit(documents)
        return [self.transform_one(document) for document in documents]


def cosine_similarity(left: SparseVector, right: SparseVector) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())

