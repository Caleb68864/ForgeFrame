"""Pure helpers for timeline / track-level audio mixing + ducking.

No I/O lives here: this module only does deterministic number crunching --
dB-keyframe formatting, pan mapping, EQ preset band tables, and the
voice-activity-to-duck-envelope conversion.  All side effects (parsing /
serialising the project, snapshotting, running ffmpeg silence detection) live in
the bundle module ``edit_mcp/server/bundles/timeline_audio.py``.

Track-level effects are realised as ``<filter>`` children of the track's
``<playlist>`` (render-verified against a live melt; see
``docs/research/2026-07-03-tutorial-effect-analysis/timeline-audio-mixing.md``):

* **volume** -- ``level`` in dB (0 = unity), static or frame-keyframed
  (``frame=db;frame=db``), used for track trim and the ducking envelope;
* **panner** -- ``start`` in [0, 1] (0 = left, 0.5 = centre, 1 = right);
* **avfilter.equalizer** -- one two-pole peaking band per filter
  (``av.frequency`` Hz, ``av.width_type``, ``av.width``, ``av.gain`` dB); a
  multi-band EQ is a stack of these.

Ducking has no live sidechain in MLT's headless path, so ``audio_duck``
synthesises the dip as a keyframed ``volume`` envelope driven by voice-activity
detection on the voice track's source audio.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames

# volume level floor -- ~silence.  Matches the AudioFade clip-fade convention.
DB_FLOOR = -60.0


# ---------------------------------------------------------------------------
# dB / level formatting
# ---------------------------------------------------------------------------

def fmt_db(value: float) -> str:
    """Format a dB value compactly (no trailing ``.0``), clamped to the floor."""
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"dB value must be finite, got {value!r}")
    if v < DB_FLOOR:
        v = DB_FLOOR
    return f"{v:g}"


def format_db_keyframes(points: list[tuple[int, float]]) -> str:
    """Format ``[(frame, db), ...]`` as an MLT ``frame=db;frame=db`` string.

    Points are sorted by frame; when two points share a frame the later one
    wins.  Negative frames are clamped to 0.  Returns ``""`` for no points.
    """
    merged: dict[int, float] = {}
    for frame, db in points:
        f = max(0, int(round(frame)))
        merged[f] = float(db)
    if not merged:
        return ""
    return ";".join(f"{f}={fmt_db(merged[f])}" for f in sorted(merged))


def parse_volume_keyframes(keyframes, fps: float) -> str:
    """Normalise a ``keyframes`` argument into an MLT ``level`` keyframe string.

    Accepts:
      * an MLT string already in ``frame=db;...`` form (returned validated);
      * a JSON array of ``{"at_seconds": t, "gain_db": g}`` objects;
      * an already-decoded list of such dicts.

    Raises ``ValueError`` on malformed input.
    """
    if keyframes is None:
        return ""
    if isinstance(keyframes, str):
        s = keyframes.strip()
        if not s:
            return ""
        # JSON array form?
        if s[0] in "[{":
            keyframes = json.loads(s)
        else:
            # MLT frame=db;... form -- validate each token.
            points: list[tuple[int, float]] = []
            for token in s.split(";"):
                token = token.strip()
                if not token:
                    continue
                if "=" not in token:
                    raise ValueError(f"invalid keyframe token {token!r} (expected frame=db)")
                fpart, vpart = token.split("=", 1)
                points.append((int(fpart), float(vpart)))
            return format_db_keyframes(points)
    if not isinstance(keyframes, (list, tuple)):
        raise ValueError("keyframes must be a frame=db string or a JSON array")
    if fps <= 0:
        raise ValueError(f"fps must be > 0 (got {fps})")
    points = []
    for i, kf in enumerate(keyframes):
        if not isinstance(kf, dict):
            raise ValueError(f"keyframe {i} must be an object")
        at = float(kf.get("at_seconds", 0.0))
        db = float(kf.get("gain_db", kf.get("db", 0.0)))
        points.append((seconds_to_frames(at, fps), db))
    return format_db_keyframes(points)


# ---------------------------------------------------------------------------
# pan
# ---------------------------------------------------------------------------

def pan_to_start(pan: float) -> float:
    """Map a pan in [-1, 1] (−1 = left, 0 = centre, +1 = right) to panner ``start``.

    ``panner``'s ``start`` is 0 = full left, 0.5 = centre, 1.0 = full right.
    """
    p = float(pan)
    if not math.isfinite(p):
        raise ValueError(f"pan must be finite, got {pan!r}")
    p = max(-1.0, min(1.0, p))
    return round((p + 1.0) / 2.0, 6)


# ---------------------------------------------------------------------------
# EQ presets  (carve values from the two Nuxttux tutorials + domain knowledge)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EqBand:
    """A single peaking-EQ band -> one ``avfilter.equalizer`` filter."""

    frequency: float
    gain_db: float
    width_type: int = 2       # 2 = octave (render-verified)
    width: float = 1.0

    def properties(self) -> dict[str, str]:
        return {
            "av.frequency": f"{self.frequency:g}",
            "av.width_type": str(self.width_type),
            "av.width": f"{self.width:g}",
            "av.gain": f"{self.gain_db:g}",
        }


# "music_bed": carve the MUSIC track so a voice sits on top.  The vocal energy
# ("How to Mix Your Voice with Music": fundamentals 500-2k, clarity 2-4k,
# presence 4-6k) is dipped out of the bed instead of just turning it down.
# "voice_carve": clean the VOICE track -- roll off sub-bass rumble ("Boost Your
# Sound Quality": bin1 @ 60Hz) and lift presence/clarity so it cuts through.
EQ_PRESETS: dict[str, list[EqBand]] = {
    "music_bed": [
        EqBand(800, -4.0),
        EqBand(2000, -8.0),
        EqBand(3500, -6.0),
        EqBand(5000, -4.0),
    ],
    "voice_carve": [
        EqBand(60, -12.0, width_type=2, width=1.0),
        EqBand(300, -3.0),
        EqBand(3000, 3.0),
        EqBand(5000, 2.0),
    ],
}


def parse_bands(bands) -> list[EqBand]:
    """Decode a custom band list (JSON string or list of dicts) into EqBands.

    Each band needs ``frequency`` (or ``f``) and ``gain_db`` (or ``gain``/``g``);
    ``width_type`` and ``width`` are optional.
    """
    if isinstance(bands, str):
        bands = json.loads(bands)
    if not isinstance(bands, (list, tuple)) or not bands:
        raise ValueError("bands must be a non-empty JSON array of band objects")
    out: list[EqBand] = []
    for i, b in enumerate(bands):
        if not isinstance(b, dict):
            raise ValueError(f"band {i} must be an object")
        freq = b.get("frequency", b.get("f"))
        gain = b.get("gain_db", b.get("gain", b.get("g")))
        if freq is None or gain is None:
            raise ValueError(f"band {i} needs frequency and gain_db")
        out.append(
            EqBand(
                frequency=float(freq),
                gain_db=float(gain),
                width_type=int(b.get("width_type", 2)),
                width=float(b.get("width", 1.0)),
            )
        )
    return out


def eq_bands(preset: str = "", bands=None) -> list[EqBand]:
    """Resolve EQ bands from a preset name or an explicit custom ``bands`` list.

    Custom ``bands`` (if given) take precedence over ``preset``.
    """
    if bands:
        return parse_bands(bands)
    if preset:
        key = preset.strip().lower()
        if key not in EQ_PRESETS:
            raise ValueError(
                f"unknown EQ preset {preset!r}; known: {sorted(EQ_PRESETS)} "
                "(or pass custom bands)"
            )
        return list(EQ_PRESETS[key])
    raise ValueError("track_eq needs a preset name or a custom bands list")


# ---------------------------------------------------------------------------
# voice activity  ->  duck envelope   (the flagship conversion)
# ---------------------------------------------------------------------------

def invert_silence(
    silence: list[tuple[float, float]],
    start: float,
    end: float,
) -> list[tuple[float, float]]:
    """Return speech intervals = complement of ``silence`` within ``[start, end]``.

    ``silence`` is a list of ``(start_s, end_s)`` gaps (as from
    ``adapters/ffmpeg/silence.detect_silence``).  Speech is everything in
    ``[start, end]`` not covered by a silence gap.
    """
    if end <= start:
        return []
    gaps = sorted((max(start, s), min(end, e)) for s, e in silence if e > start and s < end)
    speech: list[tuple[float, float]] = []
    cursor = start
    for gs, ge in gaps:
        if gs > cursor:
            speech.append((cursor, gs))
        cursor = max(cursor, ge)
    if cursor < end:
        speech.append((cursor, end))
    return [(s, e) for s, e in speech if e > s]


def merge_intervals(
    intervals: list[tuple[float, float]],
    gap: float = 0.0,
) -> list[tuple[float, float]]:
    """Merge overlapping / near (< ``gap``) intervals; input in any order."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [list(ordered[0])]
    for s, e in ordered[1:]:
        if s <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def voice_activity_to_duck_keyframes(
    speech: list[tuple[float, float]],
    total_frames: int,
    fps: float,
    duck_db: float = -12.0,
    attack_ms: float = 200.0,
    release_ms: float = 400.0,
) -> str:
    """Build a ducking ``volume`` ``level`` keyframe string for the music track.

    The envelope is baseline 0 dB, ramping down to ``duck_db`` over ``attack_ms``
    *before* each speech interval, held at ``duck_db`` through the speech, then
    ramping back to 0 over ``release_ms`` *after*.  Speech intervals whose ramps
    would overlap are merged so the music does not bob up between close words.

    Args:
        speech: speech ``(start_s, end_s)`` intervals in music-track time.
        total_frames: music track length in frames (for the trailing baseline).
        fps: project frame rate.
        duck_db: dip depth in dB (negative; e.g. -12).
        attack_ms / release_ms: ramp durations in milliseconds.

    Returns an MLT ``frame=db`` keyframe string, or ``""`` if there is no speech.
    """
    if fps <= 0:
        raise ValueError(f"fps must be > 0 (got {fps})")
    if total_frames <= 0:
        return ""
    duck = float(duck_db)
    attack_f = max(1, seconds_to_frames(attack_ms / 1000.0, fps))
    release_f = max(1, seconds_to_frames(release_ms / 1000.0, fps))

    # Convert to frames, clamp to the track, drop empties.
    raw: list[tuple[float, float]] = []
    for s, e in speech:
        sf = max(0.0, s * fps)
        ef = min(float(total_frames), e * fps)
        if ef > sf:
            raw.append((sf, ef))
    if not raw:
        return ""

    # Merge intervals whose attack/release ramps would collide (gap in frames).
    blocks_f = merge_intervals(raw, gap=float(attack_f + release_f))

    points: list[tuple[int, float]] = [(0, 0.0)]
    last = total_frames - 1
    for sf, ef in blocks_f:
        s = int(round(sf))
        e = int(round(ef))
        a0 = max(0, s - attack_f)          # start ramping down
        r1 = min(last, e + release_f)      # finished ramping up
        points.append((a0, 0.0))
        points.append((s, duck))
        points.append((e, duck))
        points.append((r1, 0.0))
    points.append((last, 0.0))
    return format_db_keyframes(_dedupe_min(points))


def _dedupe_min(points: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Collapse duplicate frames keeping the *lowest* (most-ducked) dB.

    Overlapping ramp endpoints can land on the same frame with different levels
    (e.g. a 0 dB baseline point and a ``duck_db`` point); keeping the minimum
    ensures the dip is not undone by a colliding baseline keyframe.
    """
    best: dict[int, float] = {}
    for f, db in points:
        f = max(0, int(f))
        if f not in best or db < best[f]:
            best[f] = db
    return sorted(best.items())
