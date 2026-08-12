"""Unit tests for the canonical ffmpeg-filtergraph path escaper.

An ffmpeg filtergraph description is unescaped **twice** before a filter sees
its argument -- once by the graph parser, once by the filter's own option
parser. Every expectation below was established empirically against a real
ffmpeg (see ``vault/wiki/ffmpeg-filtergraph-path-escaping.md``); they are not
derived from the documentation, and the naive single-level escaping they
replaced was wrong in all three respects.

The rules, in short: separators become forward slashes (a native ``\\`` is
eaten by the second pass), ``:`` takes two backslashes, ``'`` takes three.
"""
from pathlib import PureWindowsPath

from workshop_video_brain.edit_mcp.pipelines._common import escape_filter_path


class TestEscapeFilterPath:
    def test_plain_posix_path_is_unchanged(self):
        # No drive colon and no backslashes -- nothing to escape, which is
        # exactly why this bug was invisible on Linux CI.
        assert escape_filter_path("/tmp/x.trf") == "/tmp/x.trf"

    def test_windows_separators_become_forward_slashes(self):
        # A native backslash does not survive: the second unescaping pass
        # consumes "\U" and "C:\Users" arrives at the filter as "C:Users".
        assert escape_filter_path(PureWindowsPath(r"C:\ws\x.trf")) == r"C\\:/ws/x.trf"

    def test_colon_takes_two_backslashes(self):
        # One backslash is stripped by the first pass, leaving a bare ":"
        # that the second pass reads as an option separator -- silently
        # truncating the path at the drive letter.
        assert escape_filter_path("a:b") == r"a\\:b"

    def test_apostrophe_takes_three_backslashes(self):
        # The quote character is handled one pass earlier than ":", so it
        # needs one more level. Two backslashes and four both fail.
        assert escape_filter_path("/tmp/caleb's dir/x.trf") == r"/tmp/caleb\\\'s dir/x.trf"

    def test_spaces_are_not_escaped(self):
        assert escape_filter_path("/tmp/with space/x.trf") == "/tmp/with space/x.trf"

    def test_full_windows_path_with_drive_space_and_apostrophe(self):
        out = escape_filter_path(PureWindowsPath(r"C:\Users\caleb's videos\my clip\x.trf"))
        assert out == r"C\\:/Users/caleb\\\'s videos/my clip/x.trf"
        # No bare separator survives to be misread as an option boundary.
        assert "\\" not in out.replace(r"\\:", "").replace(r"\\\'", "")

    def test_accepts_path_objects_and_str_alike(self):
        assert escape_filter_path(PureWindowsPath(r"C:\x")) == escape_filter_path(r"C:\x")
