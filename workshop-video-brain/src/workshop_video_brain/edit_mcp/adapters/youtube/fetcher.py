"""YouTube data fetcher using yt-dlp."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from workshop_video_brain.core.models.youtube import ChannelStats, YouTubeVideo

logger = logging.getLogger(__name__)


def _safe_int(value: object) -> int:
    """Convert value to int, returning 0 for None or conversion errors."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    """Convert value to float, returning 0.0 for None or conversion errors."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_str(value: object) -> str:
    """Convert value to str, returning '' for None."""
    if value is None:
        return ""
    return str(value)


def _safe_list(value: object) -> list[str]:
    """Convert value to list[str], returning [] for None or non-list types."""
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _entry_to_video(entry: dict) -> YouTubeVideo | None:
    """Convert a yt-dlp info dict entry to a YouTubeVideo.

    Returns None if the entry is missing a video_id (e.g., private/deleted videos).
    """
    video_id = _safe_str(entry.get("id"))
    if not video_id:
        return None

    return YouTubeVideo(
        video_id=video_id,
        title=_safe_str(entry.get("title")),
        description=_safe_str(entry.get("description")),
        upload_date=_safe_str(entry.get("upload_date")),
        duration_seconds=_safe_float(entry.get("duration")),
        view_count=_safe_int(entry.get("view_count")),
        like_count=_safe_int(entry.get("like_count")),
        comment_count=_safe_int(entry.get("comment_count")),
        tags=_safe_list(entry.get("tags")),
        categories=_safe_list(entry.get("categories")),
        thumbnail_url=_safe_str(entry.get("thumbnail")),
        url=_safe_str(entry.get("webpage_url")),
        channel_name=_safe_str(entry.get("channel")),
        channel_id=_safe_str(entry.get("channel_id")),
    )


def fetch_channel_videos(channel_url: str, max_videos: int = 50) -> list[YouTubeVideo]:
    """Fetch video data from a YouTube channel using yt-dlp.

    Args:
        channel_url: YouTube channel URL (e.g., https://youtube.com/@username or channel ID).
        max_videos: Maximum videos to fetch.

    Returns:
        List of YouTubeVideo objects with public data.

    Raises:
        ImportError: if yt-dlp is not installed.
        Exception: if the channel URL is invalid or inaccessible.
    """
    try:
        import yt_dlp  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "yt-dlp is required for YouTube analytics. Install with: pip install yt-dlp"
        ) from exc

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "playlistend": max_videos,
        "ignoreerrors": True,
    }

    url = f"{channel_url.rstrip('/')}/videos"
    videos: list[YouTubeVideo] = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        logger.warning("yt-dlp returned no info for %s", url)
        return videos

    entries = info.get("entries") or []
    for entry in entries:
        if entry is None:
            continue
        try:
            video = _entry_to_video(entry)
            if video is not None:
                videos.append(video)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping entry due to error: %s", exc)
            continue

    return videos


def fetch_single_video(video_url: str) -> YouTubeVideo:
    """Fetch data for a single YouTube video.

    Args:
        video_url: Full YouTube video URL or short ID.

    Returns:
        YouTubeVideo with all available public metadata.

    Raises:
        ImportError: if yt-dlp is not installed.
        ValueError: if the video cannot be fetched or has no ID.
    """
    try:
        import yt_dlp  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "yt-dlp is required for YouTube analytics. Install with: pip install yt-dlp"
        ) from exc

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    if info is None:
        raise ValueError(f"Could not fetch video data for: {video_url}")

    video = _entry_to_video(info)
    if video is None:
        raise ValueError(f"No video ID found in data for: {video_url}")

    return video


def build_channel_stats(videos: list[YouTubeVideo], channel_url: str = "") -> ChannelStats:
    """Calculate aggregated stats from a list of videos.

    Args:
        videos: List of YouTubeVideo objects.
        channel_url: Original channel URL for reference.

    Returns:
        ChannelStats with totals, averages, and top performers.
    """
    if not videos:
        return ChannelStats(
            channel_url=channel_url,
            fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    # Derive channel name/id from first video that has them
    channel_name = ""
    channel_id = ""
    for v in videos:
        if v.channel_name:
            channel_name = v.channel_name
        if v.channel_id:
            channel_id = v.channel_id
        if channel_name and channel_id:
            break

    total_videos = len(videos)
    total_views = sum(v.view_count for v in videos)
    total_likes = sum(v.like_count for v in videos)
    avg_views = total_views / total_videos if total_videos else 0.0
    avg_likes = total_likes / total_videos if total_videos else 0.0
    avg_duration = (
        sum(v.duration_seconds for v in videos) / total_videos if total_videos else 0.0
    )

    most_viewed_video = max(videos, key=lambda v: v.view_count)
    most_liked_video = max(videos, key=lambda v: v.like_count)

    return ChannelStats(
        channel_name=channel_name,
        channel_id=channel_id,
        channel_url=channel_url,
        total_videos=total_videos,
        total_views=total_views,
        total_likes=total_likes,
        avg_views=avg_views,
        avg_likes=avg_likes,
        avg_duration=avg_duration,
        most_viewed=most_viewed_video.title,
        most_liked=most_liked_video.title,
        videos=videos,
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
