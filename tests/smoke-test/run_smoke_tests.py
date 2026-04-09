#!/usr/bin/env python3
"""Smoke tests for Kdenlive project generation.

Downloads test media, creates projects with increasing complexity,
and validates the generated .kdenlive XML at each step.

Usage:
    uv run python tests/smoke-test/run_smoke_tests.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

SMOKE_DIR = Path("/tmp/forgeframe-smoke-test")
MEDIA_DIR = SMOKE_DIR / "media"
RESULTS_DIR = SMOKE_DIR / "results"

# Ensure we can import the project
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workshop-video-brain" / "src"))


def banner(msg: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}\n")


def check(condition: bool, msg: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {msg}")
    return condition


def get_props(elem: ET.Element) -> dict[str, str]:
    """Extract <property name="...">value</property> into a dict."""
    return {p.get("name", ""): (p.text or "") for p in elem.findall("property")}


def validate_kdenlive(path: Path, label: str) -> tuple[bool, ET.Element | None]:
    """Validate a .kdenlive file and return (all_pass, root)."""
    banner(f"Validating: {label}")
    print(f"  File: {path}")

    if not path.exists():
        print(f"  [FAIL] File does not exist!")
        return False, None

    size = path.stat().st_size
    print(f"  Size: {size} bytes")
    check(size > 100, "File has content (>100 bytes)")

    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"  [FAIL] XML parse error: {e}")
        return False, None

    check(root.tag == "mlt", "Root element is <mlt>")

    all_pass = True

    # Root attributes
    all_pass &= check(
        root.get("producer") == "main_bin",
        'Root has producer="main_bin"',
    )
    all_pass &= check(
        root.get("LC_NUMERIC") == "C",
        'Root has LC_NUMERIC="C"',
    )

    # Profile
    profile = root.find("profile")
    all_pass &= check(profile is not None, "Profile element exists")
    if profile is not None:
        all_pass &= check(
            profile.get("frame_rate_num") is not None,
            "Profile has frame_rate_num",
        )
        all_pass &= check(
            profile.get("progressive") == "1",
            "Profile has progressive=1",
        )

    # Black track
    black = root.find("./producer[@id='black_track']")
    all_pass &= check(black is not None, "black_track producer exists")
    if black is not None:
        bt_props = get_props(black)
        all_pass &= check(
            bt_props.get("mlt_service") == "color",
            "black_track mlt_service=color",
        )

    # Main bin
    main_bin = root.find("./playlist[@id='main_bin']")
    all_pass &= check(main_bin is not None, "main_bin playlist exists")

    # Count user producers (exclude black_track)
    all_producers = [
        p for p in root.findall("producer") if p.get("id") != "black_track"
    ]
    print(f"\n  Producers found: {len(all_producers)}")

    if main_bin is not None:
        bin_entries = main_bin.findall("entry")
        all_pass &= check(
            len(bin_entries) == len(all_producers),
            f"main_bin has {len(bin_entries)} entries (expected {len(all_producers)})",
        )

        # Check all producers are in main_bin
        bin_ids = {e.get("producer") for e in bin_entries}
        for prod in all_producers:
            pid = prod.get("id")
            all_pass &= check(
                pid in bin_ids,
                f"Producer '{pid}' is in main_bin",
            )

    # Check kdenlive metadata on each producer
    for prod in all_producers:
        pid = prod.get("id")
        props = get_props(prod)
        all_pass &= check(
            "kdenlive:uuid" in props and props["kdenlive:uuid"].startswith("{"),
            f"Producer '{pid}' has kdenlive:uuid",
        )
        all_pass &= check(
            "kdenlive:id" in props and props["kdenlive:id"].isdigit(),
            f"Producer '{pid}' has kdenlive:id (integer)",
        )
        all_pass &= check(
            "kdenlive:clip_type" in props,
            f"Producer '{pid}' has kdenlive:clip_type",
        )
        # Validate clip_type value
        ct = props.get("kdenlive:clip_type", "")
        service = props.get("mlt_service", "")
        if service.startswith("avformat"):
            all_pass &= check(ct == "3", f"Producer '{pid}' clip_type=3 (AV)")
        elif service == "kdenlivetitle":
            all_pass &= check(ct == "6", f"Producer '{pid}' clip_type=6 (Text)")
        elif service == "color":
            all_pass &= check(ct == "4", f"Producer '{pid}' clip_type=4 (Color)")

    # Tractor
    tractor = root.find("tractor")
    if tractor is not None:
        tracks = tractor.findall("track")
        all_pass &= check(len(tracks) >= 1, f"Tractor has {len(tracks)} tracks")
        if tracks:
            all_pass &= check(
                tracks[0].get("producer") == "black_track",
                "First tractor track is black_track",
            )

        # Internal transitions
        transitions = tractor.findall("transition")
        internal_transitions = [
            t for t in transitions if get_props(t).get("internal_added") == "237"
        ]
        user_transitions = [
            t for t in transitions if get_props(t).get("internal_added") != "237"
        ]
        print(f"\n  Transitions: {len(internal_transitions)} internal, {len(user_transitions)} user")

        for t in internal_transitions:
            t_props = get_props(t)
            all_pass &= check(
                t_props.get("a_track") == "0",
                f"Internal transition a_track=0 (service={t_props.get('mlt_service')})",
            )
            b_track = t_props.get("b_track", "0")
            all_pass &= check(
                b_track != "0",
                f"Internal transition b_track={b_track} (not 0)",
            )

        # Check user transitions don't have a_track == b_track
        for t in user_transitions:
            t_props = get_props(t)
            a = t_props.get("a_track")
            b = t_props.get("b_track")
            if a is not None and b is not None:
                all_pass &= check(
                    a != b,
                    f"User transition a_track={a} != b_track={b}",
                )

        # Paired playlists
        playlists = root.findall("playlist")
        pair_playlists = [p for p in playlists if p.get("id", "").endswith("_kdpair")]
        content_playlists = [
            p for p in playlists
            if p.get("id") != "main_bin" and not p.get("id", "").endswith("_kdpair")
        ]
        print(f"  Playlists: {len(content_playlists)} content, {len(pair_playlists)} paired")
        all_pass &= check(
            len(pair_playlists) == len(content_playlists),
            "Each content playlist has a paired empty playlist",
        )

    return all_pass, root


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_1_single_clip() -> Path:
    """Test 1: Project with a single video clip."""
    banner("TEST 1: Single clip project")

    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject, Producer, Playlist, PlaylistEntry,
        ProjectProfile, Track,
    )
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

    clip_path = str(MEDIA_DIR / "clip_a.mp4")
    project = KdenliveProject(
        title="Smoke Test 1 - Single Clip",
        profile=ProjectProfile(width=416, height=240, fps=24.0),
        producers=[
            Producer(
                id="clip0",
                resource=clip_path,
                properties={"resource": clip_path, "mlt_service": "avformat"},
            ),
        ],
        tracks=[
            Track(id="playlist0", track_type="video"),
            Track(id="playlist1", track_type="audio"),
        ],
        playlists=[
            Playlist(
                id="playlist0",
                entries=[PlaylistEntry(producer_id="clip0", in_point=0, out_point=240)],
            ),
            Playlist(
                id="playlist1",
                entries=[PlaylistEntry(producer_id="clip0", in_point=0, out_point=240)],
            ),
        ],
        guides=[],
        opaque_elements=[],
    )

    out = RESULTS_DIR / "test1_single_clip.kdenlive"
    serialize_project(project, out)
    return out


def test_2_two_clips() -> Path:
    """Test 2: Project with two video clips on the timeline."""
    banner("TEST 2: Two clips project")

    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject, Producer, Playlist, PlaylistEntry,
        ProjectProfile, Track,
    )
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

    clip_a = str(MEDIA_DIR / "clip_a.mp4")
    clip_b = str(MEDIA_DIR / "clip_b.mp4")

    project = KdenliveProject(
        title="Smoke Test 2 - Two Clips",
        profile=ProjectProfile(width=416, height=240, fps=24.0),
        producers=[
            Producer(
                id="clip_a",
                resource=clip_a,
                properties={
                    "resource": clip_a,
                    "mlt_service": "avformat",
                    "kdenlive:clipname": "Bunny Scene A",
                },
            ),
            Producer(
                id="clip_b",
                resource=clip_b,
                properties={
                    "resource": clip_b,
                    "mlt_service": "avformat",
                    "kdenlive:clipname": "Bunny Scene B",
                },
            ),
        ],
        tracks=[
            Track(id="video_track", track_type="video"),
            Track(id="audio_track", track_type="audio"),
        ],
        playlists=[
            Playlist(
                id="video_track",
                entries=[
                    PlaylistEntry(producer_id="clip_a", in_point=0, out_point=240),
                    PlaylistEntry(producer_id="clip_b", in_point=0, out_point=240),
                ],
            ),
            Playlist(
                id="audio_track",
                entries=[
                    PlaylistEntry(producer_id="clip_a", in_point=0, out_point=240),
                    PlaylistEntry(producer_id="clip_b", in_point=0, out_point=240),
                ],
            ),
        ],
        guides=[],
        opaque_elements=[],
    )

    out = RESULTS_DIR / "test2_two_clips.kdenlive"
    serialize_project(project, out)
    return out


def test_3_clips_with_transition() -> Path:
    """Test 3: Two clips with a dissolve transition between them."""
    banner("TEST 3: Two clips with dissolve transition")

    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject, Producer, Playlist, PlaylistEntry,
        ProjectProfile, Track, OpaqueElement,
    )
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

    clip_a = str(MEDIA_DIR / "clip_a.mp4")
    clip_b = str(MEDIA_DIR / "clip_b.mp4")

    # Dissolve: last 24 frames of clip_a overlap with first 24 frames of clip_b
    # This requires two video tracks for the overlap region
    project = KdenliveProject(
        title="Smoke Test 3 - Dissolve",
        profile=ProjectProfile(width=416, height=240, fps=24.0),
        producers=[
            Producer(
                id="clip_a",
                resource=clip_a,
                properties={
                    "resource": clip_a,
                    "mlt_service": "avformat",
                    "kdenlive:clipname": "Bunny Scene A",
                },
            ),
            Producer(
                id="clip_b",
                resource=clip_b,
                properties={
                    "resource": clip_b,
                    "mlt_service": "avformat",
                    "kdenlive:clipname": "Bunny Scene B",
                },
            ),
        ],
        tracks=[
            Track(id="v1", track_type="video"),
            Track(id="v2", track_type="video"),
            Track(id="a1", track_type="audio"),
        ],
        playlists=[
            # V1: clip_a full
            Playlist(
                id="v1",
                entries=[
                    PlaylistEntry(producer_id="clip_a", in_point=0, out_point=240),
                ],
            ),
            # V2: blank for 216 frames, then clip_b (starts 24f before clip_a ends)
            Playlist(
                id="v2",
                entries=[
                    PlaylistEntry(producer_id="", in_point=0, out_point=215),  # blank
                    PlaylistEntry(producer_id="clip_b", in_point=0, out_point=240),
                ],
            ),
            # A1: audio from both clips
            Playlist(
                id="a1",
                entries=[
                    PlaylistEntry(producer_id="clip_a", in_point=0, out_point=240),
                    PlaylistEntry(producer_id="clip_b", in_point=0, out_point=240),
                ],
            ),
        ],
        guides=[],
        opaque_elements=[
            # Luma dissolve between v1 and v2 tracks during overlap (frames 216-240)
            OpaqueElement(
                tag="transition",
                xml_string=(
                    '<transition in="216" out="240">'
                    '<property name="mlt_service">luma</property>'
                    '<property name="a_track">1</property>'
                    '<property name="b_track">3</property>'
                    '<property name="kdenlive_id">dissolve</property>'
                    '</transition>'
                ),
                position_hint="after_tractor",
            ),
        ],
    )

    out = RESULTS_DIR / "test3_dissolve.kdenlive"
    serialize_project(project, out)
    return out


def test_4_with_title_card() -> Path:
    """Test 4: Two clips with a title card and transition."""
    banner("TEST 4: Clips + title card")

    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject, Producer, Playlist, PlaylistEntry,
        ProjectProfile, Track, Guide,
    )
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

    clip_a = str(MEDIA_DIR / "clip_a.mp4")
    clip_b = str(MEDIA_DIR / "clip_b.mp4")

    project = KdenliveProject(
        title="Smoke Test 4 - Title Cards",
        profile=ProjectProfile(width=416, height=240, fps=24.0),
        producers=[
            Producer(
                id="title_intro",
                resource="",
                properties={
                    "mlt_service": "kdenlivetitle",
                    "kdenlive:clipname": "Intro Title",
                    "length": "72",
                    "xmldata": (
                        '<kdenlivetitle width="416" height="240" out="71">'
                        '<item type="QGraphicsTextItem" z-index="0">'
                        '<position x="50" y="80"><transform>1,0,0,0,1,0,0,0,1</transform></position>'
                        '<content font="Sans" font-size="36" font-weight="700" '
                        'font-color="255,255,255,255" alignment="4">'
                        'Big Buck Bunny Test</content>'
                        '</item>'
                        '<background color="0,0,0,255"/>'
                        '</kdenlivetitle>'
                    ),
                },
            ),
            Producer(
                id="clip_a",
                resource=clip_a,
                properties={
                    "resource": clip_a,
                    "mlt_service": "avformat",
                    "kdenlive:clipname": "Bunny Scene A",
                },
            ),
            Producer(
                id="clip_b",
                resource=clip_b,
                properties={
                    "resource": clip_b,
                    "mlt_service": "avformat",
                    "kdenlive:clipname": "Bunny Scene B",
                },
            ),
        ],
        tracks=[
            Track(id="v1", track_type="video"),
            Track(id="a1", track_type="audio"),
        ],
        playlists=[
            Playlist(
                id="v1",
                entries=[
                    PlaylistEntry(producer_id="title_intro", in_point=0, out_point=71),
                    PlaylistEntry(producer_id="clip_a", in_point=0, out_point=240),
                    PlaylistEntry(producer_id="clip_b", in_point=0, out_point=240),
                ],
            ),
            Playlist(
                id="a1",
                entries=[
                    PlaylistEntry(producer_id="", in_point=0, out_point=71),  # blank for title
                    PlaylistEntry(producer_id="clip_a", in_point=0, out_point=240),
                    PlaylistEntry(producer_id="clip_b", in_point=0, out_point=240),
                ],
            ),
        ],
        guides=[
            Guide(position=0, label="Intro", category="0"),
            Guide(position=72, label="Scene A", category="0"),
            Guide(position=312, label="Scene B", category="0"),
        ],
        opaque_elements=[],
    )

    out = RESULTS_DIR / "test4_title_card.kdenlive"
    serialize_project(project, out)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_pass = True
    results = []

    # Generate projects
    tests = [
        ("Test 1: Single clip", test_1_single_clip),
        ("Test 2: Two clips", test_2_two_clips),
        ("Test 3: Dissolve transition", test_3_clips_with_transition),
        ("Test 4: Title card + clips", test_4_with_title_card),
    ]

    for label, test_fn in tests:
        try:
            out_path = test_fn()
            passed, root = validate_kdenlive(out_path, label)
            results.append((label, passed, out_path))
            all_pass &= passed
        except Exception as e:
            print(f"\n  [FAIL] {label}: {e}")
            import traceback
            traceback.print_exc()
            results.append((label, False, None))
            all_pass = False

    # Summary
    banner("SMOKE TEST SUMMARY")
    for label, passed, path in results:
        status = "PASS" if passed else "FAIL"
        path_str = str(path) if path else "N/A"
        print(f"  [{status}] {label}")
        if path:
            print(f"         {path_str}")

    print(f"\n  Overall: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print(f"\n  Output files in: {RESULTS_DIR}/")
    print(f"  Copy to a machine with Kdenlive to test opening them.")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
