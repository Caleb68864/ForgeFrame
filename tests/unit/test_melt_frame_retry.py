"""engine._melt_frame: a melt that writes nothing (exit 0) or stalls is retried; errors say why."""
from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.mlt import engine

# A stand-in for melt: behaviour per call number comes from a plan file.
_FAKE = r'''#!{python}
import pathlib, sys, time
here = pathlib.Path(__file__).parent
count_file = here / "calls"
n = int(count_file.read_text()) if count_file.exists() else 0
count_file.write_text(str(n + 1))
plan = (here / "plan").read_text().split(",")
action = plan[min(n, len(plan) - 1)]
pattern = next(a for a in sys.argv if a.startswith("avformat:"))[len("avformat:"):]
sys.stderr.write('mlt_repository_register: Duplicate filter registration for "frei0r.B"\n')
if action == "empty":
    sys.exit(0)
if action == "hang":
    time.sleep(30)
if action == "error":
    sys.stderr.write("Failed to load project: no such producer\n")
    sys.exit(1)
pathlib.Path(pattern.replace("%05d", "00001")).write_bytes(b"\x89PNG fake")
'''


@pytest.fixture
def fake_melt(tmp_path):
    folder = tmp_path / "bin"
    folder.mkdir()
    melt = folder / "melt"
    melt.write_text(_FAKE.replace("{python}", sys.executable))
    melt.chmod(melt.stat().st_mode | stat.S_IEXEC)

    def run(plan: str):
        (folder / "plan").write_text(plan)
        (folder / "calls").unlink(missing_ok=True)
        out = tmp_path / "out"
        out.mkdir(exist_ok=True)
        return engine._melt_frame(tmp_path / "p.kdenlive", 45, None, out, str(melt))

    run.calls = lambda: int((folder / "calls").read_text())
    return run


def test_empty_exit_zero_is_retried(fake_melt):
    path = fake_melt("empty,ok")
    assert path.read_bytes().startswith(b"\x89PNG")
    assert fake_melt.calls() == 2


def test_stall_is_cut_short_and_retried(fake_melt, monkeypatch):
    monkeypatch.setattr(engine, "_GRAB_ATTEMPT_TIMEOUT_SECONDS", 2)
    assert fake_melt("hang,ok").exists()
    assert fake_melt.calls() == 2


def test_gives_up_with_exit_codes_and_reasons(fake_melt):
    with pytest.raises(engine.MltWorkerError) as excinfo:
        fake_melt("empty")
    message = str(excinfo.value)
    assert fake_melt.calls() == 3
    assert message.count("melt exit 0, no frame written") == 3
    assert "plugin-load noise" in message


def test_real_error_is_not_retried_and_shows_stderr(fake_melt):
    with pytest.raises(engine.MltWorkerError) as excinfo:
        fake_melt("error,ok")
    assert fake_melt.calls() == 1
    assert "melt exit 1" in str(excinfo.value)
    assert "Failed to load project: no such producer" in str(excinfo.value)
