# Factory Memory -- Composite Blend Modes

## Project Conventions
- Python 3.12+, Pydantic v2, pytest.
- Build: `uv sync`. Test: `uv run pytest tests/ -v`.
- Source root: `workshop-video-brain/src/workshop_video_brain/`.
- Unit tests: `tests/unit/`. Integration: `tests/integration/`.
- Fixtures: `tests/integration/fixtures/keyframe_project.kdenlive`.

## Stage 1-2 Findings
- Master spec at `docs/specs/2026-04-13-composite-blend-modes.md` quality 32/35.
- Depends on shipped Specs 1-5: `patch_project`, `AddComposition` intent, `apply_pip`, `apply_wipe`, `get_pip_layout`, effect catalog with `find_by_service`.

## Stage 3 Kdenlive Blend-Mode Discovery (CRITICAL)

The `composite` transition (`/usr/share/kdenlive/transitions/composite.xml`) carries NO blend mode property -- only `geometry`, `distort`, `aligned`, `halign`, `valign`, `luma` (for wipe PGM), `softness`, `progressive`. Blend modes live on two separate MLT services:

### Service A: `frei0r.cairoblend` (transition)
- Property `1` (string): `normal;add;saturate;multiply;screen;overlay;darken;lighten;colordodge;colorburn;hardlight;softlight;difference;exclusion;hslhue;hslsaturation;hslcolor;hslluminosity`
- Property `0` (0-100, factor=100): opacity
- Serializer already hardcodes `frei0r.cairoblend` at `serializer.py:323` as the auto-generated inter-track transition's `mlt_service`.

### Service B: `qtblend` (transition, Kdenlive "Composite and transform")
- Property `compositing` (int list): `0;11;12;13;14;15;16;17;18;19;20;21;22;23;24;25;26;27;28;29;6;8`
- Label list: `Alpha blend,Xor,Plus,Multiply,Screen,Overlay,Darken,Lighten,Color dodge,Color burn,Hard light,Soft light,Difference,Exclusion,Bitwise or,Bitwise and,Bitwise xor,Bitwise nor,Bitwise nand,Bitwise not xor,Destination in,Destination out`
- Index mapping (by position): 0=Alpha blend, 11=Xor, 12=Plus, 13=Multiply, 14=Screen, 15=Overlay, 16=Darken, 17=Lighten, 18=Color dodge, 19=Color burn, 20=Hard light, 21=Soft light, 22=Difference, 23=Exclusion, 24-29=Bitwise ops, 6=Destination in, 8=Destination out.

### Recommended abstract-name -> service mapping

| abstract name       | service                | property | MLT value    | notes |
|---------------------|------------------------|----------|--------------|-------|
| cairoblend          | frei0r.cairoblend      | "1"      | "normal"     | default / alpha blend via Cairo |
| screen              | frei0r.cairoblend      | "1"      | "screen"     | |
| lighten             | frei0r.cairoblend      | "1"      | "lighten"    | |
| darken              | frei0r.cairoblend      | "1"      | "darken"     | |
| multiply            | frei0r.cairoblend      | "1"      | "multiply"   | |
| add                 | frei0r.cairoblend      | "1"      | "add"        | |
| overlay             | frei0r.cairoblend      | "1"      | "overlay"    | |
| subtract            | (AMBIGUOUS)            | --       | --           | Not present on either service natively. Worker must escalate if called; closest MLT-native is `frei0r.subtract` as a full filter, not a composite transition property. |
| destination_in      | qtblend                | compositing | "6"       | |
| destination_out     | qtblend                | compositing | "8"       | |
| source_over         | qtblend                | compositing | "0"       | QPainter source-over = standard alpha composition |

### Escalation flag for Sub-Spec 1 worker

Per spec.md escalation triggers:
- "If the MLT property carrying blend mode on the `composite` transition is not `compositing`, stop and confirm" -- IT IS NOT. The `composite` service has no blend-mode property at all. The worker must switch `composition_type` per blend mode (NOT use a single `composite` service).
- "If the MLT value identifiers diverge from abstract names and require a non-trivial mapping table, stop and present" -- THEY DO. frei0r uses strings, qtblend uses integers.
- "If the catalog entry for `composite` lacks the blend mode parameter (meaning blend modes live on a different MLT service), stop and ask which service to use" -- CONFIRMED. Two services.
- `subtract` has no clean composite-transition mapping. Worker must either (a) map `subtract -> frei0r.cairoblend "difference"` (semantically not identical), (b) drop it from `BLEND_MODES` and escalate, or (c) route via a different mechanism.

**Recommendation to worker:** implement the 10 unambiguous modes via the table above; for `subtract`, stop at step 1 and escalate per spec.md before adding it to `BLEND_MODES`.

## Codebase Patterns Found

- `apply_pip` at `compositing.py:40` currently emits `AddComposition(composition_type="composite", params={"geometry": geometry})`. Note: the `composite` service alone produces a transition without alpha blending configured -- Kdenlive/MLT may fall back to default. The existing behavior must be preserved for regression.
- `patcher._apply_add_composition` at `patcher.py:746` emits `<transition mlt_service="{composition_type}">` with `a_track,b_track,in,out` + merged params.
- MCP tool pattern: `@mcp.tool()` decorated, uses `_require_workspace`, `_ok(data)`, `_err(msg)`, `create_snapshot(ws_path, proj_path, description=...)`, `parse_project`, `serialize_project`. See `composite_pip` at `server/tools.py:4240` as the canonical template.
- `AddComposition.params: dict[str, str]` confirmed at `core/models/timeline.py:157` -- carries arbitrary str k/v.

## Build / Test Commands
- Build: `uv sync`
- Tests: `uv run pytest tests/ -v`

## Issues Log
- Stage 3 WARNING: `subtract` blend mode has no native MLT composite-transition value. Worker must escalate per spec before shipping it.
- Stage 3 NOTE: Sub-Spec 1 acceptance criterion "BLEND_MODE_TO_MLT: dict[str, str]" is insufficient -- the mapping must also carry (a) the service name and (b) the property name, since those differ per mode. Worker must extend the data structure to `dict[str, tuple[service, property, value]]` or similar, and document the deviation.

## Stage Outputs

### Stage 3: Prep
- Artifact: phase-specs/ (2 files + index)
- Sub-specs refined: (1) Blend Mode Discovery + Pipeline Extension, (2) Rewire apply_pip + MCP Surface.
- Interface contracts: Sub-Spec 1 provides `apply_composite`, `BLEND_MODES`, `BLEND_MODE_TO_MLT` (extended form) from `pipelines/compositing.py`. Sub-Spec 2 consumes these for MCP tool `composite_set` and internal `apply_pip` rewire.
- Patterns found: MCP tool template at `server/tools.py:4240` (`composite_pip`); composition intent emission at `pipelines/compositing.py:40` (`apply_pip`).
- Build command: `uv sync`
- Test command: `uv run pytest tests/ -v`
