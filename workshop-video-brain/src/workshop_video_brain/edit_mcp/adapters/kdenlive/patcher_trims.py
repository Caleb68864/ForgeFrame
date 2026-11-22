"""Apply functions for the trim intents: SlipClip, SlideClip, ReplaceClip, RippleInsert.

Dispatched from ``patcher_intents.patch_project``. The frame math is in
``pipelines/trim_ops``; this module applies a plan to the video entry *and* its
linked audio entry (the audio-track entry with the same producer starting on
the same frame, as prompt 02 places every A/V clip). If the audio half cannot
take the same change, the whole intent is skipped: video never moves alone.

Every no-op logs a warning containing "skipped" (``PatchReport`` relies on it).
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
)
from workshop_video_brain.core.models.timeline import ReplaceClip, RippleInsert, SlideClip, SlipClip

# The patcher_intents logger: PatchReport captures "skipped" warnings from it.
logger = logging.getLogger("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher_intents")


def _pi():
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher_intents
    return patcher_intents


def _ops():
    from workshop_video_brain.edit_mcp.pipelines import trim_ops
    return trim_ops


def _audio_track_ids(project: KdenliveProject) -> set[str]:
    return {t.id for t in project.tracks if t.track_type == "audio"}


def _base_id(producer_id: str) -> str:
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import AUDIO_TWIN_SUFFIX
    return producer_id.removesuffix(AUDIO_TWIN_SUFFIX)


def _clip_spans(entries: list[PlaylistEntry]):
    """(real_index, start_frame, entry) for every clip."""
    from workshop_video_brain.edit_mcp.pipelines.clip_place import entry_length

    real, start = -1, 0
    for entry in entries:
        if entry.producer_id:
            real += 1
            yield real, start, entry
        start += entry_length(entry)


def find_linked_audio(
    project: KdenliveProject, video_playlist: Playlist, clip_index: int,
) -> tuple[Playlist, int] | None:
    """The audio half of a video clip: (audio playlist, its clip index), or None."""
    spans = {i: (s, e) for i, s, e in _clip_spans(video_playlist.entries)}
    if clip_index not in spans:
        return None
    start, entry = spans[clip_index]
    audio_ids = _audio_track_ids(project)
    for playlist in project.playlists:
        if playlist is video_playlist or playlist.id not in audio_ids:
            continue
        for index, a_start, a_entry in _clip_spans(playlist.entries):
            if a_start == start and _base_id(a_entry.producer_id) == _base_id(entry.producer_id):
                return playlist, index
    return None


def _producer(project: KdenliveProject, producer_id: str) -> Producer | None:
    return next((p for p in project.producers if p.id == producer_id), None)


def _is_timewarp(project: KdenliveProject, producer_id: str) -> bool:
    producer = _producer(project, producer_id)
    return bool(producer and producer.properties.get("mlt_service") == "timewarp")


def ensure_producer_length(project: KdenliveProject, producer_id: str) -> None:
    """Hard rule 14: a producer's ``length`` covers every entry that uses it (never lowered)."""
    producer = _producer(project, producer_id)
    if producer is None or "length" not in producer.properties:
        return
    needed = max((e.out_point + 1 for pl in project.playlists for e in pl.entries
                  if e.producer_id and _base_id(e.producer_id) == _base_id(producer_id)), default=0)
    try:
        current = int(producer.properties["length"])
    except ValueError:
        return
    if needed > current:
        producer.properties["length"] = str(needed)


def _register(project: KdenliveProject, producer_id: str, source_path: str) -> None:
    if producer_id and _producer(project, producer_id) is None:
        project.producers.append(Producer(
            id=producer_id, resource=source_path or "",
            properties={"resource": source_path} if source_path else {},
        ))


def _target(project: KdenliveProject, name: str, track_ref: str, clip_index: int):
    playlist = _pi()._find_playlist(project, track_ref)
    if playlist is None:
        logger.warning("%s: no playlist '%s' -- skipped.", name, track_ref)
        return None
    real = [e for e in playlist.entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(real):
        logger.warning("%s: clip_index %d out of range (track has %d clips) -- skipped.",
                       name, clip_index, len(real))
        return None
    return playlist, real[clip_index]


# ---------------------------------------------------------------------------
# transitions
# ---------------------------------------------------------------------------

def _parse_time(text: str, fps: float) -> tuple[int, bool] | None:
    """(frames, was_timecode) for an int or HH:MM:SS.mmm value."""
    text = (text or "").strip()
    if not text:
        return None
    if text.lstrip("-").isdigit():
        return int(text), False
    parts = text.split(":")
    if len(parts) == 3:
        try:
            seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except ValueError:
            return None
        return int(seconds * fps + 0.5), True
    return None


def _format_time(frames: int, timecode: bool, fps: float) -> str:
    if not timecode:
        return str(frames)
    total_ms = int(round(frames / fps * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _transition_range(root: ET.Element, fps: float):
    """((in, in_is_tc, in_holder), (out, ...)) where holder is ('attr'|element)."""
    def read(name):
        if root.get(name) is not None:
            parsed = _parse_time(root.get(name), fps)
            return (parsed[0], parsed[1], "attr") if parsed else None
        for child in root.findall("property"):
            if child.get("name") == name:
                parsed = _parse_time(child.text or "", fps)
                return (parsed[0], parsed[1], child) if parsed else None
        return None
    return read("in"), read("out")


def _transitions(project: KdenliveProject):
    for elem in project.opaque_elements:
        if elem.tag != "transition":
            continue
        try:
            root = ET.fromstring(elem.xml_string)
        except ET.ParseError:
            continue
        yield elem, root


def _overlapping_transition(project: KdenliveProject, start: int, end: int) -> bool:
    fps = float(project.profile.fps or 25)
    for _elem, root in _transitions(project):
        t_in, t_out = _transition_range(root, fps)
        if t_in and t_out and t_in[0] <= end and t_out[0] >= start:
            return True
    return False


def _shift_transitions(project: KdenliveProject, frame: int, length: int) -> bool:
    """Shift transitions starting at/after *frame* by *length*. False (nothing changed) if one straddles it."""
    fps = float(project.profile.fps or 25)
    plan: list[tuple[OpaqueElement, ET.Element, tuple, tuple]] = []
    for elem, root in _transitions(project):
        t_in, t_out = _transition_range(root, fps)
        if not t_in or not t_out:
            continue
        if t_in[0] < frame <= t_out[0]:
            return False
        if t_in[0] >= frame:
            plan.append((elem, root, t_in, t_out))
    for elem, root, t_in, t_out in plan:
        for (value, timecode, holder), name in ((t_in, "in"), (t_out, "out")):
            text = _format_time(value + length, timecode, fps)
            if holder == "attr":
                root.set(name, text)
            else:
                holder.text = text
        elem.xml_string = ET.tostring(root, encoding="unicode")
    return True


# ---------------------------------------------------------------------------
# apply functions
# ---------------------------------------------------------------------------

def apply_slip(project: KdenliveProject, intent: SlipClip) -> None:
    found = _target(project, "SlipClip", intent.track_ref, intent.clip_index)
    if found is None:
        return
    playlist, entry = found
    if _is_timewarp(project, entry.producer_id):
        logger.warning("SlipClip: clip %d is speed-changed (timewarp); slipping it is not supported -- skipped.",
                       intent.clip_index)
        return
    linked = find_linked_audio(project, playlist, intent.clip_index)
    try:
        video = _ops().plan_slip(playlist.entries, intent.clip_index, intent.delta_frames, intent.source_frames)
        audio = (_ops().plan_slip(linked[0].entries, linked[1], intent.delta_frames, intent.source_frames)
                 if linked else None)
    except ValueError as exc:
        logger.warning("SlipClip: %s -- skipped.", exc)
        return
    playlist.entries = video
    if linked:
        linked[0].entries = audio
    ensure_producer_length(project, entry.producer_id)
    logger.info("SlipClip: clip %d on '%s' by %d frames (audio %s)", intent.clip_index,
                intent.track_ref, intent.delta_frames, "synced" if linked else "none")


def apply_slide(project: KdenliveProject, intent: SlideClip) -> None:
    from workshop_video_brain.edit_mcp.pipelines.clip_place import clip_start_frame, entry_length

    found = _target(project, "SlideClip", intent.track_ref, intent.clip_index)
    if found is None:
        return
    playlist, entry = found
    if _is_timewarp(project, entry.producer_id):
        logger.warning("SlideClip: clip %d is speed-changed (timewarp); sliding it is not supported -- skipped.",
                       intent.clip_index)
        return
    start = clip_start_frame(playlist.entries, intent.clip_index)
    end = start + entry_length(entry) - 1
    lo, hi = min(start, start + intent.delta_frames), max(end, end + intent.delta_frames)
    if _overlapping_transition(project, lo, hi):
        logger.warning("SlideClip: a transition overlaps frames %d-%d; remove it first -- skipped.", lo, hi)
        return
    linked = find_linked_audio(project, playlist, intent.clip_index)
    try:
        video = _ops().plan_slide(playlist.entries, intent.clip_index, intent.delta_frames,
                                  intent.prev_source_frames, intent.next_source_frames)
        audio = (_ops().plan_slide(linked[0].entries, linked[1], intent.delta_frames,
                                   intent.prev_source_frames, intent.next_source_frames)
                 if linked else None)
    except ValueError as exc:
        logger.warning("SlideClip: %s -- skipped.", exc)
        return
    playlist.entries = video
    if linked:
        linked[0].entries = audio
    for pl in (playlist, linked[0] if linked else None):
        if pl is None:
            continue
        for e in pl.entries:
            if e.producer_id:
                ensure_producer_length(project, e.producer_id)
    logger.info("SlideClip: clip %d on '%s' by %d frames", intent.clip_index, intent.track_ref,
                intent.delta_frames)


def apply_replace(project: KdenliveProject, intent: ReplaceClip) -> None:
    found = _target(project, "ReplaceClip", intent.track_ref, intent.clip_index)
    if found is None:
        return
    playlist, entry = found
    if not intent.producer_id:
        logger.warning("ReplaceClip: no producer_id -- skipped.")
        return
    if _is_timewarp(project, entry.producer_id):
        logger.warning("ReplaceClip: clip %d is speed-changed (timewarp); replacing it is not supported -- skipped.",
                       intent.clip_index)
        return
    linked = find_linked_audio(project, playlist, intent.clip_index) if intent.replace_audio else None
    ops = _ops()
    try:
        video = ops.plan_replace(playlist.entries, intent.clip_index, intent.producer_id,
                                 intent.new_in, intent.source_frames)
        audio = None
        if linked:
            audio = (ops.plan_replace(linked[0].entries, linked[1], intent.producer_id,
                                      intent.new_in, intent.source_frames)
                     if intent.new_has_audio else ops.blank_out(linked[0].entries, linked[1]))
    except ValueError as exc:
        logger.warning("ReplaceClip: %s -- skipped.", exc)
        return
    _register(project, intent.producer_id, intent.source_path)
    playlist.entries = video
    if linked:
        linked[0].entries = audio
        if not intent.new_has_audio:
            # The audio clip became a blank: later clips on that track drop an index.
            removed = linked[1]
            count = sum(1 for e in audio if e.producer_id) + 1
            index_map = {i: (i if i < removed else None if i == removed else i - 1) for i in range(count)}
            _pi()._remap_clip_filters(project, project.playlists.index(linked[0]), index_map)
    ensure_producer_length(project, intent.producer_id)
    logger.info("ReplaceClip: clip %d on '%s' -> '%s' from frame %d", intent.clip_index,
                intent.track_ref, intent.producer_id, intent.new_in)


def _insert_blank_mapped(project: KdenliveProject, track_index: int, frame: int, length: int) -> None:
    """plan_insert_blank on one track, keeping its clip filters on the right clips.

    A clip split by the blank becomes two clips; both halves keep its filters.
    """
    from workshop_video_brain.edit_mcp.pipelines.clip_place import plan_insert_blank

    playlist = project.playlists[track_index]
    split = _ops().split_index_at(playlist.entries, frame)
    playlist.entries = plan_insert_blank(playlist.entries, frame, length)
    if split is None:
        return
    count = sum(1 for e in playlist.entries if e.producer_id)
    _pi()._remap_clip_filters(project, track_index, {i: (i + 1 if i > split else i) for i in range(count)})
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


def apply_ripple_insert(project: KdenliveProject, intent: RippleInsert) -> None:
    from workshop_video_brain.edit_mcp.pipelines import clip_place as cp

    pi = _pi()
    playlist = pi._find_playlist(project, intent.track_ref)
    track_index = pi._playlist_index(project, intent.track_ref)
    if playlist is None or track_index is None:
        logger.warning("RippleInsert: no playlist '%s' -- skipped.", intent.track_ref)
        return
    if not intent.producer_id or intent.out_point < intent.in_point:
        logger.warning("RippleInsert: needs a producer and out_point >= in_point -- skipped.")
        return
    try:
        frame = _ops().insert_frame_for(playlist.entries, intent.before_clip_index)
    except ValueError as exc:
        logger.warning("RippleInsert: %s -- skipped.", exc)
        return
    length = intent.out_point - intent.in_point + 1

    # Refuse before touching anything when a transition straddles the frame.
    if not _shift_transitions(project, frame, length):
        logger.warning("RippleInsert: a transition spans frame %d; remove it first -- skipped.", frame)
        return

    _register(project, intent.producer_id, intent.source_path)
    clip = cp.PlacedClip(producer_id=intent.producer_id, in_point=intent.in_point, out_point=intent.out_point)
    result = cp.plan_insert(playlist.entries, frame, clip)
    playlist.entries = result.entries
    pi._remap_clip_filters(project, track_index, result.index_map)

    audio_ids = _audio_track_ids(project)
    audio_index = next((i for i, pl in enumerate(project.playlists)
                        if pl.id in audio_ids and i != track_index), None)
    if audio_index is not None:
        audio = project.playlists[audio_index]
        if intent.with_audio:
            a_result = cp.plan_insert(audio.entries, frame, clip)
            audio.entries = a_result.entries
            pi._remap_clip_filters(project, audio_index, a_result.index_map)
        else:
            # No sound in the new media: a blank of the same length keeps sync.
            pad = cp.plan_insert(audio.entries, frame, cp.PlacedClip("", 0, length - 1))
            audio.entries = pad.entries
            pi._remap_clip_filters(project, audio_index, pad.index_map)
    if intent.ripple_all_tracks:
        for other_index in range(len(project.playlists)):
            if other_index in (track_index, audio_index):
                continue
            _insert_blank_mapped(project, other_index, frame, length)
        for guide in project.guides:
            if guide.position >= frame:
                guide.position += length
    ensure_producer_length(project, intent.producer_id)
    logger.info("RippleInsert: '%s' (%d frames) at frame %d on '%s'", intent.producer_id, length,
                frame, intent.track_ref)
