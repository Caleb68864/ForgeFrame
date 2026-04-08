"""MCP server entry point for workshop-video-brain."""
from fastmcp import FastMCP

mcp = FastMCP("workshop-video-brain")


@mcp.tool()
def ping() -> str:
    """Health check. Returns server status."""
    return "pong: workshop-video-brain is running"


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
