"""Prompt 24 experiment: producer layout variants of a serialized project.

Post-processes serializer output (it never touches the serializer):

* ``V0``  shared: unchanged -- one producer per media, used by main_bin and
  every track and placement (CLAUDE.md hard rule 14 keeps its length).
* ``V1``  per track: one clone per (media, timeline playlist), id ``<id>_t<n>``.
* ``V2``  per placement: one clone per timeline entry, id ``<id>_p<n>``.
* ``V1u`` / ``V2u``: as V1 / V2, and the bin element plus every clone share
  one ``kdenlive:control_uuid``, as Kdenlive's own saves do.

Clones keep every property (``kdenlive:id`` included) and get a ``length``
covering only their own entries; the bin element keeps its length.
"""
from __future__ import annotations

import copy
import uuid
import xml.etree.ElementTree as ET

VARIANTS = ("V0", "V1", "V2", "V1u", "V2u")
_NOT_MEDIA = {"producer_black", "black_track"}


def _props(element: ET.Element) -> dict[str, ET.Element]:
    return {p.get("name"): p for p in element.findall("property")}


def _set_prop(element: ET.Element, name: str, value: str) -> None:
    prop = _props(element).get(name)
    if prop is None:
        prop = ET.SubElement(element, "property", {"name": name})
    prop.text = value


def timeline_playlists(root: ET.Element) -> list[ET.Element]:
    return [p for p in root.findall("playlist") if p.get("id") != "main_bin"]


def media_ids(root: ET.Element) -> list[str]:
    """Producers/chains referenced by timeline entries (not the black track)."""
    defined = {e.get("id") for e in root if e.tag in ("producer", "chain")}
    used = []
    for playlist in timeline_playlists(root):
        for entry in playlist.findall("entry"):
            pid = entry.get("producer")
            if pid in defined and pid not in _NOT_MEDIA and pid not in used:
                used.append(pid)
    return used


def set_length(xml_text: str, producer_id: str, length: int) -> str:
    """The rule-14 control: force one producer's ``length`` (and ``out``)."""
    root = ET.fromstring(xml_text)
    for element in root:
        if element.tag in ("producer", "chain") and element.get("id") == producer_id:
            _set_prop(element, "length", str(length))
            element.set("out", str(length - 1))
    return ET.tostring(root, encoding="unicode")


def make_variant(xml_text: str, variant: str) -> str:
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}")
    if variant == "V0":
        return xml_text
    root = ET.fromstring(xml_text)
    per_placement = variant.startswith("V2")
    elements = {e.get("id"): e for e in root if e.tag in ("producer", "chain")}
    shared_uuid = "{" + str(uuid.uuid4()) + "}" if variant.endswith("u") else None
    children = list(root)
    insert_after: dict[str, list[ET.Element]] = {}
    counter = 0
    for media in media_ids(root):
        original = elements[media]
        if shared_uuid:
            _set_prop(original, "kdenlive:control_uuid", shared_uuid)
        clones: dict[str, ET.Element] = {}
        needed: dict[str, int] = {}
        for t_index, playlist in enumerate(timeline_playlists(root)):
            for entry in playlist.findall("entry"):
                if entry.get("producer") != media:
                    continue
                if per_placement:
                    key = f"{media}_p{counter}"
                    counter += 1
                else:
                    key = f"{media}_t{t_index}"
                if key not in clones:
                    clone = copy.deepcopy(original)
                    clone.set("id", key)
                    clones[key] = clone
                entry.set("producer", key)
                needed[key] = max(needed.get(key, 0), int(entry.get("out", "0")) + 1)
        for key, clone in clones.items():
            _set_prop(clone, "length", str(needed[key]))
            clone.set("out", str(needed[key] - 1))
            if shared_uuid:
                _set_prop(clone, "kdenlive:control_uuid", shared_uuid)
        insert_after[media] = list(clones.values())
    # Re-insert the clones right after their original element.
    for child in children:
        root.remove(child)
    for child in children:
        root.append(child)
        for clone in insert_after.get(child.get("id"), []):
            root.append(clone)
    return ET.tostring(root, encoding="unicode")


def count_layout(xml_text: str) -> dict:
    """Producer/chain elements per media resource, and per timeline playlist (for re-saved files)."""
    root = ET.fromstring(xml_text)
    by_resource: dict[str, list[str]] = {}
    for element in root:
        if element.tag not in ("producer", "chain"):
            continue
        resource = (_props(element).get("resource").text if _props(element).get("resource") is not None else "") or ""
        by_resource.setdefault(resource, []).append(element.get("id"))
    per_playlist = {p.get("id"): sorted({e.get("producer") for e in p.findall("entry")})
                    for p in root.findall("playlist")}
    return {"elements_per_resource": by_resource, "producers_per_playlist": per_playlist}


# ---------------------------------------------------------------------------
# scenarios and measurement (used by scripts/chain_placement_experiment.py
# and tests/integration/external/test_chain_layout_variants.py)
# ---------------------------------------------------------------------------

SEGMENT_COLOURS = ("red", "green", "blue", "white")  # 2 s (50 frames) each


def make_media(path) -> "Path":
    """Four 2 s solid segments (red, green, blue, white), 320x180 at 25 fps, with a sine track."""
    import subprocess
    from pathlib import Path

    path = Path(path)
    inputs = []
    for colour in ("red", "lime", "blue", "white"):
        inputs += ["-f", "lavfi", "-i", f"color=c={colour}:s=320x180:r=25:d=2"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                    "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]", "-map", "[v]", "-map", "4:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                   check=True, capture_output=True, timeout=120)
    return path


def colour_of_source(frame: int) -> str:
    return SEGMENT_COLOURS[min(3, frame // 50)]


def build_scenarios(media) -> dict[str, dict]:
    """``{name: {"xml", "expected": [(timeline_frame, colour)], "frames"}}`` serialized with the real serializer."""
    import tempfile
    from pathlib import Path

    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject, Playlist, PlaylistEntry, Producer, ProjectProfile, Track,
    )
    from workshop_video_brain.core.models.timeline import SetClipSpeed
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

    def project(tracks, entries_by_track):
        p = KdenliveProject(title="chain", profile=ProjectProfile(width=320, height=180, fps=25.0))
        p.producers = [Producer(id="media", resource=str(media), properties={
            "resource": str(media), "mlt_service": "avformat", "length": "200"})]
        p.tracks = [Track(id=tid, track_type=kind) for tid, kind in tracks]
        p.playlists = [Playlist(id=tid, entries=[PlaylistEntry(producer_id="media" if a >= 0 else "",
                                                               in_point=max(a, 0), out_point=b if a >= 0 else b)
                                                 for a, b in entries_by_track.get(tid, [])])
                       for tid, _kind in tracks]
        return p

    def serialized(p) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "p.kdenlive"
            serialize_project(p, out)
            return out.read_text(encoding="utf-8")

    av = [("v1", "video"), ("a1", "audio")]
    s1 = project(av, {"v1": [(0, 49)], "a1": [(0, 49)]})
    s2 = project(av, {"v1": [(0, 49), (100, 149)], "a1": [(0, 49), (100, 149)]})
    s3 = project([("v1", "video"), ("v2", "video"), ("a1", "audio")],
                 {"v1": [(0, 49)], "v2": [(150, 199)], "a1": [(0, 49)]})
    s4 = project(av, {"v1": [(0, 49), (100, 149)], "a1": [(0, 49), (100, 149)]})
    s4 = patch_project(s4, [SetClipSpeed(track_ref="v1", clip_index=1, speed=2.0)])
    s2_xml = serialized(s2)
    return {
        "S1_av": {"xml": serialized(s1), "expected": [(25, "red")], "frames": 50},
        "S2_twice": {"xml": s2_xml, "expected": [(25, "red"), (75, "blue")], "frames": 100},
        "S2short_twice_len50": {"xml": set_length(s2_xml, "media", 50), "expected": [(25, "red"), (75, "blue")],
                                "frames": 100},
        # Playlist order puts v2 above v1 (checked on V0 with melt: the frame is white).
        "S3_two_tracks": {"xml": serialized(s3), "expected": [(25, "white")], "frames": 50},
        "S4_speed": {"xml": serialized(s4), "expected": [(25, "red"), (62, "blue")], "frames": 75},
    }


def frame_colour(video, frame: int) -> str:
    """Dominant colour name of one frame of a rendered file (ffmpeg extract)."""
    import subprocess
    import tempfile
    from pathlib import Path

    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "f.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"select=eq(n\\,{frame})",
                        "-frames:v", "1", str(png)], check=True, capture_output=True, timeout=120)
        if not png.exists():
            return "missing"
        with Image.open(png) as image:
            r, g, b = image.convert("RGB").resize((8, 8)).getpixel((4, 4))
    if min(r, g, b) > 180:
        return "white"
    if max(r, g, b) < 50:
        return "black"
    return max((("red", r), ("green", g), ("blue", b)), key=lambda kv: kv[1])[0]
