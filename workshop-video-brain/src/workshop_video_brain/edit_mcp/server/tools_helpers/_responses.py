"""Response-shape helpers -- the legacy ``status`` envelope contract.

The canonical ``_ok`` / ``_err`` pair every tool leans on for success/error
dicts (the richer ``errors.err`` family is layered on top of ``_err``).
"""
from __future__ import annotations


def _ok(data: dict) -> dict:
    return {"status": "success", "data": data}


def _err(message: str) -> dict:
    return {"status": "error", "message": message}
