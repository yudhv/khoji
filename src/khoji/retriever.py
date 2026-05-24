from __future__ import annotations

from dataclasses import dataclass

from .models import IdentificationResult, Line, RankedLine, RankedShabad, Shabad
from .normalization import make_search_text
from .vectorizer import CharNgramTfidf, SparseVector, cosine_similarity


@dataclass(frozen=True)
class _LineIndex:
    shabad: Shabad
    vectorizer: CharNgramTfidf
    vectors: list[SparseVector]


class KhojiIndex:
    def __init__(self, shabads: list[Shabad]) -> None:
        if not shabads:
            raise ValueError("KhojiIndex needs at least one shabad")
        self.shabads = shabads
        self._shabads_by_id = {shabad.shabad_id: shabad for shabad in shabads}

        shabad_documents = [_shabad_document(shabad) for shabad in shabads]
        self._shabad_vectorizer = CharNgramTfidf()
        self._shabad_vectors = self._shabad_vectorizer.fit_transform(shabad_documents)

        self._line_indexes: dict[str, _LineIndex] = {}

    def search_shabads(self, query: str, top_k: int = 5) -> tuple[RankedShabad, ...]:
        query_vector = self._shabad_vectorizer.transform_one(query)
        scored = sorted(
            (
                (shabad, cosine_similarity(query_vector, vector))
                for shabad, vector in zip(self.shabads, self._shabad_vectors, strict=True)
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]
        confidences = _relative_confidences([score for _, score in scored])
        return tuple(
            RankedShabad(shabad=shabad, score=score, confidence=confidence)
            for (shabad, score), confidence in zip(scored, confidences, strict=True)
        )

    def search_lines(
        self, query: str, shabad_id: str, top_k: int = 5
    ) -> tuple[RankedLine, ...]:
        shabad = self._shabads_by_id.get(shabad_id)
        if shabad is None:
            raise KeyError(f"Unknown shabad_id: {shabad_id}")
        line_index = self._line_indexes.get(shabad_id)
        if line_index is None:
            line_index = _build_line_index(shabad)
            self._line_indexes[shabad_id] = line_index

        query_vector = line_index.vectorizer.transform_one(query)
        scored = sorted(
            (
                (line, cosine_similarity(query_vector, vector))
                for line, vector in zip(
                    line_index.shabad.lines, line_index.vectors, strict=True
                )
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]
        confidences = _relative_confidences([score for _, score in scored])
        return tuple(
            RankedLine(line=line, score=score, confidence=confidence)
            for (line, score), confidence in zip(scored, confidences, strict=True)
        )

    def identify(
        self,
        query: str,
        top_k_shabads: int = 5,
        top_k_lines: int = 5,
        within_shabad_id: str | None = None,
    ) -> IdentificationResult:
        top_shabads = self.search_shabads(query, top_k=top_k_shabads)
        shabad_id = within_shabad_id or (
            top_shabads[0].shabad.shabad_id if top_shabads else None
        )
        top_lines: tuple[RankedLine, ...] = ()
        if shabad_id:
            top_lines = self.search_lines(query, shabad_id, top_k=top_k_lines)
        return IdentificationResult(
            query=query,
            top_shabads=top_shabads,
            top_lines=top_lines,
        )


def _build_line_index(shabad: Shabad) -> _LineIndex:
    documents = [_line_document(line) for line in shabad.lines]
    vectorizer = CharNgramTfidf().fit(documents)
    return _LineIndex(
        shabad=shabad,
        vectorizer=vectorizer,
        vectors=[vectorizer.transform_one(document) for document in documents],
    )


def _shabad_document(shabad: Shabad) -> str:
    return make_search_text(
        shabad.title,
        shabad.raag,
        shabad.author,
        " ".join(_line_document(line) for line in shabad.lines),
    )


def _line_document(line: Line) -> str:
    return make_search_text(
        line.gurmukhi,
        line.transliteration,
        line.english,
        line.section,
        "rahao" if line.is_refrain else "",
    )


def _relative_confidences(scores: list[float]) -> list[float]:
    total = sum(max(score, 0.0) for score in scores)
    if total == 0:
        return [0.0 for _ in scores]
    return [max(score, 0.0) / total for score in scores]
