"""Prompt 24 experiment harness: the producer-layout post-processor (no melt)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from tests.integration.external import _chain_layout as layout


@pytest.fixture(scope="module")
def scenarios(tmp_path_factory):
    # A placeholder file is enough: nothing renders here.
    media = tmp_path_factory.mktemp("m") / "media.mp4"
    media.write_bytes(b"")
    return layout.build_scenarios(media)


def _elements(xml):
    root = ET.fromstring(xml)
    return root, {e.get("id"): e for e in root if e.tag in ("producer", "chain")}


def _prop(element, name):
    found = [p.text for p in element.findall("property") if p.get("name") == name]
    return found[0] if found else None


def _timeline_refs(root):
    return [(p.get("id"), e.get("producer"), int(e.get("out")))
            for p in layout.timeline_playlists(root) for e in p.findall("entry") if e.get("producer") != "producer_black"]


def test_v0_is_unchanged(scenarios):
    xml = scenarios["S2_twice"]["xml"]
    assert layout.make_variant(xml, "V0") == xml


@pytest.mark.parametrize("variant, clones", [("V1", 2), ("V2", 4), ("V1u", 2), ("V2u", 4)])
def test_clone_counts_ids_and_identity(scenarios, variant, clones):
    xml = layout.make_variant(scenarios["S2_twice"]["xml"], variant)
    root, elements = _elements(xml)
    copies = [i for i in elements if i.startswith("media_")]
    assert len(copies) == clones
    ids = [e.get("id") for e in root if e.tag in ("producer", "chain")]
    assert len(ids) == len(set(ids))
    assert {_prop(elements[i], "kdenlive:id") for i in copies} == {_prop(elements["media"], "kdenlive:id")}
    refs = _timeline_refs(root)
    assert all(producer in copies for _p, producer, _o in refs)  # every placement repointed
    bin_refs = [e.get("producer") for e in root.find("playlist[@id='main_bin']").findall("entry")]
    assert "media" in bin_refs and not set(bin_refs) & set(copies)
    uuids = {_prop(elements[i], "kdenlive:control_uuid") for i in ["media", *copies]}
    assert (len(uuids) == 1 and None not in uuids) if variant.endswith("u") else uuids == {None}


def test_clone_lengths_cover_only_their_entries(scenarios):
    root, elements = _elements(layout.make_variant(scenarios["S2_twice"]["xml"], "V2"))
    for _playlist, producer, out in _timeline_refs(root):
        assert int(_prop(elements[producer], "length")) == out + 1
    v1_root, v1 = _elements(layout.make_variant(scenarios["S2_twice"]["xml"], "V1"))
    assert {int(_prop(v1[p], "length")) for _pl, p, _o in _timeline_refs(v1_root)} == {150}


def test_rule14_control_shortens_only_the_shared_producer(scenarios):
    _root, elements = _elements(scenarios["S2short_twice_len50"]["xml"])
    assert _prop(elements["media"], "length") == "50"
    _root2, v1 = _elements(layout.make_variant(scenarios["S2short_twice_len50"]["xml"], "V1"))
    assert _prop(v1["media"], "length") == "50" and _prop(v1["media_t0"], "length") == "150"


def test_count_layout(scenarios):
    counts = layout.count_layout(layout.make_variant(scenarios["S3_two_tracks"]["xml"], "V1"))
    media = [ids for r, ids in counts["elements_per_resource"].items() if r.endswith("media.mp4")][0]
    assert "media" in media and len(media) == 4  # the bin element + one per track (v1, v2, a1)
