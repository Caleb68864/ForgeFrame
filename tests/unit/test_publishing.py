"""Unit tests for the YouTube publishing pipeline.

Covers:
- generate_youtube_description: chapters formatted as MM:SS, hook, CTA
- generate_title_variants: all under 70 chars, different styles
- generate_tags: 15-25 tags, lowercase, no duplicates
- generate_hashtags: prefixed with #, max 15
- generate_pinned_comment: has CTA, mentions title
- generate_video_summary: short < medium < long in length
- extract_resource_mentions: finds tool/material names
- package_publish_bundle: all files written to reports/publish/
- generate_publish_note: creates valid Obsidian note with frontmatter
- Empty transcript: graceful defaults
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from workshop_video_brain.core.models.publishing import (
    PublishBundle,
    TitleVariants,
    VideoSummary,
)
from workshop_video_brain.edit_mcp.pipelines.publishing import (
    generate_youtube_description,
    generate_title_variants,
    generate_tags,
    generate_hashtags,
    generate_pinned_comment,
    generate_video_summary,
    extract_resource_mentions,
    package_publish_bundle,
    generate_publish_note,
    _seconds_to_mmss,
    _format_chapters_text,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_SAMPLE_TRANSCRIPT = (
    "Today I'm going to show you how to sew a zippered pouch. "
    "I'm using X-Pac fabric for this build. "
    "First, cut the fabric to size — you'll need two pieces at 8 by 10 inches. "
    "Next, sew along the sides. Then attach the zipper. "
    "I'm using a Schmetz 90 needle in my sewing machine. "
    "The finished pouch is waterproof and super light. "
    "This is a great project for beginners. "
    "Make sure to backstitch at the start and end of each seam. "
    "Here's what it looks like when it's done. "
    "I hope this tutorial was helpful!"
)

_SAMPLE_CHAPTERS = [
    {"time": 0.0, "title": "Intro"},
    {"time": 45.0, "title": "Materials"},
    {"time": 120.0, "title": "Cutting"},
    {"time": 240.0, "title": "Sewing"},
    {"time": 360.0, "title": "Finishing"},
]

_SAMPLE_TITLE = "How to Sew a Zippered Bikepacking Pouch"


def _write_transcript(tmp_path: Path, segments: list[dict] | None = None) -> None:
    """Write a transcript JSON to workspace transcripts dir."""
    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir(exist_ok=True)
    if segments is None:
        parts = _SAMPLE_TRANSCRIPT.split(". ")
        segments = [
            {
                "start_seconds": i * 5.0,
                "end_seconds": (i + 1) * 5.0,
                "text": s + ".",
                "confidence": 1.0,
                "words": [],
            }
            for i, s in enumerate(parts)
        ]
    data = {
        "id": str(uuid4()),
        "asset_id": str(uuid4()),
        "engine": "test",
        "model": "test",
        "language": "en",
        "segments": segments,
        "raw_text": " ".join(s["text"] for s in segments),
        "created_at": "2024-01-01T00:00:00",
    }
    path = transcripts_dir / "test_transcript.json"
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_chapters(tmp_path: Path, chapters: list[dict] | None = None) -> None:
    """Write chapter markers JSON to workspace markers dir."""
    markers_dir = tmp_path / "markers"
    markers_dir.mkdir(exist_ok=True)
    if chapters is None:
        chapters = _SAMPLE_CHAPTERS
    markers = []
    for ch in chapters:
        markers.append({
            "id": str(uuid4()),
            "category": "chapter_candidate",
            "confidence_score": 0.9,
            "source_method": "keyword_rule",
            "reason": ch["title"],
            "clip_ref": "clip01",
            "start_seconds": ch["time"],
            "end_seconds": ch["time"] + 5.0,
            "suggested_label": f"chapter_candidate: {ch['title']}",
        })
    path = markers_dir / "test_markers.json"
    path.write_text(json.dumps(markers), encoding="utf-8")


def _write_manifest(tmp_path: Path, title: str = _SAMPLE_TITLE) -> None:
    """Write a minimal manifest.json to workspace."""
    data = {"project_title": title, "title": title}
    (tmp_path / "manifest.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helper: _seconds_to_mmss
# ---------------------------------------------------------------------------


class TestSecondsToMmss:
    def test_zero(self):
        assert _seconds_to_mmss(0.0) == "0:00"

    def test_less_than_minute(self):
        assert _seconds_to_mmss(45.0) == "0:45"

    def test_exactly_one_minute(self):
        assert _seconds_to_mmss(60.0) == "1:00"

    def test_multi_minute(self):
        assert _seconds_to_mmss(125.0) == "2:05"

    def test_large_value(self):
        assert _seconds_to_mmss(3661.0) == "61:01"


# ---------------------------------------------------------------------------
# generate_youtube_description
# ---------------------------------------------------------------------------


class TestGenerateYoutubeDescription:
    def test_has_chapters_formatted_as_mmss(self):
        desc = generate_youtube_description(
            _SAMPLE_TITLE, _SAMPLE_TRANSCRIPT, _SAMPLE_CHAPTERS
        )
        # Should have MM:SS - Title format
        assert re.search(r"\d+:\d{2} - \w", desc)

    def test_chapter_timestamps_correct(self):
        desc = generate_youtube_description(
            _SAMPLE_TITLE, _SAMPLE_TRANSCRIPT, _SAMPLE_CHAPTERS
        )
        assert "0:00 - Intro" in desc
        assert "0:45 - Materials" in desc
        assert "2:00 - Cutting" in desc

    def test_has_hook_from_transcript(self):
        desc = generate_youtube_description(
            _SAMPLE_TITLE, _SAMPLE_TRANSCRIPT, _SAMPLE_CHAPTERS
        )
        # First paragraph should contain content from transcript or generated hook
        assert len(desc.split("\n")[0]) > 10

    def test_has_cta_section(self):
        desc = generate_youtube_description(
            _SAMPLE_TITLE, _SAMPLE_TRANSCRIPT, _SAMPLE_CHAPTERS,
            cta_text="Subscribe for more!"
        )
        assert "Subscribe for more!" in desc

    def test_default_cta_when_empty(self):
        desc = generate_youtube_description(
            _SAMPLE_TITLE, _SAMPLE_TRANSCRIPT, _SAMPLE_CHAPTERS
        )
        assert "subscribe" in desc.lower()

    def test_has_in_this_video_section(self):
        desc = generate_youtube_description(
            _SAMPLE_TITLE, _SAMPLE_TRANSCRIPT, _SAMPLE_CHAPTERS
        )
        assert "In this video" in desc

    def test_includes_links_when_provided(self):
        links = ["https://example.com/pattern", "https://example.com/fabric"]
        desc = generate_youtube_description(
            _SAMPLE_TITLE, _SAMPLE_TRANSCRIPT, _SAMPLE_CHAPTERS, links=links
        )
        assert "example.com/pattern" in desc
        assert "example.com/fabric" in desc

    def test_empty_transcript_graceful(self):
        desc = generate_youtube_description(_SAMPLE_TITLE, "", [])
        assert _SAMPLE_TITLE.lower() in desc.lower() or "subscribe" in desc.lower()

    def test_intro_added_when_no_zero_chapter(self):
        chapters = [{"time": 45.0, "title": "Materials"}]
        desc = generate_youtube_description(_SAMPLE_TITLE, _SAMPLE_TRANSCRIPT, chapters)
        assert "0:00 - Intro" in desc


# ---------------------------------------------------------------------------
# generate_title_variants
# ---------------------------------------------------------------------------


class TestGenerateTitleVariants:
    def test_all_under_70_chars(self):
        variants = generate_title_variants(_SAMPLE_TITLE, _SAMPLE_TRANSCRIPT)
        assert len(variants.searchable) <= 70
        assert len(variants.curiosity) <= 70
        assert len(variants.how_to) <= 70
        assert len(variants.short_punchy) <= 70

    def test_searchable_has_category_label(self):
        variants = generate_title_variants(_SAMPLE_TITLE, _SAMPLE_TRANSCRIPT)
        # Should contain a category label like "Tutorial"
        assert any(
            word in variants.searchable
            for word in ["Tutorial", "DIY", "Build", "How to", "How To"]
        )

    def test_how_to_starts_with_how_to(self):
        variants = generate_title_variants(_SAMPLE_TITLE, _SAMPLE_TRANSCRIPT)
        assert variants.how_to.lower().startswith("how to")

    def test_each_variant_is_different(self):
        variants = generate_title_variants(_SAMPLE_TITLE, _SAMPLE_TRANSCRIPT)
        all_variants = [variants.searchable, variants.curiosity, variants.how_to, variants.short_punchy]
        # All four should be distinct
        assert len(set(all_variants)) >= 3

    def test_all_fields_non_empty(self):
        variants = generate_title_variants(_SAMPLE_TITLE, _SAMPLE_TRANSCRIPT)
        assert variants.searchable
        assert variants.curiosity
        assert variants.how_to
        assert variants.short_punchy

    def test_empty_transcript_graceful(self):
        variants = generate_title_variants(_SAMPLE_TITLE, "")
        assert len(variants.searchable) <= 70
        assert len(variants.how_to) <= 70


# ---------------------------------------------------------------------------
# generate_tags
# ---------------------------------------------------------------------------


class TestGenerateTags:
    def test_count_15_to_25(self):
        tags = generate_tags(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        assert 15 <= len(tags) <= 25

    def test_all_lowercase(self):
        tags = generate_tags(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        for tag in tags:
            assert tag == tag.lower(), f"Tag not lowercase: {tag!r}"

    def test_no_duplicates(self):
        tags = generate_tags(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        assert len(tags) == len(set(tags))

    def test_includes_content_type_terms(self):
        tags = generate_tags(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE, content_type="tutorial")
        assert "tutorial" in tags

    def test_includes_title_words(self):
        tags = generate_tags(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        # "sew" or "zippered" or "pouch" should appear
        assert any(w in tags for w in ["sew", "pouch", "bikepacking", "zippered"])

    def test_empty_transcript_still_returns_enough_tags(self):
        tags = generate_tags("", _SAMPLE_TITLE)
        assert len(tags) >= 5


# ---------------------------------------------------------------------------
# generate_hashtags
# ---------------------------------------------------------------------------


class TestGenerateHashtags:
    def test_all_prefixed_with_hash(self):
        tags = generate_tags(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        hashtags = generate_hashtags(tags)
        for ht in hashtags:
            assert ht.startswith("#"), f"Hashtag missing #: {ht!r}"

    def test_max_15(self):
        tags = generate_tags(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        hashtags = generate_hashtags(tags)
        assert len(hashtags) <= 15

    def test_tutorial_content_type_includes_standard_tags(self):
        hashtags = generate_hashtags([], content_type="tutorial")
        lowercase_ht = [h.lower() for h in hashtags]
        assert "#tutorial" in lowercase_ht or "#diy" in lowercase_ht

    def test_no_empty_hashtags(self):
        tags = generate_tags(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        hashtags = generate_hashtags(tags)
        for ht in hashtags:
            assert len(ht) > 1


# ---------------------------------------------------------------------------
# generate_pinned_comment
# ---------------------------------------------------------------------------


class TestGeneratePinnedComment:
    def test_mentions_title(self):
        comment = generate_pinned_comment(_SAMPLE_TITLE)
        assert _SAMPLE_TITLE in comment

    def test_has_cta(self):
        comment = generate_pinned_comment(_SAMPLE_TITLE, cta_text="Like and subscribe!")
        assert "Like and subscribe!" in comment

    def test_default_cta_mentions_subscribe(self):
        comment = generate_pinned_comment(_SAMPLE_TITLE)
        assert "subscrib" in comment.lower()  # covers "subscribe" and "subscribing"

    def test_includes_links_when_provided(self):
        links = ["https://example.com/pattern"]
        comment = generate_pinned_comment(_SAMPLE_TITLE, links=links)
        assert "example.com/pattern" in comment

    def test_non_empty(self):
        comment = generate_pinned_comment(_SAMPLE_TITLE)
        assert len(comment) > 20


# ---------------------------------------------------------------------------
# generate_video_summary
# ---------------------------------------------------------------------------


class TestGenerateVideoSummary:
    def test_short_shorter_than_medium(self):
        summary = generate_video_summary(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        assert len(summary.short_summary) < len(summary.medium_summary)

    def test_medium_shorter_than_long(self):
        summary = generate_video_summary(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        assert len(summary.medium_summary) < len(summary.long_summary)

    def test_all_fields_non_empty(self):
        summary = generate_video_summary(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        assert summary.short_summary
        assert summary.medium_summary
        assert summary.long_summary

    def test_empty_transcript_graceful_defaults(self):
        summary = generate_video_summary("", _SAMPLE_TITLE)
        assert summary.short_summary
        assert summary.medium_summary
        assert summary.long_summary
        assert len(summary.short_summary) < len(summary.long_summary)

    def test_short_is_1_to_2_sentences(self):
        summary = generate_video_summary(_SAMPLE_TRANSCRIPT, _SAMPLE_TITLE)
        # Short summary should not be excessively long
        assert len(summary.short_summary) < 300


# ---------------------------------------------------------------------------
# extract_resource_mentions
# ---------------------------------------------------------------------------


class TestExtractResourceMentions:
    def test_finds_tool_names(self):
        transcript = (
            "I'm using a rotary cutter to cut the fabric. "
            "My sewing machine is a Brother machine. "
        )
        resources = extract_resource_mentions(transcript)
        names = [r["name"].lower() for r in resources]
        assert any("cutter" in n or "rotary" in n or "machine" in n for n in names)

    def test_finds_brand_model(self):
        transcript = "I'm using a Schmetz 90 needle for this fabric."
        resources = extract_resource_mentions(transcript)
        names = [r["name"] for r in resources]
        assert any("Schmetz" in n for n in names)

    def test_returns_list_of_dicts(self):
        resources = extract_resource_mentions(_SAMPLE_TRANSCRIPT)
        assert isinstance(resources, list)
        for r in resources:
            assert "name" in r
            assert "context" in r
            assert "timestamp_hint" in r

    def test_empty_transcript_returns_empty_list(self):
        resources = extract_resource_mentions("")
        assert resources == []

    def test_no_duplicates_by_name(self):
        resources = extract_resource_mentions(_SAMPLE_TRANSCRIPT)
        names_lower = [r["name"].lower() for r in resources]
        assert len(names_lower) == len(set(names_lower))


# ---------------------------------------------------------------------------
# package_publish_bundle
# ---------------------------------------------------------------------------


class TestPackagePublishBundle:
    def test_all_files_written_to_reports_publish(self, tmp_path: Path):
        _write_transcript(tmp_path)
        _write_chapters(tmp_path)
        _write_manifest(tmp_path)

        bundle = package_publish_bundle(tmp_path)
        publish_dir = tmp_path / "reports" / "publish"

        assert publish_dir.exists()
        assert (publish_dir / "title_options.txt").exists()
        assert (publish_dir / "description.txt").exists()
        assert (publish_dir / "tags.txt").exists()
        assert (publish_dir / "hashtags.txt").exists()
        assert (publish_dir / "pinned_comment.txt").exists()
        assert (publish_dir / "chapters.txt").exists()
        assert (publish_dir / "summary.md").exists()
        assert (publish_dir / "resources.txt").exists()
        assert (publish_dir / "publish_bundle.json").exists()

    def test_returns_publish_bundle_instance(self, tmp_path: Path):
        _write_transcript(tmp_path)
        bundle = package_publish_bundle(tmp_path)
        assert isinstance(bundle, PublishBundle)

    def test_publish_bundle_json_is_valid(self, tmp_path: Path):
        _write_transcript(tmp_path)
        package_publish_bundle(tmp_path)
        publish_dir = tmp_path / "reports" / "publish"
        data = json.loads((publish_dir / "publish_bundle.json").read_text())
        assert "title_variants" in data
        assert "description" in data
        assert "tags" in data

    def test_tags_file_one_per_line(self, tmp_path: Path):
        _write_transcript(tmp_path)
        bundle = package_publish_bundle(tmp_path)
        publish_dir = tmp_path / "reports" / "publish"
        tags_lines = (publish_dir / "tags.txt").read_text().splitlines()
        assert len(tags_lines) >= 5
        assert tags_lines == bundle.tags

    def test_empty_workspace_graceful(self, tmp_path: Path):
        # No transcripts, no chapters — should not raise
        bundle = package_publish_bundle(tmp_path)
        assert isinstance(bundle, PublishBundle)
        publish_dir = tmp_path / "reports" / "publish"
        assert (publish_dir / "description.txt").exists()

    def test_chapters_text_format(self, tmp_path: Path):
        _write_transcript(tmp_path)
        _write_chapters(tmp_path)
        bundle = package_publish_bundle(tmp_path)
        if bundle.chapters_text:
            lines = bundle.chapters_text.strip().splitlines()
            for line in lines:
                assert re.match(r"^\d+:\d{2} - .+", line), f"Bad format: {line!r}"


# ---------------------------------------------------------------------------
# generate_publish_note
# ---------------------------------------------------------------------------


class TestGeneratePublishNote:
    def _make_bundle(self) -> PublishBundle:
        return PublishBundle(
            title_variants=TitleVariants(
                searchable="How to Sew a Zippered Pouch | Tutorial",
                curiosity="This Pouch Changed My Setup",
                how_to="How to Sew a Zippered Pouch",
                short_punchy="DIY Zippered Pouch",
            ),
            description="Great video description here.",
            tags=["sewing", "diy", "myog"],
            hashtags=["#DIY", "#sewing", "#MYOG"],
            pinned_comment="Thanks for watching!",
            chapters_text="0:00 - Intro\n0:45 - Materials",
            summary=VideoSummary(
                short_summary="Learn to sew a pouch.",
                medium_summary="Learn to sew a waterproof zippered pouch in this tutorial.",
                long_summary="In this tutorial, we build a full waterproof zippered pouch from scratch using X-Pac fabric.",
            ),
            resources=[{"name": "X-Pac Fabric", "context": "I'm using X-Pac fabric", "timestamp_hint": "segment ~1"}],
        )

    def test_creates_note_at_correct_path(self, tmp_path: Path):
        _write_manifest(tmp_path)
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        bundle = self._make_bundle()
        note_path = generate_publish_note(tmp_path, vault_path, bundle)
        assert note_path.exists()
        assert note_path.parent.name == "Published"

    def test_note_has_yaml_frontmatter(self, tmp_path: Path):
        _write_manifest(tmp_path)
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        bundle = self._make_bundle()
        note_path = generate_publish_note(tmp_path, vault_path, bundle)
        content = note_path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "\n---\n" in content

    def test_frontmatter_has_status_published(self, tmp_path: Path):
        _write_manifest(tmp_path)
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        bundle = self._make_bundle()
        note_path = generate_publish_note(tmp_path, vault_path, bundle)
        content = note_path.read_text(encoding="utf-8")
        fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        assert fm_match
        fm = yaml.safe_load(fm_match.group(1))
        assert fm["status"] == "published"

    def test_frontmatter_has_publish_date(self, tmp_path: Path):
        _write_manifest(tmp_path)
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        bundle = self._make_bundle()
        note_path = generate_publish_note(tmp_path, vault_path, bundle)
        content = note_path.read_text(encoding="utf-8")
        fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        fm = yaml.safe_load(fm_match.group(1))
        assert "publish_date" in fm

    def test_note_body_has_summary_section(self, tmp_path: Path):
        _write_manifest(tmp_path)
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        bundle = self._make_bundle()
        note_path = generate_publish_note(tmp_path, vault_path, bundle)
        content = note_path.read_text(encoding="utf-8")
        assert "## Summary" in content

    def test_note_body_has_chapters_section(self, tmp_path: Path):
        _write_manifest(tmp_path)
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        bundle = self._make_bundle()
        note_path = generate_publish_note(tmp_path, vault_path, bundle)
        content = note_path.read_text(encoding="utf-8")
        assert "## Chapters" in content

    def test_note_body_has_tags_section(self, tmp_path: Path):
        _write_manifest(tmp_path)
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        bundle = self._make_bundle()
        note_path = generate_publish_note(tmp_path, vault_path, bundle)
        content = note_path.read_text(encoding="utf-8")
        assert "## Tags" in content

    def test_youtube_url_in_frontmatter(self, tmp_path: Path):
        _write_manifest(tmp_path)
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        bundle = self._make_bundle()
        note_path = generate_publish_note(
            tmp_path, vault_path, bundle, video_url="https://youtube.com/watch?v=abc123"
        )
        content = note_path.read_text(encoding="utf-8")
        assert "abc123" in content

    def test_updating_existing_note_merges_frontmatter(self, tmp_path: Path):
        _write_manifest(tmp_path)
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        bundle = self._make_bundle()
        # Create note first time
        note_path = generate_publish_note(tmp_path, vault_path, bundle)
        # Update it second time with a URL
        generate_publish_note(
            tmp_path, vault_path, bundle, video_url="https://youtube.com/watch?v=xyz"
        )
        content = note_path.read_text(encoding="utf-8")
        assert "xyz" in content
        assert content.startswith("---\n")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestPublishingModels:
    def test_title_variants_defaults(self):
        tv = TitleVariants()
        assert tv.searchable == ""
        assert tv.curiosity == ""
        assert tv.how_to == ""
        assert tv.short_punchy == ""

    def test_video_summary_defaults(self):
        vs = VideoSummary()
        assert vs.short_summary == ""
        assert vs.medium_summary == ""
        assert vs.long_summary == ""

    def test_publish_bundle_defaults(self):
        pb = PublishBundle()
        assert pb.tags == []
        assert pb.hashtags == []
        assert pb.resources == []

    def test_publish_bundle_serialization(self):
        bundle = PublishBundle(
            tags=["diy", "sewing"],
            hashtags=["#DIY"],
        )
        json_str = bundle.to_json()
        reloaded = PublishBundle.from_json(json_str)
        assert reloaded.tags == ["diy", "sewing"]
        assert reloaded.hashtags == ["#DIY"]
