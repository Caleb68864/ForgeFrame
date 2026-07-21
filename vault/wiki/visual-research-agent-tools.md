# Visual research agent tools (`research_*`)

Ten MCP tools expose the deterministic visual-research pipeline to agents. They operate on **bare media/transcript file paths** (not workspaces) and never construct FFmpeg commands — everything routes through the existing adapters.

## Read-only probes

- `research_probe_video(video_path)` — ffprobe result (duration, streams, `is_vfr`, geometry).
- `research_extract_frame(video_path, timestamp_seconds, ...)` — one frame; past-EOF seeks clamp and the payload reports `actual_timestamp_seconds`; VFR sources force accurate seek and carry `metadata.vfr_warning`.
- `research_extract_frame_burst(video_path, start_seconds, end_seconds, ...)` — uniform burst. **Caveat:** frames land beside the source video (the adapter has no output-dir parameter yet).
- `research_detect_scenes(video_path, ...)` — scene-change timestamps.
- `research_transcript_search(transcript_path, query, limit)` / `research_transcript_context(transcript_path, timestamp_seconds, window_seconds)` — `.json`/`.srt`/`.vtt`; search results are **unscored**, transcript order.

## The two-call handshake (agent picks the frame)

1. `research_generate_candidates(video_path, output_dir, query=..., start_seconds=..., end_seconds=...)` writes `candidates/*.png` + `candidates.json` (schema v1: stable `cand-NNN` ids, source fingerprint, empty `selections`).
2. The agent **reads the candidate PNGs itself** and judges them against the request.
3. `research_select_candidate(candidates_dir, ["cand-003"])` persists the selection into `candidates.json`, then exports the package (`index.md`, `manifest.json`, `screenshots/`).

State is disk-only between calls. If the source video changed since generate, select refuses with a fingerprint mismatch — re-run generate.

## Deterministic one-shots

- `research_run(video_path, output_dir, query=..., start_seconds=..., end_seconds=...)` — full pipeline, auto-selects the top-scored frame per region (mirrors `wvb research`).
- `research_export_package(candidates_dir, output_dir)` — exports from a handshake dir without a selection: uses recorded `selections`, else top-scored per region.

## Overwrite safety

Every disk-writing tool refuses a non-empty `output_dir` without `overwrite=True`, and `overwrite` is only honored when the directory already contains a `manifest.json`/`candidates.json` — never under `media/raw/` or `projects/source/`.

Spec: `docs/specs/2026-07-21-visual-research-mcp-tools.md`. Related: [[golden-fixture-testing]].
