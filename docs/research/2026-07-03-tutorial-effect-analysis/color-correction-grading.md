---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: color correction & grading"
author: analysis agent
tags: [kdenlive-mcp, research, color, grading, correction]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/Color Correction & Grading - Kdenlive Effects Tutorial.md"
---

# Color-Correction & Grading Tutorial → MCP Tool Surface Mapping

One Nuxttux Creative Studio tutorial analysed against the workshop-video-brain
MCP surface (`edit_mcp/server/tools.py`, `pipelines/color_tools.py`,
`pipelines/effect_apply.py`, `pipelines/effect_catalog.py`,
`pipelines/effect_presets.py`, `pipelines/effect_wrappers/`).

- **Video**: "Color Correction & Grading - Kdenlive Effects Tutorial"
  (`JTWRb8IEUl0`, Nuxttux Creative Studio, 6:38).
- **New bundle tool built from this analysis**: `effect_color_grade`
  (pipeline `pipelines/color_grade.py`, tool appended to `server/tools.py`).

## What the tutorial actually is

This is a **quick overview of three downloadable custom effect templates** the
presenter (Jonathan) uploaded to Kdenlive's online effect-template repository,
not a from-primitives build. At **[00:03]–[00:50]** he shows *Effects → download
arrow → search "LM" → install* three stacks: `LM basic CC` (correction),
`LM creative cg2` (grade), and `LM secondary hsl` (masked secondary). They land
under the star/pencil "Templates" tab after a restart.

Because those are opaque, redistributed template blobs, we cannot reproduce them
one-for-one. The value for the MCP surface is the **named underlying Kdenlive
effects** the presenter walks through inside each stack — those *are* catalog
services we can chain. The bundle tool distils the correction+grade path into a
single call; the masked `LM secondary hsl` workflow is out of scope (it is a
masking pipeline, not correction+grade).

## Cross-cutting findings

| Capability | MCP status | Notes |
|---|---|---|
| **Lift/Gamma/Gain wheels** | **EXISTS** (catalog: `lumaliftgaingamma`) | The SYNTHESIS note and the sibling `compositing-effects.md` both claim `lift_gamma_gain` is **not** in the catalog. That is **incorrect for this catalog build**: `lumaliftgaingamma` (kdenlive_id `lumaliftgaingamma`, params `lift`/`gamma`/`gain`, each −500..500 / −1000..1000, 0 = neutral) is present. `effect_color_grade` uses it directly — no substitution needed. (The string `lift_gamma_gain` used elsewhere is a *different*, unvalidated pass-through name.) |
| **White balance / temperature** | **EXISTS** | `avfilter.colortemperature` (`av.temperature` 1000–40000 K, `av.mix`, `av.saturation`) and `movit.white_balance` (`neutral_color`, `color_temperature`). Tutorial's "white balance … temperature … or grab the Color Picker on a neutral gray" maps to either; the bundle uses `avfilter.colortemperature` (numeric, no colour-picker needed). |
| **Exposure / dark point / shadows** | **EXISTS** | `avfilter.exposure` (`av.exposure` −3..3 stops, `av.black` −1..1). Covers "control the brightness, the dark points, the Shadows". |
| **Video equalizer (sat/exposure/contrast/level in one)** | **EXISTS** | `avfilter.eq` (`av.contrast` −3..3, `av.brightness` −1..1, `av.saturation` 0..5, `av.gamma` 0..3). The presenter explicitly calls this "the equivalent of saturation, exposure, contrast and level all in one" **[03:30]**. |
| **Levels** | **EXISTS** | `avfilter.colorlevels` (per-channel in/out min/max). Not wired into the bundle (eq+exposure cover the same ground more legibly); available via generic `effect_add`. |
| **Saturation** | **EXISTS** | `frei0r.saturat0r` (single `Saturation` param) **and** `avfilter.eq`'s `av.saturation`. Bundle uses eq's saturation (clean 0..5, 1 = neutral) to avoid frei0r's normalised scale. |
| **Color balance (shadows/mids/highlights)** | **EXISTS but omitted** | `avfilter.colorbalance` (9 RGB scalars `av.rs/gs/bs/rm/gm/bm/rh/gh/bh`) and `frei0r.three_point_balance` (three COLOR pickers). Named at **[03:30]** ("add certain colors in the Shadows, midtones or highlights"). Omitted from the bundle: a 9-scalar or 3-colour surface is too large for a one-call tool; creative colour is offered instead via lift/gamma/gain + tint. Available via `effect_add`. |
| **Curves** | **EXISTS but omitted** | `avfilter.curves` is a pass-through name (not in this catalog dump; `hslrange`/`hslprimaries` are the nearest catalog HSL tools). Used at **[03:56]** to knock down a peaking red. Omitted: curves need spline-point strings, not scalars — no honest scalar mapping. |
| **Tint** | **EXISTS** | `frei0r.tint0r` (`Map black to`, `Map white to` COLOR, `Tint amount` 0..1000). Matches **[04:00]** ("the tint … black and green, value 250 … I dropped it to 0 so it doesn't influence the image"). Bundle exposes it as an *optional* stage (off at `tint_amount=0`). `tcolor` (Technicolor, `oversaturate_cr/cb`) is a cruder alternative. |
| **LUT** | **EXISTS** | `avfilter.lut3d` (`av.file`) — same path `color_apply_lut` uses. The presenter applies a LUT at the bottom of both `LM creative` and `LM secondary hsl` **[04:30]**. Bundle exposes an optional `lut_path`. |
| **Film grain / noise / sharpen** | **EXISTS** | `frei0r.filmgrain`, `avfilter.noise`, `frei0r.sharpness` — mentioned as optional add-ons **[04:00]**. Available via `effect_add`/wrappers; not core to correction+grade so not bundled. |
| **SOP/Sat (slope/offset/power)** | **MISSING** | Presenter's "SOP saturation … slope = highlights, offset = midtones, power = shadows" **[04:30]** has no direct catalog service (no `sop`/`sopsat` hit). Lift/gamma/gain is the closest tonal-wheel substitute and is what the bundle ships. |
| **Videoscopes (vectorscope / waveform / RGB parade)** | **EXISTS (monitors, not effects)** | `avfilter.vectorscope`, `avfilter.waveform`, `frei0r.rgbparade`, `frei0r.vectorscope` are catalog *services* but scopes are Kdenlive monitor panels, not clip filters — the MCP surface has no monitor-readout capability, so the "use the vectorscope to gauge your correction" guidance **[02:00]** is advisory only. |
| **Secondary HSL colour selection + mask** | **PARTIAL / out of scope** | `LM secondary hsl` **[05:00–06:14]** grabs a colour, shows the selection with "mask apply" off, then affects only the selection with lift/gamma/gain, plus Gaussian blur (`avfilter.gblur`/`frei0r.IIRblur`) and transparency (`frei0r.transparency`). This is the masking pipeline (`mask_set`/`mask_apply`), not correction+grade — excluded from the bundle. |
| **Effect placement renders in Kdenlive** | **KNOWN ISSUE (plan §1.1/§1.2)** | `effect_add`/`apply_effect` attach filters at the MLT root with custom `track=`/`clip_index=` attrs rather than nested in the playlist `<entry>`; the serializer never reads `position_hint`. `effect_color_grade` inherits this (it chains `apply_effect`), exactly as `effect_glitch_stack` does. **Not a blocker for this build** — the XML is written and round-trips through the parser/tests — but the filters may not render in Kdenlive until the §1.1 fix lands. Flagged, not fixed (per task scope). |

## Workflow breakdown (correction vs grade)

### Correction — `LM basic CC` [01:38–03:09]

Applied to the clip (presenter prefers applying correction on the project-bin
clip, grade on the timeline). Top-to-bottom order (he notes order is flexible):

1. **[02:00] White balance / temperature** — neutral-gray colour-picker or manual.
   → `avfilter.colortemperature` (`av.temperature`, default 6500 K = neutral).
2. **[02:24] Saturation** — → `avfilter.eq av.saturation` (bundle) / `frei0r.saturat0r`.
3. **[02:24] Brightness / dark points / shadows** — "get to a good baseline".
   → `avfilter.exposure` (`av.exposure`, `av.black`) + `avfilter.eq` (contrast/brightness).

### Grade — `LM creative cg2` [03:09–04:42]

1. **[03:30] Color balance** (under Levels) — shadows/mids/highlights colour.
   → `avfilter.colorbalance` / `frei0r.three_point_balance`. *(omitted, see table)*
2. **[03:30] Video equalizer** — sat/exposure/contrast/level in one.
   → `avfilter.eq`.
3. **[03:56] Curves** — target a peaking red, pull it down.
   → `avfilter.curves`. *(omitted, spline strings only)*
4. **[04:00] Lift Gain Gamma** — "color grade your footage".
   → **`lumaliftgaingamma`** (`lift`/`gamma`/`gain`).
5. **[04:00] Tint** — set to B&W/amount 0 by default so it's a no-op until dialled in.
   → `frei0r.tint0r` (optional).
6. **[04:00] Film grain / noise / sharpen** — optional flavour. → various.
7. **[04:30] SOP saturation** — slope=highlights, offset=mids, power=shadows.
   → **MISSING** (substituted by lift/gamma/gain).
8. **[04:30] LUT** — creative look at the bottom of the stack.
   → `avfilter.lut3d` (optional `lut_path`).

### Secondary — `LM secondary hsl` [04:42–06:14] *(out of scope)*

Masked secondary colour selection → lift/gamma/gain on the selection → Gaussian
blur → transparency. Belongs to the masking surface, not this bundle.

## `effect_color_grade` — design

One MCP call inserts an ordered correction→grade chain under a single snapshot.
Every stage is optional; a stage is emitted **only** when its params depart from
neutral, so the chain never carries a no-op filter. At least one non-neutral
param is required (else an error). Chain order:

`avfilter.colortemperature` → `avfilter.exposure` → `avfilter.eq` →
`lumaliftgaingamma` → `frei0r.tint0r` (opt) → `avfilter.lut3d` (opt).

Signature:

```
effect_color_grade(workspace_path, project_file, track, clip,
    temperature=6500.0, exposure=0.0, black_level=0.0,
    contrast=1.0, brightness=0.0, saturation=1.0,
    lift=0.0, gamma=0.0, gain=0.0,
    tint_amount=0.0, tint_shadows="0x000000ff",
    tint_highlights="0x00ff00ff", lut_path="") -> dict
```

Returns `{first_effect_index, filter_count, services[], snapshot_id}`.

## Omissions (with reasons)

- **Color balance** (`avfilter.colorbalance`) — 9 RGB scalars; too large a
  surface for a one-call bundle. Use `effect_add` for fine shadow/mid/high tints.
- **Curves** (`avfilter.curves`) — requires spline-point strings, no honest
  scalar mapping. Use `effect_add` with a hand-built points property.
- **SOP/Sat** — no catalog service exists; substituted by `lumaliftgaingamma`.
- **Videoscope readouts** — scopes are monitor panels; no MCP monitor capability.
- **Secondary HSL masking** — separate masking pipeline, out of correction+grade
  scope.
- **§1.1/§1.2 filter placement** — inherited root-placement issue; filters may
  not render in Kdenlive until the placement fix lands. Flagged, not fixed.
