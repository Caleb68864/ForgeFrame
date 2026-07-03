# MCP Tool Error Contract (Hardening Pass 1)

Status: STABLE — adopt as-is. Authored by the server/tools agent for the
bundles/ and pipelines/ sibling agents. Module:
`workshop_video_brain/edit_mcp/server/errors.py`.

## Why

Every MCP tool must fail **gracefully but loudly**: a structured error dict that
says *what broke* and *what to do next*. Never a raw traceback in the payload,
never a silent fake success.

## Backward compatibility (IMPORTANT — verified against live code)

The pre-existing helper is `tools_helpers._err(message)` and returns:

```python
{"status": "error", "message": "<msg>"}
```

Note: the key is **`message`**, NOT `error`. Existing tests assert
`result["status"] == "error"` and substring-match `result["message"]`, and a
couple assert the **exact** dict (e.g. `effect_info` not-found/empty). Therefore:

- **Keep the `message` key and its text unchanged** when enriching an existing
  error path. Only *add* keys.
- **Do not enrich paths asserted by exact-dict equality** (adding keys breaks
  `==`). Known cases: `effect_info` in `test_effect_catalog_mcp_tools.py`. Grep
  your package's tests for `== {` before enriching.

## The builder

```python
from workshop_video_brain.edit_mcp.server.errors import err

err(message, *, suggestion=None, cause=None, error_type=None, **details) -> dict
```

Returns:

```python
{
    "status": "error",
    "message": "<human message, unchanged from legacy>",
    "error_type": "<stable machine key>",   # optional, recommended
    "suggestion": "<actionable next step in user language>",  # optional
    "cause": "<one-line: 'FileNotFoundError: ...'>",  # optional, NEVER a traceback
    # ...echoed offending input: path=..., given=..., valid_range=...
}
```

`cause` is one line only. Full tracebacks go to the log
(`logging.getLogger("workshop_video_brain.edit_mcp.tools")`), never the payload.

## Stable `error_type` machine keys

`missing_file` · `missing_binary` · `missing_dependency` · `invalid_input` ·
`invalid_index` · `bad_json_param` · `corrupt_project` · `media_unreadable` ·
`operation_failed` · `not_found`

Exposed as module constants (`errors.MISSING_FILE`, ...) and validated set
`errors.VALID_ERROR_TYPES`.

## Prebuilt constructors

```python
missing_file(path, what="file")
missing_binary(name, install_hint)          # e.g. missing_binary("melt", "apt install melt")
missing_dependency(pkg, pip_hint)           # e.g. missing_dependency("numpy", "uv add numpy")
invalid_index(kind, given, valid_range)     # e.g. invalid_index("track", 9, "0-3")
bad_json_param(param, expected_example, given)
corrupt_project(path, cause)                # cause may be an exception or str
media_unreadable(path, cause=None)
not_found(what, given, hint=None)
invalid_input(message, suggestion, **details)
operation_failed(message, cause=None, suggestion=None)
```

All return the contract shape above.

## The backstop decorator

```python
from workshop_video_brain.edit_mcp.server.errors import tool_guard

@mcp.tool()
@tool_guard                 # goes UNDER @mcp.tool()
def my_tool(...): ...
```

`tool_guard` catches any exception that escapes the tool body, logs the full
traceback, and returns `operation_failed(...)` with a one-line cause. It uses
`functools.wraps` so FastMCP's signature/schema introspection is unchanged.
Existing `try/except` and explicit `err(...)` returns still run first; the guard
is only the outer net.

## Adoption checklist for bundles/ and pipelines/

1. `from workshop_video_brain.edit_mcp.server.errors import err, tool_guard, missing_file, ...`
2. Put `@tool_guard` under every `@mcp.tool()` in your package.
3. For each common failure mode, return the matching constructor, preserving any
   legacy `message` text your tests assert on:
   - nonexistent workspace/project/media path → `missing_file(path, what)`
   - track/clip index out of range → `invalid_index(kind, given, valid_range)`
     (read the real range from the parsed project)
   - malformed JSON string param → `bad_json_param(param, example, given)`
   - missing melt/ffmpeg → `missing_binary(name, install_hint)`
   - `ProjectParseError` → catch it explicitly → `corrupt_project(path, exc)`
     (before any generic `except`)
   - empty timeline / no-op precondition → loud `err(...)` OR an explicit no-op
     result (`skipped_intents` style). NEVER a fake success.
4. Do not rename existing `message` text; enrich by adding keys only.
5. Do not touch exact-dict-asserted error paths.
