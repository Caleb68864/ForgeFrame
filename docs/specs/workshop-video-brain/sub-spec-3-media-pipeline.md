---
type: phase-spec
master_spec: "../2026-04-08-workshop-video-brain.md"
sub_spec: 3
title: "Media Pipeline + Transcripts"
dependencies: [2]
date: 2026-04-08
---

# Sub-Spec 3: Media Pipeline + Transcripts

## Scope

Media inventory scanning via ffprobe, automatic proxy generation with configurable thresholds, transcript generation via faster-whisper with Whisper fallback, silence detection, loudness analysis, ingest pipeline orchestration.

## Interface Contracts

### Provides (to Sub-Spec 4a+)

- **FFprobe adapter** at `edit_mcp/adapters/ffmpeg/probe.py`:
  - `probe_media(path: Path) -> MediaAsset` -- extracts all metadata fields
  - `scan_directory(dir: Path, extensions: set[str] | None) -> list[MediaAsset]` -- recursive scan

- **Proxy adapter** at `edit_mcp/adapters/ffmpeg/proxy.py`:
  - `ProxyPolicy` dataclass with thresholds (max_resolution, heavy_codecs, max_bitrate)
  - `needs_proxy(asset: MediaAsset, policy: ProxyPolicy) -> bool`
  - `generate_proxy(asset: MediaAsset, output_dir: Path, policy: ProxyPolicy) -> Path`

- **Silence detector** at `edit_mcp/adapters/ffmpeg/silence.py`:
  - `detect_silence(path: Path, threshold_db: float, min_duration: float) -> list[tuple[float, float]]`

- **Whisper engine** at `edit_mcp/adapters/stt/whisper_engine.py`:
  - `transcribe(audio_path: Path, model: str, language: str | None) -> Transcript`
  - `is_available() -> bool`
  - Exports SRT via `transcript_to_srt(transcript: Transcript) -> str`

- **Ingest pipeline** at `edit_mcp/pipelines/ingest.py`:
  - `run_ingest(workspace: Workspace, config: Config) -> IngestReport`
  - Orchestrates: scan → proxy → transcribe → silence detect
  - Idempotent: skips already-processed assets

### Requires (from Sub-Spec 2)

- `MediaAsset` model with all fields
- `Transcript`, `TranscriptSegment` models
- `Workspace` model and `WorkspaceManager`
- Path utilities (`safe_filename`, `versioned_path`)
- Structured logging

## Patterns to Follow

- **FFprobe**: Run `ffprobe -v quiet -print_format json -show_format -show_streams {path}` via `subprocess.run()`. Parse JSON output.
- **FFmpeg proxy**: `ffmpeg -i {input} -vf scale=-2:720 -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k {output}`
- **Silence detection**: `ffmpeg -i {input} -af silencedetect=noise={threshold}dB:d={duration} -f null -` then parse stderr for `silence_start` / `silence_end` lines.
- **faster-whisper**: `from faster_whisper import WhisperModel; model = WhisperModel(size, device="cpu"); segments, info = model.transcribe(path)`
- **Idempotency**: Check for existing output files before processing. Use file hash to detect changes.

## Implementation Steps

### Step 1: Create ffprobe adapter

**Create** `edit_mcp/adapters/ffmpeg/probe.py`:
- `probe_media(path)` -- runs ffprobe subprocess, parses JSON, maps to MediaAsset fields
- `scan_directory(dir, extensions)` -- globs for media files, calls `probe_media` on each, catches per-file errors
- Default extensions: `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, `.mts`, `.m2ts`, `.mp3`, `.wav`, `.flac`
- Uses `hashlib.md5` on first 64KB for quick fingerprint

### Step 2: Create proxy adapter

**Create** `edit_mcp/adapters/ffmpeg/proxy.py`:
- `ProxyPolicy` dataclass: `max_width=1920`, `max_height=1080`, `heavy_codecs={"hevc","h265","prores"}`, `max_bitrate_mbps=50`
- `needs_proxy(asset, policy)` -- checks resolution, codec, bitrate against thresholds
- `generate_proxy(asset, output_dir, policy)` -- runs ffmpeg, names output as `{original_stem}_proxy.mp4`
- `proxy_path_for(asset, proxy_dir)` -- deterministic mapping from source to proxy path
- Skips if proxy already exists and is newer than source

### Step 3: Create silence detector

**Create** `edit_mcp/adapters/ffmpeg/silence.py`:
- `detect_silence(path, threshold_db=-30, min_duration=2.0)` -- runs ffmpeg silencedetect filter
- Parses stderr for `silence_start: {time}` and `silence_end: {time}` pairs
- Returns list of `(start_seconds, end_seconds)` tuples
- Stores results as JSON in workspace `markers/` directory

### Step 4: Create whisper engine

**Create** `edit_mcp/adapters/stt/whisper_engine.py`:
- `is_available()` -- tries `import faster_whisper`, falls back to `import whisper`, returns bool
- `transcribe(audio_path, model="small", language=None)` -- uses faster-whisper if available, else whisper
- Converts output to `Transcript` model with `TranscriptSegment` list
- `transcript_to_srt(transcript)` -- formats segments as SRT string
- `transcript_to_json(transcript)` -- serializes to JSON
- `extract_audio(video_path, output_path)` -- uses ffmpeg to extract audio if input is video

### Step 5: Create ingest pipeline

**Create** `edit_mcp/pipelines/ingest.py`:
- `IngestReport` dataclass: scanned_count, proxied_count, transcribed_count, silence_detected_count, errors
- `run_ingest(workspace, config)`:
  1. Scan `media/raw/` for media files
  2. For each asset: check if already processed (JSON sidecar in `transcripts/`)
  3. Generate proxy if `needs_proxy()` and no existing proxy
  4. Extract audio if needed, run whisper transcription
  5. Run silence detection
  6. Save all artifacts: transcript JSON + text + SRT in `transcripts/`, silence JSON in `markers/`
  7. Update workspace manifest with asset inventory
- Log progress per asset
- Catch per-asset errors, continue processing

### Step 6: Write tests

**Create**:
- `tests/unit/test_probe.py` -- mock subprocess to test JSON parsing, test scan_directory with fixture files
- `tests/unit/test_proxy.py` -- test `needs_proxy()` logic with various asset profiles
- `tests/integration/test_ingest_pipeline.py` -- test with tiny fixture media files (if ffmpeg available), test idempotency

**Create** `tests/fixtures/media/` with:
- A tiny valid `.mp4` file (can be generated with ffmpeg: `ffmpeg -f lavfi -i testsrc=duration=2:size=320x240:rate=25 -f lavfi -i sine=frequency=440:duration=2 tests/fixtures/media/sample.mp4`)

## Verification Commands

```bash
# Run unit tests
uv run pytest tests/unit/test_probe.py tests/unit/test_proxy.py -v

# Generate test fixture (requires ffmpeg)
ffmpeg -f lavfi -i testsrc=duration=2:size=320x240:rate=25 -f lavfi -i sine=frequency=440:duration=2 -y tests/fixtures/media/sample.mp4

# Test probe on fixture
uv run python -c "
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from pathlib import Path
asset = probe_media(Path('tests/fixtures/media/sample.mp4'))
print(f'Duration: {asset.duration}, Resolution: {asset.width}x{asset.height}')
"

# Run integration test (requires ffmpeg)
uv run pytest tests/integration/test_ingest_pipeline.py -v
```

## Acceptance Criteria

- [ ] `probe.py` extracts all required metadata fields
- [ ] Scanner handles mixed media folders without crashing on bad files
- [ ] Bad files produce isolated error entries, not pipeline crashes
- [ ] `proxy.py` generates proxies when thresholds met
- [ ] Proxy thresholds configurable via workspace config
- [ ] Proxies map back to source assets deterministically
- [ ] Existing valid proxies not regenerated on re-run
- [ ] `whisper_engine.py` produces full transcript, timestamped segments, SRT, JSON
- [ ] Whisper model size configurable (default: `small`)
- [ ] Engine falls back gracefully if faster-whisper unavailable
- [ ] `silence.py` detects silence gaps > threshold
- [ ] All artifacts stored in workspace under `transcripts/` and `markers/`
- [ ] Ingest pipeline is idempotent
