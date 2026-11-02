"""Keep-range logic and tool contracts; no binaries."""
from __future__ import annotations

import pytest

from tests._testkit import assert_registered, call_tool
from workshop_video_brain.edit_mcp.adapters.autoeditor import cli
from workshop_video_brain.edit_mcp.adapters.autoeditor.cli import AutoEditorError, build_command, keep_ranges_from_v3
from workshop_video_brain.edit_mcp.pipelines import silence_cut
from workshop_video_brain.edit_mcp.pipelines.silence_cut import build_cut_filter, resolve_engine
from workshop_video_brain.edit_mcp.server.bundles.media_remove_silence import (
    media_remove_silence,
    media_silence_keep_ranges,
)

SRC = "/abs/test_audio_with_silence.mp4"
REAL_V3 = {
    "version": "3", "timebase": "30/1", "resolution": [320, 180], "samplerate": 48000, "layout": "mono",
    "v": [[{"name": "video", "src": SRC, "start": 0, "dur": 51, "offset": 0, "stream": 0},
           {"name": "video", "src": SRC, "start": 51, "dur": 51, "offset": 99, "stream": 0}]],
    "a": [[{"name": "audio", "src": SRC, "start": 0, "dur": 51, "offset": 0, "stream": 0},
           {"name": "audio", "src": SRC, "start": 51, "dur": 51, "offset": 99, "stream": 0}]],
}


def test_real_auto_editor_output_gives_the_kept_spans():
    assert keep_ranges_from_v3(REAL_V3) == [(0.0, 1.7), (3.3, 5.0)]


def test_ntsc_timebase_is_exact():
    v3 = {"timebase": "30000/1001", "v": [[{"offset": 30, "dur": 30}]]}
    assert keep_ranges_from_v3(v3) == [(1.001, 2.002)]


def test_empty_video_layer_falls_back_to_audio():
    v3 = {"timebase": "30/1", "v": [], "a": [[{"offset": 21, "dur": 78}]]}
    assert keep_ranges_from_v3(v3) == [(0.7, 3.3)]
    assert keep_ranges_from_v3({"timebase": "30/1", "v": [[]], "a": [[{"offset": 0, "dur": 30}]]}) == [(0.0, 1.0)]


def test_touching_ranges_merge_and_sort():
    v3 = {"timebase": "10/1", "v": [[{"offset": 20, "dur": 10}, {"offset": 0, "dur": 10}, {"offset": 10, "dur": 5}]]}
    assert keep_ranges_from_v3(v3) == [(0.0, 1.5), (2.0, 3.0)]


def test_speed_changed_clip_raises():
    with pytest.raises(AutoEditorError, match="speed"):
        keep_ranges_from_v3({"timebase": "30/1", "v": [[{"offset": 0, "dur": 30, "speed": 2.0}]]})


def test_malformed_cut_list_raises():
    with pytest.raises(AutoEditorError, match="unexpected shape"):
        keep_ranges_from_v3({"v": []})


def test_build_command_flags():
    command = build_command("/b/auto-editor", "/s.mp4", "/t/cut.v3",
                            threshold_linear=10 ** (-30 / 20), margin_seconds=0.2, temp_dir="/t/w")
    joined = " ".join(command)
    assert "--export v3" in joined
    assert "--progress none" in joined
    assert "--no-open" in joined
    assert "audio:threshold=0.0316" in joined
    assert "--margin 0.2s" in joined
    assert "kdenlive" not in joined


def test_build_cut_filter_exact_string():
    graph = build_cut_filter([(0.0, 1.7), (3.3, 5.0)], has_video=True, has_audio=True)
    assert graph == (
        "[0:v]trim=start=0.000000:end=1.700000,setpts=PTS-STARTPTS[v0];"
        "[0:a]atrim=start=0.000000:end=1.700000,asetpts=PTS-STARTPTS[a0];"
        "[0:v]trim=start=3.300000:end=5.000000,setpts=PTS-STARTPTS[v1];"
        "[0:a]atrim=start=3.300000:end=5.000000,asetpts=PTS-STARTPTS[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]"
    )


def test_build_cut_filter_audio_only():
    graph = build_cut_filter([(0.0, 1.0)], has_video=False, has_audio=True)
    assert graph == "[0:a]atrim=start=0.000000:end=1.000000,asetpts=PTS-STARTPTS[a0];[a0]concat=n=1:v=0:a=1[outa]"


def test_build_cut_filter_refuses_too_many_ranges():
    with pytest.raises(ValueError, match="too many ranges"):
        build_cut_filter([(float(i), i + 0.5) for i in range(501)], has_video=True, has_audio=False)


def test_auto_falls_back_to_ffmpeg_without_a_binary(monkeypatch):
    monkeypatch.setattr(cli, "resolve_binary", lambda: None)
    assert resolve_engine("auto") == "ffmpeg"


def test_auto_prefers_auto_editor_with_a_binary(monkeypatch):
    monkeypatch.setattr(cli, "resolve_binary", lambda: "/b/auto-editor")
    assert resolve_engine("auto") == "auto-editor"


def test_venv_launcher_on_path_is_not_treated_as_a_binary(monkeypatch, tmp_path):
    """Running the pip launcher would start a download; the adapter must never do that."""
    class Spec:
        submodule_search_locations = [str(tmp_path)]

    monkeypatch.setattr(cli.importlib.util, "find_spec", lambda _name: Spec())
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/venv/bin/auto-editor")
    assert cli.resolve_binary() is None


def test_system_binary_is_used_without_the_package(monkeypatch):
    monkeypatch.setattr(cli.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/usr/bin/auto-editor")
    assert str(cli.resolve_binary()) == "/usr/bin/auto-editor"


def test_keep_ranges_pads_and_clamps_the_ffmpeg_engine(monkeypatch):
    class Asset:
        duration = 5.0

    monkeypatch.setattr(silence_cut, "probe_media", lambda _p: Asset())
    monkeypatch.setattr(silence_cut, "detect_silence", lambda *_a, **_k: [(1.5, 3.5)])
    engine, ranges, duration = silence_cut.keep_ranges("x.mp4", engine="ffmpeg", margin=0.2)
    assert engine == "ffmpeg"
    assert ranges == [(0.0, 1.7), (3.3, 5.0)]
    assert duration == 5.0


@pytest.fixture
def media(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"not decoded")
    return path


def test_tools_are_registered():
    assert_registered("media_remove_silence", "media_silence_keep_ranges")


def test_tool_refuses_empty_output_path(media):
    result = call_tool(media_remove_silence, str(media), " ")
    assert result["error_type"] == "invalid_input"


def test_tool_refuses_a_protected_output_path(media, tmp_path, monkeypatch):
    monkeypatch.setattr(silence_cut, "keep_ranges", lambda *_a, **_k: ("ffmpeg", [(0.0, 1.0)], 2.0))
    protected = tmp_path / "media" / "raw" / "out.mp4"
    result = call_tool(media_remove_silence, str(media), str(protected), engine="ffmpeg")
    assert result["error_type"] == "invalid_input"
    assert not protected.exists()


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [({"threshold_db": 3.0}, "threshold_db"), ({"min_silence": 0.0}, "min_silence"),
     ({"margin": -1.0}, "margin"), ({"threshold_db": float("nan")}, "threshold_db"),
     ({"engine": "nope"}, "engine")],
)
def test_tool_validates_numbers_and_engine(media, kwargs, field):
    result = call_tool(media_silence_keep_ranges, str(media), **kwargs)
    assert result["error_type"] == "invalid_input", field


def test_tool_missing_auto_editor_is_missing_dependency(media, monkeypatch):
    monkeypatch.setattr(cli, "resolve_binary", lambda: None)
    result = call_tool(media_silence_keep_ranges, str(media), engine="auto-editor")
    assert result["error_type"] == "missing_dependency"


def test_tool_auto_editor_failure_is_operation_failed(media, monkeypatch):
    monkeypatch.setattr(cli, "resolve_binary", lambda: "/b/auto-editor")

    def bad(*_a, **_k):
        raise AutoEditorError("auto-editor failed (rc=1): boom")

    monkeypatch.setattr(silence_cut.autoeditor, "run_v3", bad)
    monkeypatch.setattr(silence_cut, "_duration", lambda _p: 5.0)
    result = call_tool(media_silence_keep_ranges, str(media), engine="auto-editor")
    assert result["error_type"] == "operation_failed"
    assert "boom" in result["message"]
