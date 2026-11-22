"""Plain-file media helpers: output resolution, concat graph and list (prompt 30; no ffmpeg)."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.utils.paths import ProtectedPathError
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg
from workshop_video_brain.edit_mcp.pipelines.media_edit import build_concat_graph, concat_list_text
from workshop_video_brain.edit_mcp.pipelines.media_files import default_output_dir, resolve_output


def test_default_name_and_output_dir(tmp_path):
    src = tmp_path / "clip.mov"
    src.write_bytes(b"x")
    assert resolve_output(src, suffix="_trim") == (tmp_path / "clip_trim.mov").resolve()
    out = resolve_output(src, output_dir=str(tmp_path / "out"), suffix="_x", ext=".mp4")
    assert out == (tmp_path / "out" / "clip_x.mp4").resolve() and out.parent.is_dir()


def test_raw_sources_default_to_processed(tmp_path):
    raw = tmp_path / "ws" / "media" / "raw"
    raw.mkdir(parents=True)
    src = raw / "take.mp4"
    src.write_bytes(b"x")
    assert default_output_dir(src) == (tmp_path / "ws" / "media" / "processed").resolve()
    assert resolve_output(src).parent == (tmp_path / "ws" / "media" / "processed").resolve()


def test_refusals(tmp_path):
    raw = tmp_path / "ws" / "media" / "raw"
    raw.mkdir(parents=True)
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    with pytest.raises(ProtectedPathError):
        resolve_output(src, output_path=str(raw / "new.mp4"))
    assert not (raw / "new.mp4").exists()
    with pytest.raises(ValueError, match="overwrite the source"):
        resolve_output(src, output_path=str(src))
    (tmp_path / "a_out.mp4").write_bytes(b"x")
    with pytest.raises(ValueError, match="overwrite=true"):
        resolve_output(src)
    assert resolve_output(src, overwrite=True) == (tmp_path / "a_out.mp4").resolve()


def test_concat_graph_silences_a_mute_input():
    graph, with_audio = build_concat_graph([{"has_audio": True, "duration": 5.0},
                                            {"has_audio": False, "duration": 20.02}], 1920, 1080, 29.97)
    assert with_audio
    assert "anullsrc=r=48000:cl=stereo,atrim=duration=20.020[a1]" in graph
    assert "[0:a]aresample=48000" in graph and graph.endswith("concat=n=2:v=1:a=1[v][a]")
    graph, with_audio = build_concat_graph([{"has_audio": False, "duration": 1.0}] * 2, 640, 360, 25)
    assert not with_audio and graph.endswith("concat=n=2:v=1:a=0[v]") and "anullsrc" not in graph


def test_concat_list_escapes_quotes():
    assert concat_list_text([Path("/m/it's.mp4"), Path("/m/b.mp4")]) == "file '/m/it'\\''s.mp4'\nfile '/m/b.mp4'\n"


def test_run_ffmpeg_extra_inputs_order(tmp_path):
    result = run_ffmpeg(["-c", "copy"], tmp_path / "a.mp4", tmp_path / "o.mp4", dry_run=True,
                        extra_inputs=[tmp_path / "b.mp4", tmp_path / "c.mp4"])
    cmd = result.command
    assert [cmd[i + 1] for i, a in enumerate(cmd) if a == "-i"] == [str(tmp_path / n) for n in ("a.mp4", "b.mp4", "c.mp4")]
    plain = run_ffmpeg(["-c", "copy"], tmp_path / "a.mp4", tmp_path / "o.mp4", dry_run=True).command
    assert plain == ["ffmpeg", "-y", "-i", str(tmp_path / "a.mp4"), "-c", "copy", str(tmp_path / "o.mp4")]
