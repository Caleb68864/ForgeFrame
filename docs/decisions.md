
## 2026-07-21 — SS-05 completed manually after false idempotency-gate defer
- Symptom: Factory run c4ff0654 deferred SS-01 on `idempotency-strong-build-gate: grep -c '^@mcp\.tool()' src/workshop_video_brain/...` — the gate path omitted the `workshop-video-brain/` source-root prefix, so the grep hit a nonexistent file. SS-01's module was in fact delivered (via the SS-02 worker commit 14120bb, exactly 4 @mcp.tool(), 42-test unit tier green), and SS-05 was then blocked_upstream on the phantom failure.
- Fix: Verified SS-01 on disk against its structural gate with the correct path; authored SS-05's `tests/integration/test_research_tools_e2e.py` manually (registry assert for all ten research_* tools + full generate→select→export E2E, 2 passed).
- Surfaces: forge-factory idempotency-strong-build-gate path resolution when the project uses a nested `workshop-video-brain/src/` root; phase-spec Checks used repo-relative paths and passed, the factory's own gate did not.
- Watch: Future factory runs on this repo deferring sub-specs whose gate commands reference `src/...` without the `workshop-video-brain/` prefix — same false-negative pattern.
- Commit: SS-05 E2E test commit on branch 2026/07/21-2028-caleb-feat-visual-research-mcp-tools (this entry's commit).
