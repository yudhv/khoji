#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from khoji.corpus import load_shabads
from khoji.recordings import register_recording
from khoji.retriever import KhojiIndex


DEFAULT_CORPUS = Path("data/shabados/sggs.jsonl")
DEFAULT_MANIFEST = Path("data/phase1/recordings/manifest.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register a real full recording for Phase 1/3 data collection."
    )
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--recording-id", required=True)
    parser.add_argument("--query", required=True, help="Text used to resolve the shabad ID.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--kind", default="kirtan")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--source", default="local")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    shabads = load_shabads(args.corpus)
    result = KhojiIndex(shabads).identify(args.query, top_k_shabads=1, top_k_lines=1)
    if result.best_shabad is None:
        raise RuntimeError(f"Could not resolve shabad from query: {args.query}")

    label = register_recording(
        audio_path=args.audio,
        manifest_path=args.manifest,
        recording_id=args.recording_id,
        shabad_id=result.best_shabad.shabad.shabad_id,
        kind=args.kind,
        split=args.split,
        source=args.source,
        notes=args.notes,
    )
    print(f"Registered {label.recording_id}: {label.shabad_id} ({label.duration_ms} ms)")
    print(f"Wrote {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

