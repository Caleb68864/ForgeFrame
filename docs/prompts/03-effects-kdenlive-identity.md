# 03 -- Effects must carry Kdenlive's effect identity (roadmap step 3)

Kdenlive 26.08 handles clip-filter ids in two ways:
- a filter with **no** `kdenlive_id` property is silently dropped;
- a filter whose `kdenlive_id` is **not in Kdenlive's effect registry** aborts
  `kdenlive --render` (rc 134).

`effect_add` writes no `kdenlive_id`, so the check-pack blur (step 06) renders
in melt but not in Kdenlive. Many other tools write a *wrong* id: the effect
XML's file name (`frei0r_cartoon`) instead of its registry id
(`frei0r.cartoon`), or `transform` for pan/zoom. Each of those crashes
Kdenlive. The fix has four parts:
- one generated table of real Kdenlive effect ids;
- one resolver;
- every filter builder routed through the resolver;
- a serializer safety net that never writes an unknown id.

Read `docs/prompts/00-README.md` first; its shared rules apply. Needs prompt
01. In `tests/integration/external/test_kdenlive_differential.py`, the
`FRAMES_XFAIL` entries `effect_blur` and `title` must flip to passing; remove
them as part of this task.

---

## The bug (confirmed 2026-10-14, Kdenlive 26.08.2)

Rebuild the pack with
`uv run --project /home/caleb/Projects/ForgeFrame python /home/caleb/Projects/ForgeFrame/scripts/kdenlive_check_pack.py /tmp/ff-pack`.
In `06_effect_blur.kdenlive`, the first `<entry>` of `playlist_video` holds:

```xml
<filter id="effect_0_0_avfilter.gblur" mlt_service="avfilter.gblur">
  <property name="av.sigma">12</property>
</filter>
```

The Kdenlive render playlist (captured with prompt 01's
`kdenlive_render(..., capture_playlist=...)`) shows that entry with **no
filters**. These hand-edited variants were rendered with
`xvfb-run -a kdenlive --render` and compared with melt (PSNR, 1 s window):

| `<filter>` variant | Kdenlive | PSNR vs melt |
| --- | --- | --- |
| as emitted (no `kdenlive_id`) | dropped | 25.8 |
| `mlt_service` as a `<property>` child, still no `kdenlive_id` | dropped | 25.8 |
| as emitted + `<property name="kdenlive_id">avfilter.gblur</property>` | **blurred** | 35.3 |
| `mlt_service` + `kdenlive_id` property children only (minimal) | **blurred** | 35.3 |
| `kdenlive_id=avfilter_gblur` (the catalog's value) | **abort, rc 134** `std::out_of_range unordered_map::at` | -- |
| `mlt_service=affine`, `kdenlive_id=transform`, `transition.rect` (pan/zoom shape) | **abort, rc 134** | -- |
| same, `kdenlive_id=pan_zoom` | renders | 60.6 |

What this proves:
- **The minimal working fix is a `kdenlive_id` equal to a registry id.**
  `kdenlive:collapsed` and explicit defaults are not needed.
- Kdenlive fills in the defaults of params that were not set
  (`av.sigmaV=10`, `av.steps=1`, `av.planes=7`). This is harmless: it still
  matches melt at 35 dB.
- Emit `mlt_service` as a property child as well, because the native fixtures
  do. Native evidence: `tests/fixtures/kdenlive_references/audio_mix_upstream_kde.kdenlive`,
  lines 132-176 and 356-380 (filters nested in `<entry>`, each with
  `mlt_service` and `kdenlive_id` properties).

### What the "registry id" is

The registry id is the `id=` attribute of the `<effect>` root in
`/usr/share/kdenlive/effects/<file>.xml`. If there is no `id=`, it is `tag=`
(the MLT service). It is **not** the file name. 352 of the 433 installed
files differ from their name, for example:

| File | Registry id | Note |
| --- | --- | --- |
| `avfilter_gblur.xml` | `avfilter.gblur` | |
| `hsl_primaries.xml` | `hslprimaries` | |
| `scratchlines.xml` | `lines` | |
| `ladspa_pitch.xml` | `pitch_shift` | |
| `pan_zoom.xml` | `pan_zoom` | tag `affine` |

`effect_catalog_gen.parse_effect_xml` uses the file name
(`edit_mcp/pipelines/effect_catalog_gen.py:181`, `kdenlive_id = path.stem`).
So every `EffectDef.kdenlive_id` / `CATALOG` key is a catalog key, not a
registry id.

## Code map (under `workshop-video-brain/src/workshop_video_brain/edit_mcp/`)

- `server/tools/effects_catalog.py:39` `effect_add` →
  `pipelines/effect_apply.apply_effect` → `AddEffect` intent.
- `adapters/kdenlive/patcher_intents.py:1197` `_apply_add_effect` builds the
  filter with an f-string:
  - values are not XML-escaped;
  - `mlt_service` is an attribute only;
  - there is no `kdenlive_id`.
- `adapters/kdenlive/serializer.py:219` `_extract_clip_filters` nests clip
  filters in their `<entry>`. That placement is correct; keep it.
- `server/tools_helpers/_effects.py:35` `apply_simple_effect` is the body of
  the 24 generated wrappers in `pipelines/effect_wrappers/`, which pass
  catalog keys (e.g. `'frei0r_cartoon'`). The same file's
  `_lookup_catalog_by_service` (around line 118) returns catalog keys. It is
  used by `server/tools/effects_color.py:200,653` and
  `server/tools/effects_bundles.py:87,249,461,465`.
- `pipelines/overlay_looks.py:249` `lookup_catalog_id` also returns catalog
  keys. It is used by `server/bundles/overlay_looks.py:186,363`.
- `pipelines/_common.py:131` `_build_filter_xml` uses a heuristic: for
  `avfilter.*`/`frei0r.*` it sets `kdenlive_id = mlt_service`, and it turns
  affine+`transform` into `qtblend`. Its docstring cites a non-existent
  `normalize_effect_id`. `make_filter_element_xml` (line 89) passes ids
  through unchanged.
- Hard-coded bad ids:

  | Value | Location |
  | --- | --- |
  | `transform` | `server/bundles/pan_zoom.py:35` |
  | `transform` | `server/bundles/motion_track.py:52` |
  | `transform` | `pipelines/zoom_whip.py:39` |
  | `transform` | `server/tools/effects_bundles.py:388` |
  | `transform` | `pipelines/paper_cutout.py:235` |
  | `avfilter_dblur` | `pipelines/zoom_whip.py:43` |
  | `frei0r_keyspillm0pup`, `avfilter_hsvkey`, `avfilter_despill` | `pipelines/scifi_greenscreen.py:56-60` |
  | `frei0r_alpha0ps_alphaspot` | `pipelines/masking.py:371` |
  | `avfilter_hsvkey` | `pipelines/masking.py:450` |
  | `frei0r_distort0r` | `pipelines/paper_cutout.py:147` |

  `dissolve`, `mix` and `frei0r.cairoblend` are **transition** ids and are
  correct.
- Layering (`tests/unit/test_module_boundaries.py`):
  `core < adapters < pipelines < server`. Put the table and the resolver in
  `adapters/kdenlive/` so the serializer, the intents, the pipelines and the
  shells can all import them.

## The fix: steps in order

### 1. Generated id table: `adapters/kdenlive/effect_ids.py`

- In `pipelines/effect_catalog_gen.py`, add
  `parse_effect_identity(path) -> tuple[str, str, str]` returning
  `(stem, effect_id, mlt_service)`.
  - `effect_id = root.get("id") or root.get("tag") or path.stem`.
  - It reads root attributes only, so it never fails on unknown param types.
- Add `emit_effect_ids_module(rows, source_version) -> str`. It renders:
  - a `GENERATED FILE -- do not edit` header that names the source version;
  - `EFFECT_IDS: dict[str, tuple[str, str]]` (stem → `(effect_id, mlt_service)`,
    sorted);
  - `KNOWN_EFFECT_IDS: frozenset[str]`.
- Add `scripts/generate_effect_ids.py`. Copy the argparse shape of
  `scripts/generate_effect_catalog.py`.
- Run it on `/usr/share/kdenlive/effects/` (26.08.2, 433 files) and check the
  output into the tree.
- **Do NOT regenerate `effect_catalog.py`.** A trial regeneration from 26.08.2
  drops 5 entries (`qtblend`, `frei0r_mask0mate` (a wrapper's source),
  `avfilter_delogo`, `gradientmap`, `vignette`), because the generator
  rejects the new param types `animatedrect` and `animatedfakepoint`. Report
  it; do not fix it here.

### 2. Resolver: `adapters/kdenlive/effect_identity.py`

`normalize_effect_id(mlt_service: str, kdenlive_id: str = "", props: Iterable[str] = ()) -> str | None`

Apply these rules in order:
1. `kdenlive_id` is in `KNOWN_EFFECT_IDS` → return it.
2. `kdenlive_id` is an `EFFECT_IDS` key (a file stem) → return its mapped id.
3. `mlt_service == "affine"`, `kdenlive_id == "transform"`, and
   `"transition.rect"` is in `props` → return `"pan_zoom"`. This was verified
   in Kdenlive (table above).
4. `mlt_service` is in `KNOWN_EFFECT_IDS` → return `mlt_service`.
5. Exactly one `EFFECT_IDS` row has this `mlt_service` → return its id.
6. Otherwise → return `None` and `logger.warning(...)`.

### 3. Route every builder through it

- `_apply_add_effect`:
  - build the element with `xml.etree.ElementTree` (this escapes values);
  - keep the `id`, `mlt_service`, `track` and `clip_index` attributes (the
    parser and `effect_stack.list_effects` read them);
  - children, in order: the `mlt_service` property, then the `kdenlive_id`
    property (from `normalize_effect_id(effect_name, params.get("kdenlive_id", ""), params)`;
    omit it when the result is `None`), then the remaining params.
- `effect_add` shell: add `"kdenlive_id": <resolved or None>` to the `_ok`
  payload.
  - When it is `None`, also add
    `"warning": "'<svc>' is not a Kdenlive effect: melt renders it, Kdenlive will drop it."`.
  - Still accept the call; melt-only services are supported.
- `apply_simple_effect`, `_lookup_catalog_by_service`, `lookup_catalog_id`,
  `_build_filter_xml` and `make_filter_element_xml` all resolve through
  `normalize_effect_id`. Omit the `kdenlive_id` child on `None`.
  - Keep `_build_filter_xml`'s affine+`transform` → `qtblend` branch as it is
    (no `transition.rect`).
  - Fix its stale docstring reference.
- Fix the hard-coded constants in the table above to registry ids (look each
  one up in `EFFECT_IDS`). For `transform` + `transition.rect`, use
  `pan_zoom`.
  - This applies to `pan_zoom.py` and `motion_track.py`, which use
    `transition.rect`.
  - `pipelines/zoom_whip.py:39` and `pipelines/paper_cutout.py:235` are
    different: they use affine with a plain `rect`, which is the legacy
    Transform effect. The resolver returns `None` for them, so their
    `kdenlive_id` is omitted and Kdenlive drops the effect instead of
    crashing. That is acceptable for this task.
  - Do not port those two to `qtblend` here. That changes the rendering
    (rect format), so list it in the report as follow-up work.
  - If an existing test pinned a wrong id, update that assertion and list it
    in the report.
- Do not rename any tool, wrapper module or `CATALOG` key, and do not
  regenerate the wrappers. Resolving inside `apply_simple_effect` fixes all
  24 wrappers.

### 4. Serializer safety net (`_extract_clip_filters`, serializer.py:219)

For each relocated clip filter that **has** a `kdenlive_id` property:
- if the id is not in `KNOWN_EFFECT_IDS`, replace it with
  `normalize_effect_id(...)`;
- if that returns `None`, remove the property and `logger.warning`.

Never *add* a missing `kdenlive_id` here. That would silently change filters
other prompts own: `audio_fade`'s `volume` filter (prompt 02) also has no id
and is dropped by Kdenlive today. This guarantees that no file ForgeFrame
writes can abort `kdenlive --render`, even from a builder this task missed.

### 5. Tests (all required)

Unit tests go in `tests/unit/test_effect_kdenlive_identity.py`:
- **Resolver.** Every rule in step 2:
  - `avfilter.gblur` → `avfilter.gblur`;
  - `frei0r_cartoon` → `frei0r.cartoon`;
  - `hsl_primaries` → `hslprimaries`;
  - `("affine", "transform", ["transition.rect"])` → `pan_zoom`;
  - `("foo.bar", "")` → `None`.
- **Data.** `EFFECT_IDS["avfilter_gblur"][0] == "avfilter.gblur"`.
- **`effect_add` path.**
  - Run `apply_effect` on `sequence_project` (`tests/_testkit.py`), then
    `serialize_project` to `tmp_path`.
  - The filter inside the first `<entry>` has an `mlt_service` property and
    `kdenlive_id=avfilter.gblur`.
  - A value containing `&` or `<` round-trips.
  - Through `call_tool`: an unknown service gets no `kdenlive_id` and the
    payload carries `warning`.
- **Wrapper.** `effect_frei0r_cartoon` emits `kdenlive_id=frei0r.cartoon`.
- **Safety net.** Serialize a project whose clip filter carries
  `kdenlive_id=avfilter_gblur` and assert that the written id is
  `avfilter.gblur`. Do the same with `bogus_id` and assert that the property
  is removed.
- **Guard.**
  - Serialize projects built through `effect_add`, `effect_pan_zoom`,
    `effect_frei0r_cartoon` and one `effects_color`/`effects_bundles` tool.
  - Every `kdenlive_id` inside an `<entry>` filter must be in
    `KNOWN_EFFECT_IDS`.
- **External melt proof.** Add a case to
  `tests/integration/external/test_effect_visible.py`: `effect_add`
  `avfilter.gblur` changes pixels vs a no-effect render (`frames_differ`).
- **Kdenlive differential.** Remove `effect_blur` and `title` from
  `FRAMES_XFAIL`. Both must pass at >= 33 dB (expect about 35).
- Run the unit suite, the full suite and `uvx ruff check --select F401,F841`
  on the files you touched, as in `00-README.md`.

### 6. Verify in real Kdenlive

1. Rebuild the pack. Run `kdenlive --render` and melt on `06_effect_blur` and
   `07_title`.
   - Both PSNRs must be >= 33 dB.
   - rc must be 0.
   - The captured playlist must show the gblur filter inside the `a_bars`
     entry.
2. Build throwaway projects with `effect_pan_zoom` and
   `effect_frei0r_cartoon`. Render each with `kdenlive --render`: rc must be
   0 (both were 134 before).
3. Put all the numbers in the report.

## Do NOT

- Do not touch `_apply_add_transition`, `a_track`/`b_track` or transition
  ordering in `serializer.py`.
- Do not touch `kdenlive:id` numbering or `main_bin` (prompts 04/05).
- Do not change `audio_fade` or its `volume` filter (prompt 02). Mention in
  the report that it lacks a `kdenlive_id`.
- Do not regenerate `effect_catalog.py` or the wrappers. Do not rename
  tools, wrappers or `CATALOG` keys.
- Do not move clip filters out of `<entry>`.
- Do not "fix" the F401 re-export block in `adapters/kdenlive/patcher.py`.

## Acceptance criteria

- Check-pack 06 and 07 render blurred in Kdenlive, >= 33 dB vs melt, rc 0.
- No serialized clip filter carries a `kdenlive_id` outside
  `KNOWN_EFFECT_IDS` (guard + safety-net tests).
- The pan/zoom and wrapper projects render in Kdenlive with rc 0.
- Unit, full suite and ruff are green.

## When done

1. `docs/plans/2026-04-08-feature-roadmap.md` step 3: mark it
   `**Done YYYY-MM-DD.**` and add a short summary:
   - a missing id means the filter is dropped;
   - an unknown id aborts the render;
   - the file name is not the id;
   - name the resolver and the safety net.
2. `docs/testing/2026-10-13-kdenlive-2608-differential.md`: update the 06 and
   07 rows with your PSNR, and mark defect 6 fixed.
3. `vault/wiki/kdenlive-avfilter-and-effect-zones.md`: correct the false
   "serializer already emits this exact shape" claim. Add a section "Effect
   identity (Kdenlive 26.08)" with the variant table, the id-vs-file-name
   rule, and pointers to `effect_identity.py` / `effect_ids.py`.
4. `CLAUDE.md` hard rule 11: add one sentence. A clip filter needs a registry
   `kdenlive_id` (the effect XML's `id=`, not its file name); a missing one is
   dropped and an unknown one aborts `kdenlive --render`.
5. Report (format in `00-README.md`): files, test counts, PSNR and rc
   numbers, the constants you changed, and any test assertions you updated.
