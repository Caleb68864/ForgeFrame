# Tutorial Effect Analysis — Zoom / Whip-Pan Transition

Date: 2026-07-03
Source transcript: Nuxttux Creative Studio — "Zoom Transition - Kdenlive Tutorial"
(https://www.youtube.com/watch?v=ex7GoLFOnio), landscape row #16.
Transcript: `vault/Transcripts/Kdenlive Tutorials/Zoom Transition - Kdenlive Tutorial.md`
Scope: map taught techniques → workshop-video-brain MCP tool surface; ship one
end-to-end bundle tool for the transition.

Context notes:
- Tool-surface files inspected: `edit_mcp/server/tools.py` (keyframe +
  effect_add tools), `edit_mcp/pipelines/keyframes.py` (operator table,
  `build_keyframe_string`), `edit_mcp/pipelines/effect_apply.py`,
  `edit_mcp/server/bundles/` (auto-import package), `adapters/kdenlive/patcher.py`
  (`list_effects`, `insert_effect_xml`, `get/set_effect_property`,
  `_iter_clip_filters`).
- **§1.1 caveat** (docs/plans/2026-07-03-kdenlive-mcp-improvements.md): effect
  filters are placed at the **MLT root** carrying `track=`/`clip_index=` attrs
  rather than nested inside the playlist `<entry>`. The same-project patcher
  round-trips them via those attrs (`_iter_clip_filters` matches on them), so the
  tool is internally consistent, but whether melt/Kdenlive associate a
  root-level filter with the clip is the open §1.1 question. Not a blocker for
  shipping the tool as an honest subset.

Catalog reality check:
- `avfilter.dblur` (Directional Blur) — **in catalog** (kdenlive_id
  `avfilter_dblur`; keyframable `av.angle` default 45, `av.radius` default 5,
  list `av.planes`). Used here for the motion-blur streak across the cut.
- **Transform** — **NOT a first-class catalog entry**. Emitted as
  `mlt_service="affine"` + kdenlive_id `transform` + `rect` property, matching
  the existing `keyframe_project.kdenlive` fixture and the `effect_find`
  "transform" test. The exact affine-vs-qtblend service/property mapping is an
  honest-subset assumption (§1.1), not verified against a melt render.
- Easing operators — `docs/reference/mlt/keyframe-operators.md`, exposed via
  `keyframes.build_keyframe_string` / `resolve_easing`. `cubic_in`→`g`,
  `cubic_out`→`h`, `expo_in`→`p`, `expo_out`→`q`, linear→`` (empty).

---

## Video — Zoom / Whip-Pan Transition

### a) Step-by-step technique breakdown

The tutorial actually teaches **two** transitions. Both are punch-in +
directional-treatment cuts; the shipped tool distills the common shape.

**Zoom-out transition (00:45 – 12:25)**
1. **[00:45]** Zone two ~2 s clips into the bin, drop on adjacent tracks.
2. **[01:32]** On clip 1 build an effect stack: **Box blur** (set to 0) →
   **Transform** → a lattice of **Transform + Mirror** pairs to tile a 3×3 grid
   (the "infinite zoom-out" look).
3. **[03:52]** A final **Transform** keeps keyframes: scale 300% → 100% over the
   last 8 frames; keyframes default to **smooth**, switchable to linear.
4. **[04:37]** **Box blur** keyframed 0 → ~7% at the tail so the cut streaks.
5. **[05:25]** Cut 4 frames earlier (`Shift+R`), copy the tail to the track
   above, re-key a Transform (100 → 33%) + box blur on the copy — the two-layer
   push.
6. **[06:14]** Save the stack as a **custom effect stack** ("zoom out") and a
   **preset** ("zoom out clean plate") for reuse; double-click to apply to the
   next clip.
7. **[08:31]** At the **head** of the next clip add a zoom-**in**: Transform
   scale-up + **Lens correction (keyframeable)** center/edge correction over the
   first 6 frames.
8. **[10:44]** `Create Sequence from Selection` to nest ("Runner 1/2").
9. **[11:40]** Add **Lens distortion (keyframeable)** to the nested sequences,
   keyframed hard at the last 8 frames for the barrel-warp punctuation.
10. **[12:25]** Color grade (levels, saturation, vignette, blue LUT) via effect
    zone — out of scope.

**Whip-pan transition (12:40 – 16:40)**
11. **[13:13]** Zone two motion clips, speed them up (Ctrl-drag edge).
12. **[13:20]** Transform the second to match aspect (~110% + slide).
13. **[14:01]** **Mix clips** (checkerboard button) → set Luma to **Push /
    Push-left**; nudge 4 frames each side; keyframe the push value to **1000**;
    first keyframe **smooth** for an accelerated start.
14. **[15:35]** `Create Sequence from Selection` ("whip"); add a **Box blur**
    keyframed 0 → peak → 0 across the center of the transition (middle keyframe
    **linear**, extra blur) for the whip streak.

### b) Kdenlive features / effects used (exact names)

Zone in/out → bin · adjacent-track layout · **Box blur** (keyframed) ·
**Transform** (scale + align, keyframes smooth/linear/distort) · **Mirror**
(horizontal/vertical, for the tile grid) · **custom effect stack** + **preset**
save/apply · **Lens correction (keyframeable)** · **Create Sequence from
Selection** (nesting) · **Lens distortion (keyframeable)** · **Mix clips** Luma
= **Push / Push-left** (keyframed to 1000) · smooth vs linear keyframe default ·
color grade via **effect zone** (out of scope).

### c) Capability mapping

| # | Step | MCP tool(s) | Status | Notes |
|---|------|-------------|--------|-------|
| 1 | Zone clips to bin, adjacent tracks | `markers_*`, `clip_insert`, `track_add` | partial | placement is playlist-index, not zone-to-bin |
| 2 | Box blur + Transform + Mirror stack | `effect_add("box_blur"/"affine"/"mirror")` | partial | addable; §1.1 placement; no Mirror wrapper |
| 2 | 3×3 mirror-tile grid | — | **missing** | no lattice/tile helper; hand-built stack |
| 3 | Transform scale keyframes | `effect_add("affine")` + `effect_keyframe_set_rect` | partial | transform not in catalog; §1.1; easing operators exist |
| 4 | Box blur keyframes | `effect_add("box_blur")` + `effect_keyframe_set_scalar` | partial | §1.1 placement |
| 5 | Frame cut + copy to layer + re-key | `clip_split`, `effects_copy/paste`, keyframe tools | partial | cross-track copy; §1.1 |
| 6 | Save custom stack / preset, apply | `effect_stack_preset`, `effect_stack_apply`, `effect_stack_promote` | exists | two-tier stack storage already shipped |
| 7 | Zoom-in + Lens correction at head | `effect_add("...")` + rect/scalar keyframes | partial | lens-correction not wrapped; §1.1 |
| 8 | Create Sequence from Selection | — | **missing** | nesting unsupported (parser single-tractor) |
| 9 | Lens distortion keyframes | `effect_add("frei0r.lenscorrection"?)` + keyframes | partial | not wrapped; §1.1 |
| 11 | Speed-up clips | `clip_speed` | **broken** | §1.1 no-op filter |
| 13 | Mix clips → Push/Push-left | `transitions_apply_between` | **broken** | §1.1 invalid transition XML; no same-track "mix"/Luma push |
| 13 | Keyframe push value to 1000 | `effect_keyframe_set_scalar` | partial | needs a real transition to key |
| 14 | Nest + center box-blur whip streak | `effect_add("box_blur")` + `effect_keyframe_set_scalar` | partial | §1.1; nesting missing |

### d) Bundle tool spec — `transition_zoom_whip` (SHIPPED)

Distills the common shape of both taught transitions — a **keyframed scale
punch + directional blur across the cut** — into one composable tool over two
adjacent clips on a single track.

```
transition_zoom_whip(
    workspace_path: str,          # prepended vs. the brief's bare signature:
                                  #   required for _require_workspace + snapshot
    project_file: str,
    track: int,
    out_clip_index: int,          # outgoing clip (punches + whips off)
    in_clip_index: int,           # incoming clip (mirrors the move back)
    direction: str = "left",      # "left" | "right" | "up" | "down"
    duration_frames: int = 12,    # length of each half of the transition
    zoom_amount: float = 1.4,     # peak scale multiplier at the cut
    blur: float = 6.0,            # peak avfilter.dblur radius at the cut
    easing: str = "cubic",        # ease family (cubic → in/out) or linear/smooth
    pan_fraction: float = 0.75,   # head-room fraction used for the whip pan
)
```

What it composes, in order (all keyframe strings built by
`keyframes.build_keyframe_string`, filters placed via
`patcher.insert_effect_xml` with baked-in keyframe properties):
1. **Outgoing clip** — `affine`/Transform: `rect` ramps full-frame →
   `zoom_amount` + pan toward `direction` over the clip's last
   `duration_frames`, easing `cubic_in` (accelerate into the cut).
2. **Outgoing clip** — `avfilter.dblur`: `av.radius` ramps `0 → blur`
   (`cubic_in`); `av.angle` = 0 for left/right, 90 for up/down.
3. **Incoming clip** — Transform: `rect` ramps `zoom_amount` + pan from the
   **opposite** side → full-frame over the first `duration_frames`, easing
   `cubic_out` (decelerate out of the cut).
4. **Incoming clip** — dblur: `av.radius` ramps `blur → 0` (`cubic_out`), same
   angle.

Pure planning logic lives in `edit_mcp/pipelines/zoom_whip.py`
(`build_zoom_whip_plan`, fully unit-tested across fps / direction / easing).
The bundle wrapper `edit_mcp/server/bundles/zoom_whip.py` handles parse →
snapshot → insert → serialize and returns effect indices + written keyframe
strings + snapshot id.

**Honest-subset omissions (not attempted by the tool):**
- The 3×3 **Mirror-tile grid** "infinite zoom" — no tiling helper.
- The **Push/Push-left Luma "Mix clips"** same-track transition — the tool uses
  a transform+blur push instead (`transitions_apply_*` is §1.1-broken).
- **Lens correction / Lens distortion** punctuation keyframes — not wrapped.
- **Create Sequence from Selection** nesting — parser is single-tractor (§3 low).
- **Speed-up** of the source clips — `clip_speed` is a §1.1 no-op.
- **Custom effect-stack / preset save** of the result (already covered by the
  shipped `effect_stack_*` tools; not re-implemented here).
- Verified affine-vs-qtblend Transform service mapping (§1.1 assumption).

---

## Raw data summary

- **effect_name:** `transition_zoom_whip` (SHIPPED — first `bundles/` module)
- **files:**
  - pipeline (pure): `edit_mcp/pipelines/zoom_whip.py`
  - bundle (MCP): `edit_mcp/server/bundles/zoom_whip.py`
- **tool signature:** `transition_zoom_whip(workspace_path, project_file, track,
  out_clip_index, in_clip_index, direction="left", duration_frames=12,
  zoom_amount=1.4, blur=6.0, easing="cubic", pan_fraction=0.75)`
  (`workspace_path` prepended vs. the brief for snapshot/workspace resolution).
- **effects emitted per clip:** `affine` (Transform, `rect` keyframes) +
  `avfilter.dblur` (`av.angle` const, `av.radius` keyframes).
- **omissions:** mirror-tile grid; Push/Push-left Luma mix; lens
  correction/distortion; sequence-from-selection nesting; clip speed-up;
  transform service mapping unverified (§1.1).
- **§1.1-broken deps avoided:** `transitions_apply_between` (invalid XML),
  `clip_speed` (no-op). The tool depends only on `affine`+`dblur` filter
  insertion via the patcher, keyed inline.
```
