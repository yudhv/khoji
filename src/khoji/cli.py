from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .corpus import CorpusError, load_shabads, validate_shabads
from .retriever import KhojiIndex
from .shabados import (
    DEFAULT_SOURCE_NAME,
    DEFAULT_TRANSLATION_SOURCES,
    DEFAULT_TRANSLITERATION_LANGUAGE,
    ShabadOsError,
    export_shabads_jsonl,
    inspect_shabados_v4,
    load_shabados_v4,
)


DEFAULT_CORPUS = Path("data/sample/shabads.jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="khoji",
        description="Find a shabad first, then the best line within that shabad.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    identify_parser = subparsers.add_parser("identify")
    identify_parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    identify_parser.add_argument("--query", type=str)
    identify_parser.add_argument("--query-file", type=Path)
    identify_parser.add_argument("--top-k-shabads", type=int, default=5)
    identify_parser.add_argument("--top-k-lines", type=int, default=5)
    identify_parser.add_argument("--within-shabad", type=str)
    identify_parser.add_argument("--json", action="store_true")

    validate_parser = subparsers.add_parser("validate-corpus")
    validate_parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)

    shabados_info_parser = subparsers.add_parser("shabados-info")
    shabados_info_parser.add_argument("--db", type=Path, required=True)
    shabados_info_parser.add_argument("--json", action="store_true")

    export_shabados_parser = subparsers.add_parser("export-shabados")
    export_shabados_parser.add_argument("--db", type=Path, required=True)
    export_shabados_parser.add_argument("--output", type=Path, required=True)
    export_shabados_parser.add_argument("--source", default=DEFAULT_SOURCE_NAME)
    export_shabados_parser.add_argument(
        "--transliteration-language",
        default=DEFAULT_TRANSLITERATION_LANGUAGE,
    )
    export_shabados_parser.add_argument(
        "--translation-source",
        action="append",
        dest="translation_sources",
        default=None,
        help="May be repeated. Defaults to Sant Singh Khalsa English and Prof. Sahib Singh Punjabi.",
    )
    export_shabados_parser.add_argument("--limit", type=int)

    args = parser.parse_args(argv)

    try:
        if args.command == "validate-corpus":
            shabads = load_shabads(args.corpus)
            validate_shabads(shabads)
            print(f"OK: {len(shabads)} shabads loaded from {args.corpus}")
            return 0

        if args.command == "shabados-info":
            info = inspect_shabados_v4(args.db)
            if args.json:
                print(json.dumps(info, ensure_ascii=False, indent=2))
            else:
                _print_shabados_info(info)
            return 0

        if args.command == "export-shabados":
            translation_sources = tuple(
                args.translation_sources or DEFAULT_TRANSLATION_SOURCES
            )
            shabads = load_shabados_v4(
                args.db,
                source_name=args.source,
                transliteration_language=args.transliteration_language,
                translation_sources=translation_sources,
                limit=args.limit,
            )
            export_shabads_jsonl(shabads, args.output)
            print(f"Exported {len(shabads)} shabads to {args.output}")
            return 0

        if args.command == "identify":
            query = _read_query(args.query, args.query_file)
            shabads = load_shabads(args.corpus)
            index = KhojiIndex(shabads)
            result = index.identify(
                query=query,
                top_k_shabads=args.top_k_shabads,
                top_k_lines=args.top_k_lines,
                within_shabad_id=args.within_shabad,
            )
            if args.json:
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            else:
                _print_result(result)
            return 0
    except (CorpusError, ShabadOsError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.print_help()
    return 1


def _read_query(query: str | None, query_file: Path | None) -> str:
    if query and query_file:
        raise ValueError("Use either --query or --query-file, not both")
    if query:
        return query
    if query_file:
        return query_file.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError("Provide --query, --query-file, or stdin text")


def _print_result(result) -> None:
    print("Top shabad candidates:")
    for index, candidate in enumerate(result.top_shabads, 1):
        shabad = candidate.shabad
        ang = f", ang {shabad.ang}" if shabad.ang is not None else ""
        print(
            f"{index}. {shabad.title} ({shabad.shabad_id}{ang}) "
            f"score={candidate.score:.3f} confidence={candidate.confidence:.3f}"
        )

    print()
    if result.best_shabad is None:
        print("Current line belief: none")
        return

    print(f"Current line belief within {result.best_shabad.shabad.shabad_id}:")
    for index, candidate in enumerate(result.top_lines, 1):
        line = candidate.line
        text = line.transliteration or line.gurmukhi
        print(
            f"{index}. line {line.order} ({line.line_id}) "
            f"score={candidate.score:.3f} confidence={candidate.confidence:.3f}"
        )
        print(f"   {text}")


def _print_shabados_info(info) -> None:
    print("Sources:")
    for row in info["sources"]:
        print(f"- {row['name_english']} ({row['length']} {row['page_name_english']})")

    print()
    print("Transliteration languages:")
    for row in info["languages"]:
        print(f"- {row['name_english']} ({row['name_international']})")

    print()
    print("Translation sources:")
    for row in info["translation_sources"]:
        print(f"- {row['name_english']} [{row['language']}] for {row['source']}")
