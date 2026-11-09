"""check_vfr against real ffprobe on generated media (no mocks).

Guards two bugs found 2026-11-09: the report always showed r/avg frame rate
"0/1" and 0% divergence (MediaAsset had no such fields), and a workspace in
which nothing could be probed was reported as all_cfr=True.
"""
from __future__ import annotations

import subprocess

from tests._testkit import requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.pipelines.vfr_check import check_vfr


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *args],
        check=True, capture_output=True, timeout=60,
    )


@requires_ffmpeg_ffprobe
def test_real_vfr_reported_with_rates(tmp_path):
    raw = tmp_path / "media" / "raw"
    raw.mkdir(parents=True)
    # First second at 30 fps, then frames spaced twice as far apart.
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=s=64x64:r=30:d=2",
        "-vf", "setpts='if(lt(N,30),N,30+(N-30)*2)/30/TB'",
        "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(raw / "vfr.mp4"),
    )
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=s=64x64:r=30:d=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw / "cfr.mp4"),
    )

    report = check_vfr(tmp_path)

    assert report.files_checked == 2
    assert not report.all_cfr
    assert [v.path.endswith("vfr.mp4") for v in report.vfr_files] == [True]
    vf = report.vfr_files[0]
    assert vf.r_frame_rate not in ("", "0/1"), vf
    assert vf.avg_frame_rate not in ("", "0/1"), vf
    assert vf.divergence_pct > 5.0
    assert "media_transcode_cfr" in vf.suggested_action


@requires_ffmpeg_ffprobe
def test_unprobeable_file_is_not_all_cfr(tmp_path):
    raw = tmp_path / "media" / "raw"
    raw.mkdir(parents=True)
    (raw / "broken.mp4").write_bytes(b"not a video")

    report = check_vfr(tmp_path)

    assert report.files_checked == 0
    assert report.all_cfr is False
    assert [u.path.endswith("broken.mp4") for u in report.unprobed_files] == [True]
