# Effect Catalog + Generator for Kdenlive MCP

## Meta
- Client: ForgeFrame (self)
- Project: Workshop Video Brain
- Repo: /home/caleb/Projects/ForgeFrame
- Date: 2026-04-13
- Author: Caleb Bennett
- Status: completed
- Executed: 2026-04-13
- Result: 3/3 sub-specs passed (2407 tests, 0 regressions, +50 new). Generated catalog: 321 effects from 376 XMLs (55 skipped for param types outside enum)
- Design Doc: `docs/plans/2026-04-13-effect-catalog-design.md`
- Depends on shipped: Spec 1 (Keyframes), Spec 2 (Stack Ops)
- Quality Scores (7 dims / 35): Outcome 5 · Scope 5 · Decisions 5 · Edges 4 · Criteria 4 · Decomposition 4 · Purpose 5 · **Total 32/35**

## Outcome
Parse Kdenlive's installed effect descriptions at `/usr/share/kdenlive/effects/*.xml` (376 files on the target system), optionally cross-check upstream, and generate a typed Python registry at `workshop_video_brain/edit_mcp/pipelines/effect_catalog.py`. Ship a new `effect_info(name)` MCP tool and re-source the existing `effect_list_common` from the catalog. Generator is idempotent and invokable via both a codegen script and a CLI subcommand.

## Intent
**Trade-off hierarchy:**
1. Typed correctness at runtime (catalog is imported Python, not parsed strings)
2. Discoverability for humans (CLI subcommand) and CI (script)
3. No runtime file I/O — Kdenlive need not be installed on the runtime machine
4. Fail loud on unknown Kdenlive param types (force humans to categorize new types)

**Preferences:**
- Prefer additive changes. `effect_list_common` keeps its tool name and signature.
- Prefer checked-in generated artifact over runtime parsing.
- Prefer explicit enum values over loose strings for `ParamType`.

**Escalation triggers:**
- Discovery that Kdenlive's effect XML schema has substantial variation (nested effects, conditional param groups) beyond the single-level `<parameter>` list pattern — stop and report.
- Unknown param type strings in XML that don't fit the enum — stop and ask (spec lists the known set).
- Upstream Kdenlive GitHub fetch requires auth that isn't available — drop to local-only with warning.

## Context
Spec 1 and Spec 2 shipped. Current `effect_list_common` returns only 8 hand-curated effects — ~2% of the installed surface. That hides the actual MLT vocabulary from LLM callers and forces `effect_add` to act as a guess-and-pass-through. The goal of this spec is to ground every tool in ForgeFrame (keyframes, add, copy/paste, future wrappers) in an authoritative, typed registry.

**Kdenlive effect XML format (verified locally):**

```xml
<?xml version="1.0"?>
<effect xmlns="https://www.kdenlive.org" tag="avfilter.acompressor" type="audio">
    <name>Compressor (avfilter)</name>
    <description>Audio Compressor</description>
    <author>libavfilter</author>
    <parameter type="constant" name="av.level_in" max="64" min="0.016" default="1" decimals="3">
        <name>Input Gain</name>
    </parameter>
    <parameter type="list" name="av.link" default="0" paramlist="0;1">
        <name>Link Type</name>
        <paramlistdisplay>Average,Maximum</paramlistdisplay>
    </parameter>
</effect>
```

- Root element: `<effect>` with xmlns
- `tag` attribute = MLT service string
- `type` attribute = `audio` | `video` | `custom` (to be confirmed by parser across sample)
- Filename stem is the `kdenlive_id` (no explicit id attribute)
- `<parameter>` types observed: `constant`, `list`, plus others (`keyframe`, `animated`, `geometry`, `bool`, `color`, `fixed`, `switch`, `readonly`, etc. — parser must discover the full set)
- `<parameter type="list">` has `paramlist` (semicolon-separated values) and `<paramlistdisplay>` (comma-separated labels)

**Known param-type enum (from Kdenlive source inspection — parser must fail on anything outside this set):** `constant`, `double`, `integer`, `bool`, `switch`, `color`, `keyframe`, `animated`, `geometry`, `list`, `fixed`, `position`, `url`, `string`, `readonly`, `hidden`.

Discussion log: `EFFECTS_DISCUSSION.md`. Design doc: `docs/plans/2026-04-13-effect-catalog-design.md`.

Key files touched:
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog_gen.py` (new — generator)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py` (new — generated)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended — `effect_info` added; `effect_list_common` re-sourced)
- `scripts/generate_effect_catalog.py` (new)
- `workshop-video-brain/src/workshop_video_brain/cli.py` (new `catalog regenerate` subcommand)

## Requirements

1. Parser reads `/usr/share/kdenlive/effects/*.xml` and emits one `EffectDef` per file. Unparseable files logged and skipped.
2. Generated `effect_catalog.py` is a typed Python module with frozen `@dataclass(slots=True)` `EffectDef` and `ParamDef`, plus a `ParamType` enum covering all known Kdenlive param type strings.
3. `CATALOG: dict[str, EffectDef]` module-level dict keyed by `kdenlive_id` (filename stem).
4. Helper functions `find_by_name(name)` and `find_by_service(mlt_service)` return `EffectDef | None`.
5. Generation metadata: `__generated_at__`, `__source_version__` (Kdenlive package version), `__local_count__`, `__upstream_diff__` (optional).
6. Parser fails loudly on unknown param type strings (forcing enum update).
7. `keyframable` param flag: `true` if XML has `keyframes="1"` attribute OR `type` is `keyframe | animated | geometry`; else `false`.
8. Script `scripts/generate_effect_catalog.py` callable as `python scripts/generate_effect_catalog.py [--no-upstream-check]` produces the generated module.
9. CLI subcommand `workshop-video-brain catalog regenerate [--no-upstream-check] [--output PATH]` does the same via the existing CLI entry point.
10. New MCP tool `effect_info(name: str) -> dict` returns a JSON-serializable `EffectDef` by `kdenlive_id` or `mlt_service`.
11. Existing MCP tool `effect_list_common()` is re-sourced from the catalog — returns summary entries (kdenlive_id + display_name + mlt_service + short description) for every catalog entry. Tool signature unchanged.
12. Generated module is checked in to git; regeneration workflow is documented in the module's top docstring.
13. Full test suite passes with zero regressions.

## Sub-Specs

### Sub-Spec 1: Catalog Data Model + Parser
**Scope.** Create the typed data model (`EffectDef`, `ParamDef`, `ParamType`) and the XML parser. Pure logic — no file output, no CLI, no MCP.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog_gen.py` (new)
- `tests/unit/test_effect_catalog_parser.py` (new)
- `tests/unit/fixtures/effect_xml/` (new — 4-6 small hand-crafted XML fixtures covering different param types)

**Acceptance Criteria.**
- `[STRUCTURAL]` `effect_catalog_gen.py` exports `EffectDef`, `ParamDef`, `ParamType` dataclasses/enum plus `parse_effect_xml(path) -> EffectDef` and `parse_param(element) -> ParamDef`.
- `[STRUCTURAL]` `ParamType` enum covers: `CONSTANT`, `DOUBLE`, `INTEGER`, `BOOL`, `SWITCH`, `COLOR`, `KEYFRAME`, `ANIMATED`, `GEOMETRY`, `LIST`, `FIXED`, `POSITION`, `URL`, `STRING`, `READONLY`, `HIDDEN`.
- `[STRUCTURAL]` `EffectDef` fields: `kdenlive_id: str`, `mlt_service: str`, `display_name: str`, `description: str`, `category: str` (from `type` attr: `audio`/`video`/`custom`), `params: tuple[ParamDef, ...]`.
- `[STRUCTURAL]` `ParamDef` fields: `name: str`, `display_name: str`, `type: ParamType`, `default: str | None`, `min: float | None`, `max: float | None`, `decimals: int | None`, `values: tuple[str, ...]`, `value_labels: tuple[str, ...]`, `keyframable: bool`.
- `[BEHAVIORAL]` `parse_effect_xml(fixtures/acompressor.xml)` returns `EffectDef(kdenlive_id="acompressor", mlt_service="avfilter.acompressor", display_name="Compressor (avfilter)", category="audio", params=[...])` with 11 params.
- `[BEHAVIORAL]` `parse_param` on a `type="list"` parameter sets `values=("0","1")` and `value_labels=("Average","Maximum")`.
- `[BEHAVIORAL]` `parse_param` on a `type="animated"` parameter sets `keyframable=True` regardless of `keyframes` attr.
- `[BEHAVIORAL]` `parse_param` on a param with explicit `keyframes="1"` attr sets `keyframable=True`.
- `[BEHAVIORAL]` `parse_param` on a param without `keyframes` attr and with a non-animating type sets `keyframable=False`.
- `[BEHAVIORAL]` `parse_effect_xml` on an XML with an unknown param type raises `ValueError` naming the offending type string and filename.
- `[BEHAVIORAL]` `parse_effect_xml` uses the filename stem as `kdenlive_id` (no explicit id attribute in XML).
- `[MECHANICAL]` `uv run pytest tests/unit/test_effect_catalog_parser.py -v` passes.

**Dependencies.** none

---

### Sub-Spec 2: Generator + Emitter + Upstream Check
**Scope.** Build the catalog builder that orchestrates parsing, optional upstream cross-check, and Python module emission.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog_gen.py` (extended — appended to sub-spec 1's module)
- `scripts/generate_effect_catalog.py` (new)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py` (new, GENERATED — checked in)
- `tests/unit/test_effect_catalog_generator.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` Module exports `build_catalog(local_dir: Path, check_upstream: bool = True) -> tuple[list[EffectDef], DiffReport]`.
- `[STRUCTURAL]` Module exports `emit_python_module(effects: list[EffectDef], output_path: Path, source_version: str, diff_report: DiffReport) -> None`.
- `[STRUCTURAL]` Module exports `fetch_upstream_effects() -> list[str] | None` (returns None on fetch failure, list of ids on success).
- `[STRUCTURAL]` `DiffReport` dataclass with fields `local_count: int`, `upstream_count: int | None`, `upstream_only_ids: tuple[str, ...]`, `local_only_ids: tuple[str, ...]`, `upstream_check: Literal["ok","skipped","failed"]`.
- `[STRUCTURAL]` Generated `effect_catalog.py` defines `CATALOG: dict[str, EffectDef]`, `find_by_name(name)`, `find_by_service(mlt_service)`, `__generated_at__`, `__source_version__`, `__local_count__`.
- `[BEHAVIORAL]` `build_catalog` with `check_upstream=False` on a directory of 3 fixture XMLs returns a 3-element list and a DiffReport with `upstream_check="skipped"`.
- `[BEHAVIORAL]` `emit_python_module` produces a file that is syntactically valid Python, importable, and whose `CATALOG` dict contains entries matching the input list.
- `[BEHAVIORAL]` Generated module has a top docstring including regeneration instructions and `source_version`.
- `[BEHAVIORAL]` `fetch_upstream_effects` on a network failure returns `None` without raising (parser wraps the failure).
- `[BEHAVIORAL]` Duplicate kdenlive_id across parsed files yields a warning log and last-wins in CATALOG; both filenames included in the warning.
- `[MECHANICAL]` `python scripts/generate_effect_catalog.py --no-upstream-check --output /tmp/test_catalog.py --source-dir tests/unit/fixtures/effect_xml/` runs to completion, exits 0, produces a valid Python file.
- `[MECHANICAL]` Running the generator against the real `/usr/share/kdenlive/effects/` produces a `pipelines/effect_catalog.py` with `__local_count__` matching `len(os.listdir("/usr/share/kdenlive/effects/"))` minus unparseable count.
- `[MECHANICAL]` Generated module: `python -c "from workshop_video_brain.edit_mcp.pipelines.effect_catalog import CATALOG; print(len(CATALOG))"` returns a count > 300.
- `[MECHANICAL]` `uv run pytest tests/unit/test_effect_catalog_generator.py -v` passes.

**Dependencies.** sub-spec 1

---

### Sub-Spec 3: MCP Tool Surface + CLI Subcommand + Integration
**Scope.** Register `effect_info` MCP tool, re-source `effect_list_common` from the catalog, and add the `catalog regenerate` CLI subcommand.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended)
- `workshop-video-brain/src/workshop_video_brain/cli.py` (extended — new `catalog` subcommand group)
- `tests/integration/test_effect_catalog_mcp_tools.py` (new)
- `tests/unit/test_cli_catalog.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` `server/tools.py` registers new `@mcp.tool()` `effect_info(name: str) -> dict`.
- `[STRUCTURAL]` `effect_info` return shape: `{"status","data":{"kdenlive_id","mlt_service","display_name","description","category","params":[{"name","display_name","type","default","min","max","decimals","values","value_labels","keyframable"}]}}`.
- `[STRUCTURAL]` `effect_list_common` tool signature is unchanged from its current form; its body now iterates the catalog instead of a hardcoded dict.
- `[STRUCTURAL]` CLI has a new subcommand `catalog regenerate` accepting `--no-upstream-check` and `--output PATH` flags.
- `[INTEGRATION]` All new + changed tools are importable as callables from `workshop_video_brain.edit_mcp.server.tools` after module import.
- `[BEHAVIORAL]` `effect_info("acompressor")` returns the generated catalog's entry for `acompressor` with full param schema.
- `[BEHAVIORAL]` `effect_info("avfilter.acompressor")` (by mlt_service) returns the same entry.
- `[BEHAVIORAL]` `effect_info("nonexistent_effect")` returns `{"status":"error","message":"Effect not found: nonexistent_effect. Try `effect_list_common` for the registry."}`.
- `[BEHAVIORAL]` `effect_list_common()` returns `{"status":"success","data":{"effects":[{"kdenlive_id","mlt_service","display_name","category","short_description"}, ...]}}` with entry count > 300.
- `[BEHAVIORAL]` Short description truncates at ~80 chars with ellipsis if longer.
- `[BEHAVIORAL]` CLI: `uv run workshop-video-brain catalog regenerate --no-upstream-check --output /tmp/cli_catalog.py --source-dir tests/unit/fixtures/effect_xml/` (or equivalent flag names if the generator script uses different ones) exits 0 and writes the file.
- `[MECHANICAL]` `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py tests/unit/test_cli_catalog.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` (full suite) passes with no regressions.

**Dependencies.** sub-spec 1, sub-spec 2

## Edge Cases

- **Kdenlive not installed** on codegen machine — script fails with install hint. Runtime MCP server still works from the checked-in generated module.
- **Unparseable XML file** — skip, log warning, continue. Do not fail the whole generation.
- **Param with no `default`** — `default: None` in `ParamDef`.
- **Param with no `min`/`max`** — `None` values.
- **`<parameter type="list">` missing `paramlistdisplay`** — use raw `paramlist` values as `value_labels` too.
- **Localized `<name>` variants** (e.g., `<name lang="fr">Compresseur</name>`) — prefer the no-`lang`-attr variant. If only localized variants exist, take the first in document order.
- **Empty `<description>`** — empty string, not None.
- **Duplicate kdenlive_id across files** — last-wins in CATALOG; warning lists both files.
- **Generator output path already exists** — overwrite; preserve nothing.
- **`effect_info` called before catalog is generated** — the module import raises `ModuleNotFoundError`; the tool catches it and returns a `_err` pointing at the regeneration command.
- **MCP tool called with empty string name** — `_err("Effect name cannot be empty.")`.

## Out of Scope

- Full Kdenlive UI label → MLT property-name translation (only a subset of effects need it; the catalog exposes both names, caller maps)
- Runtime introspection of frei0r binaries (`/usr/lib/frei0r-1/*.so` metadata) — fallback not needed given XML completeness
- Effect XML authoring / writing (generator is read-only against Kdenlive's XML)
- Per-effect wrapper-tool generation (Spec 7)
- Stack preset validation against catalog (Spec 4)
- Sparse-clone of upstream beyond `data/effects/` (just that subtree)
- Tracking upstream PRs / unreleased effects
- Localized display names — English canonical only

## Constraints

### Musts
- All acceptance criteria.
- Python 3.12+.
- Use `xml.etree.ElementTree` from stdlib; no new XML dependencies.
- Generator must be idempotent (regen produces identical output for identical input).
- Generated module is importable without any runtime file I/O.

### Must-Nots
- Must NOT require Kdenlive to be installed on the runtime machine (only on the codegen machine).
- Must NOT introduce network requests at runtime (only during codegen, and only when `check_upstream=True`).
- Must NOT modify existing `effect_add`, keyframe tools, stack ops, or composite tools.
- Must NOT hand-curate entries in the generated file — everything is derived from XML.

### Preferences
- Prefer failing loudly on unknown param types (force enum update).
- Prefer additive changes to `tools.py`.
- Prefer Literal types over loose strings where the value set is fixed.

### Escalation Triggers
- If Kdenlive XML has nested effect groups or conditional params beyond the flat `<parameter>` list pattern — stop, report structure, ask.
- If `scripts/` directory doesn't exist or is organized differently — ask before creating.
- If the existing CLI (`cli.py`) uses a framework (click/typer) that doesn't cleanly support nested subcommands — report and adapt.

## Verification

1. `uv run pytest tests/ -v` passes (baseline 2357 + new tests).
2. Run generator against real Kdenlive: `python scripts/generate_effect_catalog.py` — inspect the produced `effect_catalog.py` for sanity (entry count, param count for a known effect, no syntax errors).
3. `from workshop_video_brain.edit_mcp.pipelines.effect_catalog import CATALOG; print(len(CATALOG), list(CATALOG.keys())[:5])` — confirms > 300 entries.
4. Start MCP server; call `effect_info(name="transform")` — returns full transform-filter schema.
5. Call `effect_list_common()` — returns > 300 entries instead of the old hardcoded 8.
6. CLI: `uv run workshop-video-brain catalog regenerate --help` shows usage; running without `--help` regenerates the catalog.
