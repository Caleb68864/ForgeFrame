# auto-editor cut list

ForgeFrame runs the auto-editor CLI and reads its timeline v3 JSON, then renders with ffmpeg or builds its own timeline. Checked against 29.3.1 on 2026-11-02.

## The v3 schema

`--export json` is rejected ("Unknown export format: json"). Use `--export v3`, which forces the extension: `-o out.json` actually writes `out.v3`.

```json
{"version": "3", "timebase": "30/1",
 "v": [[{"name": "video", "src": "/abs/in.mp4", "start": 0, "dur": 51, "offset": 0, "stream": 0},
        {"name": "video", "src": "/abs/in.mp4", "start": 51, "dur": 51, "offset": 99, "stream": 0}]],
 "a": [[]]}
```

Units are timebase frames. `offset` is the source in-frame, `dur` the length and `start` the timeline position. A keep-range is `offset/timebase` to `(offset+dur)/timebase`, so the example keeps 0-1.7 s and 3.3-5.0 s. An audio-only input has `"v": []`, so read the first non-empty layer of `v`, then of `a`.

## Conversions

`--edit audio:threshold=` takes a linear 0..1 value: `10 ** (dB / 20)`, so -30 dB is 0.0316. Its default 0.04 is about -28 dB. `--margin` is the padding. Nothing maps to ForgeFrame's `min_silence`, so that parameter is ignored by this engine.

## The binary is downloaded on first run

`pip install auto-editor` installs only a launcher. Its first run downloads a native binary into `site-packages/auto_editor/bin/` and prints progress to stdout. Linux builds exist for x86_64 only. The adapter looks for that binary, or a system install when the package is absent, and never runs the launcher, because that would start a download. `auto` falls back to ffmpeg when no binary is present.

## Why the Kdenlive export is not imported

`--export kdenlive` bypasses the serializer's rules, and ForgeFrame could not then edit the result the way it edits its own. Headless experiment on `test_audio_with_silence.mp4`, 2026-11-02: `kdenlive --render` rc 0 with a 3.456 s output, `melt` rc 0. It writes the native 26.x shape (per-track chains, `kdenlive:audio_track`, timecode in/out), so it does load. It has not been opened in the GUI.

## Measured

`test_audio_with_silence.mp4`, 5.0 s long with silence from 1.5 to 3.5 s, source mean -23.3 dB:

| Engine | Keep-ranges (s) | Output | Mean volume |
| --- | --- | --- | --- |
| ffmpeg | 0-1.699917, 3.300062-5.0 | 3.40 s | -21.6 dB |
| auto-editor 29.3.1 | 0-1.7, 3.3-5.0 | 3.40 s | -21.6 dB |
