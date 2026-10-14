"""clip_insert records media duration in project-profile frames."""
from pathlib import Path
import xml.etree.ElementTree as ET

from tests._testkit import make_test_clip, requires_ffmpeg_ffprobe
from tests.unit.test_targeted_transitions import _THREE_CLIP_XML, _make_workspace


def _insert(tmp_path, media, *, out_seconds=-1.0):
    from workshop_video_brain.edit_mcp.server.tools import clip_insert

    workspace = _make_workspace(tmp_path, _THREE_CLIP_XML)
    result = clip_insert(str(workspace), str(media), out_seconds=out_seconds)
    assert result["status"] == "success", result.get("message")
    data = result["data"]
    root = ET.parse(Path(data["kdenlive_path"])).getroot()
    main_bin = root.find("playlist[@id='main_bin']")
    entry = main_bin.find(f"entry[@producer='{data['producer_id']}']")
    producer = root.find(f"producer[@id='{data['producer_id']}']")
    length = producer.find("property[@name='length']").text
    return data, root, entry, int(length)


@requires_ffmpeg_ffprobe
def test_insert_records_probed_length_and_main_bin_out(tmp_path):
    media = make_test_clip(tmp_path / "four_seconds.mp4", duration=4, fps=25)
    data, _, entry, length = _insert(tmp_path, media)
    assert data["producer_length"] == 100
    assert length == 100
    assert entry.get("out") == "99"


@requires_ffmpeg_ffprobe
def test_30fps_media_uses_project_frames(tmp_path):
    media = make_test_clip(tmp_path / "two_seconds_30fps.mp4", duration=2, fps=30)
    data, _, entry, length = _insert(tmp_path, media)
    assert data["out_frame"] == 49
    assert length == 50
    assert entry.get("out") == "49"


@requires_ffmpeg_ffprobe
def test_repeated_insert_reuses_producer_and_covers_both_uses(tmp_path):
    from workshop_video_brain.edit_mcp.server.tools import clip_insert

    media = make_test_clip(tmp_path / "repeat.mp4", duration=4, fps=25)
    workspace = _make_workspace(tmp_path, _THREE_CLIP_XML)
    first = clip_insert(str(workspace), str(media))
    assert first["status"] == "success", first.get("message")
    second = clip_insert(str(workspace), str(media))
    assert second["status"] == "success", second.get("message")
    root = ET.parse(Path(second["data"]["kdenlive_path"])).getroot()
    producer_id = second["data"]["producer_id"]
    assert len(root.findall(f"producer[@id='{producer_id}']")) == 1
    producer = root.find(f"producer[@id='{producer_id}']")
    assert producer.find("property[@name='length']").text == "100"
    main_bin = root.find("playlist[@id='main_bin']")
    assert main_bin.find(f"entry[@producer='{producer_id}']").get("out") == "99"
