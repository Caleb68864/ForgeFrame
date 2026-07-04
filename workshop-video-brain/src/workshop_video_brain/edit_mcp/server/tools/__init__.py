"""Aggregator for the carved ``server/tools`` package (auto-discovered).

Importing this package imports every domain submodule so that all
``@mcp.tool()`` decorators fire and register with the FastMCP singleton
(preserving the original ``import server.tools`` side effect). Discovery
mirrors ``server/bundles`` (``pkgutil.iter_modules``) so **adding a new tool
module never edits this file** -- drop a ``tools/<x>.py`` with ``@mcp.tool()``
decorators and it registers on package import.

The historical re-export surface (every public tool plus the private helpers
external code relies on, e.g. ``_build_filter_xml`` imported by
``bundles/shake_shadow``) is preserved via PEP 562 ``__getattr__``: a
``name -> source module`` map is built during the discovery loop from the names
each submodule *defines* (owns), plus the small set of helpers historically
re-exported from ``tools_helpers``. ``from ...tools import <name>`` and
``tools.<name>`` therefore keep resolving with zero caller edits.

Monkeypatch note: tests ``setattr`` names such as ``_resolve_vault_root_for_tools``
directly on this package and submodule code reads them back via
``_tools_pkg.<name>``. A real module ``__dict__`` entry always shadows
``__getattr__`` (PEP 562), so a patched attribute wins over lazy resolution and
is restored cleanly on teardown -- the patch semantics are unchanged.
"""
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

# Helpers historically re-exported through this package from the sibling
# ``tools_helpers`` package (they are imported *into* the tool submodules, not
# defined there, so ownership discovery below will not find them).
from workshop_video_brain.edit_mcp.server import tools_helpers as _tools_helpers

_HELPER_REEXPORTS = (
    "_get_video_playlists",
    "_load_latest_project",
    "_save_patched",
    "_resolve_playlist",
    "_build_filter_xml",
    "_VALID_COLOR_FORMATS_MSG",
    "_lookup_catalog_by_service",
)

# Immutable/container data constants (e.g. ``_VALID_MASK_SHAPES``) carry no
# ``__module__`` to attribute them to a defining submodule, so recognise them
# by type when deciding ownership.
_CONSTANT_TYPES = (str, bytes, int, float, bool, tuple, frozenset, dict, list, set)

# name -> source module, built during side-effect discovery below.
_EXPORTS: dict[str, ModuleType] = {}

for _mod_info in pkgutil.iter_modules(__path__):
    if _mod_info.name.startswith("_"):
        continue
    _submod = importlib.import_module(f"{__name__}.{_mod_info.name}")
    for _name, _obj in vars(_submod).items():
        if _name.startswith("__"):
            continue
        if isinstance(_obj, ModuleType):
            continue
        _owner = getattr(_obj, "__module__", None)
        if _owner == _submod.__name__:
            # A function/class defined in this submodule.
            _EXPORTS.setdefault(_name, _submod)
        elif _owner is None and isinstance(_obj, _CONSTANT_TYPES):
            # A module-level data constant defined in this submodule.
            _EXPORTS.setdefault(_name, _submod)

for _name in _HELPER_REEXPORTS:
    _EXPORTS.setdefault(_name, _tools_helpers)

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    """Resolve a re-exported tool/helper name to its owning module (PEP 562)."""
    source = _EXPORTS.get(name)
    if source is not None:
        return getattr(source, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
