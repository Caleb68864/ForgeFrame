"""Unit tests for the proxy-wiring pipeline + docproperties round-trip.

Pure-function coverage for ``pipelines/proxy_wiring`` (attach/detach/status/
use_originals/default naming) plus a parser<->serializer regression proving the
producer proxy properties and the ``kdenlive:docproperties.*`` proxy settings
survive a round-trip.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
)
from workshop_video_brain.edit_mcp.pipelines import proxy_wiring as pw


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _project(sources: list[str]) -> KdenliveProject:
    producers = [
        Producer(id=f"producer{i}", resource=src, properties={"resource": src})
        for i, src in enumerate(sources)
    ]
    entries = [PlaylistEntry(producer_id=p.id, in_point=0, out_point=99) for p in producers]
    return KdenliveProject(
        title="Proxy Test",
        producers=producers,
        playlists=[Playlist(id="playlist0", entries=entries)],
        tracks=[Track(id="playlist0", track_type="video")],
    )


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")
    return path


# ---------------------------------------------------------------------------
# default_proxy_path -- must match adapters/ffmpeg/proxy.proxy_path_for
# ---------------------------------------------------------------------------

def test_default_proxy_path_matches_generator(tmp_path):
    p = pw.default_proxy_path("/media/raw/my_clip.mp4", tmp_path)
    assert p == tmp_path / "my_clip_proxy.mp4"

    # Cross-check against the real generator naming.
    from workshop_video_brain.core.models import MediaAsset
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import proxy_path_for

    asset = MediaAsset(path="/media/raw/my_clip.mp4", media_type="video")
    assert pw.default_proxy_path(asset.path, tmp_path) == proxy_path_for(asset, tmp_path)


# ---------------------------------------------------------------------------
# attach_proxies
# ---------------------------------------------------------------------------

def test_attach_default_wires_existing_proxy(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    _touch(proxy_dir / "clip_proxy.mp4")
    project = _project(["/raw/clip.mp4"])

    _, report = pw.attach_proxies(project, proxy_dir)

    assert report.attached == ["producer0"]
    prod = project.producers[0]
    assert prod.resource == str(proxy_dir / "clip_proxy.mp4")
    assert prod.properties["kdenlive:proxy"] == str(proxy_dir / "clip_proxy.mp4")
    assert prod.properties["kdenlive:originalurl"] == "/raw/clip.mp4"
    assert project.docproperties["enableproxy"] == "1"
    assert project.docproperties["proxyparams"] == pw.PROXY_PARAMS


def test_attach_skips_missing_proxy_file(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    proxy_dir.mkdir(parents=True)
    project = _project(["/raw/clip.mp4"])  # no proxy file on disk

    _, report = pw.attach_proxies(project, proxy_dir)

    assert report.attached == []
    assert report.skipped_missing_proxy == ["producer0"]
    assert not pw.is_proxied(project.producers[0])
    assert "enableproxy" not in project.docproperties


def test_attach_source_filter_and_explicit_path(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    custom = _touch(tmp_path / "custom_proxy.mp4")
    project = _project(["/raw/a.mp4", "/raw/b.mp4"])

    _, report = pw.attach_proxies(
        project, proxy_dir, source="/raw/b.mp4", proxy_path=str(custom)
    )

    assert report.attached == ["producer1"]
    assert project.producers[1].resource == str(custom)
    assert not pw.is_proxied(project.producers[0])


def test_attach_skips_non_av_producers(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    _touch(proxy_dir / "black_proxy.mp4")
    project = _project(["/raw/clip.mp4"])
    project.producers.append(
        Producer(
            id="color0",
            resource="black",
            properties={"resource": "black", "mlt_service": "color"},
        )
    )
    assert [p.id for p in pw.proxyable_producers(project)] == ["producer0"]


# ---------------------------------------------------------------------------
# detach_proxies
# ---------------------------------------------------------------------------

def test_detach_reverts_to_original(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    _touch(proxy_dir / "clip_proxy.mp4")
    project = _project(["/raw/clip.mp4"])
    pw.attach_proxies(project, proxy_dir)

    _, report = pw.detach_proxies(project)

    assert report.detached == ["producer0"]
    prod = project.producers[0]
    assert prod.resource == "/raw/clip.mp4"
    assert prod.properties["kdenlive:proxy"] == pw.PROXY_SENTINEL
    assert project.docproperties["enableproxy"] == "0"


def test_detach_unchanged_when_not_proxied(tmp_path):
    project = _project(["/raw/clip.mp4"])
    _, report = pw.detach_proxies(project)
    assert report.detached == []
    assert report.unchanged == ["producer0"]


# ---------------------------------------------------------------------------
# proxy_status
# ---------------------------------------------------------------------------

def test_status_reports_proxied_and_missing(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    _touch(proxy_dir / "a_proxy.mp4")
    project = _project(["/raw/a.mp4", "/raw/b.mp4"])
    # Wire producer0 (proxy exists); producer1 stays unproxied.
    pw.attach_proxies(project, proxy_dir, source="/raw/a.mp4")

    rows = {r.producer_id: r for r in pw.proxy_status(project, proxy_dir)}

    assert rows["producer0"].proxied is True
    assert rows["producer0"].proxy_file_exists is True
    assert rows["producer0"].original == "/raw/a.mp4"
    assert rows["producer1"].proxied is False


def test_status_flags_missing_proxy_file(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    _touch(proxy_dir / "clip_proxy.mp4")
    project = _project(["/raw/clip.mp4"])
    pw.attach_proxies(project, proxy_dir)
    # Delete the proxy file after wiring.
    (proxy_dir / "clip_proxy.mp4").unlink()

    row = pw.proxy_status(project, proxy_dir)[0]
    assert row.proxied is True
    assert row.proxy_file_exists is False


# ---------------------------------------------------------------------------
# use_originals -- render safety
# ---------------------------------------------------------------------------

def test_use_originals_swaps_resource_back(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    _touch(proxy_dir / "clip_proxy.mp4")
    project = _project(["/raw/clip.mp4"])
    pw.attach_proxies(project, proxy_dir)
    assert project.producers[0].resource.endswith("clip_proxy.mp4")

    pw.use_originals(project)

    assert project.producers[0].resource == "/raw/clip.mp4"
    # kdenlive:proxy preserved so the GUI re-enables the proxy on open.
    assert pw.is_proxied(project.producers[0])


def test_originals_render_copy_returns_original_when_no_proxy(tmp_path):
    project = _project(["/raw/clip.mp4"])
    proj_file = tmp_path / "p.kdenlive"
    serialize_project(project, proj_file)

    out = pw.originals_render_copy(proj_file, tmp_path / "renders")
    assert out == proj_file  # unchanged: no proxies


def test_originals_render_copy_swaps_when_proxied(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    _touch(proxy_dir / "clip_proxy.mp4")
    project = _project(["/raw/clip.mp4"])
    pw.attach_proxies(project, proxy_dir)
    proj_file = tmp_path / "p.kdenlive"
    serialize_project(project, proj_file)

    out = pw.originals_render_copy(proj_file, tmp_path / "renders")
    assert out != proj_file
    swapped = parse_project(out)
    assert swapped.producers[0].resource == "/raw/clip.mp4"


# ---------------------------------------------------------------------------
# Round-trip regression: producer proxy props + doc proxy settings
# ---------------------------------------------------------------------------

def test_roundtrip_preserves_producer_proxy_props(tmp_path):
    proxy_dir = tmp_path / "media" / "proxies"
    _touch(proxy_dir / "clip_proxy.mp4")
    project = _project(["/raw/clip.mp4"])
    pw.attach_proxies(project, proxy_dir)

    proj_file = tmp_path / "p.kdenlive"
    serialize_project(project, proj_file)
    reparsed = parse_project(proj_file)

    prod = reparsed.producers[0]
    assert prod.resource == str(proxy_dir / "clip_proxy.mp4")
    assert prod.properties["kdenlive:proxy"] == str(proxy_dir / "clip_proxy.mp4")
    assert prod.properties["kdenlive:originalurl"] == "/raw/clip.mp4"


def test_roundtrip_preserves_proxy_docproperties(tmp_path):
    project = _project(["/raw/clip.mp4"])
    project.docproperties = {
        "enableproxy": "1",
        "proxyparams": pw.PROXY_PARAMS,
        "proxyextension": "mp4",
        "proxyminsize": "1000",
    }
    proj_file = tmp_path / "p.kdenlive"
    serialize_project(project, proj_file)

    xml = proj_file.read_text(encoding="utf-8")
    assert 'name="kdenlive:docproperties.enableproxy"' in xml
    assert 'name="kdenlive:docproperties.proxyparams"' in xml

    reparsed = parse_project(proj_file)
    assert reparsed.docproperties == project.docproperties


def test_roundtrip_does_not_duplicate_managed_docproperties(tmp_path):
    """Managed docproperties (version/profile/uuid) must not leak into the bag."""
    project = _project(["/raw/clip.mp4"])
    project.docproperties = {"enableproxy": "1"}
    proj_file = tmp_path / "p.kdenlive"
    serialize_project(project, proj_file)
    reparsed = parse_project(proj_file)

    # Only the proxy setting round-trips; version/profile/uuid stay managed.
    assert reparsed.docproperties == {"enableproxy": "1"}
    # And a second serialize writes each managed key exactly once.
    proj_file2 = tmp_path / "p2.kdenlive"
    serialize_project(reparsed, proj_file2)
    xml = proj_file2.read_text(encoding="utf-8")
    assert xml.count('name="kdenlive:docproperties.version"') == 1
    assert xml.count('name="kdenlive:docproperties.enableproxy"') == 1
