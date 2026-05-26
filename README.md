# Khoji

Khoji is a small MVP for the first two pieces of a real-time kirtan identification system:

1. Find the most likely shabad.
2. Given that shabad, find the most likely current line/tuk.

The current implementation is intentionally dependency-light. It works over a canonical shabad/line corpus and a text query, such as an ASR hypothesis, manual transcript, or future phonetic decoder output. The audio model is not included yet; the point of this repo is to make the shabad-first, line-second retrieval path concrete and testable before adding streaming audio.

## Quick Start

From the repo root:

```bash
PYTHONPATH=src python3 -m khoji validate-corpus --corpus data/sample/shabads.jsonl
PYTHONPATH=src python3 -m khoji identify --query "kahe re ban khojan jai"
PYTHONPATH=src python3 -m khoji identify --query "sochai soch na hovai je sochi lakh vaar" --json
```

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Corpus Format

Khoji reads JSON or JSONL. Each shabad record contains metadata and ordered line records:

```json
{
  "shabad_id": "sample_kahe_re_ban",
  "title": "Kahe Re Ban Khojan Jaai",
  "ang": 684,
  "raag": "Dhanasri",
  "lines": [
    {
      "line_id": "kahe_re_ban_001",
      "order": 1,
      "gurmukhi": "ਕਾਹੇ ਰੇ ਬਨ ਖੋਜਨ ਜਾਈ ॥",
      "transliteration": "kahe re ban khojan jai"
    }
  ]
}
```

The checked-in sample corpus is only a development fixture, not an authoritative Guru Granth Sahib database. Replace it with a licensed/canonical source before serious experiments.

## Shabad OS Corpus

Khoji's first real corpus path is the stable Shabad OS database release `4.8.7`.
The SQLite file is large, so it is downloaded locally and ignored by Git.

```bash
python3 scripts/download_shabados_db.py
PYTHONPATH=src python3 -m khoji shabados-info --db data/shabados/database.sqlite
PYTHONPATH=src python3 -m khoji export-shabados \
  --db data/shabados/database.sqlite \
  --output data/shabados/sggs.jsonl
PYTHONPATH=src python3 -m khoji identify \
  --corpus data/shabados/sggs.jsonl \
  --query "kahe re ban khojan jai"
```

By default the export uses:

- Source: `Sri Guru Granth Sahib Ji`
- Transliteration language: `English`
- Translation sources: `Dr. Sant Singh Khalsa` and `Prof. Sahib Singh`

The stable Shabad OS 4.x database stores the primary Gurmukhi field in its historical database encoding, while the Latin transliteration and translations are directly usable for retrieval. The newer Shabad OS 5.x prerelease has a different asset schema with Unicode primary lines; support for that schema should be added as a separate importer after we decide how to merge it with the 4.x transliteration tables.

## Phase 1 Audio MVP

Phase 1 proves the full local loop:

```text
audio clip -> benchmark transcript baseline -> Khoji retrieval -> HTML reader
```

Create the ignored local benchmark fixtures:

```bash
PYTHONPATH=src python3 scripts/create_phase1_benchmark.py \
  --corpus data/shabados/sggs.jsonl \
  --output-dir data/phase1/benchmark
```

Evaluate the benchmark:

```bash
PYTHONPATH=src python3 -m khoji evaluate-benchmark \
  --corpus data/shabados/sggs.jsonl \
  --manifest data/phase1/benchmark/manifest.jsonl \
  --json
```

Run the local app:

```bash
PYTHONPATH=src python3 -m khoji serve \
  --corpus data/shabados/sggs.jsonl \
  --manifest data/phase1/benchmark/manifest.jsonl
```

Then open `http://127.0.0.1:8765`.

The Phase 1 model is intentionally a benchmark harness, not the final audio model. It matches a known audio fixture by SHA-256, uses that fixture's transcript as the local baseline, and then runs the normal Khoji shabad-first/line-second retrieval. Unknown audio returns `unknown` instead of forcing a match. This gives us a working API, UI, evaluation loop, and data contract that can later swap in ASR, audio embeddings, source separation, or fine-tuned models.

The generated WAV files from `create_phase1_benchmark.py` are smoke-test fixtures only. They are not training data. Put real recordings under ignored local data and register them separately:

```bash
PYTHONPATH=src python3 scripts/register_phase1_recording.py \
  --audio data/phase1/benchmark/audio/kahe.mp3 \
  --recording-id kahe_re_ban_full_001 \
  --query "kahe re ban khojan jai" \
  --notes "Full vocal recording of Kahe Re Ban Khojan Jaayi"
```

That writes `data/phase1/recordings/manifest.jsonl` with shabad-level metadata, duration, and hash. Line-level training still needs a separate timestamp file before the recording can supervise current-line prediction.

Create a fillable line timestamp template for a recording:

```bash
PYTHONPATH=src python3 -m khoji create-line-label-template \
  --corpus data/shabados/sggs.jsonl \
  --recording-id kahe_re_ban_full_001 \
  --shabad-id SGGS:DSB \
  --audio-path ../benchmark/audio/kahe.mp3
```

This writes `data/phase1/recordings/kahe_re_ban_full_001.line_labels.tsv`.
See `docs/line_labeling.md` for the column guide.

### Surt ASR Baseline

Khoji can also use `surindersinghssj/surt-small-v3` as an optional ASR fallback for audio that is not in the Phase 1 manifest. This keeps the benchmark path deterministic while allowing arbitrary vocal audio to be transcribed and queried against the complete Shabad OS corpus.

Install the optional ASR stack:

```bash
python3 -m pip install -e '.[asr]'
```

Run `kahe.mp3` through Surt, then retrieve from the full Shabad OS export:

```bash
PYTHONPATH=src python3 -m khoji identify-audio \
  --corpus data/shabados/sggs.jsonl \
  --audio data/phase1/benchmark/audio/kahe.mp3 \
  --asr-model surt-small-v3 \
  --json
```

For line-position experiments, query a shorter window instead of the whole recording:

```bash
PYTHONPATH=src python3 -m khoji identify-audio \
  --corpus data/shabados/sggs.jsonl \
  --audio data/phase1/benchmark/audio/kahe.mp3 \
  --asr-model surt-small-v3 \
  --start-s 60 \
  --duration-s 20
```

Run the HTML app with ASR enabled for uploads and mic chunks:

```bash
PYTHONPATH=src python3 -m khoji serve \
  --corpus data/shabados/sggs.jsonl \
  --manifest data/phase1/benchmark/manifest.jsonl \
  --asr-model surt-small-v3
```

The response includes the raw ASR transcript under `asr.text`, then the usual `top_shabads`, `top_lines`, active line, context lines, and active-line-only translation. `ffmpeg` must be available on PATH because Khoji normalizes uploaded audio to 16 kHz mono WAV before transcription.

## Phase 2 Live Chunk MVP

The same server also exposes live chunking:

```text
rolling browser mic window -> POST /api/live-chunk -> sequence smoother -> reader response
```

The browser records two-second chunks, keeps the latest five chunks as an 8-10 second rolling window, and posts that window with a `session_id`. The server keeps one smoother per session. The smoother accepts same-line, next-line, rahao/refrain, and small backward movements; it holds the previous accepted line through one-off shabad jumps and returns `unknown` for audio chunks that are not recognized by the current Phase 1 benchmark harness.

You can smoke-test the live API with a generated fixture:

```bash
curl -F session_id=demo \
  -F translation_language=Punjabi \
  -F audio=@data/phase1/benchmark/audio/kahe_re_ban_kirtan_001.wav \
  http://127.0.0.1:8765/api/live-chunk
```

## How It Works

The MVP uses character n-gram TF-IDF retrieval:

```text
query text
  -> normalize
  -> rank shabad documents
  -> take best shabad
  -> rank only that shabad's lines
  -> return shabad candidates + current line candidates
```

This is a baseline, not the final model. It gives the project a stable interface for the future audio side:

```text
kirtan audio -> ASR/phonetic/audio encoder output -> Khoji shabad + line retrieval
```

## Next Work

- Replace `data/sample/shabads.jsonl` with a complete canonical corpus.
- Add recording-level labels: `recording -> shabad_id`.
- Add a pretrained audio/speech encoder that emits text, phonetic tokens, or embeddings.
- Evaluate top-1/top-5 shabad accuracy.
- Add line timestamps for a small subset and compare line-ranking quality.
- Add sequence smoothing for live tracking.
