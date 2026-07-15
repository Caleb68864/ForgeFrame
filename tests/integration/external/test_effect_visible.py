"""effect-visible: does an applied effect actually change rendered pixels?

This is the first real probe of the §1.1 pathology. The current code attaches
clip filters at the MLT root (tagged with custom track=/clip_index= attrs), not
nested inside the clip <entry> where MLT applies them -- so the effect is
expected to be a **no-op today**.

- ``test_effect_changes_pixels`` is xfail(strict): it asserts the effect
  changes pixels. It fails now (no change) and flips to passing the instant the
  §1.1 placement fix lands.
- ``test_control_no_effect_identical`` guards against flakiness: two renders of
  the same project must match.
- ``test_nested_filter_is_visible`` proves the *oracle itself works*: a filter
  placed correctly (inside the <entry>) DOES change pixels. If this ever fails,
  the harness -- not the code -- is broken.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

from . import builders
from ._oracle import frames_differ, frames_similar, render_frame

pytestmark = pytest.mark.external

FRAME = 10
EFFECT = "avfilter.negate"  # unmistakable: inverts every channel


def _render(proj, name, render_dir, frame=FRAME, melt_bin="melt"):
    path = render_dir / f"{name}.kdenlive"
    serialize_project(proj, path)
    return render_frame(path, frame, render_dir, melt_bin=melt_bin, name=f"{name}.png")


def test_control_no_effect_identical(melt_bin, render_dir: Path):
    a = _render(builders.solid_color_project(color=builders.RED), "ctl_a", render_dir, melt_bin=melt_bin)
    b = _render(builders.solid_color_project(color=builders.RED), "ctl_b", render_dir, melt_bin=melt_bin)
    assert frames_similar(a, b), "two identical renders differ -- render is nondeterministic"


def test_nested_filter_is_visible(melt_bin, render_dir: Path):
    """A correctly-placed (entry-nested) filter must change pixels.

    Proves the oracle can detect a real effect and is not self-referential.
    """
    base = _render(builders.solid_color_project(color=builders.RED), "nest_base", render_dir, melt_bin=melt_bin)

    # Serialize, then hand-inject a filter INSIDE the video clip <entry>.
    proj = builders.solid_color_project(color=builders.RED)
    nested_path = render_dir / "nested.kdenlive"
    serialize_project(proj, nested_path)
    tree = ET.parse(nested_path)
    root = tree.getroot()
    pl = next(p for p in root.findall("playlist") if p.get("id") == builders.VIDEO_TRACK)
    entry = pl.find("entry")
    filt = ET.SubElement(entry, "filter")
    ET.SubElement(filt, "property", {"name": "mlt_service"}).text = EFFECT
    tree.write(nested_path)

    from ._oracle import render_frame as _rf
    nested = _rf(nested_path, FRAME, render_dir, melt_bin=melt_bin, name="nested.png")
    assert frames_differ(base, nested), (
        "entry-nested filter did not change pixels -- the oracle cannot see "
        "effects, harness is broken"
    )


def test_effect_changes_pixels(melt_bin, render_dir: Path):
    base = _render(builders.solid_color_project(color=builders.RED), "eff_base", render_dir, melt_bin=melt_bin)

    proj = builders.solid_color_project(color=builders.RED)
    xml = builders.build_filter_xml(EFFECT, track=0, clip=0)
    patcher.insert_effect_xml(proj, (0, 0), xml, position=0)
    withfx = _render(proj, "eff_on", render_dir, melt_bin=melt_bin)

    assert frames_differ(base, withfx), (
        "root-placed effect changed nothing -- effect is a no-op in melt"
    )
