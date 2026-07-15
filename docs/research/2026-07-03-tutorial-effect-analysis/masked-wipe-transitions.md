---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: masked / custom-luma wipe transitions"
author: analysis agent
tags: [kdenlive-mcp, research, transitions, masking, luma-wipe]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_synthesis: docs/research/2026-07-03-tutorial-effect-analysis/SYNTHESIS.md
---

# Masked / Custom-Luma Wipe Transitions → MCP Tool Surface Mapping

Item #4 of the scout's top-5 (tutorials #10 + #11 in
`vault/Research/Kdenlive Tutorial Landscape - Uncovered Effects.md`). Two videos
analysed against the workshop-video-brain MCP surface
(`edit_mcp/server/tools.py`, `pipelines/compositing.py`, `pipelines/masking.py`,
`pipelines/effect_apply.py`). This report scopes the two gaps SYNTHESIS.md calls
out under its consolidated item **#7**: **`composite_wipe` extension** (custom
luma matte, invert, softness — today `apply_wipe` hardcodes
`/usr/share/kdenlive/lumas/HD/luma01.pgm` with no invert/softness) and
**`effect_luma_key`** (does not exist anywhere in the codebase).

Transcripts: `vault/Transcripts/Kdenlive Tutorials/`.

> **Caption availability.** Video #10 (`tHzP9kJQJeg`) has a full auto-caption
> transcript and is analysed frame-by-frame below. Video #11 (`Ih7c65LsLZc`,
> "Transition #2 [Custom wipes]") **has no subtitles of any kind** — `yt-dlp`
> returned "no subtitles" for both manual and auto tracks. Its section is
> reconstructed from the video's stated topic (custom `.pgm` luma-wipe files),
> the scout's landscape notes, and general Kdenlive/MLT domain knowledge, and is
> flagged as such.

## Cross-cutting findings (apply to both videos)

| Capability | MCP status | Notes |
|---|---|---|
| **Luma/wipe transition between two tracks** | **EXISTS (narrow)** | `composite_wipe(track_a, track_b, start, end, wipe_type)` → `apply_wipe`. But `wipe_type` is a 2-value enum (`dissolve`/`wipe`); the `wipe` branch **hardcodes** `resource=/usr/share/kdenlive/lumas/HD/luma01.pgm`. **No custom matte, no built-in-name selection, no invert, no softness.** This is exactly SYNTHESIS #7's "composite_wipe extension". |
| **Custom `.pgm`/`.png` luma matte as wipe resource** | **MISSING** | The MLT `luma` transition's `resource` property accepts any grayscale image path; nothing exposes it. Whole point of video #11. |
| **Built-in MLT/Kdenlive luma pattern selection** | **MISSING** | Kdenlive ships ~20+ HD lumas (`luma01.pgm`…) plus bars/clock/iris patterns; `apply_wipe` can only ever reach `luma01`. |
| **Wipe softness (edge gradient)** | **MISSING** | MLT `luma` transition `softness` property (0..1) blurs the matte threshold into a soft gradient. Not exposed. Named directly in the #10 "soft edges" step and central to `.pgm` gradient wipes (#11). |
| **Wipe invert (reverse matte direction)** | **MISSING** | MLT `luma` `invert` property (0/1) reverses black↔white ordering. Not exposed. Video #10 inverts an alpha mask by hand (`alpha operations → invert`) because there is no matte-invert primitive. |
| **Luma → alpha key (keep bright/dark, feed compositor)** | **MISSING** | No `effect_luma_key`. The FFmpeg `lumakey` filter (`avfilter.lumakey`: threshold/tolerance/softness) turns luminance into transparency — the primitive behind luminance-matte reveals and glow-plate keying. `effect_chroma_key` (color) exists; the luma analogue does not. |
| **Shape-alpha / rotoscope reveal mask** | **PARTIAL** | `mask_set`/`mask_set_shape` exist but emit a **frame-0-only** spline (SYNTHESIS #2). Static shape reveals are expressible; animated ones are not. |
| **Alpha operations (invert / blur edges)** | **PARTIAL** | `mask_set_shape(alpha_operation=…, feather=…)` covers invert + feather on a *shape* mask, but there is no standalone "alpha operations" effect wrapper to drop on an arbitrary clip's stack (video #10 uses it as its own effect). |
| **Object mask (SAM2 auto-select)** | **EXISTS** | `effect_object_mask` / `mask_set` cover the "create object mask → generate → apply" flow video #10 shows at [05:21]. Static only. |
| **Transform / box-blur animation of the revealed layer** | **PARTIAL** | `effect_add("affine")`+`effect_keyframe_set_rect` and `effect_add("avfilter.boxblur")`+`effect_keyframe_set_scalar` express the moves, but keyframe interpolation modes (smooth/cubic-out) and box-blur-into-alpha behaviour are not first-class. |
| **Filter/transition placement renders in Kdenlive** | **KNOWN RISK (plan §1.1/§1.2)** | Effects attach at MLT root, transitions land outside the `<tractor>`, because the serializer never reads `position_hint`. Applies to everything here. Noted, **not a blocker** for shipping the honest subset (per task). |

---

## Video #10 — "Masking & Transition Effects Editing" (tHzP9kJQJeg, 16:44, Nuxttux Creative Studio)

A masked *shape-reveal* transition: freeze one frame of an outgoing shot, cut a
subject (a light / a marble / a rider) out of it with a mask, invert + soften
the matte, then animate that masked cut-out (transform + box-blur) so it wipes /
grows to reveal the incoming shot. **Not** a `.pgm` luma-file wipe — it's an
alpha-matte reveal driven by masks, which is the "masked" half of item #4.

### a) Technique breakdown

1. **[00:00–00:46]** New sequence "transition car"; drop the outgoing clip; find
   the first frame to hold.
2. **[00:46]** Ripple-delete everything before the hold frame; move 1 frame,
   cut; right-click → **Save clip zone to bin** to keep the remainder for later.
3. **[01:32]** Three ways to make a still to extend: (a) monitor right-click →
   **Extract Frame / Extract Frame to Project** (saves a still into the bin);
   (b) the **Freeze** effect (freeze position 0); (c) Ctrl-drag the clip's right
   edge to stretch the last frame. Author uses **Freeze**, ~12 frames.
4. **[03:49]** Delete audio. Step 2: cut out the subject where the transition
   originates. Two masking options: **Rotoscoping** (left-click points,
   right-click to close, alpha op = **Add** to preview, refine) or…
5. **[05:21]** …**Effects → Composition → Create object mask** (SAM2-style):
   click the subject → **Generate mask** → **Apply mask**, which adds the
   **Shape alpha** effect. Shift-click to add, Ctrl-click to exclude regions.
6. **[06:52]** Shape-alpha only shows on frame 0 until you set its **out** back
   to 0 (offset bug). Then it holds for the whole clip.
7. **[06:52–07:37]** Copy the clip to the track above (Ctrl-C / Ctrl-V). On the
   **top** copy add **Alpha operations → Invert** so top = subject-only, bottom =
   hole-only. Use Alpha operations' **blur** to **soften the jagged matte edges**.
8. **[08:23]** Step 3: animate the revealed layer. Add a **Transform**; keyframe
   Y so it slides up from behind the subject; set keyframe interpolation to
   **smooth**.
9. **[09:09]** Add a **Box blur** (not directional — box blur bleeds into the
   alpha); keyframe vertical 51→1, horizontal 5→…, interpolation **cubic out**,
   so motion blur decays as the reveal completes.
10. **[10:42–12:16]** In the intro sequence: place the transition sequence over
    the talking-head; add a **Transform** to the whole sequence and zoom it out
    past canvas (cubic-out) to complete the wipe; add another **Box blur** for
    motion blur.
11. **[12:16–13:46]** Drop the saved zone after the clip for a seamless
    continuation; **speed-ramp** the base clip (change speed / Ctrl-drag / time
    remapping), optionally **frame blending** for natural motion blur.
12. **[14:32–16:44]** Other transitions in the set are the same recipe with
    different masks: reverse clip → **Rotoscope/Shape-alpha** cut-out → **Alpha
    operations** to soften → **Transform** to animate entrance/scale → **Box
    blur** for motion blur, matched on both the outgoing and incoming shots.

### b) Kdenlive features / effects named

Save-zone-to-bin; Extract Frame (/to Project/to Clipboard); **Freeze**;
Ctrl-drag edge-stretch; **Rotoscoping** (alpha op Add, refine, close);
**Create object mask** (generate/apply → **Shape alpha**); Shape-alpha `out`
offset fix; **Alpha operations** (**invert**, **blur/soften edges**);
**Transform** (Y slide, scale-past-canvas, smooth interp); **Box blur** (bleeds
into alpha, cubic-out keyframes); speed change / time remapping / frame
blending.

### c) Capability mapping

| Step | MCP tool | Status | Why |
|---|---|---|---|
| Save clip zone to bin | — | **missing** | no zone-to-bin extractor. |
| Extract frame to project | — | **missing** | no still-grab-to-bin tool (SYNTHESIS #8). |
| Freeze frame hold | — | **missing** | `clip_speed` is a §1.1 no-op; no real freeze/hold. |
| Rotoscope subject cut-out | `mask_set(type="rotoscoping")` | partial | frame-0-only spline; static reveal OK. |
| Object mask (SAM2) → shape alpha | `effect_object_mask` / `mask_set_shape` | exists | static; the [05:21] flow maps directly. |
| Shape-alpha `out`-offset fix | — | n/a | editor-UI quirk; N/A to headless XML. |
| **Alpha operations → invert** | — (approx `mask_set_shape(alpha_operation="invert")`) | **partial/missing** | shape-mask invert exists; no standalone alpha-ops effect, and **no matte-invert on the *transition* itself** → the new **`transition_masked_wipe(invert=True)`** and **`effect_luma_key`** fill this. |
| **Alpha operations → blur/soften edges** | `mask_set_shape(feather=…)` (approx) | **partial** | shape feather ≈ edge soften; the **wipe `softness` param** (new tool) is the transition-level equivalent. |
| Transform slide/scale (smooth/cubic) | `effect_add("affine")` + `effect_keyframe_set_rect` | partial | geometry expressible; interp mode not first-class; §1.1. |
| Box blur into alpha (cubic-out) | `effect_add("avfilter.boxblur")` + `effect_keyframe_set_scalar` | partial | expressible; keyframe easing not first-class; §1.1. |
| Speed ramp / frame blend | `clip_speed` | **broken (§1.1)** | writes bogus `<filter type="speed">`; no-op. |

The masked-reveal recipe is *mostly* expressible from existing mask + transform +
blur primitives; the two genuinely-missing transition primitives it motivates are
**matte invert** and **matte softness**, plus a **luminance→alpha key**
(`effect_luma_key`) as the general-purpose stand-in for "cut out by brightness".

---

## Video #11 — "Kdenlive Tutorial - Transition #2 [Custom wipes]" (Ih7c65LsLZc, ~9:00)

> **No captions available** — reconstructed from the stated topic (custom `.pgm`
> luma-wipe files) + landscape notes + MLT/Kdenlive domain knowledge. Timestamps
> are omitted because there is no transcript to cite.

### a) Technique breakdown (reconstructed)

1. Place two clips on adjacent tracks (or back-to-back on one track) with an
   overlap where the transition happens.
2. Add a **Wipe** transition across the overlap (the MLT `luma` transition).
3. In the transition's properties, instead of a built-in pattern, load a
   **custom luma image** — a grayscale `.pgm` (or `.png`) matte. MLT reads its
   **luminance**: black areas cross over first, white last (a left→right gradient
   `.pgm` gives a smooth directional wipe; a radial gradient gives an iris; a
   textured/patterned matte gives a shaped reveal).
4. **Softness** widens the black↔white threshold into a soft, feathered edge
   rather than a hard line.
5. **Invert** reverses the ordering (white-first) so one matte serves both wipe
   directions.
6. Custom `.pgm` files are made in an image editor (GIMP: grayscale gradient →
   export `.pgm`) and either pointed at directly or dropped into Kdenlive's luma
   folder to appear in the built-in list.

### b) Kdenlive features / effects named (inferred)

**Wipe** transition (MLT `luma`); **custom luma file** (`resource` = `.pgm`/
`.png` path); built-in luma pattern list; **Softness**; **Invert**; grayscale
gradient matte authoring.

### c) Capability mapping

| Step | MCP tool | Status | Why |
|---|---|---|---|
| Wipe transition across overlap | `composite_wipe(wipe_type="wipe")` | partial | works, but resource is hardcoded `luma01.pgm`. |
| **Custom `.pgm`/`.png` matte** | — → **`transition_masked_wipe(luma_file=<path>)`** | **new** | passes the path straight into the `luma` transition `resource`. |
| **Built-in luma by name** | — → **`transition_masked_wipe(luma_file="luma03.pgm")`** | **new** | resolves a bare name under the Kdenlive HD luma dir. |
| **Softness** | — → **`transition_masked_wipe(softness=…)`** | **new** | writes the `softness` property. |
| **Invert** | — → **`transition_masked_wipe(invert=True)`** | **new** | writes the `invert` property. |

Video #11 maps **one-to-one** onto the new `transition_masked_wipe` tool — it is
the direct motivation for every parameter of that tool.

---

## d) New tool specs

### `transition_masked_wipe` (NEW — this build)

```
transition_masked_wipe(
    workspace_path: str,
    project_file: str,
    track_a: int,
    track_b: int,
    start_frame: int,
    duration_frames: int,          # end_frame = start_frame + duration_frames
    luma_file: str,                # built-in name ("luma03.pgm") OR user .pgm/.png path
    invert: bool = False,          # reverse the matte ordering (MLT luma "invert")
    softness: float = 0.0,         # 0..1 edge gradient (MLT luma "softness")
)
```

Writes a `<transition mlt_service="luma">` with `resource` (resolved luma),
`softness`, and `invert` between the two tracks. `luma_file` resolution: a value
containing a path separator, or ending in `.pgm`/`.png` and existing on disk, is
used verbatim (user matte); a bare name is resolved under
`/usr/share/kdenlive/lumas/HD/` (`.pgm` appended if no extension). This is the
concrete implementation of SYNTHESIS #7's "composite_wipe extension".

### `effect_luma_key` (NEW — this build)

```
effect_luma_key(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    threshold: float = 0.0,        # luma below which pixels become transparent
    tolerance: float = 0.01,       # softness of the threshold band
    softness: float = 0.0,         # extra feather on the alpha edge
)
```

Adds the FFmpeg **`avfilter.lumakey`** filter to a clip (luminance → alpha), the
luma analogue of `effect_chroma_key`. This is the `effect_luma_key` primitive
SYNTHESIS #7 flags as non-existent.

---

## Honest omissions (documented in tool docstrings + guide note)

- **§1.1/§1.2 placement (plan `docs/plans/2026-07-03-kdenlive-mcp-improvements.md`).**
  The transition lands outside the `<tractor>` and the filter attaches at MLT
  root because the serializer ignores `position_hint`. Known project-wide issue;
  noted, not a blocker for this build (per task).
- **Static reveals only.** The masked-reveal recipe of video #10 needs animated
  rotoscoping (SYNTHESIS #2, still frame-0-only) for moving subjects; these tools
  supply the *transition/keying* primitives, not the animated matte.
- **`avfilter.lumakey` param prefix.** Params are emitted under MLT's `av.`
  convention (`av.threshold`, `av.tolerance`, `av.softness`), matching how
  `avfilter.eq`/`chromakey` are driven elsewhere; exact option availability can
  vary by MLT/FFmpeg build. `effect_name` is passed through unvalidated (same as
  `effect_add`).
- **No luma-file existence gate for built-in names.** A bare name is resolved to
  the standard HD path but not stat-checked (install paths vary across distros);
  user paths that end in `.pgm`/`.png` are existence-checked and fall through to
  verbatim if absent.
- **No freeze/hold, extract-frame, zone-to-bin, or speed-ramp** — the surrounding
  video-#10 workflow steps remain missing (SYNTHESIS #8); out of scope here.

## Raw summary

- **Video #10 — Masking & Transition Effects** (`tHzP9kJQJeg`): masked *shape-
  reveal* transition (freeze → shape-alpha/rotoscope cut-out → alpha-ops
  invert+soften → transform+box-blur reveal). Motivates **matte invert**, **matte
  softness**, and **`effect_luma_key`**. Existing mask/transform/blur primitives
  cover the reveal statically; §1.1 placement + animated roto + freeze/extract are
  the gaps.
- **Video #11 — Transition #2 [Custom wipes]** (`Ih7c65LsLZc`, **no captions**):
  custom `.pgm` luma-file wipes with softness/invert. Maps one-to-one onto the new
  **`transition_masked_wipe`** tool (custom matte + built-in name + softness +
  invert).
- **New tools built:** `transition_masked_wipe`, `effect_luma_key` (bundle module
  `edit_mcp/server/bundles/masked_wipes.py`; pure functions in
  `edit_mcp/pipelines/masked_wipes.py`).
- **SYNTHESIS #7 closed:** composite_wipe extension (custom luma / invert /
  softness) + `effect_luma_key`, both previously missing.
