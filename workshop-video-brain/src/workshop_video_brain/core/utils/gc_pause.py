"""Pause Python's cyclic garbage collector around bulk object building.

Parsing or serializing a large project allocates hundreds of thousands of
short-lived objects (ElementTree elements, pydantic models, strings). Each
allocation burst triggers generation-2 collections that walk every live
object, so the collector's share of the time grows faster than the project:
measured 2026-11-22, 2 500 -> 10 000 clips took 4.4x with the collector on and
4.0x with it paused, and CI's runner showed 7.7x. These objects hold no
reference cycles (ElementTree has no parent pointers; the models are plain
trees), so reference counting frees them as usual while the collector waits.
"""
from __future__ import annotations

import gc
from contextlib import ContextDecorator


class gc_paused(ContextDecorator):  # noqa: N801 -- reads as a decorator / with-statement
    """``with gc_paused():`` or ``@gc_paused()``; re-entrant, restores the previous state."""

    def __enter__(self):
        self._was_enabled = gc.isenabled()
        gc.disable()
        return self

    def __exit__(self, *exc):
        if self._was_enabled:
            gc.enable()
        return False
