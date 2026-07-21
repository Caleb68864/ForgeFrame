---
type: phase-spec-index
master_spec: "docs/specs/2026-07-21-visual-research-mcp-tools.md"
date: 2026-07-21
sub_specs: 5
---

# Visual Research MCP Tool Surface + Agent Candidate Handshake -- Phase Specs

Refined from [2026-07-21-visual-research-mcp-tools.md](../2026-07-21-visual-research-mcp-tools.md).

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | Media read-only tools module | none | [sub-spec-1-research-media-tools.md](sub-spec-1-research-media-tools.md) |
| 2 | Transcript read-only tools module | none | [sub-spec-2-research-transcript-tools.md](sub-spec-2-research-transcript-tools.md) |
| 3 | Handshake pipeline module + generate/select tools | none | [sub-spec-3-handshake-pipeline-and-tools.md](sub-spec-3-handshake-pipeline-and-tools.md) |
| 4 | One-shot run + package export tools | SS-03 | [sub-spec-4-run-and-export-tools.md](sub-spec-4-run-and-export-tools.md) |
| 5 | Registry + E2E integration proof (integration sub-spec) | SS-01..04 | [sub-spec-5-registry-and-e2e-integration.md](sub-spec-5-registry-and-e2e-integration.md) |

Note: SS-05 serves as the cross-sub-spec integration sub-spec — no additional auto-generated integration sub-spec was added.

## Requirement Traceability Matrix

| Requirement | Covered By |
|-------------|-----------|
| R1: Ten tools registered via auto-discovery, zero shared-file edits | Sub-specs 1-4 (produce), Sub-spec 5 (asserts all + no `__init__.py` edits) |
| R2: Thin shells; only new logic module is `handshake.py` | Sub-spec 3 (structural checks), Sub-specs 1, 2, 4 (shell-only scope) |
| R3: Handshake state fully disk-persisted (stable IDs + fingerprint) | Sub-spec 3 |
| R4: Error contract (`tool_guard`, specific constructors, `_ok`/`_err`) | Sub-specs 1-4 (per-tool error-path tests) |
| R5: All FFmpeg through existing adapters | Sub-specs 1, 3, 4 (no-subprocess structural check in SS-03; shells call adapters only) |
| R6: Bounded overwrite semantics | Sub-specs 3, 4 |
| R7: Full suite green | Sub-spec 5 (whole-suite gate; each sub-spec gates locally) |

No orphaned requirements.

## Execution

Run `/forge-run docs/specs/2026-07-21-visual-research-mcp-tools.md` to execute all phase specs (point at the master spec file -- forge-run auto-detects linked phase specs).
