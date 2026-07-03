---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: paper cutout transition"
author: analysis agent
tags: [kdenlive-mcp, research, transition, masking, rotoscoping, compositing]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/Kdenlive - Paper Cutout Transition Tutorial.md"
---

# Paper Cutout Transition (Mint Visual) → MCP Tool Surface Mapping

One Mint Visual tutorial (`Fh1xhOzfjBE`, 6:07) analysed against the
workshop-video-brain MCP surface (`edit_mcp/server/tools.py`,
`pipelines/compositing.py`, `pipelines/masking.py`, `pipelines/paper_cutout.py`,
`pipelines/effect_catalog.py`). This is the first analysis of a video *outside*
the Nuxttux playlist and the first for which a bundle tool
(`transition_paper_cutout`) was actually **built**, not just proposed.

## What the effect is

A stylised scene-to-scene transition that looks like the outgoing subject is
**torn out of the frame as pieces of crumpled paper**, revealing the next clip.
It is *not* a luma/matte wipe and uses **no torn-paper matte image driving a
wipe**. The mechanism is a hand-masked, stepped **rotoscope reveal**: a frozen
still of the incoming shot is cut into a few short pieces, each rotoscoped to a
slightly different torn outline, and dressed with a screen-blended paper texture
and a distorted, drop-shadowed white edge so each step reads as a paper cutout.

## Technique breakdown (exact names, values, timestamps)

1. **[00:00] Base cut.** Two clips. Move the playhead into clip B at the chosen
   transition frame, `Shift+R` (razor) to cut, delete the first portion of B and
   slide the remainder back so A and B butt together.
2. **[00:20] Freeze still.** Right-click the viewer at the head of clip B →
   **Extract Frame to Project** → save; the still lands in the project bin. Drag
   it onto **video track 2**.
3. **[00:30] Stepped stills.** The transition is "three images, each a few
   frames" — here **4 frames each** (frame-rate dependent). From the head of the
   still clip: +4 → cut, +4 → cut, +4 → cut the rest. `Shift`-select the three
   stills and slide them back so the **end of the last still aligns with the head
   of clip B**.
4. **[00:46] Rotoscope the last still.** Effects → **Rotoscoping** → apply.
   In the viewer left-click to drop spline points around the subject (rough is
   fine — "you're making a paper effect"), right-click to close. If the mask is
   offset (a known Kdenlive bug) drag the red centre cross to re-seat it.
   **[01:31] Feather width = 2, Feathering passes = 2.**
5. **[01:31] Propagate + carve upward.** Select last still → `Ctrl+C` → right-
   click previous still → **Paste Effects**. On each earlier still, **double-
   click to remove upper mask points** (and add points on the line) so it looks
   like the upper part is progressively torn away. Repeat for still 1. (The
   author recommends a custom shortcut for paste-effects.)
6. **[02:16] Clean the last still.** Its edge still shows clip-B background, so
   add **another mask with Alpha operation = Subtract** to knock it out.
7. **[02:35] Paper texture (VT3).** Download a "folded dark paper texture",
   import. Right-click VT2 → **Insert Track** (→ VT3). Drag the texture onto VT3,
   align to the three stills, then cut it into **three pieces matching the still
   lengths**.
8. **[03:02] Mask the texture** the same way — copy each still's mask, **Paste
   Effects** onto the texture piece above it.
9. **[03:15] Texture motion.** `Shift`-select the three texture pieces →
   **Transform** effect → drag on. On each, **move Transform ABOVE Rotoscoping**
   (so it is applied first) and adjust position / scale / rotation; playhead at
   the head of each clip.
10. **[03:48] Screen composite.** Compositions → **Composite and Transform** →
    apply to the masked texture clips; trim the composition to clip length; set
    **Compositing = Screen**. Optional: on the VT2 stills add **Contrast** and
    tweak.
11. **[04:34] White paper edge (VT1).** Right-click VT1 → Insert Track. Project
    bin → **Add Color Clip = white**. Drag to the new track, trim, cut into three
    matching pieces. Copy each still's mask → **Paste Effects** onto the color
    piece below.
12. **[05:00] Edge shaping.** `Shift`-select the color pieces → **Transform**
    (enable the "adjust for multiple clips" toggle) → **increase Scale slightly**
    and nudge position, so the white sits just proud of the subject → the rim.
    **[05:20] Distort** effect → tune **Amplitude / Frequency** to roughen the
    rim. **[05:20] Drop Shadow** → **color = black, X/Y offset ≈ 4, raise Blur
    radius.**
13. **[05:50] Done.** Optionally add paper-crumble SFX.

## Effect → MLT service map

| Tutorial step | Kdenlive effect | MLT service | MCP status |
|---|---|---|---|
| Rotoscope subject (feather 2/2) | Rotoscoping | `rotoscoping` | **EXISTS** — `mask_set` / `mask_set_shape` / `paper_cutout` pipeline. Static single-frame spline only (`masking._spline_json` emits frame 0). Fine here: each still's mask is static; only the *set* of masks changes per step. |
| Subtract cleanup mask | Rotoscoping (Alpha op = sub) | `rotoscoping` | **EXISTS** — `alpha_operation="sub"`. |
| Texture / edge Transform | Transform | `affine` (kdenlive_id `transform`) | **PARTIAL** — no first-class `effect_transform`; `paper_cutout` writes a static centred `rect` for uniform scale (the rim trick). Position/rotation and keyframing not exposed. |
| Screen paper composite | Composite and Transform | `frei0r.cairoblend` (`1=screen`) | **EXISTS** — `composite_set(blend_mode="screen")`, but §1.2 relocates the transition to the tractor/root (placement bug). Left OUT of the bundle tool; documented as a compose-with step. |
| Edge roughen | Distort | `frei0r.distort0r` (`0`=Amplitude, `1`=Frequency) | **EXISTS** — in catalog; `paper_cutout` emits it. |
| Paper lift | Drop Shadow | `dropshadow` (`radius`,`x`,`y`,`color`) | **EXISTS** — in catalog; `paper_cutout` emits it. |
| Optional look | Contrast | `avfilter.eq` / `frei0r.contrast0r` | EXISTS via `effect_add`; not in bundle (optional). |
| Extract Frame to Project | — | (host action) | **MISSING** — no extract-frame-to-bin tool (SYNTHESIS gap #8). |
| Insert Track | Insert track | (project op) | **MISSING** as a first-class MCP op in this flow. |
| Add Color Clip (white) | Color producer | `color` producer | **MISSING** — solid-colour producer (SYNTHESIS gap #9). |
| Import paper texture | Image producer | image producer | **MISSING** — single-image producer (SYNTHESIS gap #9). |

## What was built — `transition_paper_cutout`

A per-clip bundle tool (analogous to `effect_glitch_stack`) that stamps the
**torn-paper cutout filter stack** onto one clip in a single snapshot:

```
transition_paper_cutout(
    workspace_path, project_file, track, clip,
    points="",                  # JSON [[x,y],...] normalized (>=3); "" → procedural torn polygon
    feather=2, feather_passes=2, alpha_operation="add",
    edge_scale=1.0,             # >1.0 adds a centred Transform (affine) scale-up = white-rim trick
    distort_amplitude=0.0,      # >0 adds frei0r.distort0r edge roughening
    distort_frequency=0.02,
    drop_shadow=True,           # dropshadow paper-lift
    shadow_offset=4, shadow_blur=8.0, shadow_color="#000000",
)
```

Application-order stack it writes: **Transform (affine, optional) →
Rotoscoping mask → Distort (optional) → Drop shadow (optional)**. Reuses
`masking.build_rotoscoping_xml` for the mask; new pure code lives in
`pipelines/paper_cutout.py` (procedural torn-polygon generator, `affine` rect,
`frei0r.distort0r` / `dropshadow` property builders, stack composer).

### Procedural asset

Rather than depend on the missing producers, the tool generates its subject
outline procedurally when `points` is empty: `build_torn_polygon()` returns a
deterministic seeded-jitter jagged polygon (a "torn" outline) so the tool works
with no external asset. Callers who have hand-traced a subject pass their own
normalized polygon via `points`.

## Honest omissions (not reproduced by the tool)

1. **Stepped multi-still reveal** — extract-frame-to-project, the 3× still cut,
   and the per-step *carving* of the mask (removing upper points) are a manual,
   multi-clip authoring flow with no producer/timeline primitives yet. The tool
   dresses **one** clip; the caller stacks steps by calling it per still with
   progressively different `points`.
2. **Screen-blended paper texture layer** — needs an image producer + a screen
   composite. Do it with existing `composite_set(blend_mode="screen")` on its own
   track; subject to the §1.2 placement bug.
3. **Separate white-edge color-clip track** — needs a solid-colour producer. The
   tool instead approximates the rim on the same clip via `edge_scale` +
   `distort_*` + drop shadow (visually similar, structurally different).
4. **Hand-drawn / carved roto splines** — static polygon only; no interactive
   trace and no per-step point removal automation.
5. **Contrast / optional grade** — reachable via `effect_add`; not bundled.

## Known blocking issues (noted, not fixed here)

- **§1.1 filter placement** (docs/plans/2026-07-03-kdenlive-mcp-improvements.md):
  `insert_effect_xml` attaches filters with `track=`/`clip_index=` attrs that the
  serializer may relocate to the MLT root rather than nesting inside the playlist
  `<entry>`. All of this tool's filters (rotoscoping, affine, distort, dropshadow)
  ride on that path, so in-Kdenlive rendering is gated on the placement fix. The
  tool builds well-formed, correctly-ordered XML regardless.
- **§1.2 transition placement**: the screen paper-texture composite
  (`composite_set`) lands in the tractor/root — same gate.
- **Test-harness note**: under the installed dev `fastmcp` (3.x), `@mcp.tool()`
  wraps functions in a non-callable `FunctionTool`, which reddens the entire
  existing integration suite when tests call tools directly. The
  `transition_paper_cutout` integration test unwraps `.fn` so it is green in both
  environments; the other integration files are unaffected by this tool's work.
