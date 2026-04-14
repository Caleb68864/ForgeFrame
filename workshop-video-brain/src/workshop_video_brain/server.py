"""MCP server entry point for workshop-video-brain."""
from fastmcp import FastMCP

mcp = FastMCP("workshop-video-brain")


@mcp.tool()
def ping() -> str:
    """Health check. Returns server status."""
    return "pong: workshop-video-brain is running"


# Import tool and resource modules so their @mcp.tool() / @mcp.resource()
# decorators execute and register with the FastMCP instance above.
import workshop_video_brain.edit_mcp.server.tools  # noqa: E402, F401
import workshop_video_brain.edit_mcp.server.resources  # noqa: E402, F401
# Registration side effect: each generated wrapper module applies
# `@register_effect_wrapper` (which wraps `@mcp.tool()`).
import workshop_video_brain.edit_mcp.pipelines.effect_wrappers  # noqa: E402, F401


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
