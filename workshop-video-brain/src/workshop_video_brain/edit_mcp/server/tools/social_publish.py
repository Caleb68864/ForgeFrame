"""Social clip, publishing, and YouTube analytics tools.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # noqa: F401
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    bad_json_param,
    corrupt_project,
    media_unreadable,
    not_found,
    invalid_input,
    from_exception,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _validate_workspace_path,
)





# ---------------------------------------------------------------------------
# Social clip tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def social_find_clips(
    workspace_path: str,
    max_clips: int = 5,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> dict:
    """Find highlight clips suitable for YouTube Shorts/social media from transcript.

    Args:
        workspace_path: Path to the workspace root directory.
        max_clips: Maximum number of clips to return.
        min_duration: Minimum clip duration in seconds.
        max_duration: Maximum clip duration in seconds.

    Returns:
        List of clip candidates with scores and timestamps.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        from workshop_video_brain.core.models.transcript import Transcript
        from workshop_video_brain.edit_mcp.pipelines.social_clips import (
            find_highlight_segments,
        )

        transcripts_dir = ws_path / "transcripts"
        if not transcripts_dir.exists():
            return _err("No transcripts/ directory found. Run media_ingest first.")

        all_segments: list[dict] = []
        all_text_parts: list[str] = []
        for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
            try:
                transcript = Transcript.from_json(
                    json_path.read_text(encoding="utf-8")
                )
                for seg in transcript.segments:
                    all_segments.append({
                        "start_seconds": seg.start_seconds,
                        "end_seconds": seg.end_seconds,
                        "text": seg.text,
                    })
                    all_text_parts.append(seg.text)
            except Exception:
                pass

        transcript_text = " ".join(all_text_parts)
        candidates = find_highlight_segments(
            transcript_text,
            all_segments,
            min_duration=min_duration,
            max_duration=max_duration,
        )
        candidates = candidates[:max_clips]

        return _ok({
            "clips_found": len(candidates),
            "candidates": [json.loads(c.to_json()) for c in candidates],
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def social_generate_package(
    workspace_path: str,
    max_clips: int = 5,
    aspect_ratio: str = "9:16",
) -> dict:
    """Generate complete social media package: clips, titles, captions, posts.

    Args:
        workspace_path: Path to the workspace root directory.
        max_clips: Maximum number of clips to include.
        aspect_ratio: Aspect ratio for clips (9:16 for Shorts/Reels, 16:9 for YouTube).

    Returns:
        Package summary with paths to generated files.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.social_clips import (
            generate_social_package,
        )

        result = generate_social_package(
            workspace_root=ws_path,
            max_clips=max_clips,
            aspect_ratio=aspect_ratio,
        )
        return _ok(result)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def social_clip_post(
    workspace_path: str,
    clip_index: int = 0,
    platform: str = "youtube",
) -> dict:
    """Generate social media post text for a specific clip.

    Args:
        workspace_path: Path to the workspace root directory.
        clip_index: Zero-based index of the clip in the manifest.
        platform: Target platform (youtube, instagram, tiktok, twitter).

    Returns:
        Post text, hashtags, and clip title for the specified platform.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        manifest_path = ws_path / "reports" / "social" / "clips_manifest.json"
        if not manifest_path.exists():
            return _err(
                "No clips manifest found. Run social_generate_package first."
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest:
            return _err("Clips manifest is empty.")
        if clip_index < 0 or clip_index >= len(manifest):
            return _err(
                f"clip_index {clip_index} out of range (0-{len(manifest) - 1})."
            )

        from workshop_video_brain.core.models.social import ClipCandidate
        from workshop_video_brain.edit_mcp.pipelines.social_clips import (
            create_social_post_text,
        )

        clip_data = manifest[clip_index]
        # Build a minimal ClipCandidate from manifest data
        candidate = ClipCandidate(
            start_seconds=float(clip_data.get("start_seconds", 0.0)),
            end_seconds=float(clip_data.get("end_seconds", 0.0)),
            duration_seconds=float(clip_data.get("end_seconds", 0.0))
            - float(clip_data.get("start_seconds", 0.0)),
            hook_text=clip_data.get("title", ""),
            content_summary=clip_data.get("description", ""),
        )

        post = create_social_post_text(
            candidate,
            platform=platform,
            video_title=clip_data.get("title", ""),
            hashtags=clip_data.get("hashtags", []),
        )
        return _ok({
            "platform": post.platform,
            "post_text": post.post_text,
            "hashtags": post.hashtags,
            "clip_title": post.clip_title,
        })
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Publishing tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def publish_bundle(
    workspace_path: str,
    video_url: str = "",
    links: str = "",
) -> dict:
    """Generate complete YouTube publish bundle: title options, description, tags, hashtags, chapters, summary, pinned comment. Saves all files to workspace/reports/publish/.

    Args:
        workspace_path: Path to the workspace root directory.
        video_url: Optional YouTube URL (included in publish note if vault configured).
        links: Optional comma-separated list of resource links.

    Returns:
        Full publish bundle including all generated assets.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.publishing import package_publish_bundle

        links_list = [l.strip() for l in links.split(",") if l.strip()] if links else None
        bundle = package_publish_bundle(ws_path, links=links_list)

        return _ok({
            "title_variants": bundle.title_variants.model_dump(),
            "description": bundle.description,
            "tags": bundle.tags,
            "hashtags": bundle.hashtags,
            "pinned_comment": bundle.pinned_comment,
            "chapters_text": bundle.chapters_text,
            "summary": bundle.summary.model_dump(),
            "resources": bundle.resources,
            "publish_dir": str(ws_path / "reports" / "publish"),
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def publish_description(workspace_path: str) -> dict:
    """Generate YouTube description from transcript and chapters.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Generated YouTube description text.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.publishing import (
            _transcript_text_from_workspace,
            _read_chapters_from_workspace,
            _get_workspace_title,
            generate_youtube_description,
        )

        title = _get_workspace_title(ws_path)
        transcript_text = _transcript_text_from_workspace(ws_path)
        chapters = _read_chapters_from_workspace(ws_path)
        description = generate_youtube_description(title, transcript_text, chapters)

        return _ok({"description": description, "title": title})
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def publish_titles(workspace_path: str) -> dict:
    """Generate 4 title variants (searchable, curiosity, how-to, short).

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Four title variants for the video.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.publishing import (
            _transcript_text_from_workspace,
            _get_workspace_title,
            generate_title_variants,
        )

        title = _get_workspace_title(ws_path)
        transcript_text = _transcript_text_from_workspace(ws_path)
        variants = generate_title_variants(title, transcript_text)

        return _ok(variants.model_dump())
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def publish_tags(workspace_path: str) -> dict:
    """Generate SEO tags and hashtags from transcript.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        SEO tags and hashtags for the video.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.publishing import (
            _transcript_text_from_workspace,
            _get_workspace_title,
            generate_tags,
            generate_hashtags,
        )

        title = _get_workspace_title(ws_path)
        transcript_text = _transcript_text_from_workspace(ws_path)
        tags = generate_tags(transcript_text, title)
        hashtags = generate_hashtags(tags)

        return _ok({"tags": tags, "hashtags": hashtags})
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def publish_summary(workspace_path: str) -> dict:
    """Generate short, medium, and long video summaries.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Short, medium, and long summaries of the video.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.publishing import (
            _transcript_text_from_workspace,
            _get_workspace_title,
            generate_video_summary,
        )

        title = _get_workspace_title(ws_path)
        transcript_text = _transcript_text_from_workspace(ws_path)
        summary = generate_video_summary(transcript_text, title)

        return _ok(summary.model_dump())
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def publish_note(workspace_path: str, video_url: str = "") -> dict:
    """Create Obsidian publish note with full bundle in vault.

    Args:
        workspace_path: Path to the workspace root directory.
        video_url: Optional YouTube URL for the published video.

    Returns:
        Path to the created/updated Obsidian note.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.publishing import (
            package_publish_bundle,
            generate_publish_note,
        )
        from workshop_video_brain.app.config import load_config

        config = load_config()
        vault_path = getattr(config, "vault_path", None) or ""
        if not vault_path:
            return _err(
                "Vault path not configured. Set WVB_VAULT_PATH env var or run 'wvb init'."
            )

        bundle = package_publish_bundle(ws_path)
        note_path = generate_publish_note(ws_path, Path(vault_path), bundle, video_url)

        return _ok({"note_path": str(note_path), "video_url": video_url})
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# YouTube analytics tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def youtube_fetch_channel(channel_url: str, max_videos: int = 50) -> dict:
    """Fetch video data from a YouTube channel. Requires yt-dlp.

    Args:
        channel_url: YouTube channel URL (e.g., https://youtube.com/@username).
        max_videos: Maximum number of videos to fetch (default 50).

    Returns:
        Channel stats and list of video metadata.
    """
    try:
        from workshop_video_brain.edit_mcp.adapters.youtube.fetcher import (
            fetch_channel_videos,
            build_channel_stats,
        )

        videos = fetch_channel_videos(channel_url, max_videos=max_videos)
        stats = build_channel_stats(videos, channel_url=channel_url)
        return _ok({
            "channel_name": stats.channel_name,
            "channel_id": stats.channel_id,
            "total_videos": stats.total_videos,
            "total_views": stats.total_views,
            "fetched_at": stats.fetched_at,
            "videos": [v.model_dump(mode="json") for v in videos],
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def youtube_fetch_video(video_url: str) -> dict:
    """Fetch data for a single YouTube video.

    Args:
        video_url: Full YouTube video URL or short ID.

    Returns:
        Video metadata as a dict.
    """
    try:
        from workshop_video_brain.edit_mcp.adapters.youtube.fetcher import fetch_single_video

        video = fetch_single_video(video_url)
        return _ok(video.model_dump(mode="json"))
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def youtube_analyze(channel_url: str, max_videos: int = 50) -> dict:
    """Fetch and analyze a YouTube channel with stats and insights.

    Args:
        channel_url: YouTube channel URL.
        max_videos: Maximum number of videos to fetch (default 50).

    Returns:
        Channel stats with averages, top videos, and engagement metrics.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.youtube_analytics import analyze_channel

        stats = analyze_channel(channel_url, max_videos=max_videos)
        return _ok(stats.model_dump(mode="json"))
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def youtube_save_to_vault(channel_url: str, max_videos: int = 50) -> dict:
    """Fetch channel data and save analytics to Obsidian vault.

    Args:
        channel_url: YouTube channel URL.
        max_videos: Maximum number of videos to fetch (default 50).

    Returns:
        List of created note paths and summary stats.
    """
    try:
        from workshop_video_brain.app.config import load_config
        from workshop_video_brain.edit_mcp.pipelines.youtube_analytics import (
            analyze_channel,
            save_channel_to_vault,
        )

        config = load_config()
        vault_path = getattr(config, "vault_path", None) or ""
        if not vault_path:
            return _err(
                "Vault path not configured. Set WVB_VAULT_PATH env var or run 'wvb init'."
            )

        stats = analyze_channel(channel_url, max_videos=max_videos)
        created = save_channel_to_vault(Path(vault_path), stats)

        return _ok({
            "channel_name": stats.channel_name,
            "total_videos": stats.total_videos,
            "notes_created": len(created),
            "paths": [str(p) for p in created],
        })
    except Exception as exc:
        return from_exception(exc)
