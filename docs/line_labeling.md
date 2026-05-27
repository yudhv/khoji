# Line Labeling

Khoji line labels are TSV files written by the local labeler. They can still be
opened in a spreadsheet, but the normal workflow is to label from the browser.

## Browser Labeler

Run the local server:

```bash
PYTHONPATH=src python3 -m khoji serve \
  --corpus data/shabados/sggs.jsonl \
  --recordings data/phase1/recordings/manifest.jsonl
```

Then open:

```text
http://127.0.0.1:8765/labeler?recording_id=kahe_re_ban_full_001
```

The page plays the recording and loads canonical text from Shabad OS. For a
registered recording with a known `shabad_id`, the full shabad appears
immediately. For a new upload, search the full SGGS corpus first; clicking a
search result records that line and switches the picker to the full shabad that
contains it, so nearby lines can be labeled without searching again.

Clicking a line records the current audio time as that line's `start_s`. The next
line click closes the previous segment by setting its `end_s`, then starts the
new segment. Clicking the same line again records a repeated line. `Finish`
closes the final open segment at the current audio time. `Reset` clears the
label file for the recording.

Use `Add media` on the labeler page to upload a new local audio/video file. The
server saves it under ignored local data, adds it to
`data/phase1/recordings/manifest.jsonl`, and creates the corresponding label TSV
automatically as soon as labels are recorded.

Each row is one labeled audio segment. If the kirtan repeats a line, click that
line again and the labeler writes another row with a new `segment_id`. For
instrumental sections, alaap, silence, or unsure spans, use `Finish` to close
the surrounding vocal segment; explicit non-vocal span buttons can be added once
we need those labels.

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

This is optional. The browser labeler does not need a hand-filled template, but
the command is still useful when you want a spreadsheet reference.

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
