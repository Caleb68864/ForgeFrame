---
type: phase-spec-index
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-effect-catalog.md"
date: 2026-04-13
sub_specs: 3
---

# Phase Specs — Effect Catalog + Generator for Kdenlive MCP

Refined from `docs/specs/2026-04-13-effect-catalog.md` — Factory Run 2026-04-13-effect-catalog.

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | Catalog Data Model + Parser | none | [sub-spec-1-catalog-data-model-parser.md](sub-spec-1-catalog-data-model-parser.md) |
| 2 | Generator + Emitter + Upstream Check | 1 | [sub-spec-2-generator-emitter-upstream-check.md](sub-spec-2-generator-emitter-upstream-check.md) |
| 3 | MCP Tool Surface + CLI Subcommand + Integration | 1, 2 | [sub-spec-3-mcp-tool-cli-integration.md](sub-spec-3-mcp-tool-cli-integration.md) |

## Execution Order

Sequential. Sub-spec 2 imports sub-spec 1's data model. Sub-spec 3 imports the generated module produced by sub-spec 2.

## Key Interface Contracts

- **Sub-spec 1 -> 2:** `EffectDef`, `ParamDef`, `ParamType`, `parse_effect_xml` exported from `workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen`.
- **Sub-spec 2 -> 3:** generated module `workshop_video_brain.edit_mcp.pipelines.effect_catalog` with `CATALOG`, `find_by_name`, `find_by_service`.
- **Sub-spec 2 -> 3:** `build_catalog`, `emit_python_module`, `_detect_source_version` reused by the CLI subcommand.

## Codebase Notes

- CLI framework: **click** (confirmed at `workshop-video-brain/src/workshop_video_brain/app/cli.py`).
- Test framework: **pytest** with function-style tests; integration tests at `tests/integration/`, unit at `tests/unit/`.
- Build: `uv sync`. Test: `uv run pytest tests/ -v`.
- `/usr/share/kdenlive/effects/` on target machine: 376 entries (375 `.xml` + `update/` subdir).
- Kdenlive version: 25.12.3-1 (Arch).
- No `scripts/` directory exists yet at repo root — sub-spec 2 creates it.
