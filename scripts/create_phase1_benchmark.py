#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path

from khoji.corpus import load_shabads
from khoji.phase1 import sha256_file
from khoji.retriever import KhojiIndex


DEFAULT_CORPUS = Path("data/shabados/sggs.jsonl")
DEFAULT_OUTPUT = Path("data/phase1/benchmark")


@dataclass(frozen=True)
class SeedClip:
    clip_id: str
    transcript: str
    kind: str
    split: str


SEED_CLIPS = (
    SeedClip("kahe_re_ban_kirtan_001", "kahe re ban khojan jai", "kirtan", "dev"),
    SeedClip("kahe_re_ban_paath_001", "sarab nivasi sada alepa tohi sang samai rahao", "paath", "dev"),
    SeedClip("kahe_re_ban_hum_001", "puhap madh jio baas basat hai", "hum", "test"),
    SeedClip("japji_paath_001", "sochai soch na hovai je sochi lakh vaar", "paath", "dev"),
    SeedClip("japji_kirtan_001", "chupai chup na hovai je lai raha liv taar", "kirtan", "test"),
    SeedClip("japji_hum_001", "kiv sachiaara hoeeai kiv koorai tutai paal", "hum", "test"),
    SeedClip("tu_thakur_paath_001", "tu thakur tum peh ardaas", "paath", "dev"),
    SeedClip("tu_thakur_kirtan_001", "tum maat pita ham baarik tere", "kirtan", "test"),
    SeedClip("tu_thakur_hum_001", "tumri kirpa meh sookh ghanere", "hum", "test"),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a deterministic tiny Phase 1 audio benchmark fixture."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    shabads = load_shabads(args.corpus)
    index = KhojiIndex(shabads)
    audio_dir = args.output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "manifest.jsonl"

    with manifest_path.open("w", encoding="utf-8") as manifest:
        for seed in SEED_CLIPS:
            result = index.identify(seed.transcript, top_k_shabads=1, top_k_lines=1)
            if result.best_shabad is None or result.best_line is None:
                raise RuntimeError(f"Could not label seed clip: {seed.clip_id}")
            audio_path = audio_dir / f"{seed.clip_id}.wav"
            _write_synthetic_wav(audio_path, seed.transcript, seed.kind)
            record = {
                "clip_id": seed.clip_id,
                "shabad_id": result.best_shabad.shabad.shabad_id,
                "line_id": result.best_line.line.line_id,
                "start_ms": 0,
                "end_ms": _duration_ms(seed.transcript),
                "audio_path": str(audio_path.relative_to(args.output_dir)),
                "split": seed.split,
                "kind": seed.kind,
                "transcript": seed.transcript,
                "sha256": sha256_file(audio_path),
            }
            manifest.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            manifest.write("\n")

    print(f"Wrote {manifest_path}")
    return 0


def _duration_ms(transcript: str) -> int:
    return int(max(2500, min(6500, 1200 + len(transcript) * 55)))


def _write_synthetic_wav(path: Path, transcript: str, kind: str) -> None:
    sample_rate = 16000
    duration = _duration_ms(transcript) / 1000
    total_samples = int(sample_rate * duration)
    amplitude = 9500
    words = transcript.split() or ["waheguru"]

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for index in range(total_samples):
            t = index / sample_rate
            word = words[min(int(t / max(duration / len(words), 0.08)), len(words) - 1)]
            base = 180 + (sum(ord(char) for char in word) % 180)
            if kind == "paath":
                freq = 190 + (sum(ord(char) for char in word) % 35)
            elif kind == "hum":
                freq = base + 45 * math.sin(2 * math.pi * 0.35 * t)
            else:
                freq = base + 18 * math.sin(2 * math.pi * 5.5 * t)
            envelope = min(1.0, t * 8, (duration - t) * 8)
            value = int(amplitude * envelope * math.sin(2 * math.pi * freq * t))
            frames.extend(struct.pack("<h", value))
        wav.writeframes(bytes(frames))


if __name__ == "__main__":
    raise SystemExit(main())

