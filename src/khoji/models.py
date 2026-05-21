from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Line:
    shabad_id: str
    line_id: str
    order: int
    gurmukhi: str
    transliteration: str = ""
    english: str = ""
    section: str = ""
    is_refrain: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, shabad_id: str, data: dict[str, Any]) -> "Line":
        line_id = str(data.get("line_id") or f"{shabad_id}:{data.get('order')}")
        return cls(
            shabad_id=shabad_id,
            line_id=line_id,
            order=int(data["order"]),
            gurmukhi=str(data.get("gurmukhi", "")),
            transliteration=str(data.get("transliteration", "")),
            english=str(data.get("english", "")),
            section=str(data.get("section", "")),
            is_refrain=bool(data.get("is_refrain", False)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class Shabad:
    shabad_id: str
    title: str
    lines: tuple[Line, ...]
    ang: int | None = None
    raag: str = ""
    author: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Shabad":
        shabad_id = str(data["shabad_id"])
        lines = tuple(
            sorted(
                (Line.from_mapping(shabad_id, line) for line in data.get("lines", [])),
                key=lambda line: line.order,
            )
        )
        return cls(
            shabad_id=shabad_id,
            title=str(data.get("title", shabad_id)),
            lines=lines,
            ang=int(data["ang"]) if data.get("ang") is not None else None,
            raag=str(data.get("raag", "")),
            author=str(data.get("author", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class RankedShabad:
    shabad: Shabad
    score: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "confidence": self.confidence,
            "shabad": asdict(self.shabad),
        }


@dataclass(frozen=True)
class RankedLine:
    line: Line
    score: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "confidence": self.confidence,
            "line": asdict(self.line),
        }


@dataclass(frozen=True)
class IdentificationResult:
    query: str
    top_shabads: tuple[RankedShabad, ...]
    top_lines: tuple[RankedLine, ...]

    @property
    def best_shabad(self) -> RankedShabad | None:
        return self.top_shabads[0] if self.top_shabads else None

    @property
    def best_line(self) -> RankedLine | None:
        return self.top_lines[0] if self.top_lines else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "top_shabads": [candidate.to_dict() for candidate in self.top_shabads],
            "top_lines": [candidate.to_dict() for candidate in self.top_lines],
        }

