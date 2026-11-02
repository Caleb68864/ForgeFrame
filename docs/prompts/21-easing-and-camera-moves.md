# Prompt 21: baked easing presets and named camera moves (zoom punch, orbit, handheld)

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here.

**Summary.** ForgeFrame's keyframe pipeline already writes MLT's *native*
easing operators (sine/quad/cubic/quart/quint/expo/circ/back/elastic/bounce,
in/out/in_out) as one operator character per keyframe. Two things are
missing: (1) a way to **bake** any easing into dense linear keyframes, for
curves MLT has no operator for (CSS-style cubic-bezier, back/elastic with a
custom amount, damped spring) and as a portable fallback if Kdenlive's
keyframe UI mangles an operator; (2) **named camera moves** beyond the
existing Ken Burns (`effect_pan_zoom`) and shake (`effect_camera_shake`): a
zoom punch, an orbit, and a slow handheld drift. Build both on the existing
`qtblend`/keyframe machinery, with numeric unit tests and melt render proofs.

## What exists (read first)

- `edit_mcp/pipelines/keyframes.py`: `Keyframe(frame, value, easing)`,
  `VALID_EASE_FAMILIES`, `_FAMILY_TRIPLES` (family -> MLT operator chars),
  `resolve_easing`, `build_keyframe_string(kind, keyframes, fps)` for
  `scalar`/`rect`/`color`, `parse_keyframe_string`, `merge_keyframes`. The
  easing stored on a keyframe governs the segment **from that keyframe to the
  next** (see `pan_zoom.build_pan_zoom_keyframes`, ~128). Operator table
  source: `docs/reference/mlt/keyframe-operators.md`.
- `edit_mcp/pipelines/shake_shadow.py::camera_shake_keyframes` (~90): the
  model for a camera move: overscan the clip by a zoom factor, keep every
  offset inside the overscan margin (no black edges), first keyframe at rest,
  seeded `random.Random` for determinism, returns `{"rect", "rotation",
  "keyframe_count", ...}` for a `qtblend` filter. Its shell
  `edit_mcp/server/bundles/shake_shadow.py::effect_camera_shake` (~43) builds
  the filter XML and inserts it; copy that shell.
- `edit_mcp/pipelines/pan_zoom.py` + `bundles/pan_zoom.py`: push-in, pull-out,
  pans, Ken Burns (on `affine`). Do not duplicate these.
- `edit_mcp/server/tools/keyframes.py::_keyframe_tool_impl` (~80) backs
  `effect_keyframe_set_scalar/rect/color`.
- `vault/wiki/kdenlive-image-and-qtblend-pattern.md`: qtblend `rect` is
  `x y w h opacity` in canvas pixels, keyframes are **entry-local**, and the
  `rotation` keyframes must use the same timestamps as `rect`.

### Ideas harvested from another project (reimplemented, not copied)

- Easing set: linear, hold, ease-in (t^2), ease-out, ease-in-out
  (smoothstep), cubic in-out, CSS cubic-bezier with four handles (solve
  x(u)=t by bisection, ~20 iterations, then return y(u); default handles
  0.42,0,0.58,1), bounce-out (Penner), elastic-out (`2^(-10t) *
  sin((10t-0.75)*2pi/3) + 1`), overshoot/back-out with amount 1.70158. Their
  writer samples every eased segment at every frame into linear keyframes
  and leaves linear segments alone.
- Zoom punch: rest -> peak scale `1 + intensity` (centred) over
  `attack_frames` (default 3, ease-out), back to rest over `decay_frames`
  (default 10). Default intensity 0.15.
- Orbit: overscan (scale ~1.2), move the oversized frame's origin on a circle
  of `radius_px` (default 60 at 1080p), `revolutions` (default 1), sampled
  ~24 points per revolution, linear between samples.
- Handheld: overscan ~1.08, random offsets (px and degrees) sampled every 8
  frames, eased between samples, first and last sample forced to rest.
  Intensity presets subtle/medium/aggressive = (2 px, 0.4 deg), (6, 1.0),
  (14, 2.2) at 1080p (scale them to the profile width).

## Steps

1. **Easing math** `edit_mcp/pipelines/easing.py` (pure):
   - `ease(name: str, t: float, **params) -> float` for every name
     `resolve_easing` accepts that maps to a family (`ease_in_cubic`,
     `cubic_in_out`, ...) using the standard Penner formulas (MLT implements
     the same set; your unit tests must check the midpoints and endpoints),
     plus `linear`, `hold` (0 until t=1), and extras MLT lacks:
     `cubic_bezier` (params `x1,y1,x2,y2`), `back_out`/`back_in`/`back_in_out`
     with `amount`, `elastic_*` with `amplitude`/`period`, `spring`
     (`1 - exp(-damping*t) * cos(omega*t)`, normalised so `ease(1) == 1`).
     `smooth*` (MLT spline over several keyframes) cannot be baked per
     segment: raise `ValueError` naming it.
   - `bake_keyframes(keyframes, step=1, params=None, max_keyframes=3000) ->
     list[Keyframe]`: for each segment whose easing is not `linear`, insert
     samples every `step` frames with interpolated values (scalars and
     4/5-element rects component-wise; colours: interpolate RGBA if the value
     parser gives you numbers, else raise). All output easings are `linear`;
     original keyframes are kept exactly; raise `ValueError` past
     `max_keyframes`.
2. **Wire baking in**: add `bake: bool = False` and `bake_step: int = 1` to
   `effect_keyframe_set_scalar`, `_rect`, `_color` (pass through
   `_keyframe_tool_impl`; when true, call `bake_keyframes` before
   `build_keyframe_string`). Also accept the extra easing names there only when
   `bake` is true (they have no MLT operator); otherwise return
   `invalid_input` suggesting `bake=True`.
3. **Camera moves** `edit_mcp/pipelines/camera_moves.py` (pure). Each returns
   the same dict shape as `camera_shake_keyframes` (`rect`, `rotation` or
   None, `keyframe_count`, `zoom`) with entry-local frames, rotation
   timestamps identical to rect timestamps, and no black edges:
   - `zoom_punch(width, height, at_frame, fps, intensity=0.15, attack_frames=3,
     decay_frames=10, anchor=(0.5, 0.5), attack_easing="ease_out_cubic",
     decay_easing="ease_in_out_sine")`; the zoom centres on `anchor`
     (fractions of the frame) but the rect is clamped so it always covers the
     frame.
   - `orbit(width, height, start_frame, end_frame, fps, radius_px=None,
     revolutions=1.0, samples_per_rev=24)`; default radius 3% of width; the
     overscan is computed from the radius so the frame stays covered.
   - `handheld(width, height, start_frame, end_frame, fps, intensity="medium",
     frequency_hz=1.5, seed=None, rotation=True)`; eased (baked, sine in-out)
     wander between seeded random targets; deterministic for a given seed.
4. **Tool**: new module `edit_mcp/server/bundles/camera_moves.py` with one
   tool `effect_camera_move(workspace_path, project_file, track, clip_index,
   move, start_frame=0, end_frame=-1, at_frame=-1, intensity=None,
   radius_px=None, revolutions=1.0, seed=None, rotation=True)`. `move` is one
   of `zoom_punch|orbit|handheld` (`invalid_input` listing them otherwise);
   `end_frame=-1` means end of clip; `zoom_punch` requires `at_frame`.
   Shell order exactly as `effect_camera_shake`: parse (`ProjectParseError`
   -> `corrupt_project`) -> validate -> snapshot -> insert a `qtblend` filter
   (build it with the same `_build_filter_xml(mlt_service=..., kdenlive_id=
   "qtblend", track=..., clip=..., props=[...])` call the shake bundle uses
   at ~151, appended at `len(patcher.list_effects(...))`) -> serialize ->
   `_ok` with `snapshot_id`,
   `keyframe_count`, the keyframe strings.

## Tests

1. **Unit** `tests/unit/test_easing.py`, `tests/unit/test_camera_moves.py`:
   endpoints `ease(0)=0`, `ease(1)=1` for every name; known midpoints
   (`ease_in_cubic(0.5)=0.125`, `ease_out_cubic(0.5)=0.875`, ...);
   cubic-bezier(0,0,1,1) is linear; bake keeps original keyframes and makes
   every easing linear; bake refuses `smooth`; camera moves: rect always
   covers `[0,0,W,H]` at every keyframe, first keyframe at rest, punch peak
   at `at_frame`, same seed gives identical strings, different seeds differ;
   tool registered and validates `move`.
2. **External render proofs** `tests/integration/external/test_camera_moves_render.py`
   (pattern: `test_pan_zoom_render.py`):
   - Baked vs native vs linear (hermetic colour builders): a red clip
     scaled to a 25% box moving left to right over 20 frames on the black
     background. Write a small helper that returns the x-centroid of red
     pixels in a rendered PNG (PIL). At frame 10: `ease_in_cubic` baked and
     the native `g` operator agree within 2 px, and both are well left of
     the linear render. This proves the baked maths matches MLT's. First
     confirm with one render that the area outside the qtblend rect is
     black; if it is not, say so in the report and use `affine` instead.
   - Coverage: on a solid green clip, every move keeps all four corner
     pixels green at 5 sampled frames (no black edges).
   - Motion: on `make_test_clip(kind="video")` (`requires_ffmpeg`), the
     zoom-punch peak frame differs from the same frame without the effect,
     and a frame after the decay is similar to it; orbit frames at 1/4 and
     3/4 revolution differ from each other.

## Acceptance criteria

- `bake=True` works on the three keyframe tools; native output unchanged
  when `bake=False` (existing keyframe tests still pass untouched).
- `effect_camera_move` produces the three moves with no black edges in melt.
- Full suite green; ruff clean.

## Do NOT

- Do not change `build_keyframe_string`, the operator table, or the default
  behaviour of any existing tool.
- Do not re-implement push/pull/pan (use `effect_pan_zoom`) or shake.
- Do not use absolute sequence frames in keyframes; they are entry-local.

## When done

1. Human check list item for the report: open one project with a native
   `ease_in_cubic` keyframe and one with the baked version in Kdenlive 26.08
   and note whether the keyframe panel shows/keeps the native operator. You
   cannot do this headless; write the two `.kdenlive` files to
   `kdenlive-check-pack/21_easing_native.kdenlive` / `21_easing_baked.kdenlive`
   and list them in the report for the human.
2. Add the moves and `bake` to `workshop-video-brain/skills/ff-effect-cookbook/SKILL.md`;
   add `vault/wiki/kdenlive-keyframe-easing-baking.md` (operator vs baked,
   when to bake, the centroid proof).
3. Regenerate `docs/capabilities.md`; mark Phase 4 item 6 done in
   `docs/plans/2026-10-13-media-mcp-expansion.md`.
4. Report as in `00-README.md`, with the centroid numbers.
