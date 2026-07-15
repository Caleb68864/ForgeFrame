---
title: Local Transcription and Clip Search Index
date: 2026-07-03
type: reference
tags: [transcription, whisper, forgeframe, research]
---

# Local Transcription and Clip Search Index

Research for ForgeFrame (Workshop Video Brain). Two questions:

1. What local STT engine is *better/complementary* to what we already run?
2. How do we "transcribe all clips into a folder the AI can reference, with a searchable index"?

> [!info] What already exists (do not reinvent)
> ForgeFrame **already transcribes**. The pipeline lives in
> `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/stt/whisper_engine.py`
> and is exposed through the `transcript_generate`, `transcript_export`, `clips_label`,
> and `clips_search` MCP tools.
>
> - **Engine:** `faster-whisper` (primary), `openai-whisper` (fallback). Runs
>   `device="cpu", compute_type="int8"`, default model `small`.
> - **Audio prep:** ffmpeg extracts 16 kHz mono PCM WAV before transcription.
> - **Outputs per asset** in `<workspace>/transcripts/`:
>   `{stem}_transcript.json`, `{stem}_transcript.srt`, `{stem}_transcript.txt`.
> - **Markers:** `markers/{stem}_markers.json` (auto intro/silence/topic markers).
> - **Clip labels:** `clips/{stem}_label.json` (content_type, topics, tags, summary, duration).
> - **Search today:** `clips_search` scores a query against *clip-label* fields
>   (tags/topics/summary/content_type). It returns **whole-clip** matches, **not**
>   timestamped hits inside a transcript, and it does **not** search segment text.
>
> This note focuses on (a) whether to change engine and (b) building the **missing
> segment-level, timestamped search index** — not rebuilding transcription.

---

## Part 1 - Local STT engine landscape (2025/2026)

### The engines

| Engine | What it is | Accuracy (WER) | Speed | Footprint / hardware | Word timestamps | Notes |
|---|---|---|---|---|---|---|
| **faster-whisper** *(current)* | CTranslate2 reimpl of Whisper | Whisper-class (~7.4% avg leaderboard) | ~3x realtime CPU int8; ~12x realtime on RTX 4070 (large-v3) | Small (int8), CPU-friendly, optional CUDA | **Yes** — `word_timestamps=True` (not currently enabled, see below) | Best all-round default. Already integrated. |
| **whisper.cpp** | GGML C++ port of Whisper | Whisper-class (same models) | ~10x realtime on Apple Metal; ~8x CUDA | Tiny binary, zero Python, great on Apple Silicon | Yes (`--max-len`/tokens, DTW timestamps) | Wins on Mac / no-Python edge. Weaker on non-Apple GPU vs faster-whisper. |
| **NVIDIA Parakeet TDT 0.6B v3** | CTC/TDT transducer | **~6.3% WER** (beats Whisper) | **~3000x+ realtime (RTFx ~3300)** on GPU | Needs NVIDIA GPU + NeMo (or `parakeet.cpp`) | Yes (token/word offsets) | Fastest accurate option, but **25 EU languages only** (vs Whisper's 99) and NVIDIA-centric. `parakeet.cpp` removes the Python/ONNX dependency and runs on Apple Metal. |
| **NVIDIA Canary Qwen 2.5B** | ASR + LLM hybrid | **~5.6% WER (leaderboard #1)** | ~418x realtime (RTFx 418) | Large, NVIDIA GPU | Yes | Most accurate open model; heavy. Overkill for workshop clips. |
| **Moonshine (v2 / tiny)** | Ergodic streaming encoder, edge-first | Beats Whisper tiny/small at a fraction of the size | Very low latency, energy-efficient; dynamic windows (no forced 30s chunks) | **27M-param models**, phones/IoT/edge | Limited/segment-oriented (built for live commands) | Great for *live captions / voice commands*, not the best for archival word-accurate clip transcripts. |
| **Vosk** | Kaldi-based, fully offline | Below Whisper on general audio | Fast, lightweight, real-time capable | Small models, runs on Raspberry Pi | Yes (word-level with conf) | Mature, many language bindings, streaming. Accuracy trails Whisper/Parakeet on messy workshop audio. |

### Word-level timestamps + subtitle output (matters for jumping to a moment)

- **faster-whisper** natively supports `word_timestamps=True`, returning per-word
  start/end. **We are not passing this flag today** — the `WordTiming`/`words` field
  exists on `TranscriptSegment` but is written empty (`"words": []`). Enabling it is a
  near-zero-cost upgrade and is the prerequisite for jump-to-word search.
- **WhisperX** (built on faster-whisper) adds **wav2vec2 forced alignment** for
  **<100 ms** word timestamps (vs Whisper's native segment timings that drift by
  hundreds of ms) and emits `srt, vtt, txt, tsv, json, aud`. It also bundles pyannote
  diarization. This is the natural "complementary" upgrade if karaoke-accurate word
  timing is wanted.
- **whisper.cpp / Parakeet / Vosk** all expose word offsets; Moonshine is
  segment/stream-oriented.
- ForgeFrame currently emits **SRT + JSON + TXT**; adding **VTT** is trivial and is the
  web-native caption format.

### The "built into Chrome" idea — verdict

**No — Chrome's on-device Live Captions engine (SODA) is not officially usable outside the browser, so it is not a viable engine for a headless MCP pipeline.**

Details so the idea is properly closed out:

- **SODA** ("Speech On-Device API") is the proprietary engine that powers Chrome/ChromeOS
  Live Captions. It is a sandboxed, closed-source component; there is **no supported public
  API** to call it from a script or server. (A community proof-of-concept, `gasr`, reverse-
  engineers `libsoda` from ChromeOS to pipe audio → stdout, but it is unsupported, fragile,
  and legally grey — not something to ship.)
- What **is** accessible is the **Web Speech API** (`SpeechRecognition`). As of **Chrome 139
  (Aug 2025)** it gained an **on-device mode**: `SpeechRecognition` with
  `processLocally: true` plus `available({langs, processLocally})` and downloadable SODA
  language packs, so audio need not leave the device. It even supports **contextual biasing**
  (`SpeechRecognitionPhrase`).
- **But** it only runs **inside a browser tab from live/streamed audio via getUserMedia** —
  it is designed for real-time mic/voice UIs, not batch-transcribing a folder of video files,
  gives no reliable word-level timestamps or SRT/VTT export, and has had stability regressions
  (on-device disabled until ~142). It is the wrong tool for offline archival clip transcription.

**Bottom line:** keep a real ASR engine (Whisper family / Parakeet). The Chrome route is a
dead end for our use case.

### Speaker diarization (future add-on)

Not needed for solo-workshop talking-head footage today, but easy to bolt on later:

- **pyannote 3.1** — best accuracy/accessibility balance for open-source; pip-installable,
  Hugging Face model, CPU-runnable (slow) or GPU. DER ~11-19% depending on audio. Easiest
  path, and it's what **WhisperX** integrates.
- **NVIDIA NeMo (Sortformer / clustering)** — lower DER (~0.11 vs pyannote ~0.20 in a Dec-2025
  eval) but needs NVIDIA GPU + heavier setup; production/multi-speaker oriented.
- Recommendation: **defer diarization**; when needed, adopt it via **WhisperX + pyannote**
  because it reuses our existing faster-whisper backend rather than adding a second stack.

### Engine recommendation

- **Keep faster-whisper as the default** and immediately **enable `word_timestamps=True`**
  (populate the existing `WordTiming` model) — this unlocks jump-to-timestamp search with no
  new dependency.
- **Optionally add WhisperX** as an opt-in "high-precision" profile for <100 ms word timing +
  VTT + future diarization; it reuses faster-whisper so it's complementary, not a rewrite.
- **Parakeet** only earns a slot later if the user has an NVIDIA GPU and wants near-instant
  bulk transcription of English/EU footage; note the 25-language limit.

---

## Part 2 - Design: transcribe all clips + a searchable index

Goal: every clip transcribed into `transcripts/` (already happening) **plus** an index the
AI can query to get **"clip X, at 00:03:12"** hits — segment-level, ranked, correctable.

### Index format: SQLite (FTS5) vs `graph.json`

The user floated either a `graph.json` or SQLite. Recommendation below.

| Concern | `graph.json` (single file) | **SQLite + FTS5** |
|---|---|---|
| Dependency | stdlib `json` | **stdlib `sqlite3` (FTS5 compiled into CPython)** — still zero external deps |
| Ranked full-text search | Hand-rolled scoring, linear scan every query | **Built-in BM25 ranking**, `MATCH`, prefix/phrase queries, snippets/highlight |
| Incremental edit / reindex | Rewrite whole file on every change | **Row-level UPDATE/DELETE**, transactional |
| Scale (many clips × many segments) | Loads/serializes entire graph in memory | Indexed, scales to 100k+ segments trivially |
| Concurrency / partial writes | Risk of corrupting one big file | ACID, safe against crashes |
| Human-diffable in Obsidian/git | Yes (readable) | No (binary) — but transcripts stay as JSON/SRT, so source of truth is still text |
| Embeddings later | Store vectors in JSON (bloats file) | Add a `BLOB`/`vec` column or `sqlite-vec` extension cleanly |

**Recommendation: SQLite with FTS5.** It gives ranked BM25 search, cheap row-level
edit/reindex, and scales — all from the Python standard library with **no new dependency**,
which fits ForgeFrame's local-first constraint. The JSON/SRT transcript files remain the
human-readable, git-tracked source of truth; the DB is a **rebuildable derived index**
(delete-and-rebuild is always safe), so we get FTS power without giving up plain-text
portability.

### Layout (fits existing workspace convention)

```
<workspace>/
  transcripts/
    {stem}_transcript.json     # existing source of truth (add words[] + VTT)
    {stem}_transcript.srt
    {stem}_transcript.vtt      # NEW (web-native captions)
    {stem}_transcript.txt
  index/
    transcripts.db             # NEW - SQLite FTS5 index (derived, rebuildable)
```

`index/transcripts.db` is derived and can be `.gitignore`d; rebuild from `transcripts/*.json`.

### Schema sketch

```sql
-- One row per transcribed clip/asset
CREATE TABLE clips (
    clip_ref     TEXT PRIMARY KEY,   -- matches {stem}, e.g. "clip_step1"
    asset_id     TEXT,               -- UUID from Transcript.asset_id
    source_path  TEXT,               -- path to media / transcript json
    engine       TEXT,
    model        TEXT,
    language     TEXT,
    duration     REAL,
    content_type TEXT,               -- mirrored from clips/{stem}_label.json
    updated_at   TEXT
);

-- One row per transcript segment (the searchable unit -> gives timestamp)
CREATE TABLE segments (
    segment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_ref     TEXT REFERENCES clips(clip_ref) ON DELETE CASCADE,
    seg_index    INTEGER,            -- ordinal within the clip
    start_seconds REAL,
    end_seconds   REAL,
    text          TEXT,
    confidence    REAL,
    edited        INTEGER DEFAULT 0  -- 1 if human-corrected
    -- embedding BLOB   -- DEFERRED: semantic search vector (sqlite-vec)
);

-- Contentless FTS5 mirror over segment text for ranked search
CREATE VIRTUAL TABLE segments_fts USING fts5(
    text,
    content='segments',
    content_rowid='segment_id',
    tokenize='porter unicode61'     -- stemming + case/diacritic folding
);

-- Tags (from clip labels / markers) for filtered search
CREATE TABLE tags (
    clip_ref TEXT REFERENCES clips(clip_ref) ON DELETE CASCADE,
    tag      TEXT
);
```

A `segments_search` query then returns `clip_ref + start_seconds + snippet`, i.e. the
exact "jump here" target the AI needs. Embeddings are an **optional/deferred** column so
keyword search ships first and semantic search can be added without a migration.

### MCP tool sketches

```text
transcript_index_build(workspace_path, rebuild=False)
  -> Scan transcripts/*_transcript.json (+ clips/*_label.json for tags/content_type).
     Upsert clips + segments, populate segments_fts. If rebuild=True, drop & recreate.
     Returns {clips_indexed, segments_indexed, db_path}.

transcript_search(workspace_path, query, limit=20, clip_ref=None)
  -> FTS5 MATCH with BM25 ranking over segments_fts (optionally filtered by clip_ref/tag).
     Returns ranked hits: [{clip_ref, start_seconds, end_seconds, text, snippet, score}].
     This is the jump-to-timestamp search that clips_search cannot do today.

transcript_edit(workspace_path, clip_ref, seg_index, new_text)
  -> Correct a mis-transcribed segment. Writes back to transcripts/{stem}_transcript.json
     (source of truth), marks edited=1, and reindexes just that row (UPDATE + FTS sync).
     Returns {clip_ref, seg_index, old_text, new_text}.
```

### Relationship to existing `clips_search` — merge or coexist?

They operate at **different granularities**, so keep both but layer them:

- `clips_search` = **coarse, clip-level** discovery over derived *labels* (topics/tags/summary,
  content_type). Good for "find my talking-head clips about soldering."
- `transcript_search` = **fine, segment-level** retrieval over *actual transcript text* with a
  **timestamp**. Good for "where exactly did I say 'flux core'?" → `clip_step1 @ 00:03:12`.

**Recommendation:** don't rip out `clips_search`; instead **back it by the same SQLite DB**
(add a `clip_labels` FTS table) so both tools share one index, and consider a thin
`clips_search` that first runs `transcript_search`, then aggregates hits up to the clip level
with per-clip best timestamps. Long-term they converge on one index with two query surfaces
(clip-level vs segment-level), rather than two separate scanners.

---

## Recommended next steps (implementation order)

1. **Enable `word_timestamps=True`** in `whisper_engine._transcribe_faster_whisper` and
   populate `WordTiming` (near-zero cost, unlocks precise jumps).
2. **Add VTT export** alongside SRT/JSON/TXT.
3. **Ship `transcript_index_build` + `transcript_search`** backed by `index/transcripts.db`
   (SQLite FTS5, stdlib only).
4. **Add `transcript_edit`** with write-back + single-row reindex.
5. **Point `clips_search` at the same DB**; converge the two search surfaces.
6. *Later / optional:* WhisperX profile for <100 ms alignment + pyannote diarization;
   embedding column for semantic search.

---

## Sources

- [Whisper.cpp vs faster-whisper 2026 benchmarks](https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026)
- [Top Open Source STT Models 2025 - Modal](https://modal.com/blog/open-source-stt)
- [Best open-source STT 2026 benchmarks - Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Parakeet vs Whisper - Local AI Master](https://localaimaster.com/blog/parakeet-vs-whisper)
- [Parakeet.cpp vs Whisper self-hosted ASR](https://modelslab.com/blog/audio-generation/parakeet-cpp-vs-whisper-self-hosted-asr-comparison-2026)
- [Choosing Whisper variants (faster-whisper / WhisperX) - Modal](https://modal.com/blog/choosing-whisper-variants)
- [Moonshine paper (arXiv 2410.15608)](https://arxiv.org/html/2410.15608v2)
- [Moonshine GitHub](https://github.com/moonshine-ai/moonshine)
- [WhisperX GitHub (m-bain)](https://github.com/m-bain/whisperX)
- [WhisperX 2026 word timestamps + diarization guide](https://localaimaster.com/blog/whisperx-guide)
- [Web Speech API on-device explainer (WebAudio)](https://github.com/WebAudio/web-speech-api/blob/main/explainers/on-device-speech-recognition.md)
- [SpeechRecognition.processLocally - MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/processLocally)
- [On-Device Speech UIs in Chrome 139](https://medium.com/@roman_fedyskyi/on-device-speech-uis-in-chrome-139-4b9f0397b9c9)
- [SODA offline CLI PoC (gasr)](https://github.com/biemster/gasr)
- [Chromium: Web Speech API SODA backend issue](https://issues.chromium.org/issues/40286514)
- [pyannote vs NeMo diarization - La Javaness](https://lajavaness.medium.com/comparing-state-of-the-art-speaker-diarization-frameworks-pyannote-vs-nemo-31a191c6300)
- [Speaker diarization models compared 2026 - BrassTranscripts](https://brasstranscripts.com/blog/speaker-diarization-models-comparison)
- [Diarization evaluation 2025 - VoicePing](https://voiceping.net/en/blog/research-diarization-2025/)
