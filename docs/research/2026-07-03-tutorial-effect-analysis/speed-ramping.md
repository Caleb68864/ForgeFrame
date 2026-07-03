---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: Speed Ramping / Time Remapping"
author: analysis agent
tags: [kdenlive-mcp, research, speed, time-remap, timewarp, timeremap, ramp]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript:
  - "vault/Transcripts/Kdenlive Tutorials/How to Apply Speed Ramping in Kdenlive 2025.md"
  - "vault/Transcripts/Kdenlive Tutorials/Slow Motion in Kdenlive - Time Remapping Tutorial.md"
video:
  - "https://www.youtube.com/watch?v=0yr_lMTticU"
  - "https://www.youtube.com/watch?v=o69g-U1OAVI"
channel: EditingBasics / Nuxttux Creative Studio
duration: "1:13 / 9:52"
bundle_tool: speed_ramp
---

# "Speed Ramping / Time Remapping in Kdenlive" → MCP Tool Surface Mapping

Two tutorials drive the same Kdenlive feature — the **Time Remap** panel — from
opposite ends. EditingBasics' short "How to Apply Speed Ramping in Kdenlive 2025?"
(`0yr_lMTticU`, 1:13) is the elevator pitch: right-click a clip → **Time Remap**,
add keyframes where the speed should change, and shape the curve between them (a
steep curve speeds up, a flat/stretched curve slows down). Nuxttux's "Slow Motion
in Kdenlive - Time Remapping Tutorial" (`o69g-U1OAVI`, 9:52) is the deep dive:
frame-rate headroom for slow-mo, the source-time vs output-time keyframe model,
per-segment acceleration/deceleration, and the panel's checkboxes (pitch
compensation, preserve-speed-of-next-keyframe, frame blending).

Analysed against the workshop-video-brain MCP surface
(`edit_mcp/server/tools.py` `clip_speed`/`clip_split`,
`adapters/kdenlive/patcher.py`) and the improvement plan, where **`clip_speed`
was a §1.1 no-op** and is now a working `timewarp:` producer swap (commit
`de0ed27`, verified: 2x halves the rendered duration). Speed *ramping* is the
§3 "working speed control" follow-on and had **zero coverage**.

## a) Technique breakdown (steps, times, exact names)

| Time | Action |
|---|---|
| [0yr 00:00] | Right-click the clip → **Time Remap**. "Create smooth speed transitions using keyframes." |
| [0yr 00:20] | Move the playhead to where the speed change should **begin**, add a keyframe; move forward, add another where speed **returns/shifts**. |
| [0yr 00:30] | **Adjust the curve between keyframes**: a **steep curve speeds up**, a **flat/stretched curve slows down**; drag keyframes closer/farther to fine-tune pacing. |
| [o69 00:00] | Frame-rate headroom: a 30 fps project + 60 fps footage → safe slow-mo down to **50%**; a 24 fps project + 30 fps footage → tiny margin before choppiness. |
| [o69 02:50] | Simple route: right-click → **Change Speed** → e.g. 50% (constant). Could cut the clip and change speed per piece — but Time Remap gives finer control in one panel. |
| [o69 03:20] | Right-click → **Time Remap** opens the panel. Top strip = the source/output timeline; the **lower half** of a keyframe controls stretch/compression, the **upper half** controls the keyframe's source position. |
| [o69 04:00] | Add keyframes with the middle stopwatch; scrub to the point where the change should stop; add another. |
| [o69 04:50] | Drag a lower keyframe **left → compress → accelerate** (output time increases); the clip on the timeline **gets shorter**. Author pushes to **~200%**. |
| [o69 05:50] | Drag a lower keyframe **right → stretch → slow down** (output time decreases), down to **50%** for the running-through-the-hallway shot. |
| [o69 06:50] | Recap: bottom dot = stretch/compress (speed); top dot = the keyframe's original source position. |
| [o69 07:40] | Checkboxes: **pitch compression** (audio matches the speed change), **preserve speed of next keyframe** (change one segment without re-timing the rest), **frame blending** (adds motion blur / smoother slow-mo). |

## b) The remap model (source-time ↔ output-time)

Kdenlive's Time Remap keyframes define a piecewise **map from output-time to
source-time**. The local **playback speed is the slope** `d(source)/d(output)`:

- Compress a segment (keyframe dragged left) → more source per output frame →
  **faster** → shorter on the timeline.
- Stretch a segment (keyframe dragged right) → less source per output frame →
  **slower** → longer on the timeline.

So a ramp's rendered length is the integral `∫ 1/speed d(source)` over the clip —
exactly what the bundle computes and the external oracle asserts.

## c) MLT primitives — what the local build actually supports

Verified on this machine (**melt 7.40.0**, ffmpeg/ffprobe on PATH) via `melt
-query` and real render probes into `/tmp` (see "melt evidence" below):

| Primitive | `melt -query` | Headless render | Serializer-writable here? |
|---|---|---|---|
| **`timewarp` producer** (`speed:resource`) | ✅ producer, speed ∈ [0.01, 20], negative = reverse, `warp_pitch` boolean | ✅ 2x segment renders to half the frames; content timing shifts (out frame 25 ≈ source frame 50) | ✅ **yes** — plain `<producer>`, already used by `clip_speed` |
| **`timeremap` link** (`time_map`/`speed_map`, animated) | ✅ link "Time Remap", v4 | ✅ **loads & processes headless** (no fatal error; a `speed_map=0.5` chain rendered ~200 frames) | ❌ **no** — a link must live inside a `<chain>`; this serializer emits `<producer>` elements only |

**Conclusion:** the *native* time-remap link works in raw melt, but is **not
writable** through the current producer-based serializer without serializer
changes (owned by a concurrent workstream this wave). The **`timewarp` producer
swap is both melt-proven and serializer-compatible**, so the bundle ships that
route: slice the clip at ramp boundaries and play each slice through a
constant-speed `timewarp:{speed}` producer, approximating a smooth ease with many
short sub-segments. `warp_pitch=1` gives the panel's "pitch compression".

### melt evidence (fresh, this task)

- `timewarp` `2:src.mp4` over 100 source frames, entry `in=0 out=49` → **50
  output frames**; a two-segment playlist (`2x` then `0.5x`) rendered **250
  frames / 10.005 s** = the exact integral (50 + 200). Content proof: 2x segment
  output frame 25 matches source frame 50 (mean-RGB diff 16.2) better than source
  frame 25 (26.3).
- Full bundle output (solid clip, ramp 2x→0.5x) rendered by melt to **125 frames
  / 5.013 s** (up from the un-ramped 4.0 s) — the external oracle asserts this
  ±2 frames.
- `timeremap` link (`speed_map=0.5`) inside a hand-written `<chain>` **loaded and
  processed** in melt with no load failure — capability confirmed, but requires
  chain/link serialization we do not emit.

## d) Bundle tool — `speed_ramp`

Slices the clip at ramp boundaries and swaps each slice's producer for a
constant-speed `timewarp:` producer (accelerated parts shorten, slowed parts
lengthen the clip — Kdenlive's Time Remap), ramping the paired audio entry in
lock-step.

```
speed_ramp(
    workspace_path: str,
    project_file: str,          # e.g. projects/working_copies/foo.kdenlive
    track: int,                 # playlist / track index
    clip_index: int,            # real-clip index on that track
    keyframes: str,             # JSON array, two schemas (below)
    easing: str = "cubic",      # cubic | linear | ease_in | ease_out
    pitch_compensation: bool = False,  # keep audio pitch constant (warp_pitch)
) -> dict
```

**Keyframe schemas** (JSON string or list):

- **speed** — `[{"at_seconds": t, "speed": v}, ...]`: at source-time `t` (offset
  within the clip) the playback speed is `v` (`2.0` = 2x faster, `0.5` = slow
  motion). Speed **eases** between keyframes; edges hold the first/last speed.
- **timemap** — `[{"output_seconds": o, "source_seconds": s}, ...]`: at
  output-time `o` show source-time `s`; each consecutive pair is a constant speed
  `(s2-s1)/(o2-o1)` (easing not applied — the map is explicit).

Pipeline: `edit_mcp/pipelines/speed_ramp.py` (pure: `parse_keyframes`,
`keyframe_format`, `ease`, `interp_speed`, `plan_segments`, `timewarp_entry`,
`total_output_frames`, `source_output_frames`). Patcher: a new `SpeedRamp` intent
+ `_apply_speed_ramp` in `adapters/kdenlive/patcher.py` (reuses `_timewarp_resource`
and the rescale logic from `_apply_set_clip_speed`). Registration:
`edit_mcp/server/bundles/speed_ramp.py` (auto-discovered).

Flow:

1. Parse the project, resolve `(track, clip_index)` → the clip entry + its
   source length in frames; read `fps` from the profile.
2. **Pure planning** (`plan_segments`): decode keyframes, detect the schema,
   ease/subdivide → a list of constant-speed `Segment(src_in, src_out, speed)`
   in source-frame offsets covering the clip.
3. **Snapshot** (`before_speed_ramp`), then apply a `SpeedRamp` intent: for each
   segment create (once) a `timewarp:{speed}` producer and a playlist entry whose
   `in/out` are the segment's source range mapped into the warped producer's
   frame space (`round(f/speed)`). The original entry is replaced by the first
   segment; the rest are inserted after it; linked audio is ramped identically;
   the tractor length is re-bounded to the new content length. Serialize.

Returns `{kdenlive_path, track, clip_index, playlist_id, keyframe_format, easing,
pitch_compensation, segment_count, source_frames, expected_output_frames,
expected_output_seconds, original_clip_frames, snapshot_id}`. Error-result
convention throughout (missing project/clip, bad JSON, unrecognised schema,
speed out of [0.01, 20], non-monotonic timemap, snapshot failure).

## e) Honest omissions (implemented subset only)

`speed_ramp` reproduces the **mechanical core** — keyframed acceleration/
deceleration that re-times the clip and its audio, with pitch compensation — but
not the whole panel:

1. **Native `timeremap` link** — the truly continuous curve is *not* emitted; the
   ramp is a **piecewise-constant approximation** (a smooth ease is many short
   segments). The link loads in melt 7.40.0 but needs `<chain>`/`<link>`
   serialization this serializer does not produce. Documented as the alternative
   route; revisit if the serializer gains chain support.
2. **Frame blending / motion blur** — the panel's "frame blending" checkbox
   (motion-blur on slow-mo) is **not** applied. A follow-up could add an MLT
   `avfilter.tblend`/`oldfilm`-style blur or the `frei0r` motion-blur wrapper on
   the slowed segments.
3. **"Preserve speed of next keyframe"** — the tool always plans the whole clip
   from the supplied keyframes; there is no incremental "change one segment,
   hold the rest" edit mode (the caller expresses the full intended curve).
4. **Reverse (negative speed)** — ramps are forward-only (`speed > 0`); reverse
   playback is `effect_rewind`'s domain (`timewarp` supports negative speed, but
   the frame math and UX differ).
5. **Frame-rate headroom warnings** — the tutorial's "don't slow past your fps
   margin or it gets choppy" guidance is **not** enforced; the tool will honour
   any in-range speed. `frame blending` would be the mitigation.
6. **Filter-placement caveat** — not applicable here: this is a producer/entry
   swap, not an effect-stack filter, so it renders in melt (proven), unlike the
   §1.1/§1.2 root-placed `<filter>` issue.

## f) Follow-up primitives that would complete the effect

- **Chain/link serialization** → a native `timeremap` route (continuous curve,
  single producer) once the serializer can emit `<chain><link>`.
- **`frame_blending`/motion-blur** wrapper on slowed segments for cinematic
  slow-mo.
- **fps-headroom advisory** in the tool result (warn when a requested slow-mo
  undershoots the source/timeline fps ratio).
- **Speed-ramp presets** (e.g. "whip in / hold / whip out") layered on the
  keyframe schema, mirroring the effect-stack preset pattern.
