# Line Labeling

Khoji line labels are TSV files so they can be opened in a spreadsheet without
commas inside translations breaking the columns.

Each row is one labeled audio segment. If the kirtan repeats a line, duplicate
that line's row and give the duplicate a new `segment_id`. For instrumental
sections, alaap, silence, or unsure spans, add a row with an empty `line_id`,
set `segment_type`, and set `include_in_eval` to `no`.

## Columns

- `segment_id`: Unique row ID for this recording.
- `recording_id`: Recording ID from `data/phase1/recordings/manifest.jsonl`.
- `audio_path`: Path to the local audio file.
- `shabad_id`: Canonical Khoji/Shabad OS shabad ID.
- `line_id`: Canonical Khoji/Shabad OS line ID. Leave blank for non-line spans.
- `line_order`: Canonical line order inside the shabad.
- `start_s`: Segment start time in seconds, such as `34.25`.
- `end_s`: Segment end time in seconds, such as `42.80`.
- `segment_type`: Use `vocal`, `instrumental`, `alaap`, `silence`, or `unknown`.
- `include_in_eval`: Use `yes` for confident vocal line labels, otherwise `no`.
- `text`: Canonical line text/transliteration for quick reference.
- `punjabi_translation`: Punjabi meaning/teeka for quick reference.
- `english_translation`: English translation for quick reference.
- `notes`: Anything useful, such as `repeated rahao`, `overlaps tabla intro`, or
  `uncertain start`.

## Generate A Template

```bash
PYTHONPATH=src python3 -m khoji create-line-label-template \
  --corpus data/shabados/sggs.jsonl \
  --recording-id kahe_re_ban_full_001 \
  --shabad-id SGGS:DSB \
  --audio-path ../benchmark/audio/kahe.mp3
```

By default this writes:

```text
data/phase1/recordings/kahe_re_ban_full_001.line_labels.tsv
```

Raw audio and filled labels under `data/phase1/` are ignored by Git unless we
explicitly decide to publish a small sanitized fixture later.
