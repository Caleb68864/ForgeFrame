---
scenario_id: "PL-09"
title: "YouTube Analytics"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario PL-09: YouTube Analytics

## Description
Tests `analyze_channel`, `analyze_video`, `generate_analytics_report`, and
`save_channel_to_vault` from `youtube_analytics.py`. The module fetches channel
and video data via adapter functions (`fetch_channel_videos`, `fetch_single_video`,
`build_channel_stats`), computes engagement rates and performance classifications,
and renders a full markdown report. Covers: mocked fetcher returning empty channel,
performance classification thresholds (above/average/below), engagement note
generation, report sections for empty vs populated data, vault file creation, and
internal formatting helpers.

## Preconditions
- `workshop-video-brain` installed in editable mode
- All fetcher calls patched:
  - `workshop_video_brain.edit_mcp.adapters.youtube.fetcher.fetch_channel_videos`
  - `workshop_video_brain.edit_mcp.adapters.youtube.fetcher.fetch_single_video`
  - `workshop_video_brain.edit_mcp.adapters.youtube.fetcher.build_channel_stats`
- `YouTubeVideo`, `ChannelStats`, `VideoAnalytics` from
  `workshop_video_brain.core.models.youtube`
- `tmp_path` for vault save tests; no network access

## Test Cases

```
tests/unit/test_youtube_analytics.py

from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime, timezone

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_video(title="Test", view_count=1000, like_count=50,
               comment_count=10, duration_seconds=600,
               upload_date="20240101", tags=None, video_id="abc123",
               url="https://youtube.com/watch?v=abc123", description="")
    # Returns a YouTubeVideo instance

def make_channel_stats(videos=None, avg_views=1000.0, avg_likes=50.0,
                       avg_duration=600.0, total_videos=1, total_views=1000,
                       total_likes=50, channel_url="https://youtube.com/@test",
                       channel_name="Test Channel",
                       most_viewed=None, most_liked=None,
                       fetched_at=None)
    # Returns a ChannelStats; fetched_at defaults to current ISO string

# ── Internal helpers ──────────────────────────────────────────────────────────

class TestSecondsToMmss:
    def test_zero_seconds()
        # _seconds_to_mmss(0) == "0:00"
    def test_one_minute()
        # _seconds_to_mmss(60) == "1:00"
    def test_ninety_seconds()
        # _seconds_to_mmss(90) == "1:30"
    def test_large_value()
        # _seconds_to_mmss(3661) == "61:01"

class TestFormatDate:
    def test_yyyymmdd_formatted()
        # _format_date("20240115") == "2024-01-15"
    def test_already_formatted_returned_as_is()
        # _format_date("2024-01-15") == "2024-01-15"
    def test_empty_string_returned_as_is()
        # _format_date("") == ""
    def test_non_numeric_returned_as_is()
        # _format_date("unknown") == "unknown"

class TestSlugify:
    def test_spaces_become_hyphens()
        # _slugify("Hello World") == "hello-world"
    def test_special_chars_removed()
        # _slugify("Test: Video!") == "test-video"
    def test_truncated_to_80_chars()
        # input of 100 chars → len(result) <= 80
    def test_leading_trailing_hyphens_stripped()
        # _slugify("--test--") == "test"

# ── analyze_channel ───────────────────────────────────────────────────────────

class TestAnalyzeChannel:
    def test_delegates_to_fetcher_and_builder()
        # Patch fetch_channel_videos → returns [video]
        # Patch build_channel_stats → returns mock ChannelStats
        # analyze_channel("https://...") returns the mocked ChannelStats

    def test_max_videos_passed_to_fetcher()
        # analyze_channel("url", max_videos=5)
        # fetch_channel_videos called with max_videos=5

# ── analyze_video ─────────────────────────────────────────────────────────────

class TestAnalyzeVideo:
    def test_returns_video_analytics_instance()
        # Patch fetch_single_video → returns a YouTubeVideo
        # analyze_video("url") returns VideoAnalytics

    def test_engagement_rate_computed()
        # video: view_count=1000, like_count=50 → engagement_rate == 0.05

    def test_zero_views_engagement_rate_is_zero()
        # view_count=0, like_count=0 → engagement_rate == 0.0

    def test_no_channel_stats_returns_empty_performance()
        # analyze_video("url", channel_stats=None)
        # result.performance == ""
        # result.views_vs_avg == 0.0

class TestVideoPerformanceClassification:
    def test_above_average_when_views_1_5x()
        # views_vs_avg = 1.5 → performance == "above_average"

    def test_below_average_when_views_less_than_0_5x()
        # views_vs_avg = 0.499 → performance == "below_average"

    def test_average_between_thresholds()
        # views_vs_avg = 1.0 → performance == "average"

    def test_exactly_0_5_is_average()
        # views_vs_avg = 0.5 → performance == "average"

    def test_exactly_1_5_is_above_average()
        # views_vs_avg = 1.5 → performance == "above_average"

class TestVideoAnalyticsNotes:
    def test_2x_views_generates_strong_performer_note()
        # views_vs_avg >= 2.0 → note contains "strong performer"

    def test_1_5x_views_generates_above_average_note()
        # 1.5 <= views_vs_avg < 2.0 → note contains "above average"

    def test_below_0_5x_views_generates_below_average_note()
        # views_vs_avg < 0.5 → note contains "below average"

    def test_low_engagement_rate_generates_note()
        # engagement_rate < avg_engagement * 0.5 → note contains "Low engagement"

    def test_high_engagement_rate_generates_note()
        # engagement_rate >= avg_engagement * 1.5 → note contains "High engagement"

    def test_high_likes_generates_note()
        # likes_vs_avg >= 1.5 → note contains "Likes are"

    def test_no_notes_when_all_metrics_average()
        # All ratios between 0.5 and 1.5, engagement normal → notes == []

# ── generate_analytics_report ─────────────────────────────────────────────────

class TestGenerateAnalyticsReport:
    def test_empty_videos_returns_no_data_message()
        # ChannelStats with videos=[]
        # result contains "*No video data available.*"

    def test_report_starts_with_channel_heading()
        # stats.channel_name = "My Channel"
        # result starts with "# YouTube Analytics: My Channel"

    def test_channel_overview_section_present()
        # "## Channel Overview" in result

    def test_top_10_by_views_section()
        # "## Top 10 Videos by Views" in result

    def test_top_10_by_engagement_section()
        # "## Top 10 Videos by Engagement" in result

    def test_upload_frequency_section()
        # "## Upload Frequency" in result

    def test_duration_analysis_section()
        # "## Duration Analysis" in result

    def test_common_tags_section_with_tags()
        # Videos with tags → "## Common Tags" with tag table

    def test_no_tags_shows_no_tag_data_message()
        # Videos with empty tags → "*No tag data available.*"

    def test_duration_buckets_counted_correctly()
        # short(<300s), medium(300-1200s), long(>1200s) counts match input

    def test_upload_date_no_dated_videos_shows_message()
        # All videos with upload_date="" → "*Upload date data not available.*"

    def test_monthly_upload_count_computed()
        # 3 videos in month "202401", 1 in "202402"
        # active months == 2, avg per month == 2.0

    def test_falls_back_to_channel_url_when_no_name()
        # stats.channel_name = None, channel_url = "https://youtube.com/@foo"
        # heading contains "foo"

# ── save_channel_to_vault ─────────────────────────────────────────────────────

class TestSaveChannelToVault:
    def test_creates_expected_directory_structure(tmp_path)
        # save_channel_to_vault(tmp_path, stats)
        # (tmp_path / "Research" / "Analytics").is_dir() is True
        # (tmp_path / "Research" / "Analytics" / "Videos").is_dir() is True

    def test_report_md_created(tmp_path)
        # (tmp_path / "Research" / "Analytics" / "report.md").exists()

    def test_channel_overview_md_created(tmp_path)
        # (tmp_path / "Research" / "Analytics" / "Channel Overview.md").exists()

    def test_per_video_notes_created(tmp_path)
        # stats with 2 videos → 2 .md files in Videos/

    def test_video_note_slug_derived_from_title(tmp_path)
        # video.title = "How I Built a Bag"
        # Videos/how-i-built-a-bag.md exists

    def test_video_note_has_frontmatter(tmp_path)
        # note content starts with "---"

    def test_returns_list_of_created_paths(tmp_path)
        # Returns a list; len == 2 + num_videos

    def test_empty_channel_still_creates_base_files(tmp_path)
        # stats with videos=[] → report.md and Channel Overview.md created
        # returned list has 2 items

    def test_video_note_contains_stats_section(tmp_path)
        # note content contains "## Stats"
```

## Steps
1. Read source module to understand current API
2. Create test file at `tests/unit/test_youtube_analytics.py`
3. Implement test cases with mocked dependencies
4. Run: `uv run pytest tests/unit/test_youtube_analytics.py -v`

## Expected Results
- `analyze_channel` delegates entirely to the fetcher adapter; max_videos is forwarded
- Performance thresholds: `>= 1.5x` → above_average, `< 0.5x` → below_average
- `generate_analytics_report` includes all six section headings when videos are present
- `save_channel_to_vault` creates `Research/Analytics/`, `Videos/`, `report.md`,
  `Channel Overview.md`, and one `.md` per video; returns paths of all files created
- Zero-view videos are excluded from engagement-rate rankings to avoid division by zero

## Pass / Fail Criteria
- Pass: All test cases pass, no import errors
- Fail: Any test fails or source API doesn't match expectations
