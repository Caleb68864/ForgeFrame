---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-effect-catalog.md"
sub_spec_number: 1
title: "Catalog Data Model + Parser"
date: 2026-04-13
dependencies: [none]
---

# Sub-Spec 1: Catalog Data Model + Parser

Refined from `docs/specs/2026-04-13-effect-catalog.md` — Factory Run 2026-04-13-effect-catalog.

## Scope

Build the typed data model and pure XML parser for Kdenlive effect descriptions. This sub-spec is **logic-only** — no file output, no CLI, no MCP registration, no I/O against `/usr/share/`. The output is a single Python module exposing dataclasses, an enum, and two pure functions: `parse_effect_xml(path) -> EffectDef` and `parse_param(element) -> ParamDef`.

The XML shape is verified locally against Kdenlive 25.12.3 (`/usr/share/kdenlive/effects/`, 376 files). Root element is `<effect xmlns="https://www.kdenlive.org" tag="..." type="...">`. The filename stem is the `kdenlive_id` (no explicit id attribute). Parameters appear flat under the root. The `xmlns` means parsers must use namespace-aware element matching (or strip the namespace when reading via ElementTree).

The parser must fail loudly on any param `type` value outside the known enum — this is intentional, to force humans to update the enum when Kdenlive ships new types. Unparseable file handling (skip + log) lives in sub-spec 2's generator, not here.

Codebase findings:
- Tests live at `/home/caleb/Projects/ForgeFrame/tests/unit/`. No existing `tests/unit/fixtures/` directory yet — sub-spec creates it under `tests/unit/fixtures/effect_xml/`.
- Pipeline pattern reference: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py` — module-level pure functions, `from __future__ import annotations`, dataclasses where applicable.
- Test convention: `tests/unit/test_<pipeline_name>.py`, pytest function-style tests with `from __future__ import annotations`.

## Interface Contracts

### Provides
- `EffectDef` (frozen `@dataclass(slots=True)`): typed effect record; consumed by sub-spec 2 (generator emits it) and sub-spec 3 (MCP serializes it).
- `ParamDef` (frozen `@dataclass(slots=True)`): typed parameter record.
- `ParamType` (`enum.Enum`): closed set of param type strings.
- `parse_effect_xml(path: pathlib.Path) -> EffectDef`: parses one XML file into one `EffectDef`. Raises `ValueError` on unknown param type.
- `parse_param(element: xml.etree.ElementTree.Element) -> ParamDef`: parses one `<parameter>` element.
- Module path for downstream import: `workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen`.

### Requires
None — no dependencies.

### Shared State
None. Pure functions over inputs.

## Implementation Steps

### Step 1: Create test fixtures directory and seed XML files
- **Files:** `tests/unit/fixtures/effect_xml/acompressor.xml`, `tests/unit/fixtures/effect_xml/transform.xml`, `tests/unit/fixtures/effect_xml/list_no_display.xml`, `tests/unit/fixtures/effect_xml/animated_param.xml`, `tests/unit/fixtures/effect_xml/keyframes_attr.xml`, `tests/unit/fixtures/effect_xml/unknown_type.xml`
- **Action:** create
- **Content:**
  - `acompressor.xml`: copy verbatim from `/usr/share/kdenlive/effects/acompressor.xml` (canonical reference for the 11-param assertion).
  - `transform.xml`: hand-craft a minimal `<effect tag="affine" type="video">` with one `type="constant"` and one `type="geometry"` param.
  - `list_no_display.xml`: a `<parameter type="list" paramlist="0;1;2">` WITHOUT `<paramlistdisplay>` to exercise the fallback.
  - `animated_param.xml`: one `<parameter type="animated" name="rect" default="...">` (no `keyframes` attr) to test type-driven keyframable.
  - `keyframes_attr.xml`: one `<parameter type="constant" name="opacity" keyframes="1">` to test attr-driven keyframable.
  - `unknown_type.xml`: one `<parameter type="quantum_flux" name="bogus">` to assert ValueError.
- **Note:** Use `cp /usr/share/kdenlive/effects/acompressor.xml tests/unit/fixtures/effect_xml/acompressor.xml` for the canonical fixture; hand-write the others.

### Step 2: Write failing test file
- **File:** `tests/unit/test_effect_catalog_parser.py`
- **Pattern:** Follow `tests/unit/test_effect_apply.py` (function-style pytest, `from __future__ import annotations`).
- **Tests to write (one per behavioral criterion):**
  1. `test_paramtype_enum_covers_known_set` — assert all 16 enum members exist by name.
  2. `test_effectdef_fields_present` — instantiate with all fields, assert frozen (`pytest.raises(dataclasses.FrozenInstanceError)` on assignment).
  3. `test_paramdef_fields_present` — same, all 10 fields including `keyframable`.
  4. `test_parse_acompressor_fixture` — full equality on `kdenlive_id="acompressor"`, `mlt_service="avfilter.acompressor"`, `display_name="Compressor (avfilter)"`, `category="audio"`, `len(params) == 11`.
  5. `test_parse_list_param_with_display` — values=("0","1"), value_labels=("Average","Maximum") on the `av.link` param of acompressor.
  6. `test_parse_list_param_without_display` — uses `list_no_display.xml`; value_labels equals values.
  7. `test_parse_animated_type_keyframable` — uses `animated_param.xml`; `keyframable is True`.
  8. `test_parse_keyframes_attr_keyframable` — uses `keyframes_attr.xml`; `keyframable is True`.
  9. `test_parse_constant_no_keyframes_not_keyframable` — uses any constant param without `keyframes`; `keyframable is False`.
  10. `test_unknown_param_type_raises` — `unknown_type.xml` raises `ValueError` and the message contains both `"quantum_flux"` and `"unknown_type.xml"`.
  11. `test_kdenlive_id_from_filename_stem` — temp-rename `acompressor.xml` to `foo.xml` (use `tmp_path` fixture); parsed `kdenlive_id == "foo"`.
  12. `test_missing_default_attr` — param missing `default` produces `ParamDef.default is None`.
  13. `test_missing_min_max` — produces `min is None`, `max is None`.
  14. `test_localized_name_prefers_no_lang` — fixture with both `<name>` and `<name lang="fr">`; parsed display_name is the no-lang one.
  15. `test_empty_description_is_empty_string` — not None.
- **Run:** `uv run pytest tests/unit/test_effect_catalog_parser.py -v`
- **Expected:** all FAIL (module doesn't exist).

### Step 3: Create the data model module
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog_gen.py`
- **Action:** create
- **Pattern:** Follow stdlib-only style of `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py`.
- **Contents:**
  - Module docstring describing purpose: "Catalog generator: parses Kdenlive effect XML into typed records."
  - `from __future__ import annotations`
  - Imports: `dataclasses`, `enum`, `pathlib`, `xml.etree.ElementTree as ET`, `logging`.
  - `class ParamType(str, enum.Enum)` with the 16 members listed in the master spec (CONSTANT="constant", DOUBLE="double", INTEGER="integer", BOOL="bool", SWITCH="switch", COLOR="color", KEYFRAME="keyframe", ANIMATED="animated", GEOMETRY="geometry", LIST="list", FIXED="fixed", POSITION="position", URL="url", STRING="string", READONLY="readonly", HIDDEN="hidden"). Use lowercase string values matching Kdenlive XML.
  - `_KEYFRAMABLE_TYPES = frozenset({ParamType.KEYFRAME, ParamType.ANIMATED, ParamType.GEOMETRY})`.
  - `KDENLIVE_NS = "{https://www.kdenlive.org}"` for namespace-prefixed tag matching, OR strip namespace via `ET.iterparse` post-processing. Pick one and document.
  - `@dataclass(frozen=True, slots=True) class ParamDef:` with fields `name: str`, `display_name: str`, `type: ParamType`, `default: str | None`, `min: float | None`, `max: float | None`, `decimals: int | None`, `values: tuple[str, ...]`, `value_labels: tuple[str, ...]`, `keyframable: bool`.
  - `@dataclass(frozen=True, slots=True) class EffectDef:` with fields `kdenlive_id: str`, `mlt_service: str`, `display_name: str`, `description: str`, `category: str`, `params: tuple[ParamDef, ...]`.

### Step 4: Implement parse_param
- **File:** same module
- **Function:** `def parse_param(element: ET.Element) -> ParamDef:`
- **Logic:**
  - Read `type` attr; lookup in `ParamType` (raises `ValueError` via enum constructor — re-raise with clearer message including `name` attr).
  - `name = element.get("name", "")`.
  - `display_name`: pick child `<name>` element preferring one without `lang` attr; fallback to first `<name>` in document order; fallback to `name` attr.
  - `default = element.get("default")` (None if absent).
  - `min`, `max`, `decimals`: parse to float / int when present, else None.
  - `values`, `value_labels`:
    - If `type == LIST`: split `paramlist` attr on `;` -> values; split `<paramlistdisplay>` text on `,` -> value_labels (strip whitespace). If no `<paramlistdisplay>`, value_labels = values.
    - Else: empty tuples.
  - `keyframable`: `True` if `element.get("keyframes") == "1"` OR `param_type in _KEYFRAMABLE_TYPES`, else `False`.
- **Run:** `uv run pytest tests/unit/test_effect_catalog_parser.py::test_parse_list_param_with_display -v`
- **Expected:** that test passes.

### Step 5: Implement parse_effect_xml
- **File:** same module
- **Function:** `def parse_effect_xml(path: pathlib.Path) -> EffectDef:`
- **Logic:**
  - Parse with `ET.parse(path).getroot()`.
  - Strip namespace from all tags (recursive helper) so subsequent element lookups don't need namespace prefixes.
  - Validate root tag is `effect`; else raise `ValueError(f"Not a Kdenlive effect XML: {path}")`.
  - `kdenlive_id = path.stem`.
  - `mlt_service = root.get("tag", "")`.
  - `category = root.get("type", "custom")`.
  - `display_name`: first `<name>` child (with no-lang preference, same logic as parse_param's helper — extract to `_pick_name(parent, fallback)`).
  - `description`: `<description>` text or `""` (never None).
  - `params`: tuple of `parse_param(p)` for each direct `<parameter>` child. On `ValueError` from a param, re-raise with file path appended: `raise ValueError(f"{exc} in file {path.name}") from exc`.
- **Run:** `uv run pytest tests/unit/test_effect_catalog_parser.py -v`
- **Expected:** all 15 tests PASS.

### Step 6: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog_gen.py tests/unit/test_effect_catalog_parser.py tests/unit/fixtures/effect_xml/`
- **Message:** `feat: catalog data model + parser for Kdenlive effect XML`

## Acceptance Criteria

- `[STRUCTURAL]` `effect_catalog_gen.py` exports `EffectDef`, `ParamDef`, `ParamType` dataclasses/enum plus `parse_effect_xml(path) -> EffectDef` and `parse_param(element) -> ParamDef`.
- `[STRUCTURAL]` `ParamType` enum covers: `CONSTANT`, `DOUBLE`, `INTEGER`, `BOOL`, `SWITCH`, `COLOR`, `KEYFRAME`, `ANIMATED`, `GEOMETRY`, `LIST`, `FIXED`, `POSITION`, `URL`, `STRING`, `READONLY`, `HIDDEN`.
- `[STRUCTURAL]` `EffectDef` fields: `kdenlive_id: str`, `mlt_service: str`, `display_name: str`, `description: str`, `category: str`, `params: tuple[ParamDef, ...]`.
- `[STRUCTURAL]` `ParamDef` fields: `name: str`, `display_name: str`, `type: ParamType`, `default: str | None`, `min: float | None`, `max: float | None`, `decimals: int | None`, `values: tuple[str, ...]`, `value_labels: tuple[str, ...]`, `keyframable: bool`.
- `[BEHAVIORAL]` `parse_effect_xml(fixtures/acompressor.xml)` returns `EffectDef(kdenlive_id="acompressor", mlt_service="avfilter.acompressor", display_name="Compressor (avfilter)", category="audio", params=[...])` with 11 params.
- `[BEHAVIORAL]` `parse_param` on a `type="list"` parameter sets `values=("0","1")` and `value_labels=("Average","Maximum")`.
- `[BEHAVIORAL]` `parse_param` on a `type="animated"` parameter sets `keyframable=True` regardless of `keyframes` attr.
- `[BEHAVIORAL]` `parse_param` on a param with explicit `keyframes="1"` attr sets `keyframable=True`.
- `[BEHAVIORAL]` `parse_param` on a param without `keyframes` attr and with a non-animating type sets `keyframable=False`.
- `[BEHAVIORAL]` `parse_effect_xml` on an XML with an unknown param type raises `ValueError` naming the offending type string and filename.
- `[BEHAVIORAL]` `parse_effect_xml` uses the filename stem as `kdenlive_id` (no explicit id attribute in XML).
- `[MECHANICAL]` `uv run pytest tests/unit/test_effect_catalog_parser.py -v` passes.

## Completeness Checklist

`ParamType` enum members (all required):

| Value | Required |
|-------|----------|
| CONSTANT = "constant" | required |
| DOUBLE = "double" | required |
| INTEGER = "integer" | required |
| BOOL = "bool" | required |
| SWITCH = "switch" | required |
| COLOR = "color" | required |
| KEYFRAME = "keyframe" | required |
| ANIMATED = "animated" | required |
| GEOMETRY = "geometry" | required |
| LIST = "list" | required |
| FIXED = "fixed" | required |
| POSITION = "position" | required |
| URL = "url" | required |
| STRING = "string" | required |
| READONLY = "readonly" | required |
| HIDDEN = "hidden" | required |

`EffectDef` fields:

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| kdenlive_id | str | required | sub-spec 2 (CATALOG key), sub-spec 3 (lookup) |
| mlt_service | str | required | sub-spec 2 (find_by_service), sub-spec 3 (lookup) |
| display_name | str | required | sub-spec 3 (effect_list_common output) |
| description | str | required (may be empty) | sub-spec 3 (short_description) |
| category | str | required ("audio"/"video"/"custom") | sub-spec 3 |
| params | tuple[ParamDef, ...] | required (may be empty) | sub-spec 3 (effect_info output) |

`ParamDef` fields:

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| name | str | required | sub-spec 3 (param schema) |
| display_name | str | required | sub-spec 3 |
| type | ParamType | required | sub-spec 3 |
| default | str \| None | optional | sub-spec 3 |
| min | float \| None | optional | sub-spec 3 |
| max | float \| None | optional | sub-spec 3 |
| decimals | int \| None | optional | sub-spec 3 |
| values | tuple[str, ...] | required (may be empty) | sub-spec 3 |
| value_labels | tuple[str, ...] | required (may be empty) | sub-spec 3 |
| keyframable | bool | required | sub-spec 3, future Spec 7 |

Resource limits: none.

## Verification Commands

- **Build:** `uv sync`
- **Tests:** `uv run pytest tests/unit/test_effect_catalog_parser.py -v`
- **Acceptance:**
  - `uv run python -c "from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import EffectDef, ParamDef, ParamType, parse_effect_xml, parse_param; print('exports ok')"`
  - `uv run python -c "from pathlib import Path; from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import parse_effect_xml; e = parse_effect_xml(Path('tests/unit/fixtures/effect_xml/acompressor.xml')); print(e.kdenlive_id, e.mlt_service, len(e.params))"` -> expect `acompressor avfilter.acompressor 11`.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py`: pure module-level functions, stdlib-first imports, `from __future__ import annotations`.
- `tests/unit/test_effect_apply.py`: function-style pytest, no class wrappers, descriptive `test_<behavior>` names.
- Use `tmp_path` pytest fixture for any test that needs a renamed XML file.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog_gen.py` | Create | Data model + parser (this sub-spec); will be extended by sub-spec 2. |
| `tests/unit/test_effect_catalog_parser.py` | Create | Unit tests for parser. |
| `tests/unit/fixtures/effect_xml/acompressor.xml` | Create | Canonical fixture (copy of system file). |
| `tests/unit/fixtures/effect_xml/transform.xml` | Create | Multi-type param fixture. |
| `tests/unit/fixtures/effect_xml/list_no_display.xml` | Create | List param without paramlistdisplay. |
| `tests/unit/fixtures/effect_xml/animated_param.xml` | Create | Type-driven keyframable. |
| `tests/unit/fixtures/effect_xml/keyframes_attr.xml` | Create | Attr-driven keyframable. |
| `tests/unit/fixtures/effect_xml/unknown_type.xml` | Create | Unknown-type ValueError fixture. |
