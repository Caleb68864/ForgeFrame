# MLT Python bindings worker

`edit_mcp/adapters/mlt/_worker.py` loads projects with the real MLT engine. `engine.py` runs it and interprets the result.

## Why it is out of process

The bindings exist only for a system Python: 3.14 on this Arch machine, 3.12 for Ubuntu's `python3-mlt`. They are not on PyPI and do not exist for Windows or macOS. The project venv cannot import them. They also segfault on bad handles, so every request gets its own process, and a crash comes back as `MltWorkerCrashed` or a validation error rather than a dead server. There is no pool. The interpreter comes from `WVB_MLT_PYTHON`, which never silently falls back, else the venv's Python, else `/usr/bin/python3`.

## Protocol

One JSON request line on stdin, `{"protocol": 1, "op": ..., "args": {...}}`. Zero or more `{"event": ...}` lines, then one `{"ok": true, "result": ...}` or `{"ok": false, "error": ...}`.

Some MLT C code writes to fd 1, so the worker first duplicates stdout for itself and points fd 1 at stderr:

```python
PROTO = os.fdopen(os.dup(1), "w", buffering=1)
os.dup2(2, 1)
```

MLT also prints about 170 lines to stderr on every init (`Duplicate filter registration`, failed dlopens). `engine.py` strips those from error tails. A streaming op sends stderr to a temp file, because that noise would fill an unread pipe and deadlock.

## Traps

- **Segfaults.** Bind every MLT object to a local name for the whole op. Wrappers built from garbage-collected temporaries crash.
- **The walk.** `Multitrack(root.producer())`, then `track(0)`. If that is a cut, take its `parent()`, the sequence tractor. Each track is a per-track tractor holding playlists, or in legacy flat files a bare playlist. The background is a producer of length `INT_MAX`; skip it.
- **`is_valid()` lies about missing media.** It is true even when a clip's file is gone; MLT only logs `failed to load chain`. Missing media belongs to `adapters/render/media_check`, and the load check does not duplicate it.
- **`ci.resource`** is resolved against the document root, so a `color` producer reads `<root>/0xff0000ff`. Never stat it.
- **`prof.description()`** is stale. Do not use it.

## Load check

`engine.load_check` compares what MLT built with our parsed model: profile, playlists, clip count, and each clip's in, out and timeline start. Differences are `load_check` items in `project_validate`, on by default. `load_check=False` turns it off. Without bindings it falls back to `melt`, which only shows whether the file loads. Set `WVB_LOAD_CHECK_ON_WRITE=1` to also log the check after each save; a failure there never fails the save.

## Frame grabs

```python
producer.seek(frame); image_frame = producer.get_frame()
image = image_frame.get_image(mlt.mlt_image_rgb, width, height)
```

`get_image(fmt, 0, 0)` returns an **empty** buffer, so always pass the size. Tracks are composited. The system Python has no Pillow, so the worker writes PNGs with `struct` and `zlib`.

`timeline_thumbnails` uses this, and falls back to `melt <project> in=F out=F -consumer avformat:...`, once per frame.

## Render progress

`WVB_RENDER_ENGINE` is `melt` (default), `mlt` or `auto`. `mlt` renders through the worker's `render` op with the same consumer properties melt receives, and streams `{"event": "progress", "frame", "total"}`. `adapters/render/progress.Throttle` limits what reaches the job record, because each write is a SQLite `BEGIN IMMEDIATE`.

The bindings engine matches melt's own render at the project's profile (at least 40 dB, equal frame counts). It stays opt-in.

## Findings on the fixtures (2026-11-02)

The load check over `tests/fixtures/kdenlive_references/`: 10 of 11 files give no errors. `mix_slide_upstream_kde.kdenlive` segfaults MLT 7.42 on load and comes back as a validation error, not a crash. Warnings on the others are native saves the parser cannot fully read; see the timecode note in `docs/prompts/00-README.md`.

A title composited on a top track grabs the same through the bindings as through the old "render `0..F` and keep the last" melt method, so `review_loop` now uses the grab.
