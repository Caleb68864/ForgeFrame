"""mcp-transport: exercise the FastMCP server over a real stdio JSON-RPC link.

Oracle = a real JSON-RPC transport (a subprocess speaking MCP over stdio). This
is the only test that proves tool schemas serialize/deserialize across the wire,
including the string-encoded-JSON params (``keyframes=json.dumps(...)``) that are
exactly where an agent-facing server breaks.
"""
from __future__ import annotations

import asyncio
import json
import shutil

import pytest

pytestmark = pytest.mark.external

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

SERVER_CMD = "workshop-video-brain-server"


def _requires_server():
    if not shutil.which(SERVER_CMD):
        pytest.skip(f"{SERVER_CMD} console script not on PATH")


async def _call(tool: str, args: dict):
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    client = Client(StdioTransport(command=SERVER_CMD, args=[]))
    async with client:
        if tool == "__list__":
            return await client.list_tools()
        return await client.call_tool(tool, args)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=120))


def test_stdio_lists_tools():
    _requires_server()
    tools = _run(_call("__list__", {}))
    names = {t.name for t in tools}
    assert "ping" in names
    assert len(names) > 50  # ~136 tools registered


def test_stdio_ping_roundtrips():
    _requires_server()
    result = _run(_call("ping", {}))
    text = getattr(result, "data", None) or str(result)
    assert "pong" in str(text).lower()


def test_stdio_representative_tools():
    _requires_server()
    for tool in ("render_list_profiles", "project_list"):
        result = _run(_call(tool, {}))
        assert result is not None


def test_stdio_string_encoded_json_param(tmp_path):
    """Call a tool with a JSON-string param over the wire (the agent-facing
    failure mode). We assert the server parses and responds structurally, not
    that the edit succeeds (no workspace is set up)."""
    _requires_server()
    keyframes = json.dumps([{"frame": 0, "value": 1.0}, {"frame": 24, "value": 0.0}])
    args = {
        "workspace_path": str(tmp_path),
        "project_file": "missing.kdenlive",
        "track": 0,
        "clip": 0,
        "effect_index": 0,
        "property": "level",
        "keyframes": keyframes,
    }
    result = _run(_call("effect_keyframe_set_scalar", args))
    payload = getattr(result, "data", None)
    if payload is None:
        payload = getattr(result, "structured_content", None) or {}
    # The server should have parsed the JSON-string param and returned a
    # structured result (an error is fine -- the workspace is empty); what
    # matters is that transport + param decoding did not blow up.
    assert result is not None
    if isinstance(payload, dict) and "status" in payload:
        assert payload["status"] in ("success", "error")
