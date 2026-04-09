"""YouTube analytics pipeline.

Fetches channel/video data, computes performance metrics, generates
markdown reports, and saves analytics notes to an Obsidian vault.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

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

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _seconds_to_mmss(seconds: float) -> str:
    """Convert float seconds to MM:SS string."""
    total_secs = int(seconds)
    minutes = total_secs // 60
    secs = total_secs % 60
    return f"{minutes}:{secs:02d}"


def _format_date(upload_date: str) -> str:
    """Convert YYYYMMDD string to YYYY-MM-DD, or return as-is if already formatted/empty."""
    if len(upload_date) == 8 and upload_date.isdigit():
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    return upload_date


def _slugify(text: str) -> str:
    """Create a safe filename slug from text."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")[:80]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_channel(channel_url: str, max_videos: int = 50) -> ChannelStats:
    """Fetch and analyze a YouTube channel.

    Args:
        channel_url: YouTube channel URL.
        max_videos: Maximum number of videos to fetch.

    Returns:
        ChannelStats with all videos and aggregated metrics.
    """
    videos = fetch_channel_videos(channel_url, max_videos=max_videos)
    return build_channel_stats(videos, channel_url=channel_url)


def analyze_video(
    video_url: str, channel_stats: ChannelStats | None = None
) -> VideoAnalytics:
    """Analyze a single video's performance vs channel averages.

    Args:
        video_url: YouTube video URL.
        channel_stats: Optional channel stats for comparison. If None, only raw
            data is returned without comparative metrics.

    Returns:
        VideoAnalytics with performance classification and insights.
    """
    video = fetch_single_video(video_url)
    return _compute_video_analytics(video, channel_stats)


def _compute_video_analytics(
    video: YouTubeVideo, channel_stats: ChannelStats | None
) -> VideoAnalytics:
    """Build a VideoAnalytics from an already-fetched video + optional channel context."""
    # Engagement rate: likes / views
    engagement_rate = (
        video.like_count / video.view_count if video.view_count > 0 else 0.0
    )

    if channel_stats is None or channel_stats.avg_views == 0:
        return VideoAnalytics(
            video=video,
            performance="",
            views_vs_avg=0.0,
            likes_vs_avg=0.0,
            engagement_rate=engagement_rate,
            notes=[],
        )

    views_vs_avg = video.view_count / channel_stats.avg_views
    likes_vs_avg = (
        video.like_count / channel_stats.avg_likes
        if channel_stats.avg_likes > 0
        else 0.0
    )

    # Classify performance based on views ratio
    if views_vs_avg >= 1.5:
        performance = "above_average"
    elif views_vs_avg < 0.5:
        performance = "below_average"
    else:
        performance = "average"

    # Generate insights
    notes: list[str] = []

    if views_vs_avg >= 2.0:
        notes.append(
            f"This video got {views_vs_avg:.1f}x your average views — strong performer."
        )
    elif views_vs_avg >= 1.5:
        notes.append(
            f"Views are {views_vs_avg:.1f}x the channel average — above average."
        )
    elif views_vs_avg < 0.5:
        notes.append(
            f"Views are only {views_vs_avg:.1f}x the channel average — below average."
        )

    avg_engagement = (
        channel_stats.avg_likes / channel_stats.avg_views
        if channel_stats.avg_views > 0
        else 0.0
    )
    if avg_engagement > 0 and engagement_rate < avg_engagement * 0.5:
        notes.append(
            f"Low engagement rate ({engagement_rate:.1%}) compared to channel average "
            f"({avg_engagement:.1%})."
        )
    elif avg_engagement > 0 and engagement_rate >= avg_engagement * 1.5:
        notes.append(
            f"High engagement rate ({engagement_rate:.1%}) — audience responded well."
        )

    if likes_vs_avg >= 1.5:
        notes.append(f"Likes are {likes_vs_avg:.1f}x the channel average.")

    return VideoAnalytics(
        video=video,
        performance=performance,
        views_vs_avg=views_vs_avg,
        likes_vs_avg=likes_vs_avg,
        engagement_rate=engagement_rate,
        notes=notes,
    )


def generate_analytics_report(stats: ChannelStats) -> str:
    """Generate a markdown analytics report for a channel.

    Args:
        stats: ChannelStats from analyze_channel or build_channel_stats.

    Returns:
        Full markdown string.
    """
    lines: list[str] = []

    channel_label = stats.channel_name or stats.channel_url or "Unknown Channel"

    lines.append(f"# YouTube Analytics: {channel_label}")
    lines.append("")
    lines.append(f"*Report generated: {stats.fetched_at}*")
    lines.append("")

    # --- Channel Overview ---
    lines.append("## Channel Overview")
    lines.append("")
    lines.append(f"- **Total Videos Analysed:** {stats.total_videos:,}")
    lines.append(f"- **Total Views:** {stats.total_views:,}")
    lines.append(f"- **Total Likes:** {stats.total_likes:,}")
    lines.append(f"- **Average Views:** {stats.avg_views:,.0f}")
    lines.append(f"- **Average Likes:** {stats.avg_likes:,.0f}")
    lines.append(f"- **Average Duration:** {_seconds_to_mmss(stats.avg_duration)}")
    if stats.most_viewed:
        lines.append(f"- **Most Viewed:** {stats.most_viewed}")
    if stats.most_liked:
        lines.append(f"- **Most Liked:** {stats.most_liked}")
    lines.append("")

    videos = stats.videos
    if not videos:
        lines.append("*No video data available.*")
        return "\n".join(lines)

    # --- Top 10 by Views ---
    lines.append("## Top 10 Videos by Views")
    lines.append("")
    lines.append("| # | Title | Views | Likes | Engagement |")
    lines.append("|---|-------|-------|-------|------------|")
    top_by_views = sorted(videos, key=lambda v: v.view_count, reverse=True)[:10]
    for i, v in enumerate(top_by_views, start=1):
        engagement = (
            f"{v.like_count / v.view_count:.1%}" if v.view_count > 0 else "—"
        )
        lines.append(
            f"| {i} | {v.title} | {v.view_count:,} | {v.like_count:,} | {engagement} |"
        )
    lines.append("")

    # --- Top 10 by Engagement ---
    lines.append("## Top 10 Videos by Engagement")
    lines.append("")
    lines.append("| # | Title | Views | Likes | Engagement |")
    lines.append("|---|-------|-------|-------|------------|")
    videos_with_views = [v for v in videos if v.view_count > 0]
    top_by_engagement = sorted(
        videos_with_views,
        key=lambda v: v.like_count / v.view_count,
        reverse=True,
    )[:10]
    for i, v in enumerate(top_by_engagement, start=1):
        engagement = f"{v.like_count / v.view_count:.1%}"
        lines.append(
            f"| {i} | {v.title} | {v.view_count:,} | {v.like_count:,} | {engagement} |"
        )
    lines.append("")

    # --- Upload Frequency ---
    lines.append("## Upload Frequency")
    lines.append("")
    dated_videos = [v for v in videos if len(v.upload_date) == 8 and v.upload_date.isdigit()]
    if dated_videos:
        dates = sorted(v.upload_date for v in dated_videos)
        lines.append(f"- Oldest video date: {_format_date(dates[0])}")
        lines.append(f"- Newest video date: {_format_date(dates[-1])}")
        # Monthly counts
        month_counts: Counter[str] = Counter()
        for v in dated_videos:
            month_counts[v.upload_date[:6]] += 1
        if month_counts:
            lines.append(
                f"- Active months: {len(month_counts)}"
            )
            avg_per_month = len(dated_videos) / len(month_counts)
            lines.append(f"- Average uploads per active month: {avg_per_month:.1f}")
    else:
        lines.append("*Upload date data not available.*")
    lines.append("")

    # --- Average Duration Analysis ---
    lines.append("## Duration Analysis")
    lines.append("")
    videos_with_dur = [v for v in videos if v.duration_seconds > 0]
    if videos_with_dur:
        short = [v for v in videos_with_dur if v.duration_seconds < 300]
        medium = [v for v in videos_with_dur if 300 <= v.duration_seconds < 1200]
        long_ = [v for v in videos_with_dur if v.duration_seconds >= 1200]
        lines.append(f"- Short (< 5 min): {len(short)} videos")
        lines.append(f"- Medium (5–20 min): {len(medium)} videos")
        lines.append(f"- Long (> 20 min): {len(long_)} videos")
        lines.append(f"- Average duration: {_seconds_to_mmss(stats.avg_duration)}")
    else:
        lines.append("*Duration data not available.*")
    lines.append("")

    # --- Tag Analysis ---
    lines.append("## Common Tags")
    lines.append("")
    all_tags: list[str] = []
    for v in videos:
        all_tags.extend(t.lower() for t in v.tags if t)
    if all_tags:
        tag_counts = Counter(all_tags)
        lines.append("| Tag | Count |")
        lines.append("|-----|-------|")
        for tag, count in tag_counts.most_common(20):
            lines.append(f"| {tag} | {count} |")
    else:
        lines.append("*No tag data available.*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Vault saving
# ---------------------------------------------------------------------------


def save_channel_to_vault(vault_path: Path, stats: ChannelStats) -> list[Path]:
    """Save channel analytics to an Obsidian vault.

    Creates:
    - Research/Analytics/Channel Overview.md (channel summary)
    - Research/Analytics/Videos/<slug>.md (one note per video)
    - Research/Analytics/report.md (full analytics report)

    Args:
        vault_path: Path to the Obsidian vault root.
        stats: ChannelStats to persist.

    Returns:
        List of Paths created.
    """
    vault_path = Path(vault_path)
    analytics_dir = vault_path / "Research" / "Analytics"
    videos_dir = analytics_dir / "Videos"
    analytics_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []

    # 1. Full report
    report_path = analytics_dir / "report.md"
    report_path.write_text(generate_analytics_report(stats), encoding="utf-8")
    created.append(report_path)

    # 2. Channel overview note
    overview_path = analytics_dir / "Channel Overview.md"
    overview_path.write_text(
        _build_channel_overview_note(stats), encoding="utf-8"
    )
    created.append(overview_path)

    # 3. Per-video notes
    avg_views = stats.avg_views
    avg_likes = stats.avg_likes
    avg_views_nonzero = avg_views if avg_views > 0 else None

    for video in stats.videos:
        analytics = _compute_video_analytics(
            video,
            stats if avg_views_nonzero is not None else None,
        )
        note_content = _build_video_note(analytics)
        slug = _slugify(video.title) or video.video_id
        note_path = videos_dir / f"{slug}.md"
        note_path.write_text(note_content, encoding="utf-8")
        created.append(note_path)

    return created


def _build_channel_overview_note(stats: ChannelStats) -> str:
    """Build the channel overview Obsidian note."""
    fetched_date = stats.fetched_at[:10] if stats.fetched_at else ""
    channel_label = stats.channel_name or stats.channel_url or "Unknown"

    lines: list[str] = []
    lines.append("---")
    lines.append("title: Channel Analytics")
    lines.append(f'channel: "{channel_label}"')
    lines.append(f"total_videos: {stats.total_videos}")
    lines.append(f"total_views: {stats.total_views}")
    lines.append(f"fetched: {fetched_date}")
    lines.append("---")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- Total Videos: {stats.total_videos:,}")
    lines.append(f"- Total Views: {stats.total_views:,}")
    lines.append(f"- Average Views: {stats.avg_views:,.0f}")
    lines.append(f"- Average Likes: {stats.avg_likes:,.0f}")
    lines.append(f"- Average Duration: {_seconds_to_mmss(stats.avg_duration)}")
    lines.append("")

    videos = stats.videos
    if not videos:
        lines.append("*No video data available.*")
        return "\n".join(lines)

    # Top videos by views table
    lines.append("## Top Videos by Views")
    lines.append("")
    lines.append("| # | Title | Views | Likes | Engagement |")
    lines.append("|---|-------|-------|-------|------------|")
    top_by_views = sorted(videos, key=lambda v: v.view_count, reverse=True)[:10]
    for i, v in enumerate(top_by_views, start=1):
        engagement = (
            f"{v.like_count / v.view_count:.1%}" if v.view_count > 0 else "—"
        )
        lines.append(
            f"| {i} | {v.title} | {v.view_count:,} | {v.like_count:,} | {engagement} |"
        )
    lines.append("")

    # Top videos by engagement table
    lines.append("## Top Videos by Engagement")
    lines.append("")
    lines.append("| # | Title | Views | Likes | Engagement |")
    lines.append("|---|-------|-------|-------|------------|")
    videos_with_views = [v for v in videos if v.view_count > 0]
    top_by_eng = sorted(
        videos_with_views,
        key=lambda v: v.like_count / v.view_count,
        reverse=True,
    )[:10]
    for i, v in enumerate(top_by_eng, start=1):
        engagement = f"{v.like_count / v.view_count:.1%}"
        lines.append(
            f"| {i} | {v.title} | {v.view_count:,} | {v.like_count:,} | {engagement} |"
        )
    lines.append("")

    # Common tags
    all_tags: list[str] = []
    for v in videos:
        all_tags.extend(t.lower() for t in v.tags if t)
    if all_tags:
        tag_counts = Counter(all_tags)
        lines.append("## Common Tags")
        lines.append("")
        for tag, count in tag_counts.most_common(15):
            lines.append(f"- {tag} ({count})")
        lines.append("")

    # Upload frequency
    dated = [v for v in videos if len(v.upload_date) == 8 and v.upload_date.isdigit()]
    if dated:
        month_counts: Counter[str] = Counter(v.upload_date[:6] for v in dated)
        lines.append("## Upload Frequency")
        lines.append("")
        lines.append(f"- Active months tracked: {len(month_counts)}")
        avg_pm = len(dated) / len(month_counts) if month_counts else 0
        lines.append(f"- Average uploads/month: {avg_pm:.1f}")
        lines.append("")

    return "\n".join(lines)


def _build_video_note(analytics: VideoAnalytics) -> str:
    """Build a single video Obsidian note."""
    v = analytics.video
    date_str = _format_date(v.upload_date)
    engagement_pct = f"{analytics.engagement_rate:.1%}"
    performance_display = analytics.performance.replace("_", " ").title() if analytics.performance else ""

    lines: list[str] = []
    lines.append("---")
    lines.append(f'title: "{v.title}"')
    lines.append(f"video_id: {v.video_id}")
    lines.append(f"upload_date: {date_str}")
    lines.append(f"views: {v.view_count}")
    lines.append(f"likes: {v.like_count}")
    lines.append(f"duration: {int(v.duration_seconds)}")
    lines.append(f"engagement_rate: {analytics.engagement_rate:.3f}")
    lines.append(f"performance: {analytics.performance}")
    tags_yaml = ", ".join(v.tags) if v.tags else ""
    lines.append(f"tags: [{tags_yaml}]")
    lines.append(f'url: "{v.url}"')
    lines.append("---")
    lines.append("")

    lines.append("## Stats")
    lines.append("")
    lines.append(f"- Views: {v.view_count:,}")
    lines.append(f"- Likes: {v.like_count:,}")
    lines.append(f"- Comments: {v.comment_count:,}")
    lines.append(f"- Duration: {_seconds_to_mmss(v.duration_seconds)}")
    lines.append(f"- Engagement: {engagement_pct}")
    if performance_display and analytics.views_vs_avg > 0:
        lines.append(
            f"- Performance: {performance_display} ({analytics.views_vs_avg:.1f}x channel avg)"
        )
    elif performance_display:
        lines.append(f"- Performance: {performance_display}")
    lines.append("")

    if v.description:
        lines.append("## Description")
        lines.append("")
        lines.append(v.description)
        lines.append("")

    if v.tags:
        lines.append("## Tags")
        lines.append("")
        for tag in v.tags:
            lines.append(f"- {tag}")
        lines.append("")

    if analytics.notes:
        lines.append("## Notes")
        lines.append("")
        for note in analytics.notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)
