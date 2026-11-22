# Keyframe easing: native operators vs baked keyframes

Prompt 21, 2026-11-22. Code: `edit_mcp/pipelines/easing.py` (`ease`, `bake_keyframes`), the `bake` / `bake_step` arguments of `effect_keyframe_set_scalar/rect/color`, `pipelines/camera_moves.py`.

## Native operators

MLT stores an easing as one character between the keyframe time and `=`: `00:00:00.000g=0;00:00:00.400=1` is cubic-in from the first keyframe to the next (the easing on a keyframe governs the segment that follows it). The full table is in `docs/reference/mlt/keyframe-operators.md`: the Penner families sine, quad, cubic, quart, quint, expo, circ, back, elastic, bounce, each in/out/in-out, plus hold (`|`) and the splines (`~`, `$`, `-`).

## Baking

`bake_keyframes` samples each non-linear segment every `bake_step` frames and writes plain linear keyframes. The original keyframes stay exactly; linear segments get nothing extra; a hold stays flat until the frame before the next keyframe. Use it:

- for curves MLT has no operator for: `cubic_bezier(x1,y1,x2,y2)` (CSS handles), `spring(damping,omega)`, `back_*(amount)`, `elastic_*(amplitude,period)`;
- as a fallback if Kdenlive's keyframe panel does not keep an operator (owner check pending: `21_easing_native.kdenlive` vs `21_easing_baked.kdenlive` in the check pack).

The splines (`smooth*`) span several keyframes and cannot be baked per segment; `bake_keyframes` refuses them. Baked strings are longer: cap 3000 keyframes, raise `bake_step` for long animations.

## The centroid proof

`tests/integration/external/test_camera_moves_render.py::test_baked_cubic_in_matches_mlt_operator` renders a quarter-size red box sliding left to right over 20 frames with a `qtblend` rect, and measures the red pixels' x-centroid at frame 10 (t = 0.5). Measured with melt 7.42: native `g` 69.6 px, baked cubic-in 69.6 px, linear 159.5 px (theory: 70 and 160). So the Penner formulas here are the ones MLT uses. Outside the qtblend rect the frame is black, so the centroid is clean.

## Camera moves

`effect_camera_move` writes a `qtblend` rect (and for `handheld` a `rotation` with `rotate_center=1`), overscanned with 2 px of safety per side so no black edge shows at any keyframe: `zoom_punch` (native easings, peaks at `at_frame`), `orbit` (a circle through the rest position), `handheld` (seeded, baked sine in-out between random targets, first and last keyframe at rest). Rotation keyframes share the rect's timestamps.
