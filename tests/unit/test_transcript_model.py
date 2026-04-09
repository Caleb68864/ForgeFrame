"""Tests for WordTiming, TranscriptSegment, Transcript (MD-14)."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.transcript import (
    Transcript,
    TranscriptSegment,
    WordTiming,
)


# ---------------------------------------------------------------------------
# WordTiming
# ---------------------------------------------------------------------------

def test_word_timing_required():
    with pytest.raises(ValidationError):
        WordTiming()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        WordTiming(word="hello", start=0.5)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        WordTiming(word="hello", end=1.0)  # type: ignore[call-arg]


def test_word_timing_defaults():
    wt = WordTiming(word="hello", start=0.5, end=1.0)
    assert wt.confidence == 1.0


def test_word_timing_all_fields():
    wt = WordTiming(word="hello", start=0.5, end=1.0, confidence=0.95)
    d = wt.model_dump()
    assert d["word"] == "hello"
    assert d["start"] == 0.5
    assert d["end"] == 1.0
    assert d["confidence"] == 0.95


def test_word_timing_confidence_boundary():
    wt1 = WordTiming(word="test", start=0.0, end=0.5, confidence=0.0)
    wt2 = WordTiming(word="test", start=0.0, end=0.5, confidence=1.0)
    assert wt1.confidence == 0.0
    assert wt2.confidence == 1.0


def test_word_timing_confidence_beyond_range():
    # No range validator in source
    wt = WordTiming(word="test", start=0.0, end=0.5, confidence=1.5)
    assert wt.confidence == 1.5


# ---------------------------------------------------------------------------
# TranscriptSegment
# ---------------------------------------------------------------------------

def test_transcript_segment_required():
    with pytest.raises(ValidationError):
        TranscriptSegment()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        TranscriptSegment(start_seconds=0.0, end_seconds=5.0)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        TranscriptSegment(start_seconds=0.0, text="hello")  # type: ignore[call-arg]


def test_transcript_segment_defaults():
    seg = TranscriptSegment(start_seconds=0.0, end_seconds=5.0, text="Hello there")
    assert seg.confidence == 1.0
    assert seg.words == []


def test_transcript_segment_with_words():
    words = [
        WordTiming(word="Hello", start=0.0, end=0.5),
        WordTiming(word="there", start=0.5, end=1.0),
    ]
    seg = TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="Hello there", words=words)
    seg2 = TranscriptSegment.from_json(seg.to_json())
    assert len(seg2.words) == 2
    assert seg2.words[0].word == "Hello"


def test_transcript_segment_all_fields():
    seg = TranscriptSegment(
        start_seconds=5.0,
        end_seconds=10.0,
        text="Cut to length",
        confidence=0.98,
    )
    d = seg.model_dump()
    assert d["text"] == "Cut to length"
    assert d["confidence"] == 0.98


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------

def test_transcript_required():
    with pytest.raises(ValidationError):
        Transcript()  # type: ignore[call-arg]


def test_transcript_defaults():
    asset_id = uuid.uuid4()
    t = Transcript(asset_id=asset_id)
    assert t.engine == ""
    assert t.model == ""
    assert t.language == ""
    assert t.segments == []
    assert t.raw_text == ""


def test_transcript_id_auto_generated():
    asset_id = uuid.uuid4()
    t1 = Transcript(asset_id=asset_id)
    t2 = Transcript(asset_id=asset_id)
    assert t1.id != t2.id


def test_transcript_created_at_utc():
    asset_id = uuid.uuid4()
    t = Transcript(asset_id=asset_id)
    assert t.created_at.tzinfo is not None


def test_transcript_asset_id_required_valid_uuid():
    # Valid UUID string is accepted and coerced to UUID
    asset_id = str(uuid.uuid4())
    t = Transcript(asset_id=asset_id)
    assert str(t.asset_id) == asset_id


def test_transcript_asset_id_invalid_uuid():
    with pytest.raises(ValidationError):
        Transcript(asset_id="not-a-valid-uuid-string")


def test_transcript_all_fields():
    asset_id = uuid.uuid4()
    words = [WordTiming(word="Hello", start=0.0, end=0.5)]
    seg = TranscriptSegment(start_seconds=0.0, end_seconds=5.0, text="Hello world", words=words)
    t = Transcript(
        asset_id=asset_id,
        engine="faster-whisper",
        model="large-v3",
        language="en",
        segments=[seg],
        raw_text="Hello world",
    )
    d = t.model_dump()
    assert d["engine"] == "faster-whisper"
    assert len(d["segments"]) == 1
    assert len(d["segments"][0]["words"]) == 1


def test_transcript_json_round_trip():
    asset_id = uuid.uuid4()
    seg = TranscriptSegment(start_seconds=0.0, end_seconds=5.0, text="Step one")
    t = Transcript(asset_id=asset_id, engine="whisper", segments=[seg])
    t2 = Transcript.from_json(t.to_json())
    assert t2 == t


def test_transcript_yaml_round_trip():
    asset_id = uuid.uuid4()
    t = Transcript(asset_id=asset_id, language="en", raw_text="Sample text")
    t2 = Transcript.from_yaml(t.to_yaml())
    assert t2 == t


def test_transcript_segment_yaml_round_trip():
    words = [WordTiming(word="test", start=0.0, end=0.5, confidence=0.9)]
    seg = TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="test", words=words)
    seg2 = TranscriptSegment.from_yaml(seg.to_yaml())
    assert seg2 == seg
    assert seg2.words[0].word == "test"


def test_transcript_empty_segments():
    asset_id = uuid.uuid4()
    t = Transcript(asset_id=asset_id)
    d = t.model_dump()
    assert d["segments"] == []
