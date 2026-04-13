---
scenario_id: "SR-01"
title: "Masking pipeline module exports correct surface"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - sub-spec-1
---

# Scenario SR-01: Masking pipeline module exports correct surface

## Description
Verifies the [STRUCTURAL] requirement that `pipelines/masking.py` exports the full public API. Ensures downstream code and tests can import the expected names.

## Preconditions
- `uv sync` complete
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/masking.py` present

## Steps
1. Run: `uv run python -c "from workshop_video_brain.edit_mcp.pipelines import masking; print([n for n in ['MaskShape','MaskParams','shape_to_points','build_rotoscoping_xml','build_object_mask_xml','build_chroma_key_xml','build_chroma_key_advanced_xml','color_to_mlt_hex'] if hasattr(masking, n)])"`
2. Capture stdout.

## Expected Results
- All eight names are present in the printed list: `MaskShape`, `MaskParams`, `shape_to_points`, `build_rotoscoping_xml`, `build_object_mask_xml`, `build_chroma_key_xml`, `build_chroma_key_advanced_xml`, `color_to_mlt_hex`.
- No `ImportError` or `AttributeError` is raised.

## Execution Tool
bash — run the import probe command from the repo root.

## Pass / Fail Criteria
- **Pass:** all 8 names present, no errors.
- **Fail:** missing name, import error, or module not found.
