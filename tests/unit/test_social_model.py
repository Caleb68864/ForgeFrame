"""Tests for ClipCandidate, ClipExport, SocialPost (MD-12)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.social import ClipCandidate, ClipExport, SocialPost


# ---------------------------------------------------------------------------
# ClipCandidate
# ---------------------------------------------------------------------------

def test_clip_candidate_required():
    with pytest.raises(ValidationError):
        ClipCandidate()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ClipCandidate(start_seconds=0.0, end_seconds=10.0)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ClipCandidate(start_seconds=0.0, duration_seconds=10.0)  # type: ignore[call-arg]


def test_clip_candidate_defaults():
    cc = ClipCandidate(start_seconds=0.0, end_seconds=10.0, duration_seconds=10.0)
    assert cc.hook_text == ""
    assert cc.content_summary == ""
    assert cc.hook_strength == 0.0
    assert cc.clarity == 0.0
    assert cc.engagement == 0.0
    assert cc.overall_score == 0.0
    assert cc.source_step == ""


def test_clip_candidate_all_fields():
    cc = ClipCandidate(
        start_seconds=5.0,
        end_seconds=35.0,
        duration_seconds=30.0,
        hook_text="Did you know this trick?",
        content_summary="Shows a quick seam technique",
        hook_strength=0.9,
        clarity=0.8,
        engagement=0.85,
        overall_score=0.85,
        source_step="step_3",
    )
    d = cc.model_dump()
    assert d["start_seconds"] == 5.0
    assert d["hook_strength"] == 0.9
    assert d["source_step"] == "step_3"


def test_clip_candidate_score_boundary():
    cc = ClipCandidate(
        start_seconds=0.0, end_seconds=5.0, duration_seconds=5.0,
        hook_strength=0.0, clarity=1.0,
    )
    assert cc.hook_strength == 0.0
    assert cc.clarity == 1.0
    # No range validator -- values beyond 1.0 also accepted
    cc2 = ClipCandidate(
        start_seconds=0.0, end_seconds=5.0, duration_seconds=5.0,
        overall_score=1.5,
    )
    assert cc2.overall_score == 1.5


def test_clip_candidate_json_round_trip():
    cc = ClipCandidate(
        start_seconds=10.0, end_seconds=40.0, duration_seconds=30.0,
        hook_text="Watch this!", overall_score=0.75,
    )
    cc2 = ClipCandidate.from_json(cc.to_json())
    assert cc2 == cc


def test_clip_candidate_yaml_round_trip():
    cc = ClipCandidate(start_seconds=0.0, end_seconds=60.0, duration_seconds=60.0)
    cc2 = ClipCandidate.from_yaml(cc.to_yaml())
    assert cc2 == cc


# ---------------------------------------------------------------------------
# ClipExport
# ---------------------------------------------------------------------------

def test_clip_export_default_construction():
    ce = ClipExport()
    assert ce is not None


def test_clip_export_defaults():
    ce = ClipExport()
    assert ce.clip_id == ""
    assert ce.start_seconds == 0.0
    assert ce.end_seconds == 0.0
    assert ce.title == ""
    assert ce.caption == ""
    assert ce.description == ""
    assert ce.hashtags == []
    assert ce.aspect_ratio == "9:16"
    assert ce.source_video == ""


def test_clip_export_aspect_ratio_default():
    ce = ClipExport()
    assert ce.aspect_ratio == "9:16"


def test_clip_export_aspect_ratio_override():
    ce = ClipExport(aspect_ratio="16:9")
    assert ce.aspect_ratio == "16:9"


def test_clip_export_hashtags():
    ce = ClipExport(hashtags=["#woodworking", "#diy", "#craft"])
    d = ce.model_dump()
    assert d["hashtags"] == ["#woodworking", "#diy", "#craft"]
    ce2 = ClipExport.model_validate(d)
    assert ce2.hashtags == ["#woodworking", "#diy", "#craft"]


def test_clip_export_mutable_default_isolation():
    ce1 = ClipExport()
    ce2 = ClipExport()
    ce1.hashtags.append("#test")
    assert ce2.hashtags == []


def test_clip_export_json_round_trip():
    ce = ClipExport(
        clip_id="clip_001",
        start_seconds=5.0,
        end_seconds=35.0,
        title="Cool Trick",
        hashtags=["#build"],
    )
    ce2 = ClipExport.from_json(ce.to_json())
    assert ce2 == ce


# ---------------------------------------------------------------------------
# SocialPost
# ---------------------------------------------------------------------------

def test_social_post_default_construction():
    sp = SocialPost()
    assert sp is not None


def test_social_post_defaults():
    sp = SocialPost()
    assert sp.platform == "youtube"
    assert sp.post_text == ""
    assert sp.hashtags == []
    assert sp.clip_title == ""


def test_social_post_platforms():
    for platform in ["instagram", "tiktok", "twitter", "youtube"]:
        sp = SocialPost(platform=platform)
        assert sp.platform == platform


def test_social_post_hashtags():
    sp = SocialPost(hashtags=["#reel", "#craft"])
    sp2 = SocialPost.from_json(sp.to_json())
    assert sp2.hashtags == ["#reel", "#craft"]


def test_social_post_yaml_round_trip():
    sp = SocialPost(platform="instagram", post_text="Check this out!", hashtags=["#diy"])
    sp2 = SocialPost.from_yaml(sp.to_yaml())
    assert sp2 == sp
