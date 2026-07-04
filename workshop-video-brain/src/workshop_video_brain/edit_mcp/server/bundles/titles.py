"""Title-card bundle tool — real on-screen ``kdenlivetitle`` producers.

Registers :func:`title_card_add`, which builds a Kdenlive title document (via
``pipelines/titles.py``), registers it as a ``kdenlivetitle`` producer in the
project model, and places it on a dedicated top video track so it composites
over the footage below.  The serializer already knows how to write producers and
their ``xmldata`` from the model, so nothing here touches serializer/patcher
code.

Style presets live in ``templates/titles/*.yaml`` (see ``lower-third.yaml`` /
``chapter-card.yaml``), mirroring the ``templates/render/*.yaml`` convention.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    invalid_input,
    bad_json_param,
    corrupt_project,
    operation_failed,
    from_exception,
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)

# --- template discovery ----------------------------------------------------


def _titles_template_dir() -> Path:
    """Locate the repo ``templates/titles`` directory from this module."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "templates" / "titles"
        if candidate.is_dir():
            return candidate
    # Fall back to the conventional location even if it does not yet exist.
    return here.parents[5] / "templates" / "titles"


# TitleSpec styling fields a template YAML may set (timing/profile/text are
# supplied by the tool call, not the template).
_STYLE_FIELDS = {
    "font_family",
    "title_font_size",
    "subtitle_font_size",
    "title_font_scale",
    "subtitle_font_scale",
    "font_color",
    "subtitle_color",
    "outline_color",
    "outline_width",
    "align",
    "anchor",
    "safe_margin",
    "background",
    "background_color",
    "background_padding",
}


def _load_style(style: str) -> dict:
    """Load styling overrides for *style* from ``templates/titles/<style>.yaml``."""
    path = _titles_template_dir() / f"{style}.yaml"
    if not path.is_file():
        available = sorted(p.stem for p in _titles_template_dir().glob("*.yaml"))
        raise ValueError(
            f"Unknown title style {style!r}. Available: {available or '(none)'}"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: v for k, v in data.items() if k in _STYLE_FIELDS}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:24] or "title"


def _err(message: str) -> dict:
    return {"status": "error", "message": message}


def _ok(data: dict) -> dict:
    return {"status": "success", "data": data}


@mcp.tool()
@tool_guard
def title_card_add(
    project_file: str,
    text: str,
    subtitle: str | None = None,
    style: str = "lower-third",
    at_seconds: float = 0.0,
    duration_seconds: float = 4.0,
    track: int | None = None,
) -> dict:
    """Add an on-screen title card to a Kdenlive project.

    Builds a ``kdenlivetitle`` producer from the named style and places it on a
    top video track at ``at_seconds`` for ``duration_seconds``.  A snapshot is
    taken before the project is written.

    Args:
        project_file: Path to the ``.kdenlive`` file to modify.
        text: Title (primary) text.
        subtitle: Optional secondary line.
        style: Template name in ``templates/titles/`` (e.g. ``lower-third``,
            ``chapter-card``).
        at_seconds: Timeline position of the card, in seconds.
        duration_seconds: How long the card stays on screen.
        track: Video-track index to place the card on.  ``None`` (default)
            creates a new dedicated top video track.
    """
    from workshop_video_brain.core.models.kdenlive import Playlist, Producer, Track
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import clip_place as cp
    from workshop_video_brain.edit_mcp.pipelines.titles import (
        TitleSpec,
        build_title_xml,
        duration_frames,
    )

    try:
        if not project_file or not project_file.strip():
            return invalid_input("project_file must be a non-empty string", suggestion="Pass a non-empty value for this argument.")
        if not text or not text.strip():
            return invalid_input("text must be a non-empty string", suggestion="Pass a non-empty value for this argument.")
        project_path = Path(project_file)
        if not project_path.exists():
            return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)
        if at_seconds < 0:
            return err("at_seconds must be >= 0", suggestion="Pass at_seconds as 0 or more (the timeline second to place the title at).")
        if duration_seconds <= 0:
            return err("duration_seconds must be > 0", suggestion="Pass a positive duration_seconds for how long the title stays on screen.")

        try:
            style_overrides = _load_style(style)
        except ValueError as exc:
            return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

        # Parse BEFORE snapshotting so a corrupt project fails cleanly
        # (corrupt_project) instead of the outer generic operation_failed, and
        # without leaving a leaked snapshot behind.
        try:
            project = parse_project(project_path)
        except Exception as exc:  # noqa: BLE001 -- corrupt/unparseable project
            return from_exception(exc)
        new = project.model_copy(deep=True)
        prof = new.profile
        fps = prof.fps or 25.0

        spec = TitleSpec(
            text=text,
            subtitle=subtitle or "",
            width=prof.width,
            height=prof.height,
            fps=fps,
            duration_seconds=duration_seconds,
            **style_overrides,
        )
        xml = build_title_xml(spec)
        frames = duration_frames(spec)

        # --- register the title producer in the model ------------------
        existing_ids = {p.id for p in new.producers}
        digest = hashlib.md5(
            f"{text}|{subtitle}|{at_seconds}|{style}".encode()
        ).hexdigest()[:6]
        producer_id = f"title_{_slug(text)}_{digest}"
        while producer_id in existing_ids:
            producer_id += "_x"
        new.producers.append(
            Producer(
                id=producer_id,
                resource="",
                properties={
                    "mlt_service": "kdenlivetitle",
                    "xmldata": xml,
                    "length": str(frames),
                    "kdenlive:clipname": text[:60],
                },
            )
        )

        # --- resolve / create the target top video track --------------
        audio_ids = {t.id for t in new.tracks if t.track_type == "audio"}
        video_playlists = [pl for pl in new.playlists if pl.id not in audio_ids]

        if track is None:
            base = "playlist_video"
            all_ids = {t.id for t in new.tracks} | {p.id for p in new.playlists}
            track_id = base
            n = 1
            while track_id in all_ids:
                track_id = f"{base}_{n}"
                n += 1
            new.tracks.append(
                Track(id=track_id, track_type="video", name="Titles")
            )
            target = Playlist(id=track_id)
            new.playlists.append(target)
            resolved_track = len(video_playlists)  # index of the new top track
        else:
            if track < 0 or track >= len(video_playlists):
                return err(
                    f"track index {track} out of range "
                    f"(project has {len(video_playlists)} video track(s))",
                    suggestion=f"Pass a track within 0-{max(0, len(video_playlists) - 1)}. Use project_summary to see the video tracks.",
                )
            target = video_playlists[track]
            resolved_track = track

        # --- place the card at at_seconds via the canonical clip_place engine
        # (absolute overwrite placement at at_frame, pinned to never overlap
        # existing content -- the engine emits the leading pad blank).
        at_frame = max(0, round(at_seconds * fps))
        placed = cp.PlacedClip(
            producer_id=producer_id, in_point=0, out_point=frames - 1
        )
        place_at = max(at_frame, cp.playlist_length(target.entries))
        result = cp.plan_overwrite(target.entries, place_at, placed)
        target.entries = result.entries

        # --- snapshot before write (best effort) ----------------------
        _snapshot_before_write(project_path)

        serialize_project(new, project_path)

        return _ok(
            {
                "project_file": str(project_path),
                "producer_id": producer_id,
                "style": style,
                "track": resolved_track,
                "track_id": target.id,
                "at_seconds": at_seconds,
                "at_frame": at_frame,
                "duration_seconds": duration_seconds,
                "duration_frames": frames,
                "new_track": track is None,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive
        return operation_failed(str(exc), cause=exc)


def _snapshot_before_write(project_path: Path) -> None:
    """Snapshot *project_path* if it lives inside a workspace (best effort)."""
    try:
        from workshop_video_brain.workspace import snapshot as snapshot_manager

        ws_root = project_path.parent
        for _ in range(10):
            if (ws_root / "projects" / "working_copies").exists():
                break
            if ws_root.parent == ws_root:
                return
            ws_root = ws_root.parent
        else:
            return
        snapshot_manager.create(
            workspace_root=ws_root,
            file_to_snapshot=project_path,
            description=f"before_title_card_{project_path.name}",
        )
    except Exception:
        pass
