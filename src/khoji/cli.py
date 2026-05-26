from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .asr import DEFAULT_SURT_MODEL_ID, build_audio_transcriber, extract_audio_window
from .corpus import CorpusError, load_shabads, validate_shabads
from .line_labels import build_line_label_template_rows, write_line_label_template
from .phase1 import DEFAULT_TRANSLATION_LANGUAGE, Phase1Identifier, evaluate_benchmark, write_benchmark_report
from .retriever import KhojiIndex
from .server import run_server
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

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--corpus", type=Path, default=Path("data/shabados/sggs.jsonl"))
    serve_parser.add_argument("--manifest", type=Path, default=Path("data/phase1/benchmark/manifest.jsonl"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--asr-model", choices=["none", "surt-small-v3"], default="none")
    serve_parser.add_argument("--surt-model-id", default=DEFAULT_SURT_MODEL_ID)
    serve_parser.add_argument("--asr-device")
    serve_parser.add_argument("--asr-chunk-length-s", type=int, default=30)

    benchmark_parser = subparsers.add_parser("evaluate-benchmark")
    benchmark_parser.add_argument("--corpus", type=Path, default=Path("data/shabados/sggs.jsonl"))
    benchmark_parser.add_argument("--manifest", type=Path, required=True)
    benchmark_parser.add_argument("--output", type=Path)
    benchmark_parser.add_argument("--json", action="store_true")

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

    identify_audio_parser = subparsers.add_parser("identify-audio")
    identify_audio_parser.add_argument("--corpus", type=Path, default=Path("data/shabados/sggs.jsonl"))
    identify_audio_parser.add_argument("--audio", type=Path, required=True)
    identify_audio_parser.add_argument("--manifest", type=Path)
    identify_audio_parser.add_argument("--translation-language", default=DEFAULT_TRANSLATION_LANGUAGE)
    identify_audio_parser.add_argument("--asr-model", choices=["none", "surt-small-v3"], default="surt-small-v3")
    identify_audio_parser.add_argument("--surt-model-id", default=DEFAULT_SURT_MODEL_ID)
    identify_audio_parser.add_argument("--asr-device")
    identify_audio_parser.add_argument("--asr-chunk-length-s", type=int, default=30)
    identify_audio_parser.add_argument("--start-s", type=float)
    identify_audio_parser.add_argument("--duration-s", type=float)
    identify_audio_parser.add_argument("--json", action="store_true")

    line_label_template_parser = subparsers.add_parser("create-line-label-template")
    line_label_template_parser.add_argument("--corpus", type=Path, default=Path("data/shabados/sggs.jsonl"))
    line_label_template_parser.add_argument("--recording-id", required=True)
    line_label_template_parser.add_argument("--shabad-id", required=True)
    line_label_template_parser.add_argument("--audio-path", default="")
    line_label_template_parser.add_argument("--output", type=Path)

    args = parser.parse_args(argv)

    try:
        if args.command == "validate-corpus":
            shabads = load_shabads(args.corpus)
            validate_shabads(shabads)
            print(f"OK: {len(shabads)} shabads loaded from {args.corpus}")
            return 0

        if args.command == "serve":
            transcriber = build_audio_transcriber(
                args.asr_model,
                model_id=args.surt_model_id,
                device=_parse_device(args.asr_device),
                chunk_length_s=args.asr_chunk_length_s,
            )
            run_server(
                corpus_path=args.corpus,
                manifest_path=args.manifest,
                host=args.host,
                port=args.port,
                audio_transcriber=transcriber,
            )
            return 0

        if args.command == "evaluate-benchmark":
            report = evaluate_benchmark(args.corpus, args.manifest)
            if args.output:
                write_benchmark_report(report, args.output)
            if args.json or not args.output:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(
                    "Benchmark OK: "
                    f"shabad_top1={report['shabad_top1_accuracy']:.3f}, "
                    f"line_top3={report['line_top3_accuracy']:.3f}"
                )
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

        if args.command == "identify-audio":
            transcriber = build_audio_transcriber(
                args.asr_model,
                model_id=args.surt_model_id,
                device=_parse_device(args.asr_device),
                chunk_length_s=args.asr_chunk_length_s,
            )
            identifier = Phase1Identifier(
                args.corpus,
                args.manifest,
                translation_language=args.translation_language,
                audio_transcriber=transcriber,
            )
            audio_bytes = extract_audio_window(
                args.audio.read_bytes(),
                start_s=args.start_s,
                duration_s=args.duration_s,
            )
            result = identifier.identify_audio(
                audio_bytes,
                translation_language=args.translation_language,
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                _print_audio_result(result)
            return 0

        if args.command == "create-line-label-template":
            shabads = load_shabads(args.corpus)
            shabad = next(
                (candidate for candidate in shabads if candidate.shabad_id == args.shabad_id),
                None,
            )
            if shabad is None:
                raise ValueError(f"Unknown shabad_id: {args.shabad_id}")
            output = args.output or Path(
                f"data/phase1/recordings/{args.recording_id}.line_labels.tsv"
            )
            rows = build_line_label_template_rows(
                shabad,
                recording_id=args.recording_id,
                audio_path=args.audio_path,
            )
            write_line_label_template(rows, output)
            print(f"Wrote {len(rows)} label rows to {output}")
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
    except (CorpusError, ShabadOsError, KeyError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.print_help()
    return 1


def _parse_device(device: str | None) -> str | int | None:
    if device is None or device == "":
        return None
    try:
        return int(device)
    except ValueError:
        return device


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


def _print_audio_result(result: dict) -> None:
    if result.get("asr"):
        print("ASR transcript:")
        print(result["asr"]["text"])
        print()

    if result.get("status") != "identified":
        print(f"Not confident yet: {result.get('unknown_reason')}")
        return

    shabad = result["shabad"]
    ang = f", ang {shabad['ang']}" if shabad.get("ang") is not None else ""
    print(f"Best shabad: {shabad['title']} ({shabad['shabad_id']}{ang})")
    active = result["active_line"]
    print(f"Active line: {active['order']} ({active['line_id']})")
    print(active["text"])
    if active.get("translation"):
        print(active["translation"])
    print(f"Confidence: {result['confidence']:.3f}")


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
