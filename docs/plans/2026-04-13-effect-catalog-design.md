---
date: 2026-04-13
topic: "Effect catalog + generator for Kdenlive MCP"
author: Caleb Bennett
status: draft
tags:
  - design
  - effect-catalog
  - kdenlive
  - mcp
---

# Effect Catalog + Generator — Design

## Summary
Build a parser that reads Kdenlive's installed effect XML descriptions at `/usr/share/kdenlive/effects/*.xml`, cross-checks against the upstream Kdenlive GitHub master, and emits a typed Python registry at `workshop_video_brain/edit_mcp/pipelines/effect_catalog.py` containing ~150 effects with params, types, ranges, and a `keyframable` flag per param. Ship an `effect_info(name)` MCP tool for LLM introspection and replace the 8-entry `effect_list_common` stub with a catalog-backed impl of the same tool name.

## Approach Selected
**Generated Python module with typed data + dual invocation (script + CLI subcommand).** Parser reads local XML, emits a checked-in Python module so no runtime file I/O is needed. A CI script and a user-facing CLI both call the same underlying `build_catalog()` function. MCP exposes a typed introspection tool so LLMs can query param schemas without client-side catalog duplication.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Generator (same function, two entrypoints)                   │
│  - scripts/generate_effect_catalog.py (CI + manual)          │
│  - `workshop-video-brain catalog regenerate` (CLI)           │
│  - Both call: pipelines.effect_catalog_gen.build_catalog()   │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ pipelines/effect_catalog_gen.py (new — generator logic)      │
│  - discover_xml_files(local_dir, remote_dir?)                │
│  - parse_effect_xml(path) -> EffectDef                       │
│  - fetch_github_master_effects() -> list[EffectDef]          │
│  - diff_against_upstream(local, remote) -> DiffReport        │
│  - emit_python_module(effects, output_path)                  │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ pipelines/effect_catalog.py (GENERATED, checked in)          │
│  - CATALOG: dict[str, EffectDef]   # keyed by kdenlive_id    │
│  - EffectDef / ParamDef / ParamType (typed dataclasses)      │
│  - find_by_name(name) / find_by_service(mlt_service)         │
│  - __generated_at__ / __source_version__ metadata            │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ MCP surface (server/tools.py)                                │
│  - effect_info(name) -> dict         # new                   │
│  - effect_list_common()              # catalog-backed rewrite│
└──────────────────────────────────────────────────────────────┘
```

## Components

### `pipelines/effect_catalog_gen.py` (new, generator)
Not imported at runtime. Only invoked by the codegen script/CLI.

- `build_catalog(local_dir: Path, check_upstream: bool = True) -> tuple[list[EffectDef], DiffReport]`
- `parse_effect_xml(xml_path: Path) -> EffectDef` — walks `<kdenlive_effect>` tree, extracts `name`, `id`, `tag` (MLT service), `description`, `params[]`
- `parse_param(param_element) -> ParamDef` — extracts `name`, `type`, `min`, `max`, `default`, `keyframes` attribute, `value` enums where present
- `fetch_github_master_effects() -> list[str]` — `git ls-remote` + sparse clone of `data/effects/` from `mltframework/kdenlive` master
- `diff_against_upstream(local, remote) -> DiffReport` — set-diff of effect ids; warn on upstream-only additions
- `emit_python_module(effects, output_path)` — renders `effect_catalog.py` with frozen dataclasses + dict literal, includes generation metadata

### `pipelines/effect_catalog.py` (generated, checked in)
Pure data module + tiny helpers. Imported at runtime.

```python
from dataclasses import dataclass
from enum import Enum
from typing import Literal

class ParamType(Enum):
    DOUBLE = "double"
    INTEGER = "integer"
    BOOL = "bool"
    COLOR = "color"              # #RRGGBB/#RRGGBBAA
    KEYFRAME = "keyframe"        # scalar animation
    ANIMATED = "animated"        # rect animation
    GEOMETRY = "geometry"        # rect (static or animated)
    CONSTANT = "constant"
    LIST = "list"                # enum-like
    STRING = "string"

@dataclass(frozen=True, slots=True)
class ParamDef:
    name: str
    type: ParamType
    default: str | None
    min: float | None
    max: float | None
    values: tuple[str, ...] = ()   # for LIST type
    keyframable: bool = False

@dataclass(frozen=True, slots=True)
class EffectDef:
    kdenlive_id: str
    mlt_service: str
    display_name: str              # English canonical (localizations stripped)
    description: str
    params: tuple[ParamDef, ...]

CATALOG: dict[str, EffectDef] = { ... }  # ~150 entries
__generated_at__ = "2026-04-13T00:00:00Z"
__source_version__ = "kdenlive-25.12.3"

def find_by_name(name: str) -> EffectDef | None: ...
def find_by_service(mlt_service: str) -> EffectDef | None: ...
```

### `edit_mcp/server/tools.py` changes
- **New:** `effect_info(name: str) -> dict` — returns JSON-serializable dict of an `EffectDef` by `kdenlive_id` or `mlt_service`. Schema: `{"kdenlive_id","mlt_service","display_name","description","params":[{"name","type","default","min","max","values","keyframable"}]}`
- **Replace body of existing `effect_list_common`** — drop the 8-entry hand-curated dict; return a trimmed catalog view (kdenlive_id + display_name + mlt_service + short description for all entries). Tool signature unchanged.

### CLI subcommand
`workshop-video-brain catalog regenerate [--no-upstream-check] [--output <path>]` — calls `build_catalog` and writes the generated module. Announces a diff summary.

## Data Flow

**Build-time:**
1. Script/CLI calls `build_catalog(Path("/usr/share/kdenlive/effects"))`
2. Parser glob-walks `*.xml`, filters to `<kdenlive_effect>` root elements, parses each
3. Extracts English canonical `display_name` (prefer `<name>` without `lang=` attr; fall back to the un-translated `<name>` element)
4. Optionally fetches upstream `data/effects/` via sparse clone to `/tmp/kdenlive-upstream`; diffs
5. Generates Python module; writes to `pipelines/effect_catalog.py`
6. Human reviews diff, commits

**Runtime:**
1. MCP tool call lands in `server/tools.py`
2. `effect_info(name)` → `effect_catalog.find_by_name(name) or find_by_service(name)` → dict-ify `EffectDef` → `_ok(...)`
3. `effect_list_common()` → iterate `CATALOG.values()` → trim to summary fields → `_ok(...)`

## Decisions Locked

- **Generator invocation:** both script (`scripts/generate_effect_catalog.py`) and CLI subcommand (`workshop-video-brain catalog regenerate`). Both call the same `build_catalog()` function in `pipelines/effect_catalog_gen.py`.
- **Registry format:** generated Python module with typed frozen dataclasses + module-level `CATALOG: dict`. No runtime file I/O.
- **MCP `effect_info` tool:** ship as part of this spec. Schema mirrors `EffectDef`.
- **`effect_list_common`:** drop-in replacement. Tool signature unchanged; internals re-sourced from catalog.
- **`keyframable` default:** `False` when attribute absent, BUT any param whose `type` is `keyframe`, `animated`, or `geometry` is force-marked `keyframable: True` regardless.
- **Param type mapping:** `ParamType` enum in the generated module, one value per distinct Kdenlive type string.

## Error Handling

- **Local XML dir missing** (`/usr/share/kdenlive/effects/` not present) → generator fails loudly with install hint. Only affects codegen, not runtime.
- **Unparseable XML file** → skip with a warning logged to stdout; include skipped count in diff report. Do not crash.
- **Unknown param type** (new Kdenlive version introduces a type not in the enum) → generator fails; requires enum update. Intentional — force humans to categorize.
- **Upstream fetch failure** (no internet, GitHub rate limit) → generator continues with local-only; emits a `DiffReport` with `upstream_check: "skipped"`.
- **Duplicate `kdenlive_id`** across XML files → last-parsed wins, warning logged with both file paths.
- **Generated module import error** (e.g., broken after a regen) → `effect_info` and `effect_list_common` tools surface `_err` with pointer to `scripts/generate_effect_catalog.py` as the fix path.
- **`effect_info(unknown_name)`** → `_err("Effect not found: {name}. Try `effect_list_common` for the registry.")`.

## Open Questions

- None — scope clean.

## Approaches Considered

- **A — Generated Python module + dual invocation (selected).** Typed, IDE-friendly, no runtime file I/O, one source of truth, discoverable via CLI.
- **B — YAML data file + loader.** Editable without regen, but no type checking and easy to drift from Kdenlive reality. Rejected.
- **C — Runtime parse on startup.** Simplest code, but costs ~100ms on MCP server boot and requires `/usr/share/kdenlive/effects/` to be present on the runtime machine. Rejected — some deployments (remote MCP) won't have Kdenlive installed.

## Next Steps

- [ ] Turn this into a Forge spec
- [ ] Spec 4 (Stack presets) will consume catalog `ParamType` info to validate saved presets
- [ ] Spec 7 (Effect wrappers) will consume catalog to generate per-effect wrapper tools automatically
