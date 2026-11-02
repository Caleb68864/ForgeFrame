"""Canonical MLT profile names for standard formats (CLAUDE.md hard rule 4).

An anonymous name makes Kdenlive warn about a "non standard framerate". The table
is copied from ``/usr/share/mlt-7/profiles`` (MLT 7.42) rather than read at run
time, because that directory differs on Windows and CI. Descriptions are verbatim.
"""
from __future__ import annotations

_CANONICAL: dict[tuple[int, int, int, int], tuple[str, str]] = {
    (1080, 1920, 30, 1): ("vertical_hd_30", "Vertical HD 30 fps"),
    (1080, 1920, 60, 1): ("vertical_hd_60", "Vertical HD 60 fps"),
    (1280, 720, 24, 1): ("atsc_720p_24", "HD 720p 24 fps"),
    (1280, 720, 25, 1): ("atsc_720p_25", "HD 720p 25 fps"),
    (1280, 720, 30, 1): ("atsc_720p_30", "HD 720p 30 fps"),
    (1280, 720, 50, 1): ("atsc_720p_50", "HD 720p 50 fps"),
    (1280, 720, 60, 1): ("atsc_720p_60", "HD 720p 60 fps"),
    (1280, 720, 24000, 1001): ("atsc_720p_2398", "HD 720p 23.98 fps"),
    (1280, 720, 30000, 1001): ("atsc_720p_2997", "HD 720p 29.97 fps"),
    (1280, 720, 60000, 1001): ("atsc_720p_5994", "HD 720p 59.94 fps"),
    (1920, 1080, 24, 1): ("atsc_1080p_24", "HD 1080p 24 fps"),
    (1920, 1080, 25, 1): ("atsc_1080p_25", "HD 1080p 25 fps"),
    (1920, 1080, 30, 1): ("atsc_1080p_30", "HD 1080p 30 fps"),
    (1920, 1080, 50, 1): ("atsc_1080p_50", "HD 1080p 50 fps"),
    (1920, 1080, 60, 1): ("atsc_1080p_60", "HD 1080p 60 fps"),
    (1920, 1080, 24000, 1001): ("atsc_1080p_2398", "HD 1080p 23.98 fps"),
    (1920, 1080, 30000, 1001): ("atsc_1080p_2997", "HD 1080p 29.97 fps"),
    (1920, 1080, 60000, 1001): ("atsc_1080p_5994", "HD 1080p 59.94 fps"),
    (2560, 1440, 24, 1): ("qhd_1440p_24", "2.5K QHD 1440p 24 fps"),
    (2560, 1440, 25, 1): ("qhd_1440p_25", "2.5K QHD 1440p 25 fps"),
    (2560, 1440, 30, 1): ("qhd_1440p_30", "2.5K QHD 1440p 30 fps"),
    (2560, 1440, 50, 1): ("qhd_1440p_50", "2.5K QHD 1440p 50 fps"),
    (2560, 1440, 60, 1): ("qhd_1440p_60", "2.5K QHD 1440p 60 fps"),
    (2560, 1440, 24000, 1001): ("qhd_1440p_2398", "2.5K QHD 1440p 23.98 fps"),
    (2560, 1440, 30000, 1001): ("qhd_1440p_2997", "2.5K QHD 1440p 29.97 fps"),
    (2560, 1440, 60000, 1001): ("qhd_1440p_5994", "2.5K QHD 1440p 59.94 fps"),
    (3840, 2160, 24, 1): ("uhd_2160p_24", "4K UHD 2160p 24 fps"),
    (3840, 2160, 25, 1): ("uhd_2160p_25", "4K UHD 2160p 25 fps"),
    (3840, 2160, 30, 1): ("uhd_2160p_30", "4K UHD 2160p 30 fps"),
    (3840, 2160, 50, 1): ("uhd_2160p_50", "4K UHD 2160p 50 fps"),
    (3840, 2160, 60, 1): ("uhd_2160p_60", "4K UHD 2160p 60 fps"),
    (3840, 2160, 24000, 1001): ("uhd_2160p_2398", "4K UHD 2160p 23.98 fps"),
    (3840, 2160, 30000, 1001): ("uhd_2160p_2997", "4K UHD 2160p 29.97 fps"),
    (3840, 2160, 60000, 1001): ("uhd_2160p_5994", "4K UHD 2160p 59.94 fps"),
}


def canonical_profile_name(
    width: int,
    height: int,
    fps_num: int,
    fps_den: int,
    progressive: bool = True,
) -> tuple[str, str] | None:
    """Return ``(name, description)`` for a standard format, else ``None``."""
    if not progressive:
        return None
    return _CANONICAL.get((width, height, fps_num, fps_den))
