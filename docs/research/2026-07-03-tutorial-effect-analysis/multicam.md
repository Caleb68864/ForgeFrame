---
date: 2026-07-03
topic: "Kdenlive multicam workflow → MCP capability mapping (audio sync, stacked placement, switch-cutting)"
author: analysis agent
tags: [kdenlive-mcp, research, multicam, audio-sync, tracks, spec]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "(none — video HSqwLwl6-Qk has no captions; see §0)"
video: HSqwLwl6-Qk
channel: "(Kdenlive multicam tutorial)"
built_tool: media_sync_by_audio
landscape_entry: 20
---

# Kdenlive Multicam → MCP Tool Surface Mapping

Landscape entry **#20 (Multicam)**, analysed against the workshop-video-brain
MCP surface (`edit_mcp/pipelines/`, `edit_mcp/server/tools.py`,
`edit_mcp/server/bundles/`, `edit_mcp/adapters/kdenlive/`). This report ships
the buildable core of Phase A — `media_sync_by_audio` — and specs Phases A/B/C.

## 0. Source note (no transcript available)

The target tutorial *"Kdenlive Tutorial - Multicam editing [one video from
multiple camera's footage]"* (`HSqwLwl6-Qk`) has **no manual or auto captions**,
so `scripts/download_playlist_transcripts.py` skipped it and wrote no transcript
note (the index note was left untouched — the script only rewrites the index
when at least one note is written). This analysis is therefore built from
Kdenlive's documented multicam workflow (24.08+/25.x) and the project's own
research notes, **not** a transcript. Claims about exact GUI wording are omitted;
claims about the MLT/`.kdenlive` structures are grounded in the existing
kdenlive adapters/parsers and are marked where inferred.

## 1. How Kdenlive's multicam workflow operates

Kdenlive has no separate "multicam clip" object the way Premiere/Resolve do.
Multicam is assembled out of ordinary primitives plus a GUI *editing mode*:

1. **Stack the angles.** Each camera/recorder angle goes on its **own video
   track**, vertically aligned so the same real-world moment sits at the same
   timeline position across tracks.
2. **Sync the angles.** The angles started rolling at different moments, so each
   track must be slid until a shared reference lines up. Two ways:
   - *Manual* — line up a visible clap/flash or an audio waveform by eye.
   - *Audio-align* — cross-correlate the tracks' audio (or fingerprint them) to
     recover the start offset automatically. This is the step
     `media_sync_by_audio` mechanises. Kdenlive's own "align audio to reference"
     does the equivalent inside the GUI.
   The offset is realised as a **leading gap** on the later-starting track (an
   MLT `<blank>` before the clip) or by trimming a track's head.
3. **Multicam view + switch-cutting.** With angles stacked and synced, the
   editor enters **Multicam editing mode**: the monitor shows every angle
   (grid), and during playback clicking an angle performs a **cut** on the
   target track and switches the program output to that angle from that frame
   on. Repeatedly clicking builds the edit as a sequence of cuts. The result is
   an angle-switching program feed driven entirely from one track's visibility /
   segment selection.

### What project-file structures this produces

`.kdenlive` is MLT XML (see `adapters/kdenlive/parser.py`, `writer.py`,
`core/models/kdenlive_model.py`):

- **One `<playlist>` per track**, each holding `<entry producer=… in=… out=…>`
  clip references and `<blank length=…>` gaps.
- **Sync offset** = a leading `<blank>` (frames of silence/black) on the
  later track, or adjusted `in`/`out` on the head clip. No special attribute —
  it is ordinary timeline placement.
- **A `<tractor>`** binds the track playlists via `<track>` refs and carries the
  `<transition>` (qtblend/frei0r `cairoblend` compositing, plus `mix` for audio)
  that decides which stacked track is visible. Track **compositing + order** is
  what makes the top-most active angle show over the ones below.
- **Switch-cutting** (inferred) materialises as the target angle track being
  **split into many `<entry>` segments** (`clip_split`), with each switch point a
  cut boundary; the visible angle per segment is chosen by segment presence +
  track visibility/compositing rather than a bespoke "multicam" node. The
  **multicam *view* itself is a monitor mode and persists nothing** to the file.

## 2. Existing vs missing primitives

| Multicam need | Existing primitive(s) | Gap |
|---|---|---|
| Recover start offset between two angles | **`media_sync_by_audio` (NEW, this build)** | — |
| Add N stacked video tracks | `track_add` | orchestration only |
| Place a clip on a track at a frame offset | `clip_insert`, `gap_insert` (leading blank) | blocked by placement-fix (§4) |
| Choose which stacked angle is visible | `track_visibility`, `track_mute`, `composite_set`, `transitions_apply*` | choreography only |
| Cut an angle at switch points | `clip_split` | orchestration only |
| Snapshot before writing | `snapshot_list` / restore (all write tools) | — |
| **Multicam monitor grid / live switching** | — | **GUI-only, out of scope (Phase C)** |

The machinery exists; what is missing are **two orchestrating tools** that chain
these into the multicam workflow, plus the shared placement-fix they depend on.

## 3. Phased MCP spec

### Phase A — audio sync + stacked placement  *(partially shipped)*

**Goal:** given N recordings of one event, produce a project with each angle on
its own synced, stacked track.

- **A1 `media_sync_by_audio(workspace_path, source_a, source_b, method, window_seconds)` — SHIPPED (this build).**
  Recovers `{offset_seconds, confidence}` between two recordings by
  cross-correlating low-rate audio energy/onset envelopes (pure NumPy), or via
  FFmpeg's `chromaprint` fingerprint muxer when present. Read-only; writes
  nothing. Files: `edit_mcp/pipelines/audio_sync.py`,
  `edit_mcp/server/bundles/audio_sync.py`. Sign convention: `+offset` ⇒
  `source_b`'s event is that many seconds later than `source_a`'s.
- **A2 `multicam_assemble(workspace_path, project_file, sources[], reference_index=0)` — SPEC (not built here).**
  For each non-reference source, call the A1 estimator against the reference to
  get its offset; `track_add` one video track per angle; `clip_insert` each
  angle at its computed frame offset (leading `gap_insert` for the later ones).
  Returns the per-angle offsets/confidences + `snapshot_id`.
  **Primitives:** A1 (built) + `track_add`, `clip_insert`, `gap_insert` (all
  exist). **Blocker:** the clip-placement fix (§4) — until clips land at the
  requested offset inside the playlist `<entry>`, stacked alignment is wrong.

**Phase A feasibility verdict: BUILDABLE once the placement-fix lands.** The
estimator (the only genuinely new capability) is done and empirically verified
(±≤10 ms on a 3.7 s synthetic offset). A2 is pure orchestration of existing
primitives; it is intentionally deferred to after the placement-fix so it is not
built on a known-broken offset path.

### Phase B — switch-cut tooling

**Goal:** turn a stacked/synced project + a list of `(time, angle)` switch points
into an angle-switching program feed, without the GUI multicam monitor.

- **B1 `multicam_switch(workspace_path, project_file, target_track, cuts[])` — SPEC.**
  `cuts[]` = ordered `(frame, angle_track)` pairs. For each cut, `clip_split`
  the affected tracks at the boundary, then choreograph visibility so the chosen
  angle is the composited/topmost one for that segment (`track_visibility` /
  `composite_set` / track order). Snapshot first; return the cut list + segment
  count.
  **Primitives:** `clip_split`, `track_visibility`, `track_mute`,
  `composite_set`, `transitions_apply_at` — **all exist**. No new low-level
  capability is required; the work is deterministic segment/visibility
  bookkeeping across tracks.

**Phase B feasibility verdict: BUILDABLE, no missing primitives.** Higher
complexity than A2 (multi-track segment accounting, off-by-one at cut
boundaries), so it should follow Phase A and land with a roundtrip test that
re-parses the written `.kdenlive` and asserts the segment/visibility pattern.

### Phase C — full multicam *view*

The live grid monitor and click-to-switch-during-playback is a **Kdenlive GUI
feature that persists nothing to the project file**. There is no MLT structure to
emit and no melt/ffmpeg path to reproduce it headlessly. **Out of scope.** The
MCP equivalent of "using the multicam view" is Phase B's `multicam_switch`
(scripted cuts) — same resulting edit, authored by data instead of clicks.

## 4. Dependency: the clip-placement fix

Phase A2 and Phase B both need clips/gaps to land at exact frame offsets inside
the playlist `<entry>` structure. The known placement/filter-nesting issue is
tracked in `docs/plans/2026-07-03-kdenlive-mcp-improvements.md` (§1.1) and is
called out by sibling guide notes (e.g. *Camera Shake and Drop Shadow*). Until it
lands, `media_sync_by_audio` is still fully useful on its own — it reports the
offsets a human (or a later `multicam_assemble`) applies — but the automated
stacked-placement orchestration is deferred rather than shipped on a broken path.

## 5. What shipped in this pass

- **`media_sync_by_audio`** MCP tool + `audio_sync` pipeline (Phase A1).
  - `method="correlate"` (default): FFmpeg mono PCM decode (8 kHz) → RMS/onset
    envelope (100 Hz) → normalized NumPy cross-correlation with parabolic
    sub-frame peak refinement → `{offset_seconds, confidence}`.
  - `method="chromaprint"`: FFmpeg `chromaprint` muxer fingerprint + raw-item
    bit-agreement correlation **iff** `ffmpeg -muxers` lists `chromaprint`;
    otherwise an actionable error pointing at `libchromaprint` / `correlate`.
    (The local build lacks the muxer, so this path returns the guided error.)
- Empirical proof (ffmpeg-gated integration test, `tests/integration/`): B = A
  delayed by a known 3.7 s with a *different* noise bed → recovered **3.7 s**
  (onset conf 0.998, energy conf 0.974), and **−3.7 s** with the sources
  swapped — well inside the ±50 ms bar.

## 6. Omissions / not done

- **Phase A2 (`multicam_assemble`) and Phase B (`multicam_switch`) not built** —
  specced only; both gated behind the §4 placement-fix and deferred by scope
  (this pass is "research + spec + one additive build").
- **`chromaprint` correlation path is unverifiable locally** (muxer absent); the
  parsing/bit-agreement math is unit-tested on synthetic fingerprints, but the
  end-to-end FFmpeg fingerprint route has no live oracle on this machine.
- **No transcript** for `HSqwLwl6-Qk` (captions absent) — see §0.
