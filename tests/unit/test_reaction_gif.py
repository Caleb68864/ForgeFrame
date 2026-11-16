"""Unit tests for the reaction-GIF pipeline (pure parts: no ffmpeg, no network)."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines import reaction_gif as rg

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "reaction_gif"


# ---------------------------------------------------------------------------
# SRT parsing + search
# ---------------------------------------------------------------------------


class TestParseSrt:
    def test_parses_all_cues_with_times(self):
        cues = rg.parse_srt((FIX / "kingsolomon_excerpt.srt").read_text())
        assert len(cues) == 10
        first = cues[0]
        assert first.index == 1
        assert first.start == pytest.approx(19 * 60 + 58.1)
        assert first.end == pytest.approx(20 * 60)
        assert first.text == "Hold the rope!"

    def test_crlf_and_multiline_text(self):
        cues = rg.parse_srt((FIX / "crlf.srt").read_text())
        assert len(cues) == 2
        assert cues[0].text == "I've got it\nsecond line"
        assert cues[0].end == pytest.approx(2.5)

    def test_strips_markup(self):
        cues = rg.parse_srt((FIX / "kingsolomon_excerpt.srt").read_text())
        assert cues[8].text == "I'VE GOT IT!"


class TestSearchSrt:
    @pytest.fixture
    def cues(self):
        return rg.parse_srt((FIX / "kingsolomon_excerpt.srt").read_text())

    def test_repeated_line_returns_every_match_case_insensitive(self, cues):
        matches = rg.search_srt(cues, "i've GOT it")
        assert [m["cue"]["index"] for m in matches] == [6, 9]

    def test_four_preceding_context_cues(self, cues):
        m = rg.search_srt(cues, "I've got it")[0]
        assert [c["index"] for c in m["context"]] == [2, 3, 4, 5]
        assert m["context"][-1]["text"] == "Grab it!"

    def test_context_is_clamped_at_file_start(self, cues):
        m = rg.search_srt(cues, "pull, umbopo")[0]
        assert [c["index"] for c in m["context"]] == [1]

    def test_context_count_configurable(self, cues):
        m = rg.search_srt(cues, "I've got it", context=2)[0]
        assert [c["index"] for c in m["context"]] == [4, 5]

    def test_picture_offset_applied_to_suggested_window(self, cues):
        m = rg.search_srt(cues, "I've got it")[0]
        sub_start = 20 * 60 + 12.5
        assert m["cue"]["start"] == pytest.approx(sub_start)
        assert m["picture_time"] == pytest.approx(sub_start + 3.0)
        win = m["suggested_window"]
        assert win["start"] == pytest.approx(sub_start + 3.0 - 15.0)
        assert win["end"] == pytest.approx(sub_start + 3.0 + 15.0)
        assert win["start_mmss"] == "20:00"
        assert win["end_mmss"] == "20:30"

    def test_custom_offset_and_window(self, cues):
        m = rg.search_srt(cues, "I've got it", picture_offset=2.0, window=10.0)[0]
        assert m["picture_time"] == pytest.approx(20 * 60 + 14.5)
        assert m["suggested_window"]["end"] - m["suggested_window"]["start"] == pytest.approx(10.0)

    def test_window_clamped_at_zero(self, cues):
        m = rg.search_srt(cues, "opening line")[0]
        assert m["suggested_window"]["start"] == 0.0

    def test_apostrophe_variants_match(self, cues):
        # Curly apostrophe in the query still finds the straight one.
        assert len(rg.search_srt(cues, "I’ve got it")) == 2

    def test_no_match(self, cues):
        assert rg.search_srt(cues, "nonexistent line") == []

    def test_empty_query_rejected(self, cues):
        with pytest.raises(ValueError):
            rg.search_srt(cues, "   ")


class TestTimeParsing:
    @pytest.mark.parametrize(
        ("text", "seconds"),
        [("20:15", 1215.0), ("1:02:03", 3723.0), ("15.5", 15.5), ("00:17.52", 17.52), (12, 12.0)],
    )
    def test_parse_time(self, text, seconds):
        assert rg.parse_time(text) == pytest.approx(seconds)

    def test_bad_time(self):
        with pytest.raises(ValueError):
            rg.parse_time("abc")


# ---------------------------------------------------------------------------
# Caption sizing + filtergraph
# ---------------------------------------------------------------------------


class TestCaptionMetrics:
    def test_480_matches_note_example(self):
        m = rg.caption_metrics(480)
        assert (m.fontsize, m.borderw, m.margin) == (48, 4, 16)

    def test_scales_with_width(self):
        m = rg.caption_metrics(320)
        assert m.fontsize == 32
        assert m.borderw == 3  # round(32/12)
        assert m.margin == 11  # round(32/3)

    def test_border_never_zero(self):
        assert rg.caption_metrics(40).borderw >= 1


class TestFiltergraph:
    def test_graph_shape(self, tmp_path):
        cap = tmp_path / "cap.txt"
        graph = rg.build_gif_filtergraph(cap, width=480, fps=15, font_file=None)
        assert graph.startswith("fps=15,scale=480:-1:flags=lanczos,")
        assert "fontsize=48" in graph
        assert "borderw=4" in graph
        assert "bordercolor=black" in graph
        assert "fontcolor=white" in graph
        assert "x=(w-tw)/2" in graph
        assert "y=h-th-16" in graph
        assert "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" in graph

    def test_textfile_path_is_escaped(self, tmp_path):
        cap = Path("/tmp/it's here:x/cap.txt")
        graph = rg.build_gif_filtergraph(cap, font_file=None)
        assert "textfile=" + "/tmp/it\\\\\\'s here\\\\:x/cap.txt" in graph

    def test_caption_text_never_in_graph(self, tmp_path):
        cap = rg.write_caption_file("I'VE GOT IT!", tmp_path)
        graph = rg.build_gif_filtergraph(cap, font_file=None)
        assert "I'VE" not in graph
        assert "GOT IT" not in graph
        assert cap.read_text() == "I'VE GOT IT!"

    def test_font_file_included(self, tmp_path):
        graph = rg.build_gif_filtergraph(tmp_path / "c.txt", font_file="/fonts/Lib Bold.ttf")
        assert "drawtext=fontfile=/fonts/Lib Bold.ttf:textfile=" in graph

    def test_no_caption_no_drawtext(self):
        graph = rg.build_gif_filtergraph(None)
        assert "drawtext" not in graph
        assert "palettegen" in graph

    def test_render_command(self, tmp_path):
        cmd = rg.build_gif_args(15.5, 17.52, tmp_path / "c.txt", font_file=None)
        pre, args = cmd
        assert pre[:2] == ["-ss", "15.500"]
        assert pre[2:] == ["-t", "2.020"]
        assert "-lavfi" in args and "-an" in args
        assert args[args.index("-loop") + 1] == "0"

    def test_end_before_start_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            rg.build_gif_args(5.0, 4.0, None)


# ---------------------------------------------------------------------------
# Scene cuts, contact sheet, waveform, check strip
# ---------------------------------------------------------------------------


class TestSceneCuts:
    def test_parse_showinfo(self):
        cuts = rg.parse_showinfo_cuts((FIX / "showinfo_stderr.txt").read_text())
        assert cuts == [15.6, 17.56, 26.7]

    def test_parse_empty(self):
        assert rg.parse_showinfo_cuts("frame=0 fps=0\n") == []

    def test_end_before_cut(self):
        assert rg.end_before_cut(17.56) == pytest.approx(17.52)

    def test_scene_cut_args(self):
        args = rg.build_scene_cut_args(0.3)
        assert args[args.index("-vf") + 1] == "select='gt(scene,0.3)',showinfo"
        assert args[-2:] == ["-f", "null"]


class TestSheetsAndStrip:
    def test_contact_sheet_args_default(self):
        pre, args = rg.build_contact_sheet_args()
        assert pre == []
        vf = args[args.index("-vf") + 1]
        assert vf == (
            "fps=2,scale=240:-1,drawtext=text='%{pts\\:flt}':x=4:y=4:fontsize=16:"
            "fontcolor=yellow:box=1:boxcolor=black,tile=6x10"
        )
        assert args[-2:] == ["-frames:v", "1"]

    def test_contact_sheet_fine_range(self):
        pre, args = rg.build_contact_sheet_args(fps=6, start=15.0, duration=3.0)
        assert pre == ["-ss", "15.000", "-t", "3.000"]
        assert args[args.index("-vf") + 1].startswith("fps=6,")
        # 6 fps * 3 s = 18 frames -> 6 columns x 3 rows
        assert "tile=6x3" in args[args.index("-vf") + 1]

    def test_waveform_args(self):
        pre, args = rg.build_waveform_args(12.0)
        assert pre == ["-ss", "12.000", "-t", "6.000"]
        assert args[args.index("-filter_complex") + 1] == "showwavespic=s=1200x200"

    def test_check_strip_args(self):
        args = rg.build_check_strip_args(frame_count=30, frames=10)
        assert args[args.index("-vf") + 1] == "select='not(mod(n\\,3))',scale=320:-1,tile=5x2"

    def test_check_strip_short_gif(self):
        args = rg.build_check_strip_args(frame_count=4, frames=10)
        assert "mod(n\\,1)" in args[args.index("-vf") + 1]


class TestGallery:
    def test_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("WVB_GIF_GALLERY", str(tmp_path / "g"))
        assert rg.default_gallery_dir() == tmp_path / "g"

    def test_default(self, monkeypatch):
        monkeypatch.delenv("WVB_GIF_GALLERY", raising=False)
        assert rg.default_gallery_dir() == Path.home() / "Pictures" / "Reaction GIFs"

    def test_slug(self):
        assert rg.caption_slug("I'VE GOT IT!") == "ive-got-it"
        assert rg.caption_slug("") == "reaction"


class TestYtDlpCommands:
    def test_subs_command(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.youtube import ytdlp_cli

        cmd = ytdlp_cli.build_subs_command("https://example.test/v", tmp_path / "subs")
        assert cmd[0].endswith("yt-dlp")
        for flag in ("--write-subs", "--write-auto-subs", "--skip-download"):
            assert flag in cmd
        assert cmd[cmd.index("--sub-langs") + 1] == "en.*"
        assert cmd[cmd.index("--convert-subs") + 1] == "srt"
        assert cmd[-1] == "https://example.test/v"

    def test_section_command(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.youtube import ytdlp_cli

        cmd = ytdlp_cli.build_section_command(
            "https://example.test/v", 1215.0, 1245.0, tmp_path / "clip.mp4"
        )
        assert cmd[cmd.index("-f") + 1] == "bv*[height<=720]+ba/b[height<=720]/b"
        assert cmd[cmd.index("--download-sections") + 1] == "*20:15-20:45"
        assert "--force-keyframes-at-cuts" in cmd
        assert cmd[cmd.index("--merge-output-format") + 1] == "mp4"
        assert cmd[cmd.index("-o") + 1] == str(tmp_path / "clip.mp4")
