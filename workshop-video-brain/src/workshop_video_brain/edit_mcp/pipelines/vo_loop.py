"""Voiceover-loop pipeline: script-first editing without TTS.

Turns a markdown narration script into numbered voiceover (VO) *cues*, estimates
each cue's spoken duration from its word count at a words-per-minute rate, and
lays those cues out on the timeline at cumulative timestamps.  When the user
later records a take for a cue, :func:`insert_take_clip` drops the real audio
onto an audio track at the cue's planned position (a *model-level* insert that
mirrors ``overlay_looks.insert_overlay_clip``) and the drift between the planned
and recorded durations is reported.

This module is pure logic + FFmpeg probing; the MCP surface (snapshotting,
parsing, serialising, marker/guide writing) lives in
``edit_mcp/server/bundles/vo_loop.py``.

Design notes
------------
* Script splitting favours markdown headings: each ``#``-prefixed heading starts
  a new cue whose body is the following lines until the next heading.  A script
  with no headings falls back to blank-line-separated paragraphs.
* Duration estimation is ``words / wpm * 60`` -- the same arithmetic a
  teleprompter uses.  ``wpm`` defaults to 150 (an unhurried narration pace).
* Rippling of downstream *video* to the recorded length is out of scope (it
  composes with ``clip_place`` when that lands in Wave 3b); :func:`compute_drift`
  only *reports* how far later cues would shift.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    PlaylistEntry,
    Producer,
)
from workshop_video_brain.edit_mcp.pipelines.overlay_looks import overlay_producer_id

DEFAULT_WPM = 150.0
DEFAULT_FPS = 25.0

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")


# ---------------------------------------------------------------------------
# Script splitting + word/duration math
# ---------------------------------------------------------------------------

def word_count(text: str) -> int:
    """Count whitespace-delimited word tokens in *text* (markdown-stripped)."""
    if not text:
        return 0
    # Strip common inline markdown so words are counted, not syntax.
    cleaned = re.sub(r"[#*_`>\-]+", " ", text)
    return len([w for w in cleaned.split() if any(c.isalnum() for c in w)])


def estimate_seconds(words: int, wpm: float = DEFAULT_WPM) -> float:
    """Estimate spoken duration in seconds for *words* at *wpm*."""
    rate = float(wpm) if wpm and wpm > 0 else DEFAULT_WPM
    return (float(words) / rate) * 60.0


def split_script(text: str) -> list[dict]:
    """Split a markdown narration script into ``{heading, text}`` sections.

    Sections are delimited by markdown headings (``#`` .. ``######``); each
    heading opens a new section whose body is the lines up to the next heading.
    A script with no headings is split into blank-line-separated paragraphs.
    Empty sections are dropped.  Returns a list preserving document order.
    """
    lines = (text or "").splitlines()
    has_heading = any(_HEADING_RE.match(ln) for ln in lines)

    sections: list[dict] = []
    if has_heading:
        current: dict | None = None
        for ln in lines:
            m = _HEADING_RE.match(ln)
            if m:
                if current is not None:
                    sections.append(current)
                current = {"heading": m.group(1).strip(), "body_lines": []}
            elif current is not None:
                current["body_lines"].append(ln)
            elif ln.strip():
                # Preamble text before the first heading becomes its own cue.
                current = {"heading": "", "body_lines": [ln]}
        if current is not None:
            sections.append(current)
        result = []
        for s in sections:
            body = "\n".join(s["body_lines"]).strip()
            heading = s["heading"]
            if not body and not heading:
                continue
            result.append({"heading": heading, "text": body or heading})
        return result

    # No headings: paragraph split on blank lines.
    result = []
    for block in re.split(r"\n\s*\n", text or ""):
        body = block.strip()
        if body:
            result.append({"heading": "", "text": body})
    return result


def build_plan(script_text: str, wpm: float = DEFAULT_WPM) -> dict:
    """Build a VO plan dict from a script's text.

    Produces numbered cues with per-cue word counts, estimated durations, and
    cumulative start/end timestamps (back-to-back at the estimated lengths).
    """
    sections = split_script(script_text)
    cues: list[dict] = []
    cursor = 0.0
    for i, sec in enumerate(sections, start=1):
        words = word_count(sec["text"])
        est = round(estimate_seconds(words, wpm), 3)
        heading = sec["heading"] or f"Cue {i}"
        cues.append(
            {
                "cue_id": f"cue_{i:02d}",
                "index": i,
                "heading": heading,
                "text": sec["text"],
                "word_count": words,
                "est_seconds": est,
                "start_seconds": round(cursor, 3),
                "end_seconds": round(cursor + est, 3),
                "actual_seconds": None,
                "audio_file": None,
            }
        )
        cursor += est
    return {
        "wpm": float(wpm),
        "cue_count": len(cues),
        "total_est_seconds": round(cursor, 3),
        "cues": cues,
    }


def format_checklist(plan: dict, script_name: str = "") -> str:
    """Render a human-readable recording checklist markdown from a plan."""
    lines = ["# Voiceover Recording Checklist", ""]
    if script_name:
        lines.append(f"Script: `{script_name}`")
    lines.append(f"Pace: {plan['wpm']:g} wpm")
    lines.append(
        f"Cues: {plan['cue_count']} | Estimated total: "
        f"{plan['total_est_seconds']:.1f}s"
    )
    lines.append("")
    for cue in plan["cues"]:
        lines.append(
            f"- [ ] **{cue['cue_id']}** — {cue['heading']} "
            f"(~{cue['est_seconds']:.1f}s, {cue['word_count']} words, "
            f"starts {cue['start_seconds']:.1f}s)"
        )
        if cue["text"]:
            snippet = cue["text"].replace("\n", " ").strip()
            lines.append(f"  > {snippet}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Drift reporting (report only; does not ripple video)
# ---------------------------------------------------------------------------

def compute_drift(plan: dict) -> list[dict]:
    """Compute, per cue, how much later it would shift if takes were rippled.

    A cue's drift is the sum of ``actual - est`` deltas of all *earlier* cues
    that already have a recorded take.  This is a *report* -- the actual video
    ripple is out of scope and composes with ``clip_place`` (Wave 3b).
    """
    rows: list[dict] = []
    cumulative = 0.0
    for cue in plan["cues"]:
        planned_start = cue["start_seconds"]
        rows.append(
            {
                "cue_id": cue["cue_id"],
                "planned_start_seconds": planned_start,
                "drift_seconds": round(cumulative, 3),
                "rippled_start_seconds": round(planned_start + cumulative, 3),
            }
        )
        actual = cue.get("actual_seconds")
        if actual is not None:
            cumulative += float(actual) - float(cue["est_seconds"])
    return rows


# ---------------------------------------------------------------------------
# FFmpeg probe
# ---------------------------------------------------------------------------

def audio_duration_seconds(path: Path) -> float:
    """Return a media file's duration in seconds via ffprobe.

    Raises RuntimeError if ffprobe fails or reports no duration.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        raise RuntimeError(
            f"ffprobe failed for {path}: {tail[-1] if tail else 'unknown error'}"
        )
    raw = (proc.stdout or "").strip()
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"ffprobe returned no duration for {path}") from exc
    if seconds <= 0:
        raise RuntimeError(f"non-positive duration for {path}: {seconds}")
    return seconds


# ---------------------------------------------------------------------------
# Model-level audio-track clip insert (mirrors overlay_looks.insert_overlay_clip)
# ---------------------------------------------------------------------------

def audio_playlists(project: KdenliveProject) -> list:
    """Return the project's audio playlists (the inverse of ``video_playlists``)."""
    audio_ids = {t.id for t in project.tracks if t.track_type == "audio"}
    return [p for p in project.playlists if p.id in audio_ids]


def insert_take_clip(
    project: KdenliveProject,
    audio_track: int,
    media_path: str,
    at_frame: int,
    duration_frames: int,
) -> int:
    """Insert a recorded VO take onto the ``audio_track``-th audio playlist.

    Places a blank gap of ``at_frame`` frames (when > 0) then the take entry
    ``[0, duration_frames - 1]``, ensuring a producer exists for the media.
    Mutates ``project`` in place and returns the *real*-clip index of the
    inserted entry on that playlist.  Follows the ``overlay_looks`` blank-padding
    pattern -- no dependence on ``clip_place``.
    """
    if at_frame < 0:
        raise ValueError(f"at_frame must be >= 0; got {at_frame}")
    if duration_frames <= 0:
        raise ValueError(f"duration_frames must be > 0; got {duration_frames}")

    aps = audio_playlists(project)
    if not aps:
        raise ValueError(
            "No audio tracks/playlists found in project; add an audio track "
            "before attaching a voiceover take"
        )
    if audio_track < 0 or audio_track >= len(aps):
        raise ValueError(
            f"audio_track {audio_track} out of range "
            f"(project has {len(aps)} audio track(s))"
        )
    playlist = aps[audio_track]

    producer_id = overlay_producer_id(media_path)
    if producer_id not in {p.id for p in project.producers}:
        project.producers.append(
            Producer(
                id=producer_id,
                resource=media_path,
                properties={"resource": media_path},
            )
        )

    if at_frame > 0:
        playlist.entries.append(
            PlaylistEntry(producer_id="", in_point=0, out_point=at_frame - 1)
        )
    playlist.entries.append(
        PlaylistEntry(
            producer_id=producer_id, in_point=0, out_point=duration_frames - 1
        )
    )
    real = [e for e in playlist.entries if e.producer_id]
    return len(real) - 1


def seconds_to_frames(seconds: float, fps: float) -> int:
    """Round *seconds* to an integer frame index at *fps*."""
    if fps <= 0:
        fps = DEFAULT_FPS
    return int(round(float(seconds) * fps))
