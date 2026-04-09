"""Tests for workshop_video_brain.server (MCP entry point)."""
from unittest.mock import patch

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

        tool_names = _get_tool_names(mcp)
        assert "ping" in tool_names, f"ping not in registered tools: {tool_names}"

    def test_additional_tools_registered_from_imports(self):
        """At least one tool beyond 'ping' is registered (from tools.py import)."""
        from workshop_video_brain import server
        tool_names = _get_tool_names(server.mcp)
        assert len(tool_names) > 1, "Expected multiple tools registered"


def _get_tool_names(mcp_instance) -> list[str]:
    """Extract tool names from a FastMCP instance using list_tools()."""
    import asyncio
    tools = asyncio.run(mcp_instance.list_tools())
    return [t.name for t in tools]


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
