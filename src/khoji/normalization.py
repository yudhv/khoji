from __future__ import annotations

import re
import unicodedata


GURMUKHI_START = "\u0a00"
GURMUKHI_END = "\u0a7f"

_GURMUKHI_CONSONANTS = {
    "ਕ": "k",
    "ਖ": "kh",
    "ਗ": "g",
    "ਘ": "gh",
    "ਙ": "ng",
    "ਚ": "ch",
    "ਛ": "chh",
    "ਜ": "j",
    "ਝ": "jh",
    "ਞ": "ny",
    "ਟ": "tt",
    "ਠ": "tth",
    "ਡ": "dd",
    "ਢ": "ddh",
    "ਣ": "n",
    "ਤ": "t",
    "ਥ": "th",
    "ਦ": "d",
    "ਧ": "dh",
    "ਨ": "n",
    "ਪ": "p",
    "ਫ": "ph",
    "ਬ": "b",
    "ਭ": "bh",
    "ਮ": "m",
    "ਯ": "y",
    "ਰ": "r",
    "ਲ": "l",
    "ਵ": "v",
    "ੜ": "rr",
    "ਸ਼": "sh",
    "ਸ": "s",
    "ਹ": "h",
    "ਖ਼": "kh",
    "ਗ਼": "g",
    "ਜ਼": "z",
    "ਫ਼": "f",
    "ਲ਼": "l",
}

_GURMUKHI_INDEPENDENT_VOWELS = {
    "ਅ": "a",
    "ਆ": "aa",
    "ਇ": "i",
    "ਈ": "ee",
    "ਉ": "u",
    "ਊ": "oo",
    "ਏ": "e",
    "ਐ": "ai",
    "ਓ": "o",
    "ਔ": "au",
}

_GURMUKHI_VOWEL_SIGNS = {
    "ਾ": "aa",
    "ਿ": "i",
    "ੀ": "ee",
    "ੁ": "u",
    "ੂ": "oo",
    "ੇ": "e",
    "ੈ": "ai",
    "ੋ": "o",
    "ੌ": "au",
}

_GURMUKHI_NASAL_SIGNS = {"ਂ", "ੰ", "ਁ"}
_GURMUKHI_HALANT = "੍"
_GURMUKHI_ADDAK = "ੱ"


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
    return normalize_text(expand_gurmukhi_search_text(" ".join(str(part) for part in parts if part)))


def char_ngrams(text: str, min_n: int = 3, max_n: int = 5) -> list[str]:
    normalized = normalize_text(expand_gurmukhi_search_text(text))
    if not normalized:
        return []

    padded = f" {normalized} "
    grams: list[str] = []
    for n in range(min_n, max_n + 1):
        if len(padded) < n:
            continue
        grams.extend(padded[index : index + n] for index in range(len(padded) - n + 1))
    return grams


def expand_gurmukhi_search_text(text: str) -> str:
    if not any(GURMUKHI_START <= char <= GURMUKHI_END for char in text):
        return text
    transliterated = transliterate_gurmukhi_to_ascii(text)
    if not transliterated:
        return text
    return f"{text} {transliterated}"


def transliterate_gurmukhi_to_ascii(text: str) -> str:
    words = re.findall(r"[\u0a00-\u0a7f]+|[^\u0a00-\u0a7f]+", text)
    return "".join(_transliterate_gurmukhi_word(word) for word in words)


def _transliterate_gurmukhi_word(word: str) -> str:
    chars = list(word)
    output: list[str] = []
    index = 0
    pending_addak = False
    while index < len(chars):
        char = chars[index]
        if char in _GURMUKHI_INDEPENDENT_VOWELS:
            output.append(_GURMUKHI_INDEPENDENT_VOWELS[char])
            index += 1
            continue
        if char == _GURMUKHI_ADDAK:
            pending_addak = True
            index += 1
            continue
        if char in _GURMUKHI_NASAL_SIGNS:
            output.append("n")
            index += 1
            continue
        if char in _GURMUKHI_VOWEL_SIGNS or char == _GURMUKHI_HALANT:
            index += 1
            continue
        if char not in _GURMUKHI_CONSONANTS:
            output.append(char)
            index += 1
            continue

        base = _GURMUKHI_CONSONANTS[char]
        if pending_addak and output:
            output.append(base[0])
            pending_addak = False

        next_index = index + 1
        vowel = ""
        nasal = ""
        halant = False
        if next_index < len(chars) and chars[next_index] in _GURMUKHI_VOWEL_SIGNS:
            vowel = _GURMUKHI_VOWEL_SIGNS[chars[next_index]]
            next_index += 1
        if next_index < len(chars) and chars[next_index] in _GURMUKHI_NASAL_SIGNS:
            nasal = "n"
            next_index += 1
        if next_index < len(chars) and chars[next_index] == _GURMUKHI_HALANT:
            halant = True
            next_index += 1

        if not vowel and not halant and _has_later_gurmukhi_consonant(chars, next_index):
            vowel = "a"
        output.append(base + vowel + nasal)
        index = next_index
    return "".join(output)


def _has_later_gurmukhi_consonant(chars: list[str], start: int) -> bool:
    return any(char in _GURMUKHI_CONSONANTS for char in chars[start:])
