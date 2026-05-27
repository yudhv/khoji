# Surt Alignment Notes

This note records the first full `kahe.mp3` alignment run against the manually
labeled file:

- Audio: `data/phase1/benchmark/audio/kahe.mp3`
- Labels: `data/phase1/recordings/kahe_re_ban_full_001.line_labels.tsv`
- Model: `surindersinghssj/surt-small-v3`
- Device used locally: `mps`
- Shabad: `SGGS:DSB`

The label file currently has 21 included vocal segments. The final label ends at
242.316s and the audio duration is 243.217s, so the file is effectively fully
labeled.

## Best Current Setup

For a live-reader-style baseline:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_surt_alignment.py \
  --oracle-pads-s '' \
  --center-durations-s '' \
  --rolling-window-s 12 \
  --rolling-hop-s 5 \
  --report data/phase1/eval/kahe_rolling_12s_5s_surt.json
```

Use:

- 12s audio window
- 5s hop
- Surt transcript -> Khoji line retrieval within the locked shabad `SGGS:DSB`
- Center-time line selection for evaluation

Result on the labeled Kahe recording:

| Config | Windows | Global shabad-first accuracy | Known-shabad line accuracy | Matched boundaries | Median boundary error |
|---|---:|---:|---:|---:|---:|
| `window-12s-hop-5s-center` | 49 | 63.3% | 95.9% | 12/12 | 1.839s |

All 12 collapsed line-change boundaries were matched within 8 seconds of the
manual label file.

This supports the intended product architecture: once the shabad has been found,
line tracking should search inside that shabad instead of repeatedly asking the
global corpus to rediscover the shabad from every short ASR fragment.

## Span Checks

Exact human label spans are useful as an upper-bound sanity check for whether
the model can hear the line at all:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_surt_alignment.py \
  --oracle-pads-s 0,1,2 \
  --center-durations-s '' \
  --rolling-window-s '' \
  --rolling-hop-s '' \
  --report data/phase1/eval/kahe_oracle_pads_surt.json
```

Best span result:

| Config | Segments | Global shabad-first accuracy | Known-shabad line accuracy |
|---|---:|---:|---:|
| `span+1s-pad` | 21 | 57.1% | 95.2% |

The remaining miss was the very short 203.179s-205.339s segment, where Surt
heard the transition into `sarab nivaasee`. That is consistent with either a
too-short span or a slightly rough boundary rather than a failure to recognize
the shabad.

## Center Window Checks

For label-centered fixed windows:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_surt_alignment.py \
  --oracle-pads-s '' \
  --center-durations-s 8,12,16 \
  --rolling-window-s '' \
  --rolling-hop-s '' \
  --report data/phase1/eval/kahe_center_windows_surt.json
```

Known-shabad line accuracy was 95.2% for 8s, 12s, and 16s center windows. The
12s window is the best starting point because it preserves enough text for Surt
without as much boundary bleed as 16s.
