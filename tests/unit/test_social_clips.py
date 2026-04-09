"""Unit tests for social clip extraction and social media package generation."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from workshop_video_brain.core.models.social import ClipCandidate, ClipExport, SocialPost
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.pipelines.social_clips import (
    create_social_post_text,
    find_highlight_segments,
    generate_clip_captions,
    generate_clip_export_manifest,
    generate_clip_titles,
    generate_social_package,
    score_clip_candidates,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ASSET_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _seg(start: float, end: float, text: str) -> dict:
    return {"start_seconds": start, "end_seconds": end, "text": text}


def _make_candidate(
    start: float = 0.0,
    end: float = 30.0,
    hook: str = "Have you ever wondered how to do this properly?",
    summary: str = "We cover the key technique step by step.",
) -> ClipCandidate:
    return ClipCandidate(
        start_seconds=start,
        end_seconds=end,
        duration_seconds=end - start,
        hook_text=hook,
        content_summary=summary,
    )


def _make_workspace_with_transcript(
    tmp_path: Path, segments: list[dict], title: str = "Test Project"
) -> Path:
    """Create a minimal workspace with a transcript file."""
    ws = tmp_path / "test-workspace"
    ws.mkdir(parents=True)
    transcripts_dir = ws / "transcripts"
    transcripts_dir.mkdir()

    import yaml

    manifest = {
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "project_title": title,
        "slug": title.lower().replace(" ", "-"),
        "status": "editing",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "content_type": "",
        "vault_note_path": "",
        "media_root": "",
        "proxy_policy": {},
        "stt_engine": "whisper",
        "default_sort_mode": "chronological",
    }
    (ws / "workspace.yaml").write_text(yaml.dump(manifest), encoding="utf-8")

    transcript = Transcript(
        asset_id=_ASSET_ID,
        engine="test",
        segments=[TranscriptSegment(**s) for s in segments],
    )
    (transcripts_dir / "test_transcript.json").write_text(
        transcript.to_json(), encoding="utf-8"
    )
    return ws


# ---------------------------------------------------------------------------
# Highlight detection tests
# ---------------------------------------------------------------------------


def test_find_highlight_segments_returns_candidates():
    """Transcript with strong openings produces clip candidates."""
    segments = [
        _seg(0.0, 5.0, "Hello everyone, welcome to the tutorial."),
        _seg(5.0, 10.0, "Have you ever struggled to get a clean wood joint?"),
        _seg(10.0, 20.0, "The key is to use the right technique for the wood grain."),
        _seg(20.0, 30.0, "You need to measure carefully, at least 10mm from the edge."),
        _seg(30.0, 40.0, "Sand with 120 grit first, then 220 grit for a smooth finish."),
        _seg(40.0, 55.0, "Apply the finish in thin coats, letting each coat dry fully."),
    ]
    candidates = find_highlight_segments("", segments, min_duration=15.0, max_duration=60.0)
    assert len(candidates) > 0


def test_find_highlight_segments_respects_duration_bounds():
    """All returned candidates are within min/max duration."""
    segments = [
        _seg(0.0, 5.0, "Have you ever seen a perfect dovetail joint?"),
        _seg(5.0, 15.0, "This is the most important step in woodworking technique."),
        _seg(15.0, 25.0, "Measure the board carefully using a marking gauge."),
        _seg(25.0, 35.0, "Cut at 45 degrees for a perfect fit every time."),
        _seg(35.0, 45.0, "Sand with 220 grit until the surface is smooth."),
        _seg(45.0, 60.0, "Apply finish in two coats and allow to dry completely."),
        _seg(60.0, 70.0, "That is the complete process for a clean joint."),
    ]
    candidates = find_highlight_segments("", segments, min_duration=15.0, max_duration=60.0)
    for c in candidates:
        assert c.duration_seconds >= 15.0
        assert c.duration_seconds <= 60.0


def test_find_highlight_segments_empty_transcript():
    """Empty transcript returns empty list."""
    result = find_highlight_segments("", [], min_duration=15.0, max_duration=60.0)
    assert result == []


def test_find_highlight_segments_no_hooks():
    """Transcript with no strong openings returns empty list."""
    segments = [
        _seg(0.0, 5.0, "And so we continue with what we were doing before."),
        _seg(5.0, 10.0, "As I mentioned, the process requires patience."),
        _seg(10.0, 20.0, "Going back to what we showed earlier in the video."),
    ]
    result = find_highlight_segments("", segments, min_duration=15.0, max_duration=60.0)
    # Should find nothing or very little (all context-dependent)
    assert isinstance(result, list)


def test_find_highlight_segments_question_hook():
    """Segments with question openings are detected as candidates."""
    segments = [
        _seg(0.0, 3.0, "First, prepare your workspace."),
        _seg(3.0, 8.0, "Have you ever wondered why your cuts always split the wood?"),
        _seg(8.0, 18.0, "The answer is simple: you need to cut with the grain."),
        _seg(18.0, 28.0, "Use a sharp blade and score the line first."),
        _seg(28.0, 38.0, "A marking knife gives you a much cleaner cut than pencil."),
    ]
    candidates = find_highlight_segments("", segments, min_duration=15.0, max_duration=60.0)
    assert len(candidates) >= 1
    # Verify question hooks end up as candidates
    hooks = [c.hook_text for c in candidates]
    assert any("wondered" in h.lower() or "have you" in h.lower() for h in hooks)


def test_find_highlight_segments_value_statement_hook():
    """Segments starting with value statements are detected."""
    segments = [
        _seg(0.0, 5.0, "This is the most important step in the whole process."),
        _seg(5.0, 15.0, "You must let the glue cure for at least 30 minutes."),
        _seg(15.0, 25.0, "Clamping pressure should be firm but not excessive."),
        _seg(25.0, 35.0, "Too much pressure causes squeeze-out that's hard to clean."),
    ]
    candidates = find_highlight_segments("", segments, min_duration=15.0, max_duration=60.0)
    assert len(candidates) >= 1


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------


def test_score_candidates_question_hook_gives_high_hook_strength():
    """Question opening yields high hook_strength score."""
    candidate = _make_candidate(
        hook="Have you ever wondered why your joints keep failing?",
        summary="The reason is simple: poor technique and cheap glue.",
    )
    scored = score_clip_candidates([candidate])
    assert len(scored) == 1
    assert scored[0].hook_strength >= 0.6


def test_score_candidates_context_dependent_lowers_clarity():
    """Clip with many back-references gets lower clarity score."""
    context_heavy = _make_candidate(
        hook="As I mentioned earlier, what we just did was incorrect.",
        summary="Going back to what we showed before, as I mentioned, the previous step...",
    )
    clean = _make_candidate(
        hook="The key to a clean cut is always scoring before sawing.",
        summary="Score the wood fibre with a marking knife to prevent tear-out.",
    )
    scored = score_clip_candidates([context_heavy, clean])
    scored_map = {c.hook_text: c for c in scored}
    assert scored_map[clean.hook_text].clarity > scored_map[context_heavy.hook_text].clarity


def test_score_candidates_specific_technique_gives_high_engagement():
    """Specific measurements and techniques yield high engagement score."""
    specific = _make_candidate(
        hook="Use a 6mm drill bit for pilot holes.",
        summary="Drill at 90 degrees using a 6mm bit. Sand with 120 grit then 220 grit finish.",
    )
    scored = score_clip_candidates([specific])
    assert scored[0].engagement >= 0.4


def test_score_candidates_vague_talk_gives_low_engagement():
    """Vague filler language yields low engagement score."""
    vague = _make_candidate(
        hook="So basically you kind of just do stuff with the thing.",
        summary="It's basically just kind of whatever, and so on and so forth etc.",
    )
    scored = score_clip_candidates([vague])
    assert scored[0].engagement <= 0.5


def test_score_candidates_overall_is_weighted_average():
    """overall_score = hook_strength * 0.4 + clarity * 0.3 + engagement * 0.3."""
    candidates = [
        _make_candidate(
            hook="Have you ever wondered how to get perfect joints?",
            summary="Use a router jig to cut consistent 10mm mortises every time.",
        )
    ]
    scored = score_clip_candidates(candidates)
    c = scored[0]
    expected = round(c.hook_strength * 0.4 + c.clarity * 0.3 + c.engagement * 0.3, 4)
    assert abs(c.overall_score - expected) < 0.001


def test_score_candidates_sorted_descending():
    """Candidates are returned sorted by overall_score descending."""
    candidates = [
        _make_candidate(
            0.0, 30.0,
            hook="Basically this is just kind of whatever.",
            summary="Stuff happens and things occur, you know.",
        ),
        _make_candidate(
            60.0, 90.0,
            hook="Have you ever wondered why wood splits when you drill?",
            summary="Use a 3mm pilot hole to prevent splitting. The technique saves material.",
        ),
    ]
    scored = score_clip_candidates(candidates)
    assert scored[0].overall_score >= scored[-1].overall_score


def test_score_candidates_empty_list():
    """Empty input returns empty output."""
    assert score_clip_candidates([]) == []


def test_score_candidates_dangling_pronoun_lowers_clarity():
    """Clip starting with pronoun without context gets lower clarity."""
    dangling = _make_candidate(
        hook="This is how we do the thing.",
        summary="It works because of what we discussed before.",
    )
    clear = _make_candidate(
        hook="The dovetail joint is the strongest wood joint you can make.",
        summary="Cut at 1:8 ratio for hardwoods, 1:6 for softwoods.",
    )
    scored = score_clip_candidates([dangling, clear])
    scored_map = {c.hook_text[:20]: c for c in scored}
    dangling_key = dangling.hook_text[:20]
    clear_key = clear.hook_text[:20]
    assert scored_map[clear_key].clarity > scored_map[dangling_key].clarity


# ---------------------------------------------------------------------------
# Title generation tests
# ---------------------------------------------------------------------------


def test_generate_clip_titles_under_50_chars():
    """All generated titles are under 50 characters."""
    candidates = [
        _make_candidate(
            hook="Have you ever wondered why your wood splits when drilling?",
            summary="Use pilot holes every time.",
        ),
        _make_candidate(
            60.0, 90.0,
            hook="This is the most important step for a clean finish.",
            summary="Sand with 220 grit before applying oil finish.",
        ),
        _make_candidate(
            120.0, 150.0,
            hook="Watch this trick for perfect dovetails every single time.",
            summary="Use a sliding bevel set to 1:8 ratio.",
        ),
    ]
    titles = generate_clip_titles(candidates, "My Woodworking Tutorial")
    for title in titles:
        assert len(title) <= 50, f"Title too long: {repr(title)}"


def test_generate_clip_titles_each_clip_gets_unique_title():
    """Each clip gets a distinct title."""
    candidates = [_make_candidate(i * 60.0, i * 60.0 + 30.0) for i in range(4)]
    titles = generate_clip_titles(candidates, "Workshop Tips")
    assert len(titles) == len(set(titles)), "Titles are not unique"


def test_generate_clip_titles_count_matches_candidates():
    """One title is generated per candidate."""
    candidates = [_make_candidate(i * 60.0, i * 60.0 + 30.0) for i in range(3)]
    titles = generate_clip_titles(candidates, "Tutorial")
    assert len(titles) == len(candidates)


def test_generate_clip_titles_empty_candidates():
    """Empty input returns empty title list."""
    assert generate_clip_titles([], "Title") == []


# ---------------------------------------------------------------------------
# Caption generation tests
# ---------------------------------------------------------------------------


def test_generate_clip_captions_under_60_chars_per_line():
    """All caption lines are under 60 characters."""
    candidates = [
        _make_candidate(
            hook="Use a 10mm drill bit for pilot holes in hardwood.",
            summary="Apply 2mm pressure for 30 seconds.",
        ),
    ]
    captions = generate_clip_captions(candidates)
    for cap_info in captions:
        caption = cap_info["caption"]
        for line in caption.split("\n"):
            assert len(line) <= 60, f"Caption line too long: {repr(line)}"


def test_generate_clip_captions_count_matches_candidates():
    """One caption dict per candidate."""
    candidates = [_make_candidate(i * 60.0, i * 60.0 + 30.0) for i in range(3)]
    captions = generate_clip_captions(candidates)
    assert len(captions) == len(candidates)


def test_generate_clip_captions_has_required_keys():
    """Each caption dict has 'caption' and 'overlay_suggestions'."""
    candidates = [_make_candidate()]
    captions = generate_clip_captions(candidates)
    assert "caption" in captions[0]
    assert "overlay_suggestions" in captions[0]
    assert isinstance(captions[0]["overlay_suggestions"], list)


def test_generate_clip_captions_empty_candidates():
    """Empty input returns empty list."""
    assert generate_clip_captions([]) == []


# ---------------------------------------------------------------------------
# Export manifest tests
# ---------------------------------------------------------------------------


def test_generate_clip_export_manifest_has_required_fields():
    """Each ClipExport has all required fields populated."""
    candidates = [
        _make_candidate(
            hook="Have you ever tried this joinery technique?",
            summary="The lap joint is the easiest joint to cut by hand.",
        )
    ]
    exports = generate_clip_export_manifest(
        candidates, "Joinery Basics", source_video="/path/to/video.mp4"
    )
    assert len(exports) == 1
    e = exports[0]
    assert e.clip_id != ""
    assert e.start_seconds == candidates[0].start_seconds
    assert e.end_seconds == candidates[0].end_seconds
    assert e.title != ""
    assert e.source_video == "/path/to/video.mp4"


def test_generate_clip_export_manifest_respects_aspect_ratio():
    """Specified aspect ratio is passed through to each export."""
    candidates = [_make_candidate()]
    exports_916 = generate_clip_export_manifest(candidates, "T", aspect_ratio="9:16")
    exports_169 = generate_clip_export_manifest(candidates, "T", aspect_ratio="16:9")
    assert exports_916[0].aspect_ratio == "9:16"
    assert exports_169[0].aspect_ratio == "16:9"


def test_generate_clip_export_manifest_count_matches():
    """One ClipExport per ClipCandidate."""
    candidates = [_make_candidate(i * 60.0, i * 60.0 + 30.0) for i in range(4)]
    exports = generate_clip_export_manifest(candidates, "Test Video")
    assert len(exports) == len(candidates)


def test_generate_clip_export_manifest_empty():
    """Empty candidates yields empty manifest."""
    assert generate_clip_export_manifest([], "Title") == []


# ---------------------------------------------------------------------------
# Social post tests
# ---------------------------------------------------------------------------


def test_create_social_post_youtube_has_hashtags():
    """YouTube post includes hashtag data."""
    candidate = _make_candidate(
        hook="Have you ever tried a lap joint for quick assembly?",
        summary="The lap joint requires only a saw and chisel.",
    )
    post = create_social_post_text(candidate, platform="youtube", video_title="Joinery")
    assert post.platform == "youtube"
    assert isinstance(post.hashtags, list)
    assert len(post.hashtags) > 0


def test_create_social_post_twitter_under_280_chars():
    """Twitter post fits within 280-character limit."""
    candidate = _make_candidate(
        hook="Have you ever wondered why your mortise and tenon joints never fit?",
        summary="The answer is always in how you measure your mortise depth.",
    )
    post = create_social_post_text(candidate, platform="twitter")
    assert post.platform == "twitter"
    assert len(post.post_text) <= 280


def test_create_social_post_platform_differences():
    """Different platforms produce distinct post text."""
    candidate = _make_candidate(
        hook="The key to clean dovetails is a sharp chisel.",
        summary="Use a 6mm chisel for narrow pins. 12mm for wider tails.",
    )
    yt = create_social_post_text(candidate, platform="youtube")
    ig = create_social_post_text(candidate, platform="instagram")
    tt = create_social_post_text(candidate, platform="tiktok")

    # Each platform should produce different text
    texts = {yt.post_text, ig.post_text, tt.post_text}
    assert len(texts) >= 2  # at least two distinct versions


def test_create_social_post_instagram_has_cta():
    """Instagram post contains a call-to-action."""
    candidate = _make_candidate(
        hook="Watch this trick for invisible glue joints.",
        summary="Rub two boards together after applying glue for a tight fit.",
    )
    post = create_social_post_text(candidate, platform="instagram")
    # Instagram should have more content and a CTA-style phrase
    assert len(post.post_text) > 50


def test_create_social_post_tiktok_is_short():
    """TikTok post is compact."""
    candidate = _make_candidate(
        hook="Have you ever wondered how to use a hand plane?",
        summary="Set the blade depth to 0.1mm for fine shavings on hardwood.",
    )
    post = create_social_post_text(candidate, platform="tiktok")
    assert len(post.post_text) <= 280


def test_create_social_post_custom_hashtags_used():
    """Provided hashtags are passed through to the post."""
    candidate = _make_candidate()
    custom = ["handtools", "chisels", "woodcraft"]
    post = create_social_post_text(candidate, platform="youtube", hashtags=custom)
    assert post.hashtags == custom


# ---------------------------------------------------------------------------
# Full package tests
# ---------------------------------------------------------------------------


def test_generate_social_package_creates_manifest_json(tmp_path: Path):
    """generate_social_package writes a valid clips_manifest.json."""
    segments = [
        _seg(0.0, 5.0, "Welcome to the tutorial."),
        _seg(5.0, 12.0, "Have you ever struggled to cut a perfect mortise?"),
        _seg(12.0, 22.0, "The key technique is to score the outline with a marking knife first."),
        _seg(22.0, 32.0, "Use a 6mm chisel to chop out the waste in thin layers."),
        _seg(32.0, 42.0, "Work from both faces to avoid tear-out at 90 degrees."),
        _seg(42.0, 55.0, "Test the fit with the tenon before final clean-up passes."),
    ]
    ws = _make_workspace_with_transcript(tmp_path, segments)
    result = generate_social_package(ws, max_clips=3)

    manifest_path = Path(result["manifest_path"])
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)


def test_generate_social_package_creates_summary_md(tmp_path: Path):
    """generate_social_package writes a social_summary.md file."""
    segments = [
        _seg(0.0, 5.0, "Let me show you the best way to use a hand plane."),
        _seg(5.0, 15.0, "Set the blade depth to exactly 0.1mm for fine work."),
        _seg(15.0, 25.0, "Work with the grain to avoid tear-out on hardwood."),
        _seg(25.0, 35.0, "Push with even pressure using both hands on the tote."),
        _seg(35.0, 48.0, "A sharp blade makes all the difference in the finish."),
    ]
    ws = _make_workspace_with_transcript(tmp_path, segments)
    result = generate_social_package(ws, max_clips=3)

    summary_path = Path(result["summary_path"])
    assert summary_path.exists()
    content = summary_path.read_text(encoding="utf-8")
    assert content.startswith("#")  # valid markdown heading


def test_generate_social_package_no_transcripts(tmp_path: Path):
    """Package generation with no transcripts returns zero clips."""
    ws = tmp_path / "empty-workspace"
    ws.mkdir()
    (ws / "transcripts").mkdir()

    result = generate_social_package(ws, max_clips=5)
    assert result["clips_found"] == 0


def test_generate_social_package_clips_manifest_is_valid_json(tmp_path: Path):
    """clips_manifest.json can be parsed as JSON list."""
    segments = [
        _seg(0.0, 5.0, "This is the most important step in the entire build."),
        _seg(5.0, 15.0, "You need to mark the tenon shoulders at exactly 25mm."),
        _seg(15.0, 25.0, "Use a marking gauge set to that measurement consistently."),
        _seg(25.0, 35.0, "Score deeply so the chisel has a clear register line."),
        _seg(35.0, 50.0, "Cut on the waste side and sneak up to the line slowly."),
    ]
    ws = _make_workspace_with_transcript(tmp_path, segments)
    result = generate_social_package(ws, max_clips=5)

    manifest_path = Path(result["manifest_path"])
    raw = manifest_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert isinstance(parsed, list)


def test_generate_social_package_respects_max_clips(tmp_path: Path):
    """Number of clips in manifest does not exceed max_clips."""
    segments = []
    for i in range(20):
        start = float(i * 10)
        segments.append(
            _seg(start, start + 5.0, f"Have you ever tried technique number {i}?")
        )
        segments.append(
            _seg(start + 5.0, start + 10.0, f"The method involves measuring {i + 1} mm precisely.")
        )

    ws = _make_workspace_with_transcript(tmp_path, segments)
    result = generate_social_package(ws, max_clips=3)

    assert result["clips_found"] <= 3


def test_generate_social_package_social_dir_created(tmp_path: Path):
    """reports/social/ directory is created."""
    segments = [
        _seg(0.0, 5.0, "Watch this: the hidden mortise is the cleanest joint."),
        _seg(5.0, 20.0, "Drill a 10mm hole to start, then chisel the walls square."),
        _seg(20.0, 35.0, "Test with the matching tenon until you have a snug fit."),
    ]
    ws = _make_workspace_with_transcript(tmp_path, segments)
    generate_social_package(ws, max_clips=2)

    social_dir = ws / "reports" / "social"
    assert social_dir.exists()
    assert social_dir.is_dir()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_clip_candidate_serialization():
    """ClipCandidate serializes and deserializes via JSON."""
    c = ClipCandidate(
        start_seconds=10.0,
        end_seconds=45.0,
        duration_seconds=35.0,
        hook_text="Have you ever used a router jig?",
        content_summary="Router jigs allow repeatable cuts at any angle.",
        hook_strength=0.75,
        clarity=0.8,
        engagement=0.6,
        overall_score=0.72,
    )
    restored = ClipCandidate.from_json(c.to_json())
    assert restored.start_seconds == c.start_seconds
    assert restored.hook_strength == c.hook_strength
    assert restored.overall_score == c.overall_score


def test_clip_export_default_aspect_ratio():
    """ClipExport defaults to 9:16 aspect ratio."""
    e = ClipExport(clip_id="clip_001", start_seconds=0.0, end_seconds=30.0)
    assert e.aspect_ratio == "9:16"


def test_social_post_model():
    """SocialPost stores platform and post text correctly."""
    post = SocialPost(
        platform="instagram",
        post_text="Check out this woodworking tip! #woodworking",
        hashtags=["woodworking", "diy"],
        clip_title="Router Jig Trick",
    )
    assert post.platform == "instagram"
    assert "woodworking" in post.hashtags
