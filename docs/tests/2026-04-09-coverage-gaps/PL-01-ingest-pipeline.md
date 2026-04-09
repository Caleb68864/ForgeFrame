---
scenario_id: "PL-01"
title: "Ingest Pipeline"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario PL-01: Ingest Pipeline

## Description
Tests `run_ingest` — the full scan-proxy-transcribe-silence pipeline entry point — and the
`IngestReport` dataclass. Covers the happy path (all steps succeed), idempotency (transcript
already on disk), per-asset error isolation (one bad asset does not abort others), empty
workspace (no files in `media/raw/`), and individual sub-step failures (proxy fails, whisper
unavailable, silence detection raises).

## Preconditions
- `uv` environment with `workshop-video-brain` installed in editable mode
- `tmp_path` fixture provides an isolated workspace directory tree
- All external adapters (`scan_directory`, `generate_proxy`, `whisper_engine`,
  `detect_silence`, `WorkspaceManager.save_manifest`) are replaced with `unittest.mock.patch`

## Test Cases

```
tests/unit/test_ingest_pipeline.py

class TestIngestReport:
    def test_default_field_values()
        # IngestReport() has scanned_count=0, proxied_count=0,
        # transcribed_count=0, silence_detected_count=0, errors=[]
    def test_errors_field_is_independent_list()
        # Two IngestReport() instances do not share the same errors list

class TestRunIngestEmptyWorkspace:
    def test_returns_report_with_zero_counts_when_no_assets(tmp_path)
        # scan_directory patched to return []
        # report.scanned_count == 0, all other counts == 0, errors == []

class TestRunIngestHappyPath:
    def test_single_asset_fully_processed(tmp_path)
        # scan_directory returns one MediaAsset
        # needs_proxy→True, generate_proxy succeeds, whisper_engine.is_available→True,
        # whisper_engine.extract_audio and transcribe succeed,
        # detect_silence returns [(2.5, 5.0)]
        # assert report.scanned_count == 1
        # assert report.proxied_count == 1
        # assert report.transcribed_count == 1
        # assert report.silence_detected_count == 1
        # assert report.errors == []
        # assert transcript JSON written to transcripts/
        # assert silence JSON written to markers/

    def test_idempotency_skips_asset_when_transcript_exists(tmp_path)
        # Pre-create the transcript JSON file for the asset
        # scan_directory returns same asset
        # whisper_engine.transcribe must NOT be called
        # report.transcribed_count == 0

    def test_multiple_assets_all_processed(tmp_path)
        # scan_directory returns two MediaAssets
        # Both succeed; report.scanned_count == 2, transcribed_count == 2

class TestRunIngestPartialFailures:
    def test_proxy_failure_does_not_stop_transcription(tmp_path)
        # generate_proxy raises RuntimeError
        # Transcription still runs and succeeds
        # report.proxied_count == 0, report.transcribed_count == 1
        # asset.proxy_status == ProxyStatus.failed

    def test_whisper_unavailable_skips_transcription(tmp_path)
        # whisper_engine.is_available() returns False
        # report.transcribed_count == 0, errors == []

    def test_ffmpeg_unavailable_skips_proxy_and_transcription(tmp_path)
        # config.ffmpeg_available = False
        # generate_proxy and whisper_engine.transcribe never called

    def test_audio_extraction_failure_skips_asset(tmp_path)
        # whisper_engine.extract_audio raises RuntimeError
        # report.transcribed_count == 0, silence NOT run for that asset

    def test_transcription_failure_sets_failed_status(tmp_path)
        # whisper_engine.transcribe raises RuntimeError
        # asset.transcript_status == TranscriptStatus.failed
        # report.transcribed_count == 0

    def test_silence_detection_failure_does_not_propagate(tmp_path)
        # detect_silence raises RuntimeError
        # report.transcribed_count == 1 (transcript still saved)
        # report.silence_detected_count == 0

    def test_asset_level_exception_recorded_in_errors(tmp_path)
        # Patch _process_asset to raise for one asset, succeed for another
        # report.errors contains one entry; second asset still counted

class TestRunIngestSilenceDetection:
    def test_silence_json_written_with_correct_structure(tmp_path)
        # detect_silence returns [(1.0, 3.5), (10.0, 12.0)]
        # Parse written JSON; assert list of {"start": float, "end": float}
        # report.silence_detected_count == 1

    def test_no_silence_does_not_increment_count(tmp_path)
        # detect_silence returns []
        # report.silence_detected_count == 0

class TestRunIngestManifestSave:
    def test_manifest_saved_after_all_assets(tmp_path)
        # WorkspaceManager.save_manifest called once regardless of asset count

    def test_manifest_save_failure_does_not_raise(tmp_path)
        # WorkspaceManager.save_manifest raises IOError
        # run_ingest returns normally with correct report
```

## Steps
1. Read source module to understand current API
2. Create test file at `tests/unit/test_ingest_pipeline.py`
3. Implement test cases with mocked dependencies
4. Run: `uv run pytest tests/unit/test_ingest_pipeline.py -v`

## Expected Results
- `IngestReport` fields increment atomically per completed step
- Errors are accumulated in `report.errors` without aborting sibling assets
- Idempotency check reads the transcript JSON path via `_transcript_json_path` — if it exists
  the asset is skipped entirely (no proxy, no transcription, no silence)
- Silence JSON structure is `[{"start": float, "end": float}, ...]`
- `WorkspaceManager.save_manifest` is always called, even when assets fail

## Pass / Fail Criteria
- Pass: All test cases pass, no import errors
- Fail: Any test fails or source API doesn't match expectations
