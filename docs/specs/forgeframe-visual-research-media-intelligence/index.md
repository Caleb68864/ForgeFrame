---
type: phase-spec-index
master_spec: "docs/specs/2026-07-14-forgeframe-visual-research-media-intelligence.md"
date: 2026-07-14
sub_specs: 12
---

# ForgeFrame Visual Research & Media Intelligence — Phase Specs

Refined from [2026-07-14-forgeframe-visual-research-media-intelligence.md](../2026-07-14-forgeframe-visual-research-media-intelligence.md).

| Sub-Spec | Title | Wave | Dependencies | Phase Spec |
|----------|-------|------|--------------|------------|
| SS-01 | Domain models, ResearchConfig, transcript extension | 1 | none | [sub-spec-1-models-config.md](sub-spec-1-models-config.md) |
| SS-02 | FFmpeg runner pre-input seek + frame extraction | 2 | SS-01 | [sub-spec-2-frame-extraction.md](sub-spec-2-frame-extraction.md) |
| SS-03 | Scene-change detection adapter | 2 | SS-01 | [sub-spec-3-scene-detection.md](sub-spec-3-scene-detection.md) |
| SS-04 | Transcript parsers + repository | 2 | SS-01 | [sub-spec-4-transcript-repository.md](sub-spec-4-transcript-repository.md) |
| SS-07 | Local frame quality scoring | 2 | SS-01 | [sub-spec-7-frame-scoring.md](sub-spec-7-frame-scoring.md) |
| SS-08 | Perceptual deduplication | 2 | SS-01 | [sub-spec-8-deduplication.md](sub-spec-8-deduplication.md) |
| SS-09 | Manifest + research package export | 2 | SS-01 | [sub-spec-9-export.md](sub-spec-9-export.md) |
| SS-05 | Research region selector | 3 | SS-01, SS-04 | [sub-spec-5-regions.md](sub-spec-5-regions.md) |
| SS-12 | Optional research dependency extra | 3 | SS-07 | [sub-spec-12-optional-deps.md](sub-spec-12-optional-deps.md) |
| SS-06 | Adaptive candidate generation | 4 | SS-02, SS-03, SS-05 | [sub-spec-6-candidates.md](sub-spec-6-candidates.md) |
| SS-10 | Research service orchestrator | 5 | SS-04, SS-06, SS-07, SS-08, SS-09 | [sub-spec-10-service.md](sub-spec-10-service.md) |
| SS-11 | CLI commands with --json (integration) | 6 | SS-02, SS-03, SS-04, SS-10 | [sub-spec-11-cli.md](sub-spec-11-cli.md) |

**Integration gate:** SS-10 and SS-11 carry the `[INTEGRATION]` acceptance criteria that exercise the full transcript→regions→candidates→dedup→select→export flow and the CLI entry point end-to-end (master spec `## Verification`). No separate auto-generated integration sub-spec is added — it would duplicate SS-11.

## Requirement Traceability Matrix

| Requirement | Covered By |
|-------------|-----------|
| R1: exact-timestamp frame | SS-02, SS-11 |
| R2: burst extraction | SS-02, SS-06 |
| R3: scene detection + fallback | SS-03, SS-06 |
| R4: transcript load/search/slice | SS-04 |
| R5: research_video pipeline + default select | SS-05, SS-06, SS-07, SS-08, SS-10 |
| R6: research package + versioned manifest | SS-09, SS-10 |
| R7: --json on every command | SS-11 |
| R8: VFR-aware accurate seek | SS-02 |
| R9: single FFmpeg exec path | SS-02, SS-03 |
| R10: core runs with zero AI; scoring degrades | SS-07, SS-10 |
| R11: existing suite passes; CLI unchanged | SS-11 (full-suite check) |

## Execution

Run `/forge-run docs/specs/2026-07-14-forgeframe-visual-research-media-intelligence.md` to execute all phase specs (point at the master spec — forge-run auto-detects linked phase specs).
Run with `--sub N` to execute a single sub-spec.
