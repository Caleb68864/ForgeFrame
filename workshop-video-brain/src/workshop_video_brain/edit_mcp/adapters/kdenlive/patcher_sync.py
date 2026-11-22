"""Keep a clip's audio half in step with edits to its video half.

Prompt 02 places every A/V clip as a video entry plus an audio entry with the
same producer starting on the same frame. ``TrimClip``, ``RemoveClip``,
``MoveClip``, ``SplitClip``, ``RippleDelete`` and ``InsertGap`` used to edit
only the playlist they named, so the sound drifted away from the picture
(e.g. a removed clip's audio stayed and everything after it was out of sync).
``patch_project`` now asks :func:`partner_intent` for the matching audio edit
before applying the video one; if the audio cannot follow, the intent is
skipped whole.

Also here: clip-filter bookkeeping for edits that renumber a track's clips
(filters are keyed by ``track`` + ``clip_index``).
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from workshop_video_brain.core.models.kdenlive import KdenliveProject, OpaqueElement, Playlist
from workshop_video_brain.core.models.timeline import (
    InsertGap,
    MoveClip,
    RemoveClip,
    RippleDelete,
    SplitClip,
    TrimClip,
)

# PatchReport captures "skipped" warnings from the patcher_intents logger.
logger = logging.getLogger("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher_intents")

SYNCED = (TrimClip, RemoveClip, MoveClip, SplitClip, RippleDelete, InsertGap)


def _find(project: KdenliveProject, playlist_id: str) -> Playlist | None:
    return next((p for p in project.playlists if p.id == playlist_id), None)


def _is_audio(project: KdenliveProject, playlist: Playlist) -> bool:
    return any(t.id == playlist.id and t.track_type == "audio" for t in project.tracks)


def _target(project: KdenliveProject, intent) -> tuple[Playlist | None, int | None]:
    if isinstance(intent, TrimClip):
        if ":" in intent.clip_ref:
            playlist_id, _, index = intent.clip_ref.rpartition(":")
            playlist = _find(project, playlist_id)
        else:
            index = intent.clip_ref
            playlist = project.playlists[0] if project.playlists else None
        try:
            return playlist, int(index)
        except ValueError:
            return playlist, None
    if isinstance(intent, InsertGap):
        return _find(project, intent.track_id), None
    if isinstance(intent, MoveClip):
        return _find(project, intent.track_ref), intent.from_index
    return _find(project, intent.track_ref), intent.clip_index


def partner_intent(project: KdenliveProject, intent):
    """``(audio_intent_or_callable, refusal)`` for *intent*.

    ``(None, None)``: nothing to sync. ``(None, reason)``: the audio half
    cannot follow, skip the whole intent. For ``InsertGap`` the partner is a
    callable applying the gap to the linked audio tracks.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher_trims import find_linked_audio

    if not isinstance(intent, SYNCED) or not getattr(intent, "sync_linked_audio", False):
        return None, None
    playlist, index = _target(project, intent)
    if playlist is None or _is_audio(project, playlist):
        return None, None
    if isinstance(intent, InsertGap):
        return _gap_partner(project, playlist, intent), None
    real = [e for e in playlist.entries if e.producer_id]
    if index is None or not 0 <= index < len(real):
        return None, None  # the video intent will report its own bad index
    linked = find_linked_audio(project, playlist, index)
    if linked is None:
        return None, None
    audio, a_index = linked
    if isinstance(intent, TrimClip):
        return TrimClip(clip_ref=f"{audio.id}:{a_index}", new_in=intent.new_in, new_out=intent.new_out,
                        sync_linked_audio=False), None
    if isinstance(intent, MoveClip):
        if not 0 <= intent.to_index < len(real):
            return None, None
        target = find_linked_audio(project, playlist, intent.to_index)
        if target is None or target[0] is not audio:
            return None, (f"clip {intent.from_index} has linked audio on '{audio.id}' but the clip at "
                          f"{intent.to_index} does not, so the audio cannot follow the move")
        return MoveClip(track_ref=audio.id, from_index=a_index, to_index=target[1], sync_linked_audio=False), None
    cls = type(intent)
    fields = {"track_ref": audio.id, "clip_index": a_index, "sync_linked_audio": False}
    if isinstance(intent, SplitClip):
        fields["split_at_frame"] = intent.split_at_frame
    return cls(**fields), None


def _gap_partner(project: KdenliveProject, video: Playlist, intent: InsertGap):
    """Insert the same gap, at the same timeline frame, on audio tracks linked to clips after it."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher_trims import (
        _clip_spans,
        _insert_blank_mapped,
        find_linked_audio,
    )
    from workshop_video_brain.edit_mcp.pipelines.clip_place import entry_length

    pos = min(max(intent.position, 0), len(video.entries))
    frame = sum(entry_length(e) for e in video.entries[:pos])
    audio_indices = []
    for index, start, _entry in _clip_spans(video.entries):
        if start < frame:
            continue
        linked = find_linked_audio(project, video, index)
        if linked is not None:
            i = project.playlists.index(linked[0])
            if i not in audio_indices:
                audio_indices.append(i)
    if not audio_indices or intent.duration_frames <= 0:
        return None

    def apply(target_project: KdenliveProject) -> None:
        for i in audio_indices:
            _insert_blank_mapped(target_project, i, frame, intent.duration_frames)
    return apply


# ---------------------------------------------------------------------------
# clip-filter bookkeeping
# ---------------------------------------------------------------------------

def remap_after_remove(project: KdenliveProject, track_index: int, removed: int, count_before: int) -> None:
    """Drop the removed clip's filters; later clips' filters move down one."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher_intents import _remap_clip_filters

    _remap_clip_filters(project, track_index, {i: (i if i < removed else None if i == removed else i - 1)
                                              for i in range(count_before)})


def remap_after_move(project: KdenliveProject, track_index: int, src: int, dst: int, count: int) -> None:
    """Filters follow their clip through a move within the track."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher_intents import _remap_clip_filters

    order = list(range(count))
    order.insert(dst, order.pop(src))
    _remap_clip_filters(project, track_index, {old: new for new, old in enumerate(order)})


def remap_after_split(project: KdenliveProject, track_index: int, split: int, count_before: int) -> None:
    """Later clips' filters move up one; both halves of the split clip keep its filters."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher_intents import _remap_clip_filters

    _remap_clip_filters(project, track_index, {i: (i + 1 if i > split else i) for i in range(count_before)})
    copies = []
    for elem in project.opaque_elements:
        if elem.tag != "filter":
            continue
        try:
            root = ET.fromstring(elem.xml_string)
        except ET.ParseError:
            continue
        if root.get("track") == str(track_index) and root.get("clip_index") == str(split):
            root.set("clip_index", str(split + 1))
            copies.append(OpaqueElement(tag="filter", xml_string=ET.tostring(root, encoding="unicode"),
                                        position_hint=elem.position_hint))
    project.opaque_elements.extend(copies)
