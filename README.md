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
