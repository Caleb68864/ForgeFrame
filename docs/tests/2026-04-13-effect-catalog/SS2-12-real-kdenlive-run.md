---
scenario_id: "SS2-12"
title: "Real Kdenlive run produces > 300 entries matching dir count"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, mechanical, sequential, requires-kdenlive]
---

# Scenario SS2-12: Real Kdenlive run produces > 300 entries matching dir count

## Description
Verifies `[MECHANICAL]` end-to-end against the real `/usr/share/kdenlive/effects/` (~376 files): generated `__local_count__` equals `len(os.listdir(...))` minus unparseable count.

## Preconditions
- Kdenlive installed; `/usr/share/kdenlive/effects/` present with ~376 XML files.

## Steps
1. Run `python scripts/generate_effect_catalog.py --no-upstream-check`.
2. Assert exit 0 and writes to `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py`.
3. Count files: `total = len([f for f in os.listdir("/usr/share/kdenlive/effects/") if f.endswith(".xml")])`.
4. Run generator a second time capturing logged "skipped" warnings; let `unparseable = N`.
5. Import generated module; assert `__local_count__ == total - unparseable`.
6. Assert `__local_count__ > 300`.
7. Assert `len(CATALOG) == __local_count__`.

## Expected Results
- All parseable Kdenlive effects represented; count > 300.

## Execution Tool
bash -- script invocation + python verification

## Pass / Fail Criteria
- **Pass:** Counts match and > 300.
- **Fail:** Mismatch or count <= 300.
