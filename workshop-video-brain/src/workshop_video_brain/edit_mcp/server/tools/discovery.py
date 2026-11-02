"""Environment and capability discovery tools."""
from workshop_video_brain.server import mcp


@mcp.tool()
def forgeframe_doctor() -> dict:
    """Check local binaries, engines and model caches without downloading models."""
    from workshop_video_brain.app.doctor import environment_report
    return environment_report()


@mcp.tool()
def forgeframe_capabilities() -> dict:
    """List available MCP tools and skills from registration metadata."""
    from workshop_video_brain.app.capabilities import capability_catalog
    return capability_catalog()
