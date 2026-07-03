"""mcp-transport-faults: prove tool errors survive the real JSON-RPC wire.

Companion to ``test_mcp_transport.py``. That module proves the happy path
serializes across a real stdio MCP subprocess. This one is the adversarial
variant: it injects representative *faults* and asserts the tool's structured
error dict (``status=error`` + ``error_type`` + ``suggestion``, no traceback)
arrives intact as data across real JSON-RPC -- never as a transport-level
exception blob or an unstructured string.

Oracle = a real ``fastmcp`` client talking to the installed
``workshop-video-brain-server`` console script over stdio.
"""
from __future__ import annotations

import asyncio
import json
import shutil

import pytest

pytestmark = pytest.mark.external

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

SERVER_CMD = "workshop-video-brain-server"

VALID_ERROR_TYPES = {
    "missing_file", "missing_binary", "missing_dependency", "invalid_input",
    "invalid_index", "bad_json_param", "corrupt_project", "media_unreadable",
    "operation_failed", "not_found",
}


def _requires_server():
    if not shutil.which(SERVER_CMD):
        pytest.skip(f"{SERVER_CMD} console script not on PATH")


async def _call(tool: str, args: dict):
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    client = Client(StdioTransport(command=SERVER_CMD, args=[]))
    async with client:
        return await client.call_tool(tool, args)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=120))


def _payload(result):
    payload = getattr(result, "data", None)
    if payload is None:
        payload = getattr(result, "structured_content", None)
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = {"_raw": payload}
    return payload or {}


def _assert_structured_error(payload):
    assert isinstance(payload, dict), payload
    assert payload.get("status") == "error", payload
    assert payload.get("error_type") in VALID_ERROR_TYPES, payload
    sugg = payload.get("suggestion")
    assert sugg and len(str(sugg)) > 15, payload
    # the whole payload crossed JSON-RPC: no traceback text anywhere
    blob = json.dumps(payload)
    assert "Traceback" not in blob, payload
    assert '  File "' not in blob, payload


# Five representative, setup-free faults spanning param families + tool
# families. Each reaches its error path regardless of on-disk state.
FAULT_CASES = [
    # nonexistent workspace_path -> missing_file
    ("project_summary", {"workspace_path": "/nonexistent/ff/wire/xyz"}),
    # empty string param delivered over the wire -> invalid_input
    ("snapshot_restore", {"workspace_path": "/tmp", "snapshot_id": ""}),
    # invalid enum value -> invalid_input (checked before any project load)
    ("track_add", {"workspace_path": "/tmp", "track_type": "hologram"}),
    # missing media file -> missing_file (clip tool)
    ("clip_insert", {"workspace_path": "/tmp", "media_path": "/no/such/media.mp4"}),
    # missing rendered file for qc -> missing_file
    ("qc_check", {"file_path": "/no/such/render.mp4"}),
]


@pytest.mark.parametrize("tool,args", FAULT_CASES, ids=[c[0] for c in FAULT_CASES])
def test_tool_error_crosses_jsonrpc_as_structured_dict(tool, args):
    _requires_server()
    result = _run(_call(tool, args))
    assert result is not None
    _assert_structured_error(_payload(result))


def test_malformed_json_string_param_crosses_wire_as_bad_json(tmp_path):
    """A malformed JSON-string param (the agent-facing failure mode) must come
    back as a structured ``bad_json_param`` error over real JSON-RPC -- not a
    transport exception. Requires a real project file so the error reaches the
    JSON-decode step rather than short-circuiting on a missing file."""
    _requires_server()
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parents[1] / "fixtures" / "keyframe_project.kdenlive"
    )
    if not fixture.exists():
        pytest.skip("keyframe_project fixture not present")

    media = tmp_path / "media"
    media.mkdir()
    created = _run(_call("workspace_create",
                         {"title": "WireFault", "media_root": str(media)}))
    ws_root = _payload(created).get("data", {}).get("workspace_root")
    assert ws_root, created
    shutil.copy(fixture, Path(ws_root) / "proj.kdenlive")

    result = _run(_call("effect_keyframe_set_scalar", {
        "workspace_path": ws_root, "project_file": "proj.kdenlive",
        "track": 2, "clip": 0, "effect_index": 0, "property": "opacity",
        "keyframes": "[{ this is not valid json",
    }))
    payload = _payload(result)
    _assert_structured_error(payload)
    assert payload["error_type"] == "bad_json_param", payload


def test_transport_does_not_raise_on_injected_fault():
    """The client call must return a value, not surface a JSON-RPC exception,
    even when the tool body hits an error path."""
    _requires_server()
    result = _run(_call("project_summary", {"workspace_path": "/nonexistent/ff/wire"}))
    assert result is not None
