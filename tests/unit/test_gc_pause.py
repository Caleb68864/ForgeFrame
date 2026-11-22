"""gc_paused: parse/serialize pause the cyclic collector and always restore it."""
from __future__ import annotations

import gc

import pytest

from tests._testkit import sequence_project
from workshop_video_brain.core.utils.gc_pause import gc_paused
from workshop_video_brain.edit_mcp.adapters.kdenlive import parser, serializer


def test_restores_state_even_on_error():
    assert gc.isenabled()
    with pytest.raises(RuntimeError):
        with gc_paused():
            assert not gc.isenabled()
            raise RuntimeError("boom")
    assert gc.isenabled()
    gc.disable()
    try:
        with gc_paused():
            pass
        assert not gc.isenabled()  # was off before: stays off
    finally:
        gc.enable()


def test_parse_and_serialize_run_with_the_collector_paused(tmp_path, monkeypatch):
    seen = []
    real_tostring = serializer.ET.tostring
    monkeypatch.setattr(serializer.ET, "tostring", lambda *a, **k: (seen.append(gc.isenabled()), real_tostring(*a, **k))[1])
    out = tmp_path / "p.kdenlive"
    serializer.serialize_project(sequence_project(), out)
    assert seen and not any(seen)
    real_fromstring = parser.ET.fromstring
    monkeypatch.setattr(parser.ET, "fromstring",
                        lambda *a, **k: (seen.append(gc.isenabled()), real_fromstring(*a, **k))[1])
    seen.clear()
    parser.parse_project(out)
    assert seen and not any(seen)
    assert gc.isenabled()
