---
type: phase-spec-index
master_spec: "docs/specs/2026-04-09-phase3-pipeline-completeness.md"
date: 2026-04-09
sub_specs: 12
---

# Phase 3 Pipeline Completeness -- Phase Specs

Refined from [2026-04-09-phase3-pipeline-completeness.md](../2026-04-09-phase3-pipeline-completeness.md).

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | FFprobe Extended | none | [sub-spec-1-ffprobe-extended.md](sub-spec-1-ffprobe-extended.md) |
| 2 | Kdenlive Filter Engine | none | [sub-spec-2-kdenlive-filter-engine.md](sub-spec-2-kdenlive-filter-engine.md) |
| 3 | Render Profile Expansion | none | [sub-spec-3-render-profile-expansion.md](sub-spec-3-render-profile-expansion.md) |
| 4 | Capture Prep | none | [sub-spec-4-capture-prep.md](sub-spec-4-capture-prep.md) |
| 5 | VFR Detection | 1 | [sub-spec-5-vfr-detection.md](sub-spec-5-vfr-detection.md) |
| 6 | Full Render | 3 | [sub-spec-6-render-final.md](sub-spec-6-render-final.md) |
| 7 | QC Automation | 1 | [sub-spec-7-qc-check.md](sub-spec-7-qc-check.md) |
| 8 | Color Tools | 1, 2 | [sub-spec-8-color-tools.md](sub-spec-8-color-tools.md) |
| 9 | Effect Application | 2 | [sub-spec-9-effect-apply.md](sub-spec-9-effect-apply.md) |
| 10 | Project Profile | 1 | [sub-spec-10-project-profile.md](sub-spec-10-project-profile.md) |
| 11 | Compositing | 2 | [sub-spec-11-compositing.md](sub-spec-11-compositing.md) |
| 12 | Archive | none | [sub-spec-12-archive.md](sub-spec-12-archive.md) |

## Execution Order

**Tier 1 (parallel, no dependencies):** Sub-specs 1, 2, 3, 4, 12
**Tier 2 (after tier 1):** Sub-specs 5, 6, 7, 8, 9, 10, 11

## Execution

Run `/forge-run docs/specs/phase3-pipeline-completeness/` to execute all phase specs.
Run `/forge-run docs/specs/phase3-pipeline-completeness/ --sub N` to execute a single sub-spec.

## References

Harvested reference documents are in `references/` at the project root. See [Reference Index](../../references/Reference%20Index.md) for the full inventory.

### By Sub-Spec

| Sub-Specs | Reference | Path |
|-----------|-----------|------|
| 1, 7 | FFmpeg QC Filters (loudnorm, blackdetect, silencedetect, astats) | `references/ffmpeg-filters-qc.md` |
| 1, 5, 8, 10 | ffprobe Color Metadata and VFR Detection | `references/ffprobe-color-metadata.md` |
| 2, 8, 9, 11 | MLT XML Reference (filters, transitions, structure) | `references/mlt-xml-reference.md` |
| 3, 6 | Render Codec Reference (H.264, ProRes, DNxHR) | `references/render-codec-reference.md` |
| 1, 5 | VFR Detection and CFR Transcode | `references/vfr-cfr-transcode.md` |
| 2, 10, 11 | Kdenlive Documentation (existing) | `docs/reference/kdenlive/` |

### Sub-Specs with No External References Needed

- **Sub-Spec 4 (Capture Prep):** Pure Python logic generating markdown checklists
- **Sub-Spec 12 (Archive):** Python stdlib tarfile/zipfile streaming

## Open Reference Gaps

- **EBU R128 PDF:** Behind auth; thresholds already in spec (-14 LUFS YouTube, -24 LUFS minimum, -1 dBTP max)
- **Vimeo Guidelines:** Redirected; ProRes HQ settings are well-established standards
