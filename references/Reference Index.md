# Reference Index -- Phase 3 Pipeline Completeness

## Summary

Analyzed 12 sub-specs covering 9 features for the ForgeFrame Phase 3 Pipeline Completeness spec. Identified 22 technology references (14 explicit, 8 implied). Harvested 5 reference documents, reused 1 existing, skipped 10 (well-known or out-of-scope), 2 unresolved (low impact).

## Key Technologies

| Technology | Version | Status | Reference |
|-----------|---------|--------|-----------|
| FFmpeg / FFprobe | system | Harvested | [ffmpeg-filters-qc.md](ffmpeg-filters-qc.md), [ffprobe-color-metadata.md](ffprobe-color-metadata.md) |
| MLT Framework | 7.x | Harvested | [mlt-xml-reference.md](mlt-xml-reference.md) |
| H.264 / libx264 | system | Harvested | [render-codec-reference.md](render-codec-reference.md) |
| ProRes / prores_ks | system | Harvested | [render-codec-reference.md](render-codec-reference.md) |
| DNxHR / dnxhd | system | Harvested | [render-codec-reference.md](render-codec-reference.md) |
| VFR/CFR Transcode | - | Harvested | [vfr-cfr-transcode.md](vfr-cfr-transcode.md) |
| Kdenlive | latest | Reused | [docs/reference/kdenlive/](../docs/reference/kdenlive/) |
| Pydantic v2 | >=2.0,<3 | Skipped | Established codebase patterns |
| FastMCP | >=2.0 | Skipped | Established codebase patterns |
| Python 3.12+ | 3.12+ | Skipped | Language runtime |
| PyYAML | >=6.0 | Skipped | Standard usage |
| pytest | latest | Skipped | 1,242+ existing tests |

## Harvested References

| File | Covers Sub-Specs | Trust |
|------|------------------|-------|
| [ffmpeg-filters-qc.md](ffmpeg-filters-qc.md) | 1, 7 | High |
| [ffprobe-color-metadata.md](ffprobe-color-metadata.md) | 1, 5, 8, 10 | High |
| [mlt-xml-reference.md](mlt-xml-reference.md) | 2, 8, 9, 11 | Canonical |
| [render-codec-reference.md](render-codec-reference.md) | 3, 6 | High |
| [vfr-cfr-transcode.md](vfr-cfr-transcode.md) | 1, 5 | High |

## Existing References Reused

| Reference | Location | Covers |
|-----------|----------|--------|
| Kdenlive Docs | [docs/reference/kdenlive/](../docs/reference/kdenlive/) | 2, 10, 11 |

## Missing or Blocked References

| Reference | Reason | Impact |
|-----------|--------|--------|
| EBU R128 (PDF) | Requires auth/purchase | Low -- thresholds in spec |
| Vimeo Guidelines | Page redirects | Low -- ProRes HQ is standard |

## Related Reference Clusters

**FFmpeg/FFprobe Cluster:** ffmpeg-filters-qc.md + ffprobe-color-metadata.md + vfr-cfr-transcode.md + render-codec-reference.md
- Covers: Sub-specs 1, 3, 5, 6, 7, 8, 10

**MLT/Kdenlive Cluster:** mlt-xml-reference.md + docs/reference/kdenlive/
- Covers: Sub-specs 2, 8, 9, 10, 11

**No reference needed:** Sub-specs 4 (Capture Prep) and 12 (Archive) -- pure Python logic, no external technology dependencies
