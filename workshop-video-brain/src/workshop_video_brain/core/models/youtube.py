"""YouTube data models for analytics integration."""
from __future__ import annotations

from workshop_video_brain.core.models._base import SerializableMixin


class YouTubeVideo(SerializableMixin):
    """Data about a single YouTube video."""

    video_id: str
    title: str
    description: str = ""
    upload_date: str = ""          # YYYYMMDD format from yt-dlp
    duration_seconds: float = 0.0
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    tags: list[str] = []
    categories: list[str] = []
    thumbnail_url: str = ""
    url: str = ""
    channel_name: str = ""
    channel_id: str = ""


class ChannelStats(SerializableMixin):
    """Aggregated channel statistics."""

    channel_name: str = ""
    channel_id: str = ""
    channel_url: str = ""
    total_videos: int = 0
    total_views: int = 0
    total_likes: int = 0
    avg_views: float = 0.0
    avg_likes: float = 0.0
    avg_duration: float = 0.0
    most_viewed: str = ""
    most_liked: str = ""
    videos: list[YouTubeVideo] = []
    fetched_at: str = ""


class VideoAnalytics(SerializableMixin):
    """Analytics comparison for a single video."""

    video: YouTubeVideo
    performance: str = ""           # "above_average", "average", "below_average"
    views_vs_avg: float = 0.0      # ratio: this video views / channel avg
    likes_vs_avg: float = 0.0
    engagement_rate: float = 0.0    # likes / views
    notes: list[str] = []           # insights
