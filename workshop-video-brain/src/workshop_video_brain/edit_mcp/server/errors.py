"""Structured error contract for MCP tools.

Goal: every tool fails GRACEFULLY but LOUDLY -- a structured error dict that
tells the user *what broke* and *what to do next*, never a raw traceback and
never a silent fake success.

Backward compatibility
-----------------------
The pre-existing error shape (``tools_helpers._err``) is::

    {"status": "error", "message": "<msg>"}

Every builder here preserves those two base keys unchanged so existing tests
that assert ``result["status"] == "error"`` and substring-match
``result["message"]`` keep passing. New information is *added* under optional
keys, never renamed on top of ``message``:

    {
        "status": "error",
        "message": "<human message, unchanged from legacy>",
        "error_type": "<stable machine key>",   # optional but recommended
        "suggestion": "<actionable next step in user language>",  # optional
        "cause": "<one-line underlying cause, e.g. 'FileNotFoundError: ...'>",  # optional
        # ... plus echoed offending input where helpful (path=, given=, ...)
    }

The ``cause`` field is a *one-line* summary (usually ``type(exc).__name__ +
": " + str(exc)``). Full tracebacks are NEVER placed in the payload; they are
written to the server log via ``logging``.

Stable ``error_type`` machine keys
----------------------------------
``missing_file`` | ``missing_binary`` | ``missing_dependency`` |
``invalid_input`` | ``invalid_index`` | ``bad_json_param`` |
``corrupt_project`` | ``media_unreadable`` | ``operation_failed`` |
``not_found``

Sibling hardening agents (bundles/, pipelines/) adopt this identical contract.
"""
from __future__ import annotations

import functools
import logging
import math
from typing import Any, Callable

logger = logging.getLogger("workshop_video_brain.edit_mcp.tools")

# ---------------------------------------------------------------------------
# Stable machine-readable error_type keys
# ---------------------------------------------------------------------------
MISSING_FILE = "missing_file"
MISSING_BINARY = "missing_binary"
MISSING_DEPENDENCY = "missing_dependency"
INVALID_INPUT = "invalid_input"
INVALID_INDEX = "invalid_index"
BAD_JSON_PARAM = "bad_json_param"
CORRUPT_PROJECT = "corrupt_project"
MEDIA_UNREADABLE = "media_unreadable"
OPERATION_FAILED = "operation_failed"
NOT_FOUND = "not_found"

VALID_ERROR_TYPES = frozenset({
    MISSING_FILE,
    MISSING_BINARY,
    MISSING_DEPENDENCY,
    INVALID_INPUT,
    INVALID_INDEX,
    BAD_JSON_PARAM,
    CORRUPT_PROJECT,
    MEDIA_UNREADABLE,
    OPERATION_FAILED,
    NOT_FOUND,
})


def _one_line_cause(exc: BaseException) -> str:
    """Render an exception as a single safe line (class + message, no traceback)."""
    msg = str(exc).strip().splitlines()
    first = msg[0] if msg else ""
    if first:
        return f"{type(exc).__name__}: {first}"
    return type(exc).__name__


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------
def err(
    message: str,
    *,
    suggestion: str | None = None,
    cause: str | None = None,
    error_type: str | None = None,
    **details: Any,
) -> dict:
    """Build a structured error dict, backward compatible with legacy ``_err``.

    Args:
        message: Human-readable description of what broke. Kept under the
            legacy ``message`` key unchanged.
        suggestion: Actionable next step in user language ("check the path",
            "install melt", "pass a valid index 0-4"). Never generic filler.
        cause: One-line underlying cause. Use :func:`_one_line_cause` for an
            exception. Never a full traceback.
        error_type: One of the stable machine keys (see module constants).
        **details: Extra echo fields (e.g. ``path=...``, ``given=...``,
            ``valid_range=...``) that help the caller self-diagnose.

    Returns:
        ``{"status": "error", "message": ..., [optional keys]}``
    """
    out: dict[str, Any] = {"status": "error", "message": message}
    if error_type is not None:
        # Loud but non-fatal: unknown types still pass through so callers are
        # never blocked, but we log so drift is visible.
        if error_type not in VALID_ERROR_TYPES:
            logger.warning("err() called with unknown error_type=%r", error_type)
        out["error_type"] = error_type
    if suggestion is not None:
        out["suggestion"] = suggestion
    if cause is not None:
        out["cause"] = cause
    for key, value in details.items():
        if value is not None:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# Prebuilt constructors for the common cases
# ---------------------------------------------------------------------------
def missing_file(path: str, what: str = "file") -> dict:
    """A required path does not exist on disk."""
    return err(
        f"{what} does not exist: {path}",
        error_type=MISSING_FILE,
        suggestion=(
            f"Check that the {what} path is correct and the {what} exists. "
            "Paths are resolved relative to the current working directory unless absolute."
        ),
        path=path,
    )


def missing_binary(name: str, install_hint: str) -> dict:
    """A required external binary (melt/ffmpeg/...) is not on PATH."""
    return err(
        f"Required binary '{name}' was not found on PATH.",
        error_type=MISSING_BINARY,
        suggestion=f"Install it: {install_hint}",
        binary=name,
    )


def missing_dependency(pkg: str, pip_hint: str) -> dict:
    """A required Python package is not importable."""
    return err(
        f"Required Python package '{pkg}' is not installed.",
        error_type=MISSING_DEPENDENCY,
        suggestion=f"Install it: {pip_hint}",
        package=pkg,
    )


def invalid_index(kind: str, given: int, valid_range: str) -> dict:
    """A track/clip/etc index is out of the range the project actually has."""
    return err(
        f"{kind} index {given} is out of range (valid: {valid_range}).",
        error_type=INVALID_INDEX,
        suggestion=(
            f"Pass a {kind} index within {valid_range}. Use a summary/list tool "
            "to see how many exist in this project."
        ),
        given=given,
        valid_range=valid_range,
    )


def bad_json_param(param: str, expected_example: str, given: str) -> dict:
    """A string parameter that must contain JSON failed to parse / was malformed."""
    return err(
        f"Parameter '{param}' is not valid JSON.",
        error_type=BAD_JSON_PARAM,
        suggestion=f"Provide valid JSON, e.g. {expected_example}",
        param=param,
        given=given,
    )


def corrupt_project(path: str, cause: str | BaseException) -> dict:
    """A .kdenlive project could not be parsed (ProjectParseError et al.)."""
    cause_str = _one_line_cause(cause) if isinstance(cause, BaseException) else str(cause)
    return err(
        f"Project file could not be parsed: {path}",
        error_type=CORRUPT_PROJECT,
        suggestion=(
            "The .kdenlive file may be corrupt, truncated, or not a Kdenlive "
            "project. Restore a snapshot (snapshot_list / snapshot_restore) or "
            "reopen and re-save the project in Kdenlive."
        ),
        cause=cause_str,
        path=path,
    )


def media_unreadable(path: str, cause: str | BaseException | None = None) -> dict:
    """A media file exists but could not be probed/decoded."""
    cause_str = None
    if isinstance(cause, BaseException):
        cause_str = _one_line_cause(cause)
    elif cause is not None:
        cause_str = str(cause)
    return err(
        f"Media file could not be read: {path}",
        error_type=MEDIA_UNREADABLE,
        suggestion=(
            "Confirm the file is a valid media file and not truncated. "
            "Check that ffprobe/ffmpeg can open it."
        ),
        cause=cause_str,
        path=path,
    )


def not_found(what: str, given: str, hint: str | None = None) -> dict:
    """A named thing (effect, profile, clip label, ...) was not found."""
    return err(
        f"{what} not found: {given}",
        error_type=NOT_FOUND,
        suggestion=hint or f"List the available {what.lower()}s and pick a valid one.",
        given=given,
    )


def invalid_input(message: str, suggestion: str, **details: Any) -> dict:
    """Generic bad-argument error (empty string, out-of-domain value, ...)."""
    return err(
        message,
        error_type=INVALID_INPUT,
        suggestion=suggestion,
        **details,
    )


def operation_failed(
    message: str,
    cause: str | BaseException | None = None,
    suggestion: str | None = None,
) -> dict:
    """A tool body raised an unexpected error we could not classify."""
    cause_str = None
    if isinstance(cause, BaseException):
        cause_str = _one_line_cause(cause)
    elif cause is not None:
        cause_str = str(cause)
    return err(
        message,
        error_type=OPERATION_FAILED,
        suggestion=suggestion
        or (
            "This is an unexpected error. Please report it -- the full traceback "
            "is in the server log."
        ),
        cause=cause_str,
    )


def nonfinite_guard(**named: Any) -> dict | None:
    """Return an ``invalid_input`` error if any named float is NaN/inf, else None.

    Guards numeric tool params before they are written into a project file:
    ``float('nan')`` / ``float('inf')`` silently serialize into MLT XML and
    corrupt the timeline, so reject them loudly. Non-numeric values are ignored
    (they are validated elsewhere).
    """
    for name, val in named.items():
        if isinstance(val, bool) or val is None:
            continue
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            return invalid_input(
                f"{name} must be a finite number (got {val!r}).",
                f"Pass a real finite value for {name}; NaN and infinity are "
                "not allowed and would corrupt the project file.",
                param=name,
                given=str(val),
            )
    return None


def nonneg_index(kind: str, **named: Any) -> dict | None:
    """Return an ``invalid_index`` error if any named int is negative, else None.

    Negative indexes are dangerous for tools that index Python lists directly
    (a ``-1`` silently wraps to the *last* element and edits the wrong target),
    so reject them before use.
    """
    for name, val in named.items():
        try:
            i = int(val)
        except (TypeError, ValueError):
            continue
        if i < 0:
            return invalid_index(name if kind is None else f"{kind} {name}",
                                 i, "0 or greater")
    return None


def from_exception(exc: BaseException) -> dict:
    """Classify a caught exception into the richest matching structured error.

    Preserves the exception's own message text under ``message`` (so existing
    substring assertions on the legacy ``_err(str(exc))`` path keep passing)
    while adding a stable ``error_type``, an actionable ``suggestion`` and a
    one-line ``cause``. Used to upgrade the ubiquitous
    ``except Exception as exc: return _err(str(exc))`` backstops.

    Recognised types:
        ProjectParseError -> corrupt_project
        FileNotFoundError -> missing_file
        (ModuleNotFoundError/ImportError) -> missing_dependency
        NotADirectoryError/IsADirectoryError/ValueError/KeyError/TypeError -> invalid_input
        everything else -> operation_failed
    """
    # ProjectParseError lives in the kdenlive adapter; import lazily so this
    # module has no hard dependency on the adapter package.
    try:
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import (
            ProjectParseError,
        )
    except Exception:  # pragma: no cover - adapter always present in practice
        ProjectParseError = ()  # type: ignore[assignment]

    msg = str(exc)
    cause = _one_line_cause(exc)

    if ProjectParseError and isinstance(exc, ProjectParseError):
        path = str(getattr(exc, "path", ""))
        return err(
            msg,
            error_type=CORRUPT_PROJECT,
            suggestion=(
                "The .kdenlive file may be corrupt, truncated, or not a Kdenlive "
                "project. Restore a snapshot (snapshot_list / snapshot_restore) or "
                "reopen and re-save it in Kdenlive."
            ),
            cause=_one_line_cause(getattr(exc, "cause", exc)),
            path=path or None,
        )
    if isinstance(exc, FileNotFoundError):
        return err(
            msg,
            error_type=MISSING_FILE,
            suggestion="Check that the path is correct and the file exists.",
            cause=cause,
        )
    if isinstance(exc, (ModuleNotFoundError, ImportError)):
        name = getattr(exc, "name", None)
        return err(
            msg,
            error_type=MISSING_DEPENDENCY,
            suggestion=(
                f"A required Python package is missing"
                + (f" ('{name}')" if name else "")
                + ". Install it into the environment (e.g. `uv add <package>`)."
            ),
            cause=cause,
        )
    if isinstance(exc, (NotADirectoryError, IsADirectoryError, ValueError,
                        KeyError, TypeError)):
        return err(
            msg,
            error_type=INVALID_INPUT,
            suggestion=(
                "Check the arguments you passed -- one of them is missing, the "
                "wrong type, or out of the expected range."
            ),
            cause=cause,
        )
    return operation_failed(msg, cause=exc)


# ---------------------------------------------------------------------------
# Backstop decorator
# ---------------------------------------------------------------------------
def tool_guard(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a tool body so ANY uncaught exception becomes a structured error.

    This is the *outer backstop*. Existing specific ``try/except`` handling and
    explicit ``err(...)`` returns inside the tool still run first; the guard
    only fires for exceptions that escape them (or tools with no handling at
    all). It logs the full traceback to the server log and returns an
    ``operation_failed`` error containing only a one-line cause -- never the
    traceback -- in the payload.

    ``functools.wraps`` preserves ``__name__``/``__doc__``/``__wrapped__`` so
    FastMCP's signature introspection (and generated tool schema) is unchanged
    when this is applied *under* ``@mcp.tool()``::

        @mcp.tool()
        @tool_guard
        def my_tool(...): ...
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 -- deliberate backstop
            logger.exception("Unhandled exception in tool %s", fn.__name__)
            return operation_failed(
                f"{fn.__name__} failed unexpectedly: {type(exc).__name__}",
                cause=exc,
                suggestion=(
                    "This is an unexpected error. Please report it -- the full "
                    "traceback is in the server log."
                ),
            )

    return wrapper


__all__ = [
    "MISSING_FILE",
    "MISSING_BINARY",
    "MISSING_DEPENDENCY",
    "INVALID_INPUT",
    "INVALID_INDEX",
    "BAD_JSON_PARAM",
    "CORRUPT_PROJECT",
    "MEDIA_UNREADABLE",
    "OPERATION_FAILED",
    "NOT_FOUND",
    "VALID_ERROR_TYPES",
    "err",
    "missing_file",
    "missing_binary",
    "missing_dependency",
    "invalid_index",
    "bad_json_param",
    "corrupt_project",
    "media_unreadable",
    "not_found",
    "invalid_input",
    "operation_failed",
    "from_exception",
    "nonfinite_guard",
    "nonneg_index",
    "tool_guard",
]
