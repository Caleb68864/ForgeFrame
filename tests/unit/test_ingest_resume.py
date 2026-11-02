"""Cache recovery repairs missing artifacts without repeating completed STT."""
import os
from unittest.mock import Mock

from workshop_video_brain.app.config import Config
from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import ProxyPolicy
from workshop_video_brain.edit_mcp.pipelines import ingest


def setup(tmp_path):
    directories = {name: tmp_path / name for name in ("proxies", "audio", "transcripts", "markers")}
    for path in directories.values():
        path.mkdir()
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"source audio/video")
    asset = MediaAsset(path=str(source), media_type="video", audio_codec="aac", channels=1)
    transcript = Transcript(asset_id=asset.id, raw_text="hello", segments=[
        TranscriptSegment(start_seconds=0, end_seconds=1, text="hello")])
    config = Config(None, None, "ffmpeg", "small", True, True)
    return directories, source, asset, transcript, config


def process(dirs, asset, config, **kwargs):
    report = ingest.IngestReport()
    ingest._process_asset(asset, dirs["proxies"], dirs["audio"], dirs["transcripts"],
                          dirs["markers"], config, ProxyPolicy(), report, **kwargs)
    return report


def test_cached_transcript_repairs_missing_proxy_subtitles_and_silence(tmp_path, monkeypatch):
    dirs, source, asset, transcript, config = setup(tmp_path)
    cache = dirs["transcripts"] / "clip_transcript.json"
    cache.write_text(transcript.to_json())
    original = cache.read_bytes(), cache.stat().st_mtime_ns
    transcribe = Mock(side_effect=AssertionError("STT must not repeat"))
    monkeypatch.setattr(ingest.whisper_engine, "transcribe", transcribe)
    monkeypatch.setattr(ingest.whisper_engine, "is_available", lambda: False)
    monkeypatch.setattr(ingest, "needs_proxy", lambda *args: True)
    proxy = dirs["proxies"] / "clip_proxy.mp4"
    monkeypatch.setattr(ingest, "proxy_path_for", lambda *args: proxy)
    def generate(*args):
        proxy.write_bytes(b"complete proxy")
        return proxy
    monkeypatch.setattr(ingest, "generate_proxy", generate)
    monkeypatch.setattr(ingest, "detect_silence", lambda path: [(1, 2)])
    report = process(dirs, asset, config)
    assert not report.errors
    assert report.proxied_count == 1 and report.transcribed_count == 0
    assert (cache.read_bytes(), cache.stat().st_mtime_ns) == original
    assert (dirs["transcripts"] / "clip_transcript.srt").stat().st_size > 0
    assert (dirs["transcripts"] / "clip_transcript.txt").read_text() == "hello"
    assert (dirs["markers"] / "clip_silence.json").is_file()
    transcribe.assert_not_called()


def test_changed_source_refreshes_extracted_audio_before_transcription(tmp_path, monkeypatch):
    dirs, source, asset, transcript, config = setup(tmp_path)
    cache = dirs["transcripts"] / "clip_transcript.json"
    cache.write_text(transcript.to_json())
    audio = dirs["audio"] / "clip_audio.wav"
    audio.write_bytes(b"old audio")
    for path in (cache, audio):
        os.utime(path, (source.stat().st_mtime - 10, source.stat().st_mtime - 10))
    monkeypatch.setattr(ingest, "needs_proxy", lambda *args: False)
    monkeypatch.setattr(ingest.whisper_engine, "is_available", lambda: True)
    def extract(src, out):
        out.write_bytes(b"new audio")
    def transcribe(audio_path, **kwargs):
        assert audio_path.read_bytes() == b"new audio"
        return transcript
    monkeypatch.setattr(ingest.whisper_engine, "extract_audio", extract)
    monkeypatch.setattr(ingest.whisper_engine, "transcribe", transcribe)
    monkeypatch.setattr(ingest, "detect_silence", lambda path: [])
    pending, complete = [], []
    report = process(dirs, asset, config, pending_output=pending.append, completed_output=complete.append)
    assert not report.errors and report.transcribed_count == 1
    assert pending == complete == [audio]
    assert cache.stat().st_mtime >= source.stat().st_mtime


def test_video_without_audio_never_requests_transcription(tmp_path, monkeypatch):
    dirs, source, asset, transcript, config = setup(tmp_path)
    asset.audio_codec = ""
    asset.channels = 0
    monkeypatch.setattr(ingest, "needs_proxy", lambda *args: False)
    transcribe = Mock(side_effect=AssertionError("video-only source"))
    monkeypatch.setattr(ingest.whisper_engine, "transcribe", transcribe)
    report = process(dirs, asset, config)
    assert not report.errors and report.transcribed_count == 0
    transcribe.assert_not_called()
