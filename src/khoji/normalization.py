from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalize Gurmukhi/transliteration text for rough retrieval."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    chars: list[str] = []
    for char in normalized:
        category = unicodedata.category(char)
        if category[0] in {"P", "S"}:
            chars.append(" ")
        else:
            chars.append(char)
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def compact_text(text: str) -> str:
    return normalize_text(text).replace(" ", "")


def make_search_text(*parts: object) -> str:
    return normalize_text(" ".join(str(part) for part in parts if part))


def char_ngrams(text: str, min_n: int = 3, max_n: int = 5) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    padded = f" {normalized} "
    grams: list[str] = []
    for n in range(min_n, max_n + 1):
        if len(padded) < n:
            continue
        grams.extend(padded[index : index + n] for index in range(len(padded) - n + 1))
    return grams

