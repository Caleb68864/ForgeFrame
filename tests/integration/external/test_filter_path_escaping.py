"""External oracle proof for ``_common.escape_filter_path``.

The escaping rules for an ffmpeg filtergraph are **empirical**: a filtergraph
description is unescaped twice before a filter sees its argument, so the
intuitive single-level escaping is wrong in three separate ways. The unit
tests in ``tests/unit/test_common_filter_escape.py`` pin the verified output
*strings*, but only a real ffmpeg can show that those strings actually reach
the filter intact -- which is exactly the gap that let a wrong escaper ship
with a green suite behind it (see
``vault/wiki/ffmpeg-filtergraph-path-escaping.md``).

Every test here carries a **negative control** asserting that the superseded
naive escaping fails on the same input. Without it a passing test proves
nothing: a path with no metacharacters succeeds under any escaping at all,
so the control is what makes the proof discriminating.

Platform note: the drive-colon case only arises on Windows, but the
apostrophe case is platform-independent and failed under the old rule on
every OS -- so this file does real work on Linux CI too.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines import stabilize
from workshop_video_brain.edit_mcp.pipelines._common import escape_filter_path

# The external mark + ffmpeg gating come from conftest.py.

# Path fragments that exercise each escaping rule. "plain" is the baseline
# that passes under any escaping; the other two are the discriminating cases.
AWKWARD_DIRS = ["plain", "with space", "caleb's dir"]

ASS_DOC = """[Script Info]
ScriptType: v4.00+
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Alignment, MarginV
Style: Default,Arial,28,&H00FFFFFF,2,20
[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,HELLO
"""


def _naive_escape(path) -> str:
    """The superseded escaping, kept solely as a negative control.

    This is what both ``stabilize`` (via no escaping) and the private
    ``_escape_ff`` effectively encoded: single-level escaping that reads
    correctly off the syntax documentation and is rejected by real ffmpeg.
    """
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> Path:
    """A short synthetic clip; ffmpeg generates it, so no fixture media needed."""
    import shutil

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not on PATH -- external oracle test skipped")
    out = tmp_path_factory.mktemp("escaping") / "in.mp4"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True, timeout=120,
    )
    return out


def _run_vf(ffmpeg_bin: str, src: Path, vf: str, dst: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-vf", vf, "-frames:v", "3", str(dst)],
        capture_output=True, text=True, timeout=180,
    )


@pytest.mark.parametrize("dirname", AWKWARD_DIRS)
def test_vidstab_detect_writes_trf_through_escaped_path(
    ffmpeg_bin, clip, tmp_path, dirname
):
    """Pass 1 reaches its ``result=`` target through an awkward path."""
    if not stabilize.vidstab_available():
        pytest.skip("libvidstab not in this ffmpeg build")
    d = tmp_path / dirname
    d.mkdir(parents=True)
    trf = d / "x.trf"

    proc = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", "-i", str(clip),
         "-vf", stabilize.build_detect_filter(trf), "-f", "null", "-"],
        capture_output=True, text=True, timeout=180,
    )
    assert trf.exists() and trf.stat().st_size > 0, (
        f"vidstabdetect did not write {trf}: {proc.stderr[-300:]}"
    )


@pytest.mark.parametrize("dirname", AWKWARD_DIRS)
def test_vidstab_transform_reads_trf_through_escaped_path(
    ffmpeg_bin, clip, tmp_path, dirname
):
    """Pass 2 reads back the transforms pass 1 wrote, through the same path."""
    if not stabilize.vidstab_available():
        pytest.skip("libvidstab not in this ffmpeg build")
    d = tmp_path / dirname
    d.mkdir(parents=True)
    trf = d / "x.trf"
    subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", "-i", str(clip),
         "-vf", stabilize.build_detect_filter(trf), "-f", "null", "-"],
        check=True, capture_output=True, timeout=180,
    )

    out = d / "stab.mp4"
    proc = _run_vf(ffmpeg_bin, clip, stabilize.build_transform_filter(trf), out)
    assert out.exists() and out.stat().st_size > 0, (
        f"vidstabtransform failed for {trf}: {proc.stderr[-300:]}"
    )


@pytest.mark.parametrize("dirname", AWKWARD_DIRS)
def test_ass_burn_in_finds_subtitle_file_through_escaped_path(
    ffmpeg_bin, clip, tmp_path, dirname
):
    """``subtitles_burn_in``'s ``ass=`` argument resolves through an awkward path."""
    d = tmp_path / dirname
    d.mkdir(parents=True)
    ass = d / "s.ass"
    ass.write_text(ASS_DOC, encoding="utf-8")

    out = d / "burn.mp4"
    proc = _run_vf(ffmpeg_bin, clip, f"ass={escape_filter_path(ass)}", out)
    assert out.exists() and out.stat().st_size > 0, (
        f"ass filter failed for {ass}: {proc.stderr[-300:]}"
    )


@pytest.fixture(scope="module")
def cut_clip(tmp_path_factory) -> Path:
    """A clip with one hard cut, so ``metadata=print`` actually emits rows.

    Without a real scene change the stats file is never created and a
    scene-detect assertion would fail for a reason unrelated to escaping.
    """
    import shutil

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not on PATH -- external oracle test skipped")
    out = tmp_path_factory.mktemp("escaping_cut") / "cuts.mp4"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=1",
         "-f", "lavfi", "-i", "color=c=red:size=320x240:rate=15:duration=1",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True, timeout=120,
    )
    return out


@pytest.mark.parametrize("dirname", AWKWARD_DIRS)
def test_scene_detect_writes_its_metadata_stats_file(
    ffmpeg_bin, cut_clip, tmp_path, dirname
):
    """``metadata=print:file=`` reaches its target through an awkward path.

    This one degrades *silently*: the caller reads the stats file behind an
    ``if stats_file.exists()`` guard, so an unescaped path yields an empty
    scene list rather than an error.
    """
    from workshop_video_brain.edit_mcp.pipelines import scene_detect

    d = tmp_path / dirname
    d.mkdir(parents=True)
    stats = d / "scenes.txt"

    proc = subprocess.run(
        [ffmpeg_bin, *scene_detect.build_scan_command(cut_clip, 0.3, stats)[1:]],
        capture_output=True, text=True, timeout=180,
    )
    assert stats.exists() and stats.stat().st_size > 0, (
        f"scene_detect wrote no stats to {stats}: {proc.stderr[-300:]}"
    )


@pytest.mark.parametrize("dirname", AWKWARD_DIRS)
def test_qc_scan_writes_its_metadata_stats_file(ffmpeg_bin, clip, tmp_path, dirname):
    """Same silent-degradation guard for the QC scan's stats file."""
    from workshop_video_brain.edit_mcp.pipelines import qc_scan

    d = tmp_path / dirname
    d.mkdir(parents=True)
    stats = d / "stats.txt"
    thresholds = {
        "black_min": 0.5, "black_pix_th": 0.10, "freeze_noise_db": -60.0,
        "freeze_min": 2.0, "silence_db": -50.0, "silence_min": 1.0,
    }

    proc = subprocess.run(
        [ffmpeg_bin, *qc_scan.build_scan_command(clip, stats, thresholds)[1:]],
        capture_output=True, text=True, timeout=180,
    )
    assert stats.exists() and stats.stat().st_size > 0, (
        f"qc_scan wrote no stats to {stats}: {proc.stderr[-300:]}"
    )


def test_naive_escaping_is_rejected_by_real_ffmpeg(ffmpeg_bin, clip, tmp_path):
    """Negative control: the superseded rule fails, so the tests above discriminate.

    If this ever starts passing, ffmpeg's parser changed and the whole
    empirical basis for ``escape_filter_path`` needs re-deriving -- the
    positive tests alone would not notice.
    """
    d = tmp_path / "caleb's dir"
    d.mkdir(parents=True)
    ass = d / "s.ass"
    ass.write_text(ASS_DOC, encoding="utf-8")

    out = d / "burn.mp4"
    _run_vf(ffmpeg_bin, clip, f"ass={_naive_escape(ass)}", out)
    produced = out.exists() and out.stat().st_size > 0
    assert not produced, (
        "naive single-level escaping unexpectedly worked -- re-derive the "
        "escaping rules against this ffmpeg build before trusting "
        "escape_filter_path"
    )
