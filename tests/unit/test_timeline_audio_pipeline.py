"""Unit tests for the pure timeline-audio pipeline (mixing + ducking math).

No I/O: keyframe/ramp math, VAD->keyframe conversion, EQ preset tables, pan
mapping. The render-level proofs live in
``tests/integration/external/test_track_audio.py``.
"""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines import timeline_audio as ta


# ---------------------------------------------------------------------------
# dB formatting + keyframe parsing
# ---------------------------------------------------------------------------

def test_fmt_db_compact_and_floor():
    assert ta.fmt_db(0.0) == "0"
    assert ta.fmt_db(-12.0) == "-12"
    assert ta.fmt_db(-3.5) == "-3.5"
    # clamps below the floor
    assert ta.fmt_db(-999) == ta.fmt_db(ta.DB_FLOOR)


def test_fmt_db_rejects_nonfinite():
    with pytest.raises(ValueError):
        ta.fmt_db(float("inf"))


def test_format_db_keyframes_sorts_and_clamps():
    s = ta.format_db_keyframes([(50, -6.0), (0, 0.0), (-5, -3.0)])
    # -5 clamps to 0, which collides with the 0=0 point (later wins: -3)
    assert s == "0=-3;50=-6"


def test_format_db_keyframes_empty():
    assert ta.format_db_keyframes([]) == ""


def test_parse_volume_keyframes_mlt_string_passthrough():
    assert ta.parse_volume_keyframes("0=0;24=-12", fps=25.0) == "0=0;24=-12"


def test_parse_volume_keyframes_json_seconds():
    out = ta.parse_volume_keyframes(
        '[{"at_seconds": 0, "gain_db": 0}, {"at_seconds": 1, "gain_db": -12}]',
        fps=25.0,
    )
    assert out == "0=0;25=-12"


def test_parse_volume_keyframes_list_of_dicts():
    out = ta.parse_volume_keyframes(
        [{"at_seconds": 0.0, "gain_db": -3}, {"at_seconds": 2.0, "gain_db": -3}],
        fps=30.0,
    )
    assert out == "0=-3;60=-3"


def test_parse_volume_keyframes_bad_token():
    with pytest.raises(ValueError):
        ta.parse_volume_keyframes("0;24=-12", fps=25.0)


def test_parse_volume_keyframes_empty():
    assert ta.parse_volume_keyframes("", fps=25.0) == ""


# ---------------------------------------------------------------------------
# pan
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pan,start", [(-1.0, 0.0), (0.0, 0.5), (1.0, 1.0), (-0.5, 0.25)])
def test_pan_to_start(pan, start):
    assert ta.pan_to_start(pan) == start


def test_pan_to_start_clamps():
    assert ta.pan_to_start(-3.0) == 0.0
    assert ta.pan_to_start(3.0) == 1.0


def test_pan_to_start_rejects_nonfinite():
    with pytest.raises(ValueError):
        ta.pan_to_start(float("nan"))


# ---------------------------------------------------------------------------
# EQ presets / bands
# ---------------------------------------------------------------------------

def test_eq_presets_known():
    assert set(ta.EQ_PRESETS) == {"music_bed", "voice_carve"}
    bands = ta.eq_bands("music_bed")
    assert len(bands) == 4
    # carve = negative gains on a music bed
    assert all(b.gain_db < 0 for b in bands)


def test_eq_band_properties_shape():
    band = ta.eq_bands("voice_carve")[0]
    props = band.properties()
    assert set(props) == {"av.frequency", "av.width_type", "av.width", "av.gain"}


def test_eq_bands_unknown_preset():
    with pytest.raises(ValueError):
        ta.eq_bands("does_not_exist")


def test_eq_bands_custom_json_takes_precedence():
    bands = ta.eq_bands(
        preset="music_bed",
        bands='[{"frequency": 1000, "gain_db": -6}]',
    )
    assert len(bands) == 1
    assert bands[0].frequency == 1000
    assert bands[0].gain_db == -6


def test_eq_bands_requires_something():
    with pytest.raises(ValueError):
        ta.eq_bands(preset="", bands=None)


def test_parse_bands_missing_fields():
    with pytest.raises(ValueError):
        ta.parse_bands('[{"frequency": 1000}]')


# ---------------------------------------------------------------------------
# silence -> speech inversion + merging
# ---------------------------------------------------------------------------

def test_invert_silence_basic():
    # silence 0-0.5 and 1.0-1.5 within [0, 2] -> speech 0.5-1.0 and 1.5-2.0
    speech = ta.invert_silence([(0.0, 0.5), (1.0, 1.5)], 0.0, 2.0)
    assert speech == [(0.5, 1.0), (1.5, 2.0)]


def test_invert_silence_all_silent():
    assert ta.invert_silence([(0.0, 2.0)], 0.0, 2.0) == []


def test_invert_silence_no_silence_is_all_speech():
    assert ta.invert_silence([], 0.0, 2.0) == [(0.0, 2.0)]


def test_merge_intervals_overlap_and_gap():
    merged = ta.merge_intervals([(0.0, 1.0), (0.9, 2.0), (3.0, 4.0)], gap=0.0)
    assert merged == [(0.0, 2.0), (3.0, 4.0)]
    # with a gap the last two merge too
    merged2 = ta.merge_intervals([(0.0, 1.0), (1.4, 2.0)], gap=0.5)
    assert merged2 == [(0.0, 2.0)]


# ---------------------------------------------------------------------------
# VAD -> duck keyframes  (flagship math)
# ---------------------------------------------------------------------------

def test_duck_keyframes_empty_speech():
    assert ta.voice_activity_to_duck_keyframes([], 100, 25.0) == ""


def test_duck_keyframes_single_interval_structure():
    # speech 1.0-2.0s, 25fps, 100 frames, attack 200ms(=5f), release 400ms(=10f)
    kf = ta.voice_activity_to_duck_keyframes(
        [(1.0, 2.0)], total_frames=100, fps=25.0,
        duck_db=-12.0, attack_ms=200, release_ms=400,
    )
    points = dict(
        (int(f), float(v)) for f, v in (tok.split("=") for tok in kf.split(";"))
    )
    # baseline at 0
    assert points[0] == 0.0
    # ramp-down starts attack(5f) before speech start (25f) -> 20
    assert points[20] == 0.0
    # full duck at speech start and end
    assert points[25] == -12.0
    assert points[50] == -12.0
    # back to baseline release(10f) after end -> 60
    assert points[60] == 0.0
    # trailing baseline at last frame
    assert points[99] == 0.0


def test_duck_keyframes_dip_between_full_and_ducked():
    kf = ta.voice_activity_to_duck_keyframes(
        [(0.5, 1.0), (2.5, 3.0)], total_frames=100, fps=25.0, duck_db=-15,
    )
    vals = [float(tok.split("=")[1]) for tok in kf.split(";")]
    assert min(vals) == -15.0
    assert max(vals) == 0.0


def test_duck_keyframes_close_intervals_merge():
    # two speech bursts 40ms apart at 25fps -- ramps overlap, so they merge into
    # one ducked block (no bob back up to 0 between them).
    kf = ta.voice_activity_to_duck_keyframes(
        [(1.0, 1.2), (1.25, 1.5)], total_frames=100, fps=25.0,
        duck_db=-12, attack_ms=200, release_ms=400,
    )
    # count how many times the envelope returns to 0 in the interior (excluding
    # the leading and trailing baselines): a single merged block => the interior
    # 0s are only the pre-attack and post-release shoulders.
    points = [(int(f), float(v)) for f, v in (t.split("=") for t in kf.split(";"))]
    ducked = [f for f, v in points if v < 0]
    zero_runs = [f for f, v in points if v == 0.0]
    # the ducked frames form one contiguous span (merged), so there is exactly
    # one gap of zeros before and one after -- no interior zero between ducks.
    assert ducked, "expected a ducked span"
    interior_zeros = [f for f in zero_runs if min(ducked) < f < max(ducked)]
    assert interior_zeros == [], f"unexpected bob-up between merged ducks: {interior_zeros}"


def test_duck_keyframes_rejects_bad_fps():
    with pytest.raises(ValueError):
        ta.voice_activity_to_duck_keyframes([(0.0, 1.0)], 100, 0.0)
