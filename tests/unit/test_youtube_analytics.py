"""Tests for YouTube analytics pipeline (PL-09)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models.youtube import ChannelStats, VideoAnalytics, YouTubeVideo
from workshop_video_brain.edit_mcp.pipelines.youtube_analytics import (
    _format_date,
    _seconds_to_mmss,
    _slugify,
    analyze_channel,
    analyze_video,
    generate_analytics_report,
    save_channel_to_vault,
)

YT_MOD = "workshop_video_brain.edit_mcp.pipelines.youtube_analytics"
FETCHER_MOD = "workshop_video_brain.edit_mcp.adapters.youtube.fetcher"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_video(
    title: str = "Test",
    view_count: int = 1000,
    like_count: int = 50,
    comment_count: int = 10,
    duration_seconds: float = 600.0,
    upload_date: str = "20240101",
    tags: list[str] | None = None,
    video_id: str = "abc123",
    url: str = "https://youtube.com/watch?v=abc123",
    description: str = "",
) -> YouTubeVideo:
    return YouTubeVideo(
        video_id=video_id,
        title=title,
        description=description,
        upload_date=upload_date,
        duration_seconds=duration_seconds,
        view_count=view_count,
        like_count=like_count,
        comment_count=comment_count,
        tags=tags or [],
        url=url,
    )


def make_channel_stats(
    videos: list[YouTubeVideo] | None = None,
    avg_views: float = 1000.0,
    avg_likes: float = 50.0,
    avg_duration: float = 600.0,
    total_videos: int = 1,
    total_views: int = 1000,
    total_likes: int = 50,
    channel_url: str = "https://youtube.com/@test",
    channel_name: str = "Test Channel",
    most_viewed: str = "",
    most_liked: str = "",
    fetched_at: str | None = None,
) -> ChannelStats:
    return ChannelStats(
        channel_name=channel_name,
        channel_url=channel_url,
        total_videos=total_videos,
        total_views=total_views,
        total_likes=total_likes,
        avg_views=avg_views,
        avg_likes=avg_likes,
        avg_duration=avg_duration,
        most_viewed=most_viewed,
        most_liked=most_liked,
        videos=videos or [],
        fetched_at=fetched_at or datetime.now(tz=timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# TestSecondsToMmss
# ---------------------------------------------------------------------------


class TestSecondsToMmss:
    def test_zero_seconds(self):
        assert _seconds_to_mmss(0) == "0:00"

    def test_one_minute(self):
        assert _seconds_to_mmss(60) == "1:00"

    def test_ninety_seconds(self):
        assert _seconds_to_mmss(90) == "1:30"

    def test_large_value(self):
        assert _seconds_to_mmss(3661) == "61:01"


# ---------------------------------------------------------------------------
# TestFormatDate
# ---------------------------------------------------------------------------


class TestFormatDate:
    def test_yyyymmdd_formatted(self):
        assert _format_date("20240115") == "2024-01-15"

    def test_already_formatted_returned_as_is(self):
        assert _format_date("2024-01-15") == "2024-01-15"

    def test_empty_string_returned_as_is(self):
        assert _format_date("") == ""

    def test_non_numeric_returned_as_is(self):
        assert _format_date("unknown") == "unknown"


# ---------------------------------------------------------------------------
# TestSlugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_spaces_become_hyphens(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars_removed(self):
        result = _slugify("Test: Video!")
        assert result == "test-video"

    def test_truncated_to_80_chars(self):
        long_input = "word " * 25  # > 80 chars
        assert len(_slugify(long_input)) <= 80

    def test_leading_trailing_hyphens_stripped(self):
        assert _slugify("--test--") == "test"


# ---------------------------------------------------------------------------
# TestAnalyzeChannel
# ---------------------------------------------------------------------------


class TestAnalyzeChannel:
    @patch(f"{YT_MOD}.build_channel_stats")
    @patch(f"{YT_MOD}.fetch_channel_videos")
    def test_delegates_to_fetcher_and_builder(self, mock_fetch, mock_build):
        video = make_video()
        mock_fetch.return_value = [video]
        expected_stats = make_channel_stats(videos=[video])
        mock_build.return_value = expected_stats

        result = analyze_channel("https://youtube.com/@test")
        assert result is expected_stats

    @patch(f"{YT_MOD}.build_channel_stats")
    @patch(f"{YT_MOD}.fetch_channel_videos")
    def test_max_videos_passed_to_fetcher(self, mock_fetch, mock_build):
        mock_fetch.return_value = []
        mock_build.return_value = make_channel_stats()

        analyze_channel("https://...", max_videos=5)

        call_kwargs = mock_fetch.call_args[1]
        assert call_kwargs.get("max_videos") == 5


# ---------------------------------------------------------------------------
# TestAnalyzeVideo
# ---------------------------------------------------------------------------


class TestAnalyzeVideo:
    @patch(f"{YT_MOD}.fetch_single_video")
    def test_returns_video_analytics_instance(self, mock_fetch):
        mock_fetch.return_value = make_video()
        result = analyze_video("https://youtube.com/watch?v=abc")
        assert isinstance(result, VideoAnalytics)

    @patch(f"{YT_MOD}.fetch_single_video")
    def test_engagement_rate_computed(self, mock_fetch):
        mock_fetch.return_value = make_video(view_count=1000, like_count=50)
        result = analyze_video("https://youtube.com/watch?v=abc")
        assert abs(result.engagement_rate - 0.05) < 1e-9

    @patch(f"{YT_MOD}.fetch_single_video")
    def test_zero_views_engagement_rate_is_zero(self, mock_fetch):
        mock_fetch.return_value = make_video(view_count=0, like_count=0)
        result = analyze_video("https://youtube.com/watch?v=abc")
        assert result.engagement_rate == 0.0

    @patch(f"{YT_MOD}.fetch_single_video")
    def test_no_channel_stats_returns_empty_performance(self, mock_fetch):
        mock_fetch.return_value = make_video()
        result = analyze_video("https://youtube.com/watch?v=abc", channel_stats=None)
        assert result.performance == ""
        assert result.views_vs_avg == 0.0


# ---------------------------------------------------------------------------
# TestVideoPerformanceClassification
# ---------------------------------------------------------------------------


def _analytics_with_ratio(views_vs_avg: float) -> VideoAnalytics:
    """Create a VideoAnalytics with a specific views_vs_avg ratio."""
    from workshop_video_brain.edit_mcp.pipelines.youtube_analytics import _compute_video_analytics
    video = make_video(view_count=int(views_vs_avg * 1000))
    stats = make_channel_stats(avg_views=1000.0, avg_likes=50.0)
    stats.videos = [video]
    return _compute_video_analytics(video, stats)


class TestVideoPerformanceClassification:
    def test_above_average_when_views_1_5x(self):
        result = _analytics_with_ratio(1.5)
        assert result.performance == "above_average"

    def test_below_average_when_views_less_than_0_5x(self):
        result = _analytics_with_ratio(0.499)
        assert result.performance == "below_average"

    def test_average_between_thresholds(self):
        result = _analytics_with_ratio(1.0)
        assert result.performance == "average"

    def test_exactly_0_5_is_average(self):
        result = _analytics_with_ratio(0.5)
        assert result.performance == "average"

    def test_exactly_1_5_is_above_average(self):
        result = _analytics_with_ratio(1.5)
        assert result.performance == "above_average"


# ---------------------------------------------------------------------------
# TestVideoAnalyticsNotes
# ---------------------------------------------------------------------------


def _compute(video: YouTubeVideo, stats: ChannelStats) -> VideoAnalytics:
    from workshop_video_brain.edit_mcp.pipelines.youtube_analytics import _compute_video_analytics
    return _compute_video_analytics(video, stats)


class TestVideoAnalyticsNotes:
    def test_2x_views_generates_strong_performer_note(self):
        video = make_video(view_count=2000)
        stats = make_channel_stats(avg_views=1000.0, avg_likes=50.0)
        result = _compute(video, stats)
        assert any("strong performer" in n for n in result.notes)

    def test_1_5x_views_generates_above_average_note(self):
        video = make_video(view_count=1600)
        stats = make_channel_stats(avg_views=1000.0, avg_likes=50.0)
        result = _compute(video, stats)
        assert any("above average" in n for n in result.notes)

    def test_below_0_5x_views_generates_below_average_note(self):
        video = make_video(view_count=400)
        stats = make_channel_stats(avg_views=1000.0, avg_likes=50.0)
        result = _compute(video, stats)
        assert any("below average" in n for n in result.notes)

    def test_low_engagement_rate_generates_note(self):
        # avg engagement = 50/1000 = 5%; video engagement = 1/1000 = 0.1%
        video = make_video(view_count=1000, like_count=1)
        stats = make_channel_stats(avg_views=1000.0, avg_likes=50.0)
        result = _compute(video, stats)
        assert any("Low engagement" in n for n in result.notes)

    def test_high_engagement_rate_generates_note(self):
        # avg engagement = 50/1000 = 5%; video engagement = 100/1000 = 10%
        video = make_video(view_count=1000, like_count=100)
        stats = make_channel_stats(avg_views=1000.0, avg_likes=50.0)
        result = _compute(video, stats)
        assert any("High engagement" in n for n in result.notes)

    def test_high_likes_generates_note(self):
        # avg_likes=50, video likes=100 → likes_vs_avg=2.0 ≥ 1.5
        video = make_video(view_count=1000, like_count=100)
        stats = make_channel_stats(avg_views=1000.0, avg_likes=50.0)
        result = _compute(video, stats)
        assert any("Likes are" in n for n in result.notes)

    def test_no_notes_when_all_metrics_average(self):
        # All ratios between 0.5 and 1.5, engagement normal
        video = make_video(view_count=1000, like_count=50)
        stats = make_channel_stats(avg_views=1000.0, avg_likes=50.0)
        result = _compute(video, stats)
        # No notes — views_vs_avg=1.0, likes_vs_avg=1.0, engagement is equal to avg
        assert result.notes == []


# ---------------------------------------------------------------------------
# TestGenerateAnalyticsReport
# ---------------------------------------------------------------------------


class TestGenerateAnalyticsReport:
    def test_empty_videos_returns_no_data_message(self):
        stats = make_channel_stats(videos=[])
        result = generate_analytics_report(stats)
        assert "*No video data available.*" in result

    def test_report_starts_with_channel_heading(self):
        stats = make_channel_stats(channel_name="My Channel", videos=[])
        result = generate_analytics_report(stats)
        assert result.startswith("# YouTube Analytics: My Channel")

    def test_channel_overview_section_present(self):
        stats = make_channel_stats(videos=[])
        result = generate_analytics_report(stats)
        assert "## Channel Overview" in result

    def test_top_10_by_views_section(self):
        stats = make_channel_stats(videos=[make_video()])
        result = generate_analytics_report(stats)
        assert "## Top 10 Videos by Views" in result

    def test_top_10_by_engagement_section(self):
        stats = make_channel_stats(videos=[make_video()])
        result = generate_analytics_report(stats)
        assert "## Top 10 Videos by Engagement" in result

    def test_upload_frequency_section(self):
        stats = make_channel_stats(videos=[make_video()])
        result = generate_analytics_report(stats)
        assert "## Upload Frequency" in result

    def test_duration_analysis_section(self):
        stats = make_channel_stats(videos=[make_video()])
        result = generate_analytics_report(stats)
        assert "## Duration Analysis" in result

    def test_common_tags_section_with_tags(self):
        video = make_video(tags=["sewing", "diy", "fabric"])
        stats = make_channel_stats(videos=[video])
        result = generate_analytics_report(stats)
        assert "## Common Tags" in result
        assert "sewing" in result

    def test_no_tags_shows_no_tag_data_message(self):
        video = make_video(tags=[])
        stats = make_channel_stats(videos=[video])
        result = generate_analytics_report(stats)
        assert "*No tag data available.*" in result

    def test_duration_buckets_counted_correctly(self):
        # short < 300s, medium 300-1200s, long >= 1200s
        short_vid = make_video(duration_seconds=100.0)
        med_vid = make_video(duration_seconds=600.0, video_id="v2")
        long_vid = make_video(duration_seconds=1500.0, video_id="v3")
        stats = make_channel_stats(videos=[short_vid, med_vid, long_vid])
        result = generate_analytics_report(stats)
        assert "Short (< 5 min): 1 videos" in result
        assert "Medium (5–20 min): 1 videos" in result
        assert "Long (> 20 min): 1 videos" in result

    def test_upload_date_no_dated_videos_shows_message(self):
        video = make_video(upload_date="")
        stats = make_channel_stats(videos=[video])
        result = generate_analytics_report(stats)
        assert "*Upload date data not available.*" in result

    def test_monthly_upload_count_computed(self):
        v1 = make_video(upload_date="20240101", video_id="v1")
        v2 = make_video(upload_date="20240115", video_id="v2")
        v3 = make_video(upload_date="20240116", video_id="v3")
        v4 = make_video(upload_date="20240201", video_id="v4")
        stats = make_channel_stats(videos=[v1, v2, v3, v4])
        result = generate_analytics_report(stats)
        assert "Active months: 2" in result
        assert "Average uploads per active month: 2.0" in result

    def test_falls_back_to_channel_url_when_no_name(self):
        stats = make_channel_stats(
            channel_name="", channel_url="https://youtube.com/@foo", videos=[]
        )
        result = generate_analytics_report(stats)
        assert "foo" in result


# ---------------------------------------------------------------------------
# TestSaveChannelToVault
# ---------------------------------------------------------------------------


class TestSaveChannelToVault:
    def test_creates_expected_directory_structure(self, tmp_path):
        stats = make_channel_stats(videos=[])
        save_channel_to_vault(tmp_path, stats)
        assert (tmp_path / "Research" / "Analytics").is_dir()
        assert (tmp_path / "Research" / "Analytics" / "Videos").is_dir()

    def test_report_md_created(self, tmp_path):
        stats = make_channel_stats(videos=[])
        save_channel_to_vault(tmp_path, stats)
        assert (tmp_path / "Research" / "Analytics" / "report.md").exists()

    def test_channel_overview_md_created(self, tmp_path):
        stats = make_channel_stats(videos=[])
        save_channel_to_vault(tmp_path, stats)
        assert (tmp_path / "Research" / "Analytics" / "Channel Overview.md").exists()

    def test_per_video_notes_created(self, tmp_path):
        v1 = make_video(title="Video One", video_id="v1")
        v2 = make_video(title="Video Two", video_id="v2")
        stats = make_channel_stats(videos=[v1, v2])
        save_channel_to_vault(tmp_path, stats)
        videos_dir = tmp_path / "Research" / "Analytics" / "Videos"
        md_files = list(videos_dir.glob("*.md"))
        assert len(md_files) == 2

    def test_video_note_slug_derived_from_title(self, tmp_path):
        video = make_video(title="How I Built a Bag", video_id="v1")
        stats = make_channel_stats(videos=[video])
        save_channel_to_vault(tmp_path, stats)
        expected = tmp_path / "Research" / "Analytics" / "Videos" / "how-i-built-a-bag.md"
        assert expected.exists()

    def test_video_note_has_frontmatter(self, tmp_path):
        video = make_video(video_id="v1")
        stats = make_channel_stats(videos=[video])
        save_channel_to_vault(tmp_path, stats)
        videos_dir = tmp_path / "Research" / "Analytics" / "Videos"
        md_file = next(videos_dir.glob("*.md"))
        assert md_file.read_text().startswith("---")

    def test_returns_list_of_created_paths(self, tmp_path):
        v1 = make_video(video_id="v1", title="First")
        v2 = make_video(video_id="v2", title="Second")
        stats = make_channel_stats(videos=[v1, v2])
        result = save_channel_to_vault(tmp_path, stats)
        assert isinstance(result, list)
        assert len(result) == 4  # report + overview + 2 videos

    def test_empty_channel_still_creates_base_files(self, tmp_path):
        stats = make_channel_stats(videos=[])
        result = save_channel_to_vault(tmp_path, stats)
        assert len(result) == 2

    def test_video_note_contains_stats_section(self, tmp_path):
        video = make_video(video_id="v1", title="My Video")
        stats = make_channel_stats(videos=[video])
        save_channel_to_vault(tmp_path, stats)
        videos_dir = tmp_path / "Research" / "Analytics" / "Videos"
        md_file = next(videos_dir.glob("*.md"))
        content = md_file.read_text()
        assert "## Stats" in content
