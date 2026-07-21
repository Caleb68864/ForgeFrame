---
type: phase-spec
sub_spec_id: SS-01
master_spec: "docs/specs/2026-07-21-visual-research-mcp-tools.md"
phase: run
depends_on: []
dispatch: factory
---

# SS-01. Media read-only tools module

Four read-only `research_*` tools wrapping existing ffmpeg adapters in one grouped domain module. Thin shells only — no new logic.

## Shared Context
- Registration: drop `research_media.py` into `edit_mcp/server/tools/` — `tools/__init__.py` auto-discovers via `pkgutil.iter_modules` (verified line 53). Do NOT edit any `__init__.py`.
- Envelope: `_ok(data) -> {"status": "success", "data": data}` from `tools_helpers`; errors via specific constructors from `server/errors.py`.
- Pattern exemplar: `edit_mcp/server/tools/transcript_markers.py` — module docstring, `from workshop_video_brain.server import mcp`, errors imported with `# noqa: F401` comment style, `@mcp.tool()` then `@tool_guard` directly beneath.
- Stage functions (all exist): `probe_media(path) -> MediaAsset` (`adapters/ffmpeg/probe.py:41`), `extract_frame(video_path, timestamp_seconds, output_path=None, quality="high", fmt="png") -> FrameCandidate` (`adapters/ffmpeg/frames.py:32`), `extract_frame_burst(video_path, start_seconds, end_seconds, interval_seconds=0.5, max_frames=20) -> list[FrameCandidate]` (`frames.py:116`), `detect_scene_changes(video_path, start_seconds=None, end_seconds=None, threshold=0.30, minimum_gap_seconds=1.0) -> list[SceneChange]` (`adapters/ffmpeg/scene.py:27`).
- Models serialize via `SerializableMixin` — return `model.to_dict()`-style output (check the mixin's method name and use it; do not hand-roll dict building).
- Adapter exceptions: catch `FileNotFoundError` → `missing_file`, `FFmpegNotFound` → `missing_binary("ffmpeg", install hint)`, `FFmpegTimeout`/probe errors → `media_unreadable`. `@tool_guard` is the backstop only.
- Fixture: `tests/fixtures/media_generated/greenscreen_reporter_720.mp4` (video-only, tracked).

## Implementation Steps

### Step 1. Failing registration + probe tests
Write `tests/unit/test_research_media_tools.py` using `tests/_testkit.py` (`unwrap`, `call_tool`, `assert_registered`, `requires_ffmpeg_ffprobe`). First tests: `assert_registered("research_probe_video", "research_extract_frame", "research_extract_frame_burst", "research_detect_scenes")`; `call_tool(research_probe_video, video_path=<fixture>)` returns `status == "success"` and `data["duration_seconds"] > 0`; nonexistent path returns the `missing_file` error envelope.
Run: `uv run pytest tests/unit/test_research_media_tools.py -q` → fails (module not found / not registered).

### Step 2. Create the module
Create `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_media.py` with the four `@mcp.tool()` + `@tool_guard` functions. Signatures mirror adapter defaults verbatim:
- `research_probe_video(video_path: str) -> dict`
- `research_extract_frame(video_path: str, timestamp_seconds: float, output_path: str | None = None, quality: str = "high", fmt: str = "png") -> dict` — payload includes the actual extracted timestamp (adapter clamps past-EOF seeks; pass any `vfr_warning` through).
- `research_extract_frame_burst(video_path: str, start_seconds: float, end_seconds: float, interval_seconds: float = 0.5, max_frames: int = 20) -> dict`
- `research_detect_scenes(video_path: str, start_seconds: float | None = None, end_seconds: float | None = None, threshold: float = 0.30, minimum_gap_seconds: float = 1.0) -> dict`
Paths in payloads use forward slashes.
Run: `uv run pytest tests/unit/test_research_media_tools.py -q` → registration + probe tests pass.

### Step 3. Extraction + error-path tests, then complete behaviors
Add tests: frame at `t=1.0` writes nonempty PNG and reports actual timestamp; past-EOF timestamp clamps and records actual; `research_detect_scenes` returns a list (possibly empty); monkeypatched `FFmpegNotFound` → `missing_binary` envelope. Implement until green.
Run: `uv run pytest tests/unit/test_research_media_tools.py -q` → all pass.

### Step 4. Full-suite + lint gate, commit
`uv run pytest tests/ -q` green; `uvx ruff check --select F401,F841` — zero new findings.
Commit: `factory(SS-01): research media read-only tools [factory-managed]`

## Interface Contracts
### research_media tool names
- Direction: Sub-spec 1 -> Sub-spec 5
- Owner: Sub-spec 1
- Shape: registered tool names `research_probe_video`, `research_extract_frame`, `research_extract_frame_burst`, `research_detect_scenes` (SS-05 asserts them via `assert_registered`)

## Verification Commands
- Unit: `uv run pytest tests/unit/test_research_media_tools.py -q`
- Full: `uv run pytest tests/ -q`
- Lint: `uvx ruff check --select F401,F841`

## Checks

Auto-generated from `[STRUCTURAL]` criteria. Each command exits 0 on pass, 1 with a one-line summary on fail.

| Criterion | Type | Command |
|-----------|------|---------|
| Module defines exactly four @mcp.tool() functions | [STRUCTURAL] | `[ $(grep -c "@mcp.tool()" workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_media.py) -eq 4 ] \|\| (echo "FAIL: expected exactly 4 @mcp.tool() in research_media.py" && exit 1)` |
| tool_guard directly beneath each tool decorator | [STRUCTURAL] | `[ $(grep -A1 "@mcp.tool()" workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_media.py \| grep -c "@tool_guard") -eq 4 ] \|\| (echo "FAIL: tool_guard not directly under all 4 @mcp.tool()" && exit 1)` |
