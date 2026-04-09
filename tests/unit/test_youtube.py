"""Unit tests for YouTube analytics integration.

Covers:
- fetch_channel_videos with mocked yt-dlp → correct YouTubeVideo list
- fetch_single_video with mock → correct YouTubeVideo
- build_channel_stats → correct averages and totals
- analyze_video above_average → classified correctly
- analyze_video below_average → classified correctly
- analyze_video with no channel_stats → empty performance
- generate_analytics_report → valid markdown with tables
- save_channel_to_vault → files created in correct vault paths
- Handle missing fields (None view_count, etc.) → defaults to 0
- Handle yt-dlp error → graceful error message
- Empty channel (no videos) → empty stats, not crash
- Private/None entries → skipped gracefully
- build_channel_stats channel name/id from first video
- _seconds_to_mmss helper
- Video note content verification
- Channel overview note content verification
- Report tag analysis section
- Report upload frequency section
- _format_date helper
- _slugify helper via vault note filename
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models.youtube import (
    ChannelStats,
    VideoAnalytics,
    YouTubeVideo,
)
from workshop_video_brain.edit_mcp.adapters.youtube.fetcher import (
    build_channel_stats,
    fetch_channel_videos,
    fetch_single_video,
)
from workshop_video_brain.edit_mcp.pipelines.youtube_analytics import (
    _seconds_to_mmss,
    analyze_channel,
    analyze_video,
    generate_analytics_report,
    save_channel_to_vault,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_ydl_entry(
    video_id: str = "abc123",
    title: str = "Test Video",
    description: str = "A test video",
    upload_date: str = "20250615",
    duration: float = 720.0,
    view_count: int = 1000,
    like_count: int = 80,
    comment_count: int = 15,
    tags: list[str] | None = None,
    categories: list[str] | None = None,
    thumbnail: str = "https://img.youtube.com/abc123",
    webpage_url: str = "https://www.youtube.com/watch?v=abc123",
    channel: str = "Test Channel",
    channel_id: str = "UC_test_channel_id",
) -> dict:
    """Build a dict that mimics a yt-dlp info entry."""
    return {
        "id": video_id,
        "title": title,
        "description": description,
        "upload_date": upload_date,
        "duration": duration,
        "view_count": view_count,
        "like_count": like_count,
        "comment_count": comment_count,
        "tags": tags if tags is not None else ["woodworking", "diy"],
        "categories": categories if categories is not None else ["Howto & Style"],
        "thumbnail": thumbnail,
        "webpage_url": webpage_url,
        "channel": channel,
        "channel_id": channel_id,
    }


def _make_channel_info(entries: list[dict]) -> dict:
    """Wrap entries in a channel-level yt-dlp info dict."""
    return {
        "id": "UC_test_channel_id",
        "title": "Test Channel",
        "entries": entries,
    }


def _make_sample_videos(count: int = 5) -> list[YouTubeVideo]:
    """Create a list of YouTubeVideo objects for testing."""
    return [
        YouTubeVideo(
            video_id=f"vid{i}",
            title=f"Video {i}",
            description=f"Description for video {i}",
            upload_date=f"2025{i:02d}15" if i <= 9 else "20250115",
            duration_seconds=300.0 + i * 60,
            view_count=100 * i,
            like_count=10 * i,
            comment_count=i,
            tags=["tag1", "tag2"],
            categories=["Education"],
            url=f"https://youtube.com/watch?v=vid{i}",
            channel_name="Test Channel",
            channel_id="UC_test",
        )
        for i in range(1, count + 1)
    ]


# ---------------------------------------------------------------------------
# fetch_channel_videos tests
# ---------------------------------------------------------------------------


class TestFetchChannelVideos:
    def test_returns_correct_video_list(self):
        """fetch_channel_videos maps yt-dlp entries to YouTubeVideo objects."""
        entry = _make_ydl_entry()
        info = _make_channel_info([entry])

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            videos = fetch_channel_videos("https://youtube.com/@test", max_videos=5)

        assert len(videos) == 1
        v = videos[0]
        assert v.video_id == "abc123"
        assert v.title == "Test Video"
        assert v.view_count == 1000
        assert v.like_count == 80
        assert v.comment_count == 15
        assert v.duration_seconds == 720.0
        assert v.channel_name == "Test Channel"
        assert v.channel_id == "UC_test_channel_id"
        assert v.upload_date == "20250615"
        assert v.tags == ["woodworking", "diy"]

    def test_handles_none_entries(self):
        """None entries in the list are skipped gracefully."""
        entry = _make_ydl_entry()
        info = _make_channel_info([None, entry, None])

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            videos = fetch_channel_videos("https://youtube.com/@test")

        assert len(videos) == 1

    def test_handles_missing_fields_defaults_to_zero(self):
        """Missing / None fields in yt-dlp output default to 0 / empty string."""
        entry = {
            "id": "xyz999",
            "title": "Sparse Video",
            "description": None,
            "upload_date": None,
            "duration": None,
            "view_count": None,
            "like_count": None,
            "comment_count": None,
            "tags": None,
            "categories": None,
            "thumbnail": None,
            "webpage_url": None,
            "channel": None,
            "channel_id": None,
        }
        info = _make_channel_info([entry])

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            videos = fetch_channel_videos("https://youtube.com/@test")

        assert len(videos) == 1
        v = videos[0]
        assert v.view_count == 0
        assert v.like_count == 0
        assert v.comment_count == 0
        assert v.duration_seconds == 0.0
        assert v.tags == []
        assert v.description == ""

    def test_empty_channel_returns_empty_list(self):
        """A channel with no entries returns an empty list without crashing."""
        info = _make_channel_info([])

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            videos = fetch_channel_videos("https://youtube.com/@empty")

        assert videos == []

    def test_ydl_returns_none_returns_empty_list(self):
        """If yt-dlp returns None info, returns empty list without crashing."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = None
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            videos = fetch_channel_videos("https://youtube.com/@broken")

        assert videos == []

    def test_skips_entries_missing_video_id(self):
        """Entries with no 'id' field are skipped."""
        entry_no_id = {"title": "Private Video", "view_count": 100}
        entry_ok = _make_ydl_entry(video_id="good1")
        info = _make_channel_info([entry_no_id, entry_ok])

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            videos = fetch_channel_videos("https://youtube.com/@test")

        assert len(videos) == 1
        assert videos[0].video_id == "good1"


# ---------------------------------------------------------------------------
# fetch_single_video tests
# ---------------------------------------------------------------------------


class TestFetchSingleVideo:
    def test_returns_correct_video(self):
        """fetch_single_video maps yt-dlp info dict to YouTubeVideo."""
        entry = _make_ydl_entry(video_id="single1", title="Single Video", view_count=5000)

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = entry
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            video = fetch_single_video("https://youtube.com/watch?v=single1")

        assert video.video_id == "single1"
        assert video.title == "Single Video"
        assert video.view_count == 5000

    def test_raises_on_none_info(self):
        """fetch_single_video raises ValueError when yt-dlp returns None."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = None
        mock_ydl.__enter__ = lambda s: mock_ydl
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with pytest.raises(ValueError, match="Could not fetch video data"):
                fetch_single_video("https://youtube.com/watch?v=bad")


# ---------------------------------------------------------------------------
# build_channel_stats tests
# ---------------------------------------------------------------------------


class TestBuildChannelStats:
    def test_correct_totals_and_averages(self):
        """build_channel_stats computes correct totals and averages."""
        videos = _make_sample_videos(5)
        stats = build_channel_stats(videos, channel_url="https://youtube.com/@test")

        assert stats.total_videos == 5
        # view_counts: 100, 200, 300, 400, 500 → sum = 1500
        assert stats.total_views == 1500
        # like_counts: 10, 20, 30, 40, 50 → sum = 150
        assert stats.total_likes == 150
        assert stats.avg_views == pytest.approx(300.0)
        assert stats.avg_likes == pytest.approx(30.0)

    def test_most_viewed_and_most_liked(self):
        """build_channel_stats identifies most viewed and most liked videos."""
        videos = _make_sample_videos(5)
        stats = build_channel_stats(videos)

        assert stats.most_viewed == "Video 5"
        assert stats.most_liked == "Video 5"

    def test_channel_name_from_videos(self):
        """Channel name and ID are extracted from video data."""
        videos = _make_sample_videos(3)
        stats = build_channel_stats(videos)

        assert stats.channel_name == "Test Channel"
        assert stats.channel_id == "UC_test"

    def test_empty_videos_returns_empty_stats(self):
        """Empty video list returns default ChannelStats without error."""
        stats = build_channel_stats([], channel_url="https://youtube.com/@empty")

        assert stats.total_videos == 0
        assert stats.total_views == 0
        assert stats.avg_views == 0.0
        assert stats.videos == []

    def test_avg_duration_calculation(self):
        """Average duration is correctly calculated."""
        videos = _make_sample_videos(3)
        # durations: 360, 420, 480 → avg = 420
        stats = build_channel_stats(videos)
        assert stats.avg_duration == pytest.approx(420.0)


# ---------------------------------------------------------------------------
# analyze_video tests
# ---------------------------------------------------------------------------


class TestAnalyzeVideo:
    def _channel_stats_with_avg(self, avg_views: float) -> ChannelStats:
        """Build minimal ChannelStats with specified avg_views."""
        return ChannelStats(
            channel_name="Test Channel",
            avg_views=avg_views,
            avg_likes=avg_views * 0.08,
        )

    def test_above_average_classification(self):
        """Video with views >= 1.5x avg is classified as above_average."""
        video = YouTubeVideo(
            video_id="v1", title="Top Video",
            view_count=1500, like_count=120,
        )
        channel_stats = self._channel_stats_with_avg(avg_views=500.0)

        with patch(
            "workshop_video_brain.edit_mcp.pipelines.youtube_analytics.fetch_single_video",
            return_value=video,
        ):
            analytics = analyze_video("https://youtube.com/watch?v=v1", channel_stats)

        assert analytics.performance == "above_average"
        assert analytics.views_vs_avg == pytest.approx(3.0)

    def test_below_average_classification(self):
        """Video with views < 0.5x avg is classified as below_average."""
        video = YouTubeVideo(
            video_id="v2", title="Low Video",
            view_count=100, like_count=5,
        )
        channel_stats = self._channel_stats_with_avg(avg_views=500.0)

        with patch(
            "workshop_video_brain.edit_mcp.pipelines.youtube_analytics.fetch_single_video",
            return_value=video,
        ):
            analytics = analyze_video("https://youtube.com/watch?v=v2", channel_stats)

        assert analytics.performance == "below_average"
        assert analytics.views_vs_avg == pytest.approx(0.2)

    def test_average_classification(self):
        """Video with views between 0.5x and 1.5x avg is classified as average."""
        video = YouTubeVideo(
            video_id="v3", title="Mid Video",
            view_count=500, like_count=40,
        )
        channel_stats = self._channel_stats_with_avg(avg_views=500.0)

        with patch(
            "workshop_video_brain.edit_mcp.pipelines.youtube_analytics.fetch_single_video",
            return_value=video,
        ):
            analytics = analyze_video("https://youtube.com/watch?v=v3", channel_stats)

        assert analytics.performance == "average"

    def test_no_channel_stats_returns_empty_performance(self):
        """Without channel_stats, performance is empty string."""
        video = YouTubeVideo(
            video_id="v4", title="Solo Video",
            view_count=1000, like_count=80,
        )

        with patch(
            "workshop_video_brain.edit_mcp.pipelines.youtube_analytics.fetch_single_video",
            return_value=video,
        ):
            analytics = analyze_video("https://youtube.com/watch?v=v4", None)

        assert analytics.performance == ""
        assert analytics.views_vs_avg == 0.0
        assert analytics.notes == []

    def test_engagement_rate_calculated(self):
        """Engagement rate is likes/views."""
        video = YouTubeVideo(
            video_id="v5", title="Eng Video",
            view_count=1000, like_count=100,
        )

        with patch(
            "workshop_video_brain.edit_mcp.pipelines.youtube_analytics.fetch_single_video",
            return_value=video,
        ):
            analytics = analyze_video("https://youtube.com/watch?v=v5", None)

        assert analytics.engagement_rate == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# generate_analytics_report tests
# ---------------------------------------------------------------------------


class TestGenerateAnalyticsReport:
    def test_returns_valid_markdown(self):
        """generate_analytics_report returns a markdown string with expected sections."""
        videos = _make_sample_videos(5)
        stats = build_channel_stats(videos, channel_url="https://youtube.com/@test")
        stats = stats.model_copy(update={"channel_name": "Test Channel"})

        report = generate_analytics_report(stats)

        assert "# YouTube Analytics:" in report
        assert "## Channel Overview" in report
        assert "## Top 10 Videos by Views" in report
        assert "## Top 10 Videos by Engagement" in report
        assert "## Upload Frequency" in report
        assert "## Duration Analysis" in report
        assert "## Common Tags" in report

    def test_contains_tables(self):
        """Report contains markdown table syntax."""
        videos = _make_sample_videos(3)
        stats = build_channel_stats(videos)
        report = generate_analytics_report(stats)

        # Tables have | separators
        assert "|" in report

    def test_empty_channel_report(self):
        """Report for empty channel still generates without crashing."""
        stats = ChannelStats(channel_name="Empty Channel")
        report = generate_analytics_report(stats)

        assert "Empty Channel" in report
        assert "No video data available" in report

    def test_report_includes_totals(self):
        """Report includes total views and average metrics."""
        videos = _make_sample_videos(5)
        stats = build_channel_stats(videos)
        report = generate_analytics_report(stats)

        assert "1,500" in report  # total_views = 1500
        assert "300" in report    # avg_views = 300


# ---------------------------------------------------------------------------
# save_channel_to_vault tests
# ---------------------------------------------------------------------------


class TestSaveChannelToVault:
    def test_creates_expected_files(self, tmp_path: Path):
        """save_channel_to_vault creates channel overview, report, and video notes."""
        videos = _make_sample_videos(3)
        stats = build_channel_stats(videos, channel_url="https://youtube.com/@test")
        stats = stats.model_copy(update={"channel_name": "Test Channel"})

        created = save_channel_to_vault(tmp_path, stats)

        analytics_dir = tmp_path / "Research" / "Analytics"
        assert (analytics_dir / "report.md").exists()
        assert (analytics_dir / "Channel Overview.md").exists()

        videos_dir = analytics_dir / "Videos"
        assert videos_dir.exists()
        # 3 video notes + 1 report + 1 overview = 5 paths
        assert len(created) == 5

    def test_video_note_has_frontmatter(self, tmp_path: Path):
        """Each video note contains YAML frontmatter with expected fields."""
        videos = [
            YouTubeVideo(
                video_id="abc123",
                title="My Tutorial",
                view_count=500,
                like_count=40,
                duration_seconds=600,
                upload_date="20250601",
                url="https://youtube.com/watch?v=abc123",
                channel_name="Test Channel",
                channel_id="UC_test",
            )
        ]
        stats = build_channel_stats(videos)

        created = save_channel_to_vault(tmp_path, stats)

        # Find the video note
        video_notes = [p for p in created if "Videos" in str(p)]
        assert len(video_notes) == 1

        content = video_notes[0].read_text(encoding="utf-8")
        assert "video_id: abc123" in content
        assert "views: 500" in content
        assert "likes: 40" in content
        assert "## Stats" in content

    def test_channel_overview_has_frontmatter(self, tmp_path: Path):
        """Channel overview note has YAML frontmatter with channel fields."""
        videos = _make_sample_videos(2)
        stats = build_channel_stats(videos)
        stats = stats.model_copy(update={"channel_name": "My Workshop"})

        save_channel_to_vault(tmp_path, stats)

        overview = (tmp_path / "Research" / "Analytics" / "Channel Overview.md")
        content = overview.read_text(encoding="utf-8")
        assert "title: Channel Analytics" in content
        assert 'channel: "My Workshop"' in content
        assert "total_videos:" in content

    def test_empty_channel_saves_without_crash(self, tmp_path: Path):
        """Empty channel stats save without error."""
        stats = ChannelStats(channel_name="Empty")

        created = save_channel_to_vault(tmp_path, stats)

        # Should still create report and overview
        assert len(created) >= 2

    def test_creates_nested_directories(self, tmp_path: Path):
        """Vault subdirectories are created if they don't exist."""
        vault = tmp_path / "my-vault"
        # Do NOT pre-create it — save_channel_to_vault should create it
        videos = _make_sample_videos(1)
        stats = build_channel_stats(videos)

        save_channel_to_vault(vault, stats)

        assert (vault / "Research" / "Analytics").exists()
        assert (vault / "Research" / "Analytics" / "Videos").exists()


# ---------------------------------------------------------------------------
# Misc helper tests
# ---------------------------------------------------------------------------


class TestSecondsMmss:
    def test_under_one_hour(self):
        assert _seconds_to_mmss(720.0) == "12:00"

    def test_zero(self):
        assert _seconds_to_mmss(0.0) == "0:00"

    def test_one_hour(self):
        assert _seconds_to_mmss(3600.0) == "60:00"

    def test_fractional_seconds_truncated(self):
        assert _seconds_to_mmss(90.9) == "1:30"
