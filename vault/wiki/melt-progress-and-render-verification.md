# melt render progress and render verification

Prompt 18, 2026-11-22. Code: `adapters/render/progress.py` (`parse_melt_progress`, `MeltProgressReader`), `adapters/render/executor.py` (`_run_render_process`, `verify_render_output`), `adapters/render/timeline_length.py`.

## The stderr format

melt (7.42) writes `Current Frame:         31, percentage:         62` to **stderr**. By default each report ends with `\r` (it overwrites a terminal line); with `-progress2` each ends with `\n`. ForgeFrame passes `-progress2` and splits on both, so either form parses. Updates are coarse: a 250-frame (10 s) render at preview size gave 84 reports in ~1.8 s on this machine.

## melt never prints 100

The last report is about `frame N-1, percentage: 99` (`49, 98` for 50 frames). ForgeFrame sends `percent=100` itself, and only after `verify_render_output` passed -- a render that fails verification never shows 100.

## Drain both pipes

MLT writes ~170 lines of module-registration noise to stderr before rendering. `_run_render_process` reads stderr in 4096-byte chunks on one thread (chunks, not lines, so a `\r` report is seen live) and drains stdout on another; an unread pipe would block melt. `MeltProgressReader` keeps a line split across two chunks until its end arrives. The timeout kills the process and raises `TimeoutExpired`. The streaming path runs only when a progress callback is given; otherwise the render stays a single `subprocess.run`.

## Verification

`verify_render_output` keeps its checks (non-empty, ffprobe exit 0, a stream, positive finite duration) and adds:

- a `video` stream, unless the output is an audio container;
- an `audio` stream when the profile does not disable audio. Checked first: melt 7.42 writes an audio stream even for a timeline with no audio clips (silence), so this does not reject video-only timelines;
- not shorter than the timeline: the video stream's duration (falling back to the format's) must be at least `frames / fps - max(2 / fps, 0.5 %)`. Longer only logs (audio padding). A melt stopped at `out=24` of a 100-frame timeline exits 0 with a valid 1 s file; it is now `invalid_output`, "Render is shorter than the timeline: 1.00s of 4.00s", and the partial file is removed.
