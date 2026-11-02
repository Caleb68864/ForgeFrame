"""The worker protocol, with fake workers under this interpreter; needs no MLT."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.adapters.mlt import engine
from workshop_video_brain.edit_mcp.adapters.mlt.engine import MltWorkerCrashed, MltWorkerError


def _worker(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "fake_worker.py"
    path.write_text("import json, os, signal, sys, time\nsys.stdin.readline()\n" + body)
    return path


def _run(worker: Path, op="inspect", timeout=20.0, **kwargs):
    return engine.run_worker(op, {}, timeout=timeout, _interpreter=sys.executable, _worker_path=worker, **kwargs)


def test_final_result_is_returned(tmp_path):
    worker = _worker(tmp_path, 'print(json.dumps({"ok": True, "result": {"protocol": 1, "tracks": []}}))\n')
    assert _run(worker) == {"protocol": 1, "tracks": []}


def test_events_reach_the_callback(tmp_path):
    worker = _worker(tmp_path, (
        'print(json.dumps({"event": "progress", "percent": 50}))\n'
        'print(json.dumps({"ok": True, "result": {}}))\n'
    ))
    events = []
    _run(worker, on_event=events.append)
    assert events == [{"event": "progress", "percent": 50}]


def test_segfault_raises_crashed_naming_the_signal(tmp_path):
    worker = _worker(tmp_path, "os.kill(os.getpid(), signal.SIGSEGV)\n")
    with pytest.raises(MltWorkerCrashed, match="SIGSEGV"):
        _run(worker)


def test_hung_worker_times_out(tmp_path):
    worker = _worker(tmp_path, "time.sleep(30)\n")
    with pytest.raises(subprocess.TimeoutExpired):
        _run(worker, timeout=1.0)


def test_garbage_output_raises(tmp_path):
    worker = _worker(tmp_path, 'print("Segmentation noise, not JSON")\n')
    with pytest.raises(MltWorkerError, match="protocol"):
        _run(worker)


def test_no_final_line_raises(tmp_path):
    worker = _worker(tmp_path, 'print(json.dumps({"event": "progress"}))\n')
    with pytest.raises(MltWorkerError, match="no result"):
        _run(worker)


def test_reported_failure_raises_with_its_message(tmp_path):
    worker = _worker(tmp_path, 'print(json.dumps({"ok": False, "error": {"type": "ValueError", "message": "boom"}}))\n')
    with pytest.raises(MltWorkerError, match="boom"):
        _run(worker)


def test_nonzero_exit_after_a_good_line_raises(tmp_path):
    worker = _worker(tmp_path, 'print(json.dumps({"ok": True, "result": {}}))\nsys.exit(3)\n')
    with pytest.raises(MltWorkerError, match="rc=3"):
        _run(worker)


def test_mlt_noise_is_stripped_from_the_stderr_tail(tmp_path):
    worker = _worker(tmp_path, (
        'print("mlt_repository_register: Duplicate filter registration for x", file=sys.stderr)\n'
        'print("the real problem", file=sys.stderr)\n'
        "sys.exit(2)\n"
    ))
    with pytest.raises(MltWorkerError) as raised:
        _run(worker)
    assert raised.value.stderr_tail == "the real problem"


def test_explicit_interpreter_never_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("WVB_MLT_PYTHON", str(tmp_path / "nonexistent"))
    assert engine.find_mlt_python(refresh=True) is None


def test_ping_with_a_wrong_protocol_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("WVB_MLT_PYTHON", sys.executable)
    worker = _worker(tmp_path, 'print(json.dumps({"ok": True, "result": {"protocol": 99}}))\n')
    assert engine.find_mlt_python(refresh=True, _worker_path=worker) is None


def test_good_ping_is_cached_until_refresh(tmp_path, monkeypatch):
    monkeypatch.setenv("WVB_MLT_PYTHON", sys.executable)
    worker = _worker(tmp_path, (
        'print(json.dumps({"ok": True, "result": {"protocol": 1, "mlt_version": "7.42.0", "python": "3.14"}}))\n'
    ))
    found = engine.find_mlt_python(refresh=True, _worker_path=worker)
    assert found.mlt_version == "7.42.0"
    worker.write_text("import sys; sys.exit(9)\n")
    assert engine.find_mlt_python(_worker_path=worker) == found
    assert engine.find_mlt_python(refresh=True, _worker_path=worker) is None


def test_run_worker_without_bindings_is_unavailable(monkeypatch):
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: None)
    with pytest.raises(engine.MltUnavailable, match="WVB_MLT_PYTHON"):
        engine.run_worker("ping", {}, timeout=1)


def test_crash_during_load_check_becomes_a_validation_error(tmp_path, monkeypatch):
    def crash(*_a, **_k):
        raise MltWorkerCrashed("SIGSEGV")

    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: object())
    monkeypatch.setattr(engine, "run_worker", crash)
    result = engine.load_check(tmp_path / "p.kdenlive", KdenliveProject())
    assert result.engine == "bindings"
    assert result.items[0].severity == "error"
    assert "SIGSEGV" in result.items[0].message


def test_no_engine_at_all_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: None)
    monkeypatch.setattr(engine.shutil, "which", lambda _name: None)
    result = engine.load_check(tmp_path / "p.kdenlive", KdenliveProject())
    assert result.engine == "skipped"
    assert [item.severity for item in result.items] == ["info"]


def test_worker_imports_nothing_from_the_project():
    """It runs under a foreign interpreter with -I, so these imports could not resolve."""
    assert "workshop_video_brain" not in engine.WORKER_PATH.read_text(encoding="utf-8")
