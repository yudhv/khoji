# Gurbani-Constrained Audio Alignment Plan

## Purpose

Build the next Khoji model track around a Gurmukhi-only, canonical Guru Granth Sahib
position tracker. This replaces the current transcript-first ASR baseline with a system
that learns how sung or recited Gurbani audio maps onto fixed canonical text positions.

The desired behavior is:

```text
Punjabi/Gurbani audio
-> canonical Gurmukhi text positions
-> current shabad and current line
```

The recognizer must not depend on English transliteration, English translation, or a
free-form language-model decoder.

## Core Thesis

Khoji should not ask a general ASR model, "what sentence did I hear?"

Khoji should ask:

```text
Given this finite canonical Gurbani corpus, where is this audio most likely located?
```

That means the neural model should estimate evidence, and a canonical graph should
enforce truth.

```text
audio/text encoders give probabilities and similarities
canonical SGGS graph constrains valid positions
sequence tracker decides current line, repeat, wait, or non-lexical state
```

## Hard Constraints

- Use Gurmukhi/Unicode Punjabi text in the recognition path.
- Do not use English translations in the recognition path.
- Do not use English transliteration in the recognition path.
- Do not use an open-ended text generator as the final recognizer.
- Preserve the canonical corpus as the source of truth.
- Optimize for a small, high-quality labeled dataset: initially a few dozen recordings.
- Allow precise human labels, but avoid requiring phoneme labels unless later evidence
  shows they are necessary.

## No-Hallucination Contract

The model is allowed to estimate evidence. It is not allowed to invent text.

Allowed model outputs:

```text
audio embedding
frame-level scores over Khoji Gurmukhi unit IDs
state scores such as line, repeat, wait, non_lexical, silence
boundary scores such as line_start or line_complete
```

Disallowed final recognizer outputs:

```text
free-form Gurmukhi sentences
English transliteration
English translation
open-ended decoder text
```

The public output must be selected from canonical graph nodes:

```text
shabad_id
line_id
word_range or unit_range when available
state
confidence
```

If the graph cannot produce a confident path, Khoji should say `wait`,
`uncertain`, or `non_lexical` instead of forcing a false line.

## Target Architecture

```text
Canonical Gurmukhi corpus
-> normalized line/word/unit representation
-> canonical shabad graph

Audio span
-> audio encoder
-> audio embedding and/or frame-level unit probabilities

Canonical Gurmukhi span
-> deterministic Gurmukhi line/phrase index
-> optional learned Gurmukhi text embedding

Audio/text retrieval
-> candidate shabad/line/phrase

Constrained alignment
-> path through canonical shabad graph

Sequence tracker
-> current shabad, current line, confidence, wait/repeat/alaap state
```

There are two complementary model paths:

1. Multimodal retrieval:

```text
audio span embedding <-> Gurmukhi line/phrase embedding
```

This finds likely candidate shabads, lines, and phrases.

2. Deterministic canonical indexing:

```text
Gurmukhi phrase or unit evidence -> exact candidate lines and phrase ranges
```

This should come before a learned text encoder. Exact canonical text search, word-unit
matching, and akhar/unit matching are easier to debug and harder to overfit.

3. Constrained alignment:

```text
audio frames -> canonical Gurmukhi unit/posterior evidence -> path in shabad graph
```

This stabilizes exact position, repeats, and boundaries.

## Why The Canonical Graph Still Matters

Even if we label small units such as words or phonetic-ish Gurmukhi units, the graph
remains useful. The graph is not a workaround; it is the map of the fixed text.

The model may hear evidence for a word or unit. The graph answers:

- Is that unit plausible at this position?
- Is it a continuation of the current line?
- Is it a repeated phrase?
- Is it the rahao line returning?
- Is there enough evidence to move forward?
- Should the system wait because the phrase has not resolved?
- Should the system mark the current audio as non-lexical/alaap?

Without the graph, the model has to learn the entire structure of SGGS and all repeat
behavior from a tiny dataset. With the graph, the model can focus on acoustic evidence.

## Canonical Representation

Create a new compiled corpus artifact separate from the current UI/retrieval export:

```text
data/derived/sggs_gurmukhi_units.jsonl
```

This artifact is the first hard gate. The current Shabad OS export used by Khoji has
Gurbani text in a Shabad OS/font-style encoding such as:

```text
kwhy ry; bn Kojn jweI ]
```

That is useful as source material, but it is not the model-facing representation.
Before tokenization or model training, the compiler must produce Unicode Gurmukhi:

```text
ਕਾਹੇ ਰੇ ਬਨ ਖੋਜਨ ਜਾਈ ॥
```

The original source string may be retained for traceability, but model-facing fields
must be Unicode Gurmukhi or integer unit IDs derived from Unicode Gurmukhi.

Each record should contain:

```json
{
  "shabad_id": "...",
  "line_id": "...",
  "line_order": 3,
  "section": "Rahao",
  "is_refrain": true,
  "source_gurmukhi": "...",
  "source_gurmukhi_encoding": "shabados_legacy",
  "gurmukhi": "...",
  "normalized_gurmukhi": "...",
  "word_units": ["..."],
  "akhar_units": ["..."],
  "sub_akhar_units": ["..."],
  "unit_ids": [101, 202, 303]
}
```

### Normalization Rules

The exact rules need tests and review, but the first pass should:

- Preserve canonical Gurmukhi content.
- Convert the Shabad OS source text to Unicode Gurmukhi before any model-facing
  tokenization.
- Normalize Unicode form consistently.
- Remove or separately represent punctuation and line-ending markers.
- Preserve word boundaries.
- Preserve line order.
- Preserve section metadata such as rahao and sirlekh.
- Avoid English transliteration entirely.
- Emit stable integer unit IDs for runtime model use.

### Unit Levels

Start with three levels:

1. Line units:

```text
line_id
```

Useful for coarse retrieval and evaluation.

2. Word units:

```text
Gurmukhi words from the canonical line
```

Useful for human labels and repeat handling.

3. Akhar or orthographic syllable units:

```text
base consonant/vowel cluster plus signs/marks
```

Useful for CTC/alignment later, especially for stretched sung words.

Do not block the first usable pipeline on perfect akhar segmentation. A tested
Unicode conversion plus word-level pipeline is more useful than an overdesigned unit
compiler. Akhar units should be added with tests once word-level labeling and graph
replay are working.

## Labeling Strategy

The label format should allow progressively richer labels.

### Required Labels

For each recording:

```text
recording_id
audio_path
shabad_id
```

For each sung/recited span:

```text
start_s
end_s
line_id
state
```

Where `state` is one of:

```text
line
repeat
non_lexical
silence
uncertain
```

### Optional High-Value Labels

Add these only where easy:

```text
start_s
end_s
line_id
word_start_index
word_end_index
phrase_note
```

This allows labels like:

```text
line 3, words 1-3 repeated
line 3, words 4-6
non_lexical/alaap
```

This is likely a better use of human labeling time than trying to label every phoneme.

## Phase 0: Corpus Compiler

Goal:

```text
Compile Shabad OS SGGS text into a Gurmukhi-only canonical unit corpus.
```

Implementation:

- Load SGGS corpus.
- Ensure each line has Unicode Gurmukhi text.
- Normalize Gurmukhi.
- Tokenize into word units.
- Add an initial akhar/unit tokenizer.
- Emit JSONL.
- Add tests for known shabads, including "Kahe Re Ban Khojan Jaai".

Acceptance:

- No transliteration fields are used by this artifact.
- No translation fields are used by this artifact.
- Every model-facing text field is Gurmukhi/Unicode or structural metadata.
- Known lines round-trip from corpus to units.

## Phase 1: Canonical Shabad Graph And Deterministic Index

Goal:

```text
Represent each shabad as an allowed path through canonical Unicode Gurmukhi units,
and build deterministic lookup over lines, word ranges, and unit ranges.
```

Why this moves earlier:

The graph shapes labels, evaluation, repeat handling, rahao returns, and the final
no-hallucination contract. It should exist before learned audio/text models.

Graph states:

```text
line_start(line_id)
line_continue(line_id)
line_end(line_id)
repeat_phrase(line_id, word_range)
rahao_return(line_id)
non_lexical
silence
uncertain
wait
```

Allowed transitions:

- same line continuation
- next line
- repeat current line or phrase
- rahao repeat
- limited backward phrase repeat
- non_lexical -> previous plausible line
- silence -> wait or previous plausible line
- wait -> same state

Deterministic indexes:

- exact Unicode Gurmukhi line lookup
- word-range lookup inside a line
- phrase lookup across all SGGS lines
- initial akhar/unit lookup where available

Acceptance:

- Given a sequence of known labels, the graph can represent the path.
- Impossible jumps are rejected or heavily penalized.
- Repeated phrase labels are represented without duplicating canonical text.
- Exact Unicode Gurmukhi line text retrieves the correct line.
- Gurmukhi phrase text retrieves the containing line and word range.
- No English/transliteration is used.

## Phase 2: Labeler Upgrade For Small Units

Goal:

```text
Let a human label line spans, repeated phrase spans, and non-lexical spans quickly.
```

Implementation:

- Keep current line-click labeling.
- Add optional phrase/word-range labeling inside the selected line.
- Add state buttons: line, repeat, non-lexical, silence, uncertain.
- Add quick keyboard shortcuts.
- Export labels as JSONL or TSV with stable schema.
- Drive line/word choices from the canonical Unicode Gurmukhi graph.
- Show source audio, current segment, previous segment, and next plausible graph
  states to reduce labeling friction.

Acceptance:

- A full recording can be labeled at line level.
- Repeated phrases can be represented without inventing new text.
- Alaap/non-lexical sections can be marked explicitly.
- Labels do not depend on transliteration.
- Labels can be replayed through the canonical graph without invalid transitions,
  except when explicitly marked `uncertain`.

## Phase 3: Deterministic Replay Baseline

Goal:

```text
Prove the corpus, graph, and labels work before training any learned model.
```

Implementation:

- Replay labeled recordings from their label files.
- Use the graph to compute the current expected line/state at every timestamp.
- Compare fixed-window guesses, graph-only progression, and oracle labels.
- Add report output for boundary timing and transition errors.

Acceptance:

- A labeled recording can be replayed end-to-end.
- The report catches impossible labels and invalid transitions.
- The report separates line, repeat, non_lexical, silence, and uncertain spans.
- No model training is required for this baseline.

## Phase 4: Audio Encoder Retrieval Baseline

Goal:

```text
Map labeled audio spans to canonical Gurmukhi line/phrase candidates without
free-form transcription.
```

Implementation:

- Start with a pretrained audio encoder as frozen features.
- Train only a small projection or classification head first.
- Use positive pairs:
  - audio span and matching Gurmukhi line
  - audio span and matching phrase when phrase labels exist
- Use negative pairs:
  - other lines in same shabad
  - similar lines from other shabads
  - random SGGS lines
- Include `non_lexical` as a separate state rather than forcing a line match.
- Start with deterministic Gurmukhi text embeddings from the canonical units.
- Add a learned Gurmukhi text encoder only if deterministic unit embeddings are the
  bottleneck.

Acceptance:

- On held-out spans from labeled recordings, correct line is top-k.
- Results are reported separately for:
  - paath/monotonic recitation
  - sung kirtan
  - repeated phrase
  - non-lexical/alaap

## Phase 5: Constrained Decoder

Goal:

```text
Use model scores plus the graph to choose the most plausible current line/state.
```

Implementation:

- Start with dynamic programming or beam search.
- Inputs:
  - audio/text retrieval scores
  - deterministic Gurmukhi phrase/unit match scores
  - optional frame-level unit scores
  - previous tracker state
  - elapsed time since last confident move
- Outputs:
  - shabad_id
  - line_id
  - state
  - confidence
  - reason: same, next, repeat, rahao, wait, non_lexical

Acceptance:

- Can replay a labeled recording and produce stable line progression.
- Does not force false lines during non-lexical sections.
- Does not flicker between unrelated shabads.
- Can wait when a line has not resolved.
- Public output is always a canonical graph node, never generated text.

## Phase 6: Frame-Level Gurmukhi Unit Model

Goal:

```text
Move beyond whole-span retrieval toward actual sung alignment.
```

Implementation:

- Train a CTC-style head over Gurmukhi units:
  - blank
  - non_lexical
  - word or akhar units
- Train from labeled line/phrase spans first.
- Add word/phrase labels as available.
- Decode only through the canonical graph.

Acceptance:

- Better line timing than span-level retrieval.
- Better handling of stretched sung words.
- Better repeat detection.
- Still no free-form text generation.

## Phase 7: Boundary And Wait Model

Goal:

```text
Teach Khoji when to wait, continue, repeat, or move to the next line.
```

Implementation:

Add auxiliary heads on top of audio features:

```text
line_start
line_continue
line_complete
phrase_repeat
non_lexical
wait
```

Training labels come from line spans and optional phrase labels.

Acceptance:

- The model can avoid disruptive fixed-window decisions.
- The tracker waits during unresolved phrases.
- Repeated fragments do not force false canonical advancement.

## Phase 8: Distillation To Small Khoji Model

Goal:

```text
Reduce dependency on large pretrained encoders once the behavior is proven.
```

Implementation:

- Use the best frozen-encoder model as teacher.
- Train a smaller Gurbani-only audio encoder on:
  - labeled recordings
  - unlabeled Gurbani audio with pseudo-labels
  - augmentation
- Preserve the same Unicode Gurmukhi unit vocabulary, deterministic indexes, and graph
  decoder.

Acceptance:

- Smaller model approaches teacher accuracy on held-out recordings.
- Latency improves enough for real-time use.
- Quality does not regress on sung kirtan.

## Evaluation

Reports should include:

```text
shabad top-1 / top-5
line top-1 / top-3
phrase/word-range overlap when labels exist
boundary timing error
false-confidence rate
non-lexical false-line rate
latency
```

Separate every metric by:

```text
paath
sung kirtan
repeated phrase
non_lexical
noisy/accompanied
held-out recording
held-out shabad
```

## Near-Term Recommended Build Order

1. Build the Gurmukhi-only canonical corpus compiler.
2. Build the canonical shabad graph and deterministic Gurmukhi line/phrase index.
3. Upgrade the labeler to mark line/repeat/non-lexical/silence/uncertain spans.
4. Add optional word-range labels, driven by the canonical graph.
5. Build deterministic replay and graph-validation reports.
6. Train an audio-to-Gurmukhi-line/phrase retrieval baseline.
7. Build the constrained decoder/tracker on top of graph and retrieval scores.
8. Add frame-level CTC/unit modeling only after enough labels exist.

This order gives useful diagnostics early while still moving toward the real target
architecture.

## Key Decision Points

### Word Units vs Akhar Units

Start with word units for labels and retrieval. Add akhar units for CTC/alignment once
the line/phrase pipeline is working. The non-negotiable first step is Unicode
Gurmukhi conversion; akhar perfection can come later.

### Deterministic Index vs Learned Text Encoder

Start with deterministic Unicode Gurmukhi indexes over lines, phrases, words, and
units. Add a learned Gurmukhi text encoder only when deterministic indexing fails to
represent the needed similarity signal. This reduces model surface area while labels
are scarce.

### Contrastive Retrieval vs CTC

Use contrastive retrieval first because it is easier with few recordings. Add CTC when
precise timing and stretched singing become the bottleneck.

### Graph vs Pure Neural Tracker

Keep the graph. With a small dataset, the graph is the most reliable way to enforce
canonical SGGS structure and prevent hallucinated outputs.

### Pretrained Encoder vs From Scratch

Do not train the audio encoder fully from scratch at first. Freeze a strong pretrained
audio encoder, train small Khoji-specific heads, then distill later if needed.

## Definition Of Success

Khoji succeeds when it can:

- Listen to sung or recited Gurbani.
- Avoid inventing text.
- Use only canonical Gurmukhi text in the recognition path.
- Identify the current shabad and line.
- Wait when there is not enough evidence.
- Handle repeated phrases and rahao returns.
- Mark non-lexical/alaap instead of forcing a false line.
- Improve with a small number of precisely labeled recordings.
