---
type: phase-spec-index
master_spec: "../../2026-04-13-composite-blend-modes.md"
date: 2026-04-13
sub_specs: 2
---

# Phase Specs -- Composite Blend Modes for Kdenlive MCP

Refined from `docs/specs/2026-04-13-composite-blend-modes.md` -- Factory Run `ff-2026-04-13-composite-blend-modes`.

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | Blend Mode Discovery + Pipeline Extension | none | [sub-spec-1-blend-mode-discovery-pipeline-extension.md](sub-spec-1-blend-mode-discovery-pipeline-extension.md) |
| 2 | Rewire apply_pip + MCP Surface | 1 | [sub-spec-2-rewire-apply-pip-mcp-surface.md](sub-spec-2-rewire-apply-pip-mcp-surface.md) |

## Key Discovery (Stage 3)

Blend modes are NOT carried on the base MLT `composite` transition. They live on two separate services:
- `frei0r.cairoblend` (property `"1"`, string-enum): `cairoblend, screen, lighten, darken, multiply, add, overlay`.
- `qtblend` (property `compositing`, integer-enum): `destination_in=6, destination_out=8, source_over=0`.
- `subtract`: no native mapping -- escalate before shipping.

See `../memory.md` for the full discovery table and escalation triggers each worker must honor.
