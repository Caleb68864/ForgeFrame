"""Prompt 24 harness check: S1 and S2 render the expected colours in melt, shared and per track."""
from __future__ import annotations

import pytest

from tests._testkit import requires_ffmpeg

from . import _chain_layout as layout
from ._oracle import render_frame

pytestmark = [pytest.mark.external, requires_ffmpeg]


@pytest.fixture(scope="module")
def scenarios(tmp_path_factory):
    return layout.build_scenarios(layout.make_media(tmp_path_factory.mktemp("media") / "rgbw.mp4"))


@pytest.mark.parametrize("name", ["S1_av", "S2_twice"])
@pytest.mark.parametrize("variant", ["V0", "V1"])
def test_melt_renders_expected_colours(melt_bin, render_dir, scenarios, name, variant):
    scenario = scenarios[name]
    path = render_dir / f"{name}_{variant}.kdenlive"
    path.write_text(layout.make_variant(scenario["xml"], variant), encoding="utf-8")
    for frame, colour in scenario["expected"]:
        png = render_frame(path, frame, render_dir, melt_bin=melt_bin, name=f"{name}_{variant}_{frame}.png")
        from PIL import Image
        with Image.open(png) as image:
            r, g, b = image.convert("RGB").resize((8, 8)).getpixel((4, 4))
        got = "white" if min(r, g, b) > 180 else max((("red", r), ("green", g), ("blue", b)), key=lambda kv: kv[1])[0]
        assert got == colour, (name, variant, frame, (r, g, b))
