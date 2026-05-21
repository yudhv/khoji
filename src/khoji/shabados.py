from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import Line, Shabad


DEFAULT_SOURCE_NAME = "Sri Guru Granth Sahib Ji"
DEFAULT_TRANSLITERATION_LANGUAGE = "English"
DEFAULT_TRANSLATION_SOURCES = ("Dr. Sant Singh Khalsa", "Prof. Sahib Singh")
SQLITE_CHUNK_SIZE = 900


class ShabadOsError(ValueError):
    pass


def inspect_shabados_v4(path: str | Path) -> dict[str, Any]:
    with _connect(path) as connection:
        return {
            "sources": _fetch_all(connection, "select * from sources order by id"),
            "languages": _fetch_all(connection, "select * from languages order by id"),
            "translation_sources": _fetch_all(
                connection,
                """
                select
                    ts.id,
                    ts.name_english,
                    l.name_english as language,
                    s.name_english as source
                from translation_sources ts
                join languages l on l.id = ts.language_id
                join sources s on s.id = ts.source_id
                order by ts.id
                """,
            ),
        }


def load_shabados_v4(
    path: str | Path,
    *,
    source_name: str = DEFAULT_SOURCE_NAME,
    transliteration_language: str = DEFAULT_TRANSLITERATION_LANGUAGE,
    translation_sources: tuple[str, ...] = DEFAULT_TRANSLATION_SOURCES,
    limit: int | None = None,
) -> list[Shabad]:
    with _connect(path) as connection:
        source_id = _lookup_id(
            connection,
            "sources",
            "name_english",
            source_name,
            label="source",
        )
        transliteration_language_id = _lookup_id(
            connection,
            "languages",
            "name_english",
            transliteration_language,
            label="transliteration language",
        )
        translation_source_rows = _translation_source_rows(
            connection,
            source_id=source_id,
            names=translation_sources,
        )

        shabad_rows = _shabad_rows(connection, source_id, limit)
        if not shabad_rows:
            raise ShabadOsError(f"No shabads found for source: {source_name}")

        shabad_ids = [row["id"] for row in shabad_rows]
        line_rows = _line_rows(connection, shabad_ids, transliteration_language_id)
        translations = _translation_map(
            connection,
            line_ids=[row["id"] for row in line_rows],
            translation_source_ids=[row["id"] for row in translation_source_rows],
        )

    lines_by_shabad: dict[str, list[Line]] = {shabad_id: [] for shabad_id in shabad_ids}
    for row in line_rows:
        line_translations = translations.get(row["id"], [])
        english = _preferred_english(line_translations)
        lines_by_shabad[row["shabad_id"]].append(
            Line(
                shabad_id=_external_shabad_id(source_name, row["shabad_id"]),
                line_id=_external_line_id(source_name, row["id"]),
                order=int(row["line_order"]),
                gurmukhi=row["gurmukhi"],
                transliteration=row["transliteration"] or "",
                english=english,
                section=row["line_type"] or "",
                is_refrain=(row["line_type"] or "").casefold() == "rahao",
                metadata={
                    "source": "Shabad OS Database 4.8.7",
                    "source_name": source_name,
                    "source_page": row["source_page"],
                    "source_line": row["source_line"],
                    "original_line_id": row["id"],
                    "original_shabad_id": row["shabad_id"],
                    "gurmukhi_encoding": "Shabad OS 4.x database field; not Unicode-normalized",
                    "first_letters": row["first_letters"],
                    "vishraam_first_letters": row["vishraam_first_letters"],
                    "pronunciation": row["pronunciation"],
                    "translations": line_translations,
                },
            )
        )

    shabads: list[Shabad] = []
    for row in shabad_rows:
        shabad_lines = tuple(lines_by_shabad[row["id"]])
        if not shabad_lines:
            continue
        shabads.append(
            Shabad(
                shabad_id=_external_shabad_id(source_name, row["id"]),
                title=_shabad_title(row, shabad_lines),
                lines=shabad_lines,
                ang=int(shabad_lines[0].metadata["source_page"]),
                raag=row["section_name"] or "",
                author=row["writer_name"] or "",
                metadata={
                    "source": "Shabad OS Database 4.8.7",
                    "source_name": source_name,
                    "original_shabad_id": row["id"],
                    "sttm_id": row["sttm_id"],
                    "section_name": row["section_name"],
                    "subsection_name": row["subsection_name"],
                    "source_order": row["source_order"],
                },
            )
        )

    return shabads


def export_shabads_jsonl(shabads: list[Shabad], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        for shabad in shabads:
            output.write(json.dumps(asdict(shabad), ensure_ascii=False, separators=(",", ":")))
            output.write("\n")


def _connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    if not db_path.exists():
        raise ShabadOsError(f"Shabad OS database does not exist: {db_path}")
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    _assert_v4_schema(connection)
    return connection


def _assert_v4_schema(connection: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in connection.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
    }
    required = {"shabads", "lines", "transliterations", "translations"}
    missing = sorted(required - tables)
    if missing:
        raise ShabadOsError(
            "Unsupported Shabad OS database schema; missing tables: "
            + ", ".join(missing)
        )


def _lookup_id(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    value: str,
    *,
    label: str,
) -> int:
    row = connection.execute(
        f"select id from {table} where {column} = ?",
        (value,),
    ).fetchone()
    if row is None:
        raise ShabadOsError(f"Unknown Shabad OS {label}: {value}")
    return int(row["id"])


def _translation_source_rows(
    connection: sqlite3.Connection,
    *,
    source_id: int,
    names: tuple[str, ...],
) -> list[sqlite3.Row]:
    if not names:
        return []

    placeholders = ",".join("?" for _ in names)
    rows = connection.execute(
        f"""
        select
            ts.id,
            ts.name_english,
            l.name_english as language
        from translation_sources ts
        join languages l on l.id = ts.language_id
        where ts.source_id = ?
          and ts.name_english in ({placeholders})
        order by ts.id
        """,
        (source_id, *names),
    ).fetchall()
    found = {row["name_english"] for row in rows}
    missing = [name for name in names if name not in found]
    if missing:
        raise ShabadOsError(
            "Unknown translation source(s) for selected source: " + ", ".join(missing)
        )
    return rows


def _shabad_rows(
    connection: sqlite3.Connection, source_id: int, limit: int | None
) -> list[sqlite3.Row]:
    limit_clause = "" if limit is None else "limit ?"
    parameters: tuple[int, ...] = (source_id,) if limit is None else (source_id, limit)
    return connection.execute(
        f"""
        select
            sh.id,
            sh.sttm_id,
            sh.order_id as source_order,
            sec.name_english as section_name,
            sub.name_english as subsection_name,
            wr.name_english as writer_name
        from shabads sh
        join sections sec on sec.id = sh.section_id
        left join subsections sub on sub.id = sh.subsection_id
        join writers wr on wr.id = sh.writer_id
        where sh.source_id = ?
        order by sh.order_id
        {limit_clause}
        """,
        parameters,
    ).fetchall()


def _line_rows(
    connection: sqlite3.Connection,
    shabad_ids: list[str],
    transliteration_language_id: int,
) -> list[sqlite3.Row]:
    if not shabad_ids:
        return []
    rows: list[sqlite3.Row] = []
    for shabad_id_chunk in _chunks(shabad_ids, SQLITE_CHUNK_SIZE):
        placeholders = ",".join("?" for _ in shabad_id_chunk)
        rows.extend(
            connection.execute(
                f"""
                select
                    l.id,
                    l.shabad_id,
                    l.source_page,
                    l.source_line,
                    l.first_letters,
                    l.vishraam_first_letters,
                    l.gurmukhi,
                    l.pronunciation,
                    l.order_id as global_order,
                    row_number() over (
                        partition by l.shabad_id
                        order by l.order_id
                    ) as line_order,
                    lt.name_english as line_type,
                    tr.transliteration
                from lines l
                left join line_types lt on lt.id = l.type_id
                left join transliterations tr
                  on tr.line_id = l.id
                 and tr.language_id = ?
                where l.shabad_id in ({placeholders})
                order by l.order_id
                """,
                (transliteration_language_id, *shabad_id_chunk),
            ).fetchall()
        )
    return sorted(rows, key=lambda row: row["global_order"])


def _translation_map(
    connection: sqlite3.Connection,
    *,
    line_ids: list[str],
    translation_source_ids: list[int],
) -> dict[str, list[dict[str, str]]]:
    if not line_ids or not translation_source_ids:
        return {}

    source_placeholders = ",".join("?" for _ in translation_source_ids)
    by_line: dict[str, list[dict[str, str]]] = {}
    for line_id_chunk in _chunks(line_ids, SQLITE_CHUNK_SIZE):
        line_placeholders = ",".join("?" for _ in line_id_chunk)
        rows = connection.execute(
            f"""
            select
                t.line_id,
                ts.name_english as source,
                lang.name_english as language,
                t.translation
            from translations t
            join translation_sources ts on ts.id = t.translation_source_id
            join languages lang on lang.id = ts.language_id
            where t.line_id in ({line_placeholders})
              and t.translation_source_id in ({source_placeholders})
            order by t.line_id, t.translation_source_id
            """,
            (*line_id_chunk, *translation_source_ids),
        ).fetchall()

        for row in rows:
            by_line.setdefault(row["line_id"], []).append(
                {
                    "source": row["source"],
                    "language": row["language"],
                    "text": row["translation"],
                }
            )
    return by_line


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [
        values[index : index + size]
        for index in range(0, len(values), size)
    ]


def _preferred_english(translations: list[dict[str, str]]) -> str:
    for translation in translations:
        if translation["language"] == "English":
            return translation["text"]
    return ""


def _external_shabad_id(source_name: str, original_id: str) -> str:
    return f"{_source_slug(source_name)}:{original_id}"


def _external_line_id(source_name: str, original_id: str) -> str:
    return f"{_source_slug(source_name)}:{original_id}"


def _source_slug(source_name: str) -> str:
    if source_name == DEFAULT_SOURCE_NAME:
        return "SGGS"
    return "".join(char for char in source_name.upper() if char.isalnum())[:12]


def _shabad_title(row: sqlite3.Row, lines: tuple[Line, ...]) -> str:
    first_content_line = next(
        (
            line
            for line in lines
            if line.section.casefold() not in {"sirlekh", "manglacharan"}
        ),
        lines[0],
    )
    title_text = first_content_line.transliteration or first_content_line.gurmukhi
    title_text = title_text.replace("|", "").replace(";", "").strip()
    title_text = " ".join(title_text.split())
    if len(title_text) > 80:
        title_text = title_text[:77].rstrip() + "..."
    return f"{row['section_name']} - {title_text}"


def _fetch_all(connection: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query).fetchall()]
