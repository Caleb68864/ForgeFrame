# Harvest Report -- Phase 3 Pipeline Completeness

## What Was Analyzed

- **Plan file:** `docs/specs/phase3-pipeline-completeness/` (12 sub-specs + master spec)
- **Repository context:** Python 3.12+, Pydantic v2, FastMCP, PyYAML, Jinja2, Click, faster-whisper, yt-dlp
- **Existing references:** `docs/reference/kdenlive/` (2 files), `docs/reference/claude-code/` (4 files), `docs/reference/original/` (3 files)

## What Was Found

### Explicit Technologies (14)
FFmpeg/FFprobe, Kdenlive, MLT Framework, Python 3.12+, Pydantic v2, FastMCP, PyYAML, H.264/libx264, ProRes/prores_ks, DNxHR/dnxhd, AAC, PCM/pcm_s24le, tarfile/zipfile, pytest

### Implied Technologies (8)
BT.709/BT.601/BT.2020 color standards, HDR (PQ/HLG), EBU R128 loudness, VFR/CFR concepts, Kdenlive XML format, MLT filter/transition elements, LUT file formats, frei0r plugins

## What Was Reused

- **Kdenlive Documentation** (`docs/reference/kdenlive/`) -- partial but sufficient alongside new MLT XML reference

## What Was Downloaded

| Artifact | Size | Source |
|----------|------|--------|
| ffmpeg-filters-qc.md | ~3.5 KB | Web search + mirrors |
| ffprobe-color-metadata.md | ~3.5 KB | Web search + community |
| mlt-xml-reference.md | ~4.5 KB | mltframework.org (direct) |
| render-codec-reference.md | ~4 KB | Web search + ASF guidelines |
| vfr-cfr-transcode.md | ~3 KB | Web search + FFmpeg docs |

## What Was Linked Instead of Copied

No external repos cloned. All references are distilled into project-level markdown documents.

## What Remains Uncertain

- **EBU R128 Full Standard:** PDF behind auth. Impact: low (threshold values already documented in spec as -24 LUFS min, -14 LUFS YouTube target).
- **Vimeo Compression Guidelines:** Page redirects. Impact: low (ProRes HQ settings are well-established).

## Suggested Next Reference Actions

1. **None blocking.** All harvested references provide sufficient detail for implementation.
2. **Optional:** If Vimeo settings need verification, manually visit `https://help.vimeo.com/hc/en-us` and search for compression guidelines.
3. **Optional:** Bookmark `https://trac.ffmpeg.org/wiki/` for when Anubis protection clears (FFmpeg wiki pages were blocked during harvest).
