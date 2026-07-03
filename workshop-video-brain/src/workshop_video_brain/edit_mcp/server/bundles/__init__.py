"""Effect bundle tools — one module per tutorial-derived effect.

Modules in this package register MCP tools via ``@mcp.tool()`` on import.
Unlike ``effect_wrappers`` (generated, explicit imports), this package
auto-discovers submodules so adding a new bundle never edits shared files.
"""
from __future__ import annotations

import importlib
import pkgutil

for _mod in pkgutil.iter_modules(__path__):
    if not _mod.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_mod.name}")
