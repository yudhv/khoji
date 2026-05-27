from __future__ import annotations

from dataclasses import dataclass

from .models import IdentificationResult, Line, RankedLine, RankedShabad, Shabad
from .normalization import compact_text, make_search_text
from .vectorizer import CharNgramTfidf, SparseVector, cosine_similarity


@dataclass(frozen=True)
class _LineIndex:
    shabad: Shabad
    vectorizer: CharNgramTfidf
    vectors: list[SparseVector]


@dataclass
class _GlobalLineIndex:
    lines: tuple[Line, ...]
    shabads_by_id: dict[str, Shabad]
    first_letter_documents: tuple[str, ...]
    first_letter_lookup: dict[str, tuple[int, ...]]
    documents: tuple[str, ...] | None = None


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
        self._global_line_index: _GlobalLineIndex | None = None

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

    def search_all_lines(self, query: str, top_k: int = 20) -> tuple[RankedLine, ...]:
        if not query.strip():
            return ()
        compact_query = compact_text(query)
        if len(compact_query) < 3:
            return ()
        line_index = self._global_line_index
        if line_index is None:
            line_index = _build_global_line_index(self.shabads)
            self._global_line_index = line_index

        normalized_query = make_search_text(query)
        if _is_first_letter_query(normalized_query, compact_query):
            scored = _score_first_letter_candidates(line_index, compact_query)
            if scored:
                return _ranked_lines(scored[:top_k])

        query_tokens = frozenset(token for token in normalized_query.split() if len(token) >= 2)
        documents = _global_line_documents(line_index)
        scored = sorted(
            (
                (
                    line,
                    _line_search_score(
                        normalized_query,
                        compact_query,
                        query_tokens,
                        document,
                        first_letter_document,
                    ),
                )
                for line, document, first_letter_document in zip(
                    line_index.lines,
                    documents,
                    line_index.first_letter_documents,
                    strict=True,
                )
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        scored = [item for item in scored if item[1] > 0][:top_k]
        return _ranked_lines(scored)

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


def _build_global_line_index(shabads: list[Shabad]) -> _GlobalLineIndex:
    lines = tuple(line for shabad in shabads for line in shabad.lines)
    shabads_by_id = {shabad.shabad_id: shabad for shabad in shabads}
    first_letter_documents = tuple(_first_letter_document(line) for line in lines)
    return _GlobalLineIndex(
        lines=lines,
        shabads_by_id=shabads_by_id,
        first_letter_documents=first_letter_documents,
        first_letter_lookup=_build_first_letter_lookup(first_letter_documents),
    )


def _global_line_documents(line_index: _GlobalLineIndex) -> tuple[str, ...]:
    if line_index.documents is None:
        line_index.documents = tuple(
            _global_line_document(line_index.shabads_by_id[line.shabad_id], line)
            for line in line_index.lines
        )
    return line_index.documents


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


def _global_line_document(shabad: Shabad, line: Line) -> str:
    return make_search_text(
        shabad.title,
        shabad.raag,
        shabad.author,
        _line_document(line),
        _line_translation_text(line),
    )


def _line_translation_text(line: Line) -> str:
    translations = line.metadata.get("translations", [])
    return " ".join(str(translation.get("text", "")) for translation in translations)


def _first_letter_document(line: Line) -> str:
    metadata_pieces = [
        _metadata_text(line.metadata.get("first_letters", "")),
        _metadata_text(line.metadata.get("vishraam_first_letters", "")),
    ]
    text_pieces = [
        _first_letters_from_text(line.transliteration),
    ]
    if not any(metadata_pieces):
        text_pieces.append(_first_letters_from_text(line.gurmukhi))
    pieces = [*metadata_pieces, *text_pieces]
    unique_pieces: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        compact_piece = compact_text(piece)
        if compact_piece and compact_piece not in seen:
            unique_pieces.append(compact_piece)
            seen.add(compact_piece)
    return " ".join(unique_pieces)


def _metadata_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _first_letters_from_text(text: str) -> str:
    return "".join(
        token[0] for token in make_search_text(text).split() if token and token[0].isalpha()
    )


def _build_first_letter_lookup(
    first_letter_documents: tuple[str, ...],
) -> dict[str, tuple[int, ...]]:
    buckets: dict[str, list[int]] = {}
    for line_index, document in enumerate(first_letter_documents):
        keys = {
            candidate[start : start + 3]
            for candidate in document.split()
            for start in range(max(len(candidate) - 2, 0))
        }
        for key in keys:
            buckets.setdefault(key, []).append(line_index)
    return {key: tuple(indices) for key, indices in buckets.items()}


def _is_first_letter_query(normalized_query: str, compact_query: str) -> bool:
    return normalized_query == compact_query


def _score_first_letter_candidates(
    line_index: _GlobalLineIndex,
    compact_query: str,
) -> list[tuple[Line, float]]:
    candidate_indices = line_index.first_letter_lookup.get(compact_query[:3], ())
    scored = [
        (
            line_index.lines[index],
            _first_letter_score(compact_query, line_index.first_letter_documents[index]),
        )
        for index in candidate_indices
    ]
    return sorted(
        (item for item in scored if item[1] > 0),
        key=lambda item: item[1],
        reverse=True,
    )


def _line_search_score(
    normalized_query: str,
    compact_query: str,
    query_tokens: frozenset[str],
    document: str,
    first_letter_document: str,
) -> float:
    if not normalized_query:
        return 0.0
    score = 0.0
    if len(compact_query) >= 3:
        score += _first_letter_score(compact_query, first_letter_document)
    if normalized_query in document:
        score += 100.0 + len(normalized_query) / max(len(document), 1)
    for token in query_tokens:
        if token in document:
            score += min(len(token), 12)
    return score


def _first_letter_score(compact_query: str, first_letter_document: str) -> float:
    best_score = 0.0
    for candidate in first_letter_document.split():
        if compact_query == candidate:
            best_score = max(best_score, 500.0 + len(compact_query))
        elif candidate.startswith(compact_query):
            best_score = max(best_score, 400.0 + len(compact_query))
        elif compact_query in candidate:
            best_score = max(best_score, 250.0 + len(compact_query))
    return best_score


def _ranked_lines(scored: list[tuple[Line, float]]) -> tuple[RankedLine, ...]:
    confidences = _relative_confidences([score for _, score in scored])
    return tuple(
        RankedLine(line=line, score=score, confidence=confidence)
        for (line, score), confidence in zip(scored, confidences, strict=True)
    )


def _relative_confidences(scores: list[float]) -> list[float]:
    total = sum(max(score, 0.0) for score in scores)
    if total == 0:
        return [0.0 for _ in scores]
    return [max(score, 0.0) / total for score in scores]
