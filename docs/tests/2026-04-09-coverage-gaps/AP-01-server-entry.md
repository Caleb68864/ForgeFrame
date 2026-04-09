---
scenario_id: "AP-01"
title: "Server Entry Point"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario AP-01: Server Entry Point

## Description
Tests `server.py` — the MCP server entry point for workshop-video-brain.

The module:
1. Creates a `FastMCP` instance named `"workshop-video-brain"` and exposes it as
   the module-level `mcp` object.
2. Registers a `ping` tool that returns `"pong: workshop-video-brain is running"`.
3. Imports `edit_mcp.server.tools` and `edit_mcp.server.resources` as side effects
   so their `@mcp.tool()` / `@mcp.resource()` decorators register with the same
   `mcp` instance.
4. Exposes a `main()` function that calls `mcp.run(transport="stdio")`.

Tests avoid starting a real MCP stdio server.  `main()` is tested by mocking
`mcp.run`.  Tool registration is verified by inspecting the `mcp` object.

## Preconditions
- Python 3.12+, `uv run pytest` available.
- `fastmcp` installed in the project virtualenv.
- `workshop_video_brain.server` importable; no real stdio transport started.

## Test Cases

```python
# tests/unit/test_server_entry.py
from unittest.mock import MagicMock, patch

import pytest


class TestServerModuleAttributes:
    def test_mcp_attribute_exists(self):
        from workshop_video_brain import server
        assert hasattr(server, "mcp")

    def test_mcp_is_fastmcp_instance(self):
        from fastmcp import FastMCP
        from workshop_video_brain import server
        assert isinstance(server.mcp, FastMCP)

    def test_main_callable(self):
        from workshop_video_brain import server
        assert callable(server.main)


class TestPingTool:
    def test_ping_returns_expected_string(self):
        from workshop_video_brain.server import ping
        result = ping()
        assert result == "pong: workshop-video-brain is running"

    def test_ping_return_contains_server_name(self):
        from workshop_video_brain.server import ping
        assert "workshop-video-brain" in ping()


class TestToolRegistration:
    def test_ping_registered_with_mcp(self):
        """Verify 'ping' is registered as a tool on the mcp instance."""
        from workshop_video_brain import server
        mcp = server.mcp

        # FastMCP exposes registered tools via _tool_manager or similar attribute.
        # Use the public API to list tool names if available, otherwise fall back
        # to checking the tool_manager dict directly.
        tool_names = _get_tool_names(mcp)
        assert "ping" in tool_names, f"ping not in registered tools: {tool_names}"

    def test_additional_tools_registered_from_imports(self):
        """At least one tool beyond 'ping' is registered (from tools.py import)."""
        from workshop_video_brain import server
        tool_names = _get_tool_names(server.mcp)
        assert len(tool_names) > 1, "Expected multiple tools registered"


def _get_tool_names(mcp_instance) -> list[str]:
    """Extract tool names from a FastMCP instance using available introspection."""
    # Try _tool_manager (FastMCP internal) or _tools dict
    for attr in ("_tool_manager", "_tools"):
        container = getattr(mcp_instance, attr, None)
        if container is not None:
            if hasattr(container, "tools"):
                return list(container.tools.keys())
            if isinstance(container, dict):
                return list(container.keys())
    # Fallback: trust the import succeeded and return empty (test will note it)
    return []


class TestMainFunction:
    def test_main_calls_mcp_run_with_stdio(self):
        from workshop_video_brain import server
        with patch.object(server.mcp, "run") as mock_run:
            server.main()
        mock_run.assert_called_once_with(transport="stdio")

    def test_main_does_not_raise_when_run_mocked(self):
        from workshop_video_brain import server
        with patch.object(server.mcp, "run"):
            server.main()  # should not raise


class TestImportSideEffects:
    def test_tools_module_importable(self):
        """Importing tools should not raise."""
        import workshop_video_brain.edit_mcp.server.tools  # noqa: F401

    def test_resources_module_importable(self):
        """Importing resources should not raise."""
        import workshop_video_brain.edit_mcp.server.resources  # noqa: F401
```

## Steps
1. Read source module at `workshop-video-brain/src/workshop_video_brain/server.py`
2. Create `tests/unit/test_server_entry.py`
3. Implement test cases above
4. Run: `uv run pytest tests/unit/test_server_entry.py -v`

## Expected Results
- The module-level `mcp` attribute is a `FastMCP` instance.
- `ping()` returns the exact string `"pong: workshop-video-brain is running"`.
- `ping` is registered as a tool on the `mcp` instance.
- At least one additional tool is registered via the side-effect imports.
- `main()` calls `mcp.run(transport="stdio")`.
- `tools` and `resources` submodules import without errors.

## Pass / Fail Criteria
- Pass: All tests pass
- Fail: Any test fails
