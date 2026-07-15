---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: timeline/track audio mixing + ducking"
author: analysis agent
tags: [kdenlive-mcp, research, audio, mixing, eq, ducking, panner]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcripts:
  - "vault/Transcripts/Kdenlive Tutorials/How to Mix Your Voice with Music - Kdenlive Tutorial.md"
  - "vault/Transcripts/Kdenlive Tutorials/Boost Your Sound Quality - Kdenlive Tutorial.md"
---

# Track / Timeline Audio Mixing + Ducking → MCP Tool Surface Mapping

Drives **§3 High "Track-level audio"**: today every `audio_*` tool operates on
standalone files in `media/processed/`, disconnected from the timeline. A
one-stop shop needs mixer-style control *inside the project*: track volume, pan,
EQ carving, and voice-over ducking. This analysis verifies **how Kdenlive/MLT
stores track-level audio effects** (against a live `melt 7.40` render, not just
XML inspection), maps the two tutorials' recipes onto MLT services, and
documents the build.

Two Nuxttux Creative Studio tutorials analysed (both had captions):

- *"How to Mix Your Voice with Music"* (`oLdYnkcLUWI`, 4:32) — the core
  voice-over-music recipe: (1) look at the **audio spectrum** to see where the
  voice sits; (2) add a **Volume** effect to the *music* track set to **-4 dB**
  for a slight overall reduction; (3) add the **tap equalizer** (a LADSPA
  multi-band EQ) to the *music* track and **carve** the frequencies the voice
  occupies so the voice cuts through — the key insight the author states up
  front is *"it isn't reducing the volume of the music"*, it's EQ carving.
  The carve values he dials on the music bed: mids 500–2 kHz hold speech
  fundamentals, 2–4 kHz clarity/articulation, 4–6 kHz presence; he lowers
  bin1 ≈ -4, bin3 ≈ -8, bin4 ≈ -12, bin6 ≈ -8, bin7/bin5 ≈ -4.
- *"Boost Your Sound Quality"* (`rDGv8WEF87c`, 9:03) — a three-step *voice*
  chain applied to the vocal track: **sound quality** (noise suppressor → tap
  EQ, e.g. bin1 freq 60 Hz to roll off sub-bass rumble), **loudness** (simple
  compressor + gain + a volume/dynamics limiter normalised to 0 dB, threshold
  ~0.80–0.85), **stylize** (plate reverb, dampening ~0.2). Confirms the EQ /
  compressor / limiter vocabulary and that the mixer's "0 dB is all the way up"
  fader is the reference the limiter targets.

Neither tutorial demonstrates *ducking* (automatic music dip under speech) —
that is domain knowledge layered on top: MLT has **no live sidechain**
compressor path that survives our file-based, headless workflow, so ducking is
synthesised as **keyframed track volume** driven by voice-activity detection
(the flagship `audio_duck` tool).

---

## How Kdenlive/MLT stores track-level audio effects — VERDICT (render-verified)

**Track-level effects are `<filter>` elements nested as direct children of the
track's `<playlist>`**, placed *after* all `<entry>`/`<blank>` children. MLT
applies a playlist-attached filter to the entire playlist output, i.e. the whole
track. This is distinct from:

- **clip effects** → `<filter>` inside the clip `<entry>` (already handled by
  this codebase, commit de0ed27 / §1.1);
- **master/tractor effects** → `<filter>` inside `<tractor>` (how the subtitle
  agent attaches `avfilter.subtitles`, commit f1e20a5);
- **the audio-mixer fader/pan/mute** → Kdenlive's *Audio Mixer* panel persists
  its levels in `kdenlive:sequenceproperties` (`audioMixerVolume…`) for the GUI,
  but the actual rendered gain the mixer produces is the same `volume`/`panner`
  filter machinery. For a file-first, render-provable integration we write the
  **playlist-attached filter** (which melt honours headless) rather than only
  the GUI mixer property (which melt ignores). Track effects added via
  Kdenlive's effect stack on a track head land in exactly this playlist-child
  position, so the output round-trips into a real Kdenlive document.

### Verification (live `melt 7.40`, render + `astats`, not XML self-agreement)

A 1 kHz test tone on a single track, rendered `-consumer avformat` to wav, RMS
measured with `ffmpeg astats`:

| Project | Filter (playlist child) | Measured RMS | Δ vs control |
|---|---|---|---|
| control | none | **-24.08 dB** | — |
| track volume | `volume` `level=-12` | **-36.09 dB** | **-12.01 dB** ✓ exact |
| track EQ | `avfilter.equalizer` f=1000 width_type=2 width=1 gain=-18 | **-42.09 dB** | **-18 dB** ✓ (cuts the tone band) |
| keyframed duck | `volume` `level=0=0;45=0;50=-18;74=-18;80=0` | windowed | 0–1.6 s **-24 dB** (full), 2.1–2.9 s **-42 dB** (dipped -18) ✓ |
| track pan | `panner` `start=0.9` (hard right) | L **-38 dB** / R **-24 dB** | ✓ balance shifted |

So: playlist-child placement works, `volume`'s `level` is in **dB** and accepts
**frame-keyed keyframes** (`frame=level;frame=level`, same grammar the existing
`AudioFade` uses at clip scope), `panner`'s `start` is 0=L / 0.5=C / 1=R, and
multi-band EQ is a **stack of `avfilter.equalizer` peaking filters**.

### MLT service catalogue (from `melt -query filter=…`)

- **`volume`** (MLT native, `title: Volume`) — `level` property, dB or plain
  gain, animatable. Used for track volume and for the ducking envelope.
- **`panner`** (MLT native, `title: Audio Pan`) — `start` (0…1) balance /
  `split` / `channel`. Up to 6 channels.
- **`avfilter.equalizer`** (libavfilter two-pole peaking EQ) — per band:
  `av.frequency` (Hz), `av.width_type` (1=Hz, 2=octave/… numeric mapping;
  2 verified), `av.width`, `av.gain` (dB). Stack one filter per band. The
  tutorials' "tap equalizer" (LADSPA `tap_eq`) is **not present** in this
  melt build (`ladspa.*` absent from `melt -query filters`), so the equivalent
  carve is expressed as stacked `avfilter.equalizer` bands at the same
  frequencies. Also available: `avfilter.firequalizer`, `avfilter.superequalizer`,
  `avfilter.acompressor`, `avfilter.alimiter` (for the "Boost Your Sound Quality"
  compressor/limiter chain, out of scope here but same placement mechanism).

---

## Ducking without a live sidechain (the `audio_duck` design)

MLT cannot run a real sidechain compressor in our headless file pipeline (the
sidechain key would have to be routed between tracks at render time, which the
XML/consumer path does not expose). Instead `audio_duck` **synthesises** the
duck as a keyframed `volume` filter on the music track:

1. **Detect voice activity** on the voice track's *source* audio using the
   existing `adapters/ffmpeg/silence.detect_silence` (imported, not
   reimplemented). Silence gaps are inverted to **speech intervals**; each voice
   clip's speech is offset by its timeline start so intervals are in music-track
   frame space.
2. **Build a dB envelope** on the music `volume` filter's `level`: baseline
   `0` dB, ramping down to `duck_db` over `attack_ms` *before* each speech
   interval, held at `duck_db` through the speech, ramping back to `0` over
   `release_ms` after. Overlapping ducks merge. This is the pure, unit-tested
   `voice_activity_to_duck_keyframes` in `pipelines/timeline_audio.py`.
3. The envelope is written as a **track-level `volume` filter** on the music
   playlist (verified render path above), so a windowed RMS comparison proves
   the music is quieter under speech than between speech.

`threshold_db` feeds `detect_silence`'s `noise=` threshold (what counts as
silence vs. speech); `attack_ms` / `release_ms` shape the ramp so the dip is
not a hard step.

---

## Tool surface (build)

Intents in `core/models/timeline.py` (+ patcher dispatch), pure math in
`pipelines/timeline_audio.py`, registrations in `server/bundles/timeline_audio.py`.

- `track_volume(workspace_path, project_file, track, gain_db=0.0, keyframes="")`
  — static (`gain_db`) or dB-keyframed `volume` at track scope.
- `track_pan(workspace_path, project_file, track, pan=0.0)` — `panner` `start`
  from `pan` in [-1, 1] (−1=L, 0=C, +1=R).
- `track_eq(workspace_path, project_file, track, preset="voice_carve"|"music_bed", bands="")`
  — stacked `avfilter.equalizer` bands; presets carry the tutorials' carve
  frequencies/gains; `bands` accepts a custom JSON band list.
- `audio_duck(workspace_path, project_file, music_track, voice_track, duck_db=-12.0, attack_ms=200, release_ms=400, threshold_db=-30)`
  — the flagship VAD-driven keyframed duck.
- Clip-scoped variants reuse the existing entry-nested filter machinery
  (`track` + `clip_index` OpaqueElement) where track scope is not wanted.

### Storage representation in this codebase

Track filters are carried as `<filter track="{playlist_index}" mlt_service="…">`
OpaqueElements **without** a `clip_index` attribute (that absence is what
distinguishes a track filter from a clip filter). The serializer's
`_extract_track_filters` pulls them, strips the `track` association attribute,
and appends the bare `<filter>` to the matching `<playlist>` after its entries;
the parser reads `<filter>` direct children of a `<playlist>` back into the same
representation for round-trip. Idempotent tools give each filter a stable `id`
and replace any prior filter with that id (mirrors `_set_hide_directive`).
</content>
