"""Run MLT's Qt module without a display server.

MLT's Qt module (``kdenlivetitle``, ``qimage``, ``qtext``, ``qtblend``) will
not start without an X11/Wayland display. melt then logs "The MLT Qt module
requires a X11 or Wayland environment", keeps going, and exits 0: titles come
out as "INVALID" and Qt-drawn images as the wrong picture. Nothing downstream
notices, because the render "succeeded".

The fix is Qt's own headless platform: with ``QT_QPA_PLATFORM=offscreen`` MLT
creates its QApplication without a display. Measured 2026-11-21 on melt
7.42.0: a title frame rendered that way is pixel-identical to the same frame
under ``xvfb-run`` (mean difference 0.0), while the no-display frame differs by
~24 levels. ``xvfb-run`` is not used here: it is a shell script, and killing it
on a timeout leaves melt and Xvfb running.

So every melt / MLT-bindings subprocess runs with :func:`mlt_env`, and any
output that still carries :data:`QT_DISPLAY_ERROR` (an MLT build that refuses
``offscreen``) is treated as a failed render, never a success.
"""
from __future__ import annotations

import os
import shutil
import subprocess

QT_DISPLAY_ERROR = "requires a X11 or Wayland environment"

HEADLESS_MESSAGE = (
    "MLT's Qt module could not start: there is no display (DISPLAY / "
    "WAYLAND_DISPLAY unset) and this MLT build refused QT_QPA_PLATFORM=offscreen. "
    "Titles, Qt-drawn images and qtblend composites would render wrong, so the "
    "output was not accepted."
)
HEADLESS_SUGGESTION = (
    "Run the MCP server / wvb from a desktop session, or under a virtual display: "
    "`xvfb-run -a wvb ...` (Debian/Ubuntu: apt install xvfb). `wvb doctor` shows "
    "whether the Qt module is usable here."
)

_PROBE_TIMEOUT_SECONDS = 30


def has_display(environ: dict | None = None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def mlt_env(environ: dict | None = None) -> dict | None:
    """Environment for an MLT subprocess, or ``None`` to inherit unchanged.

    Adds ``QT_QPA_PLATFORM=offscreen`` only when there is no display and the
    caller has not chosen a Qt platform already.
    """
    env = os.environ if environ is None else environ
    if has_display(env) or env.get("QT_QPA_PLATFORM"):
        return None if environ is None else dict(env)
    return {**env, "QT_QPA_PLATFORM": "offscreen"}


def qt_display_failed(stderr: str | None) -> bool:
    """True when MLT's output says its Qt module could not start."""
    return QT_DISPLAY_ERROR in (stderr or "")


def probe_qt_module(melt: str | None = None) -> dict:
    """Can melt's Qt module run in this environment? Used by ``wvb doctor``.

    Renders one frame of a ``qtext`` producer to the null consumer with the
    same environment the renders use.
    """
    melt = melt or shutil.which("melt")
    base = {"display": has_display(), "qt_platform": None}
    if not melt:
        return {**base, "ready": False, "reason": "melt is not installed"}
    env = mlt_env()
    base["qt_platform"] = (env or os.environ).get("QT_QPA_PLATFORM") or None
    try:
        proc = subprocess.run(
            [melt, "qtext:", "text=forgeframe", "out=0", "-consumer", "null:", "terminate_on_pause=1"],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SECONDS, env=env, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {**base, "ready": False, "reason": f"melt probe failed: {exc}"}
    if qt_display_failed(proc.stderr):
        return {**base, "ready": False, "reason": HEADLESS_MESSAGE}
    if proc.returncode != 0:
        return {**base, "ready": False,
                "reason": f"melt could not load its Qt module (qtext), rc={proc.returncode}"}
    return {**base, "ready": True, "reason": ""}
