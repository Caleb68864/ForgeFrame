# FFmpeg audio adapter bugs surfaced by smoke testing

Three bugs uncovered while building
``tests/integration/test_audio_ffmpeg_smoke.py`` against the
``adapters/ffmpeg/audio.py`` module.  The first two are now fixed;
the third is documented but not yet remediated (it's a feature
shortfall rather than a hard failure).

## Bug 1: missing `-vn` on every audio function

**Symptom:** when input was a video file (``.mp4``) and output was
an audio container (``.wav``), ffmpeg failed with::

    Output file does not contain any stream
    Error opening output file ...
    Error opening output files: Invalid argument

**Root cause:** every audio-processing function in ``audio.py``
(``normalize_audio``, ``compress_audio``, ``remove_background_noise``,
``highpass_filter``, ``de_ess``, ``remove_silence``, ``limit_peaks``,
``convert_format``, ``export_compressed``) called ``run_ffmpeg`` with
``["-af", ...]`` but no ``-vn``.  ffmpeg's default stream selection
maps the best video and audio stream from the input.  WAV containers
can't carry video, so the muxer rejected the output before any
filtering happened.

Pure-audio inputs (``.mp3`` -> ``.wav``) worked because there was no
video stream to reject.  This masked the bug until a video-input
test was added.

**Fix:** prepend ``"-vn"`` to the args list in every audio function.
These functions are explicitly audio-only operations -- there's no
case where dropping video on read is wrong.

## Bug 2: `silenceremove` filter built with wrong separator

**Symptom:** every call to ``remove_silence`` failed with::

    Error parsing filterchain 'silenceremove:start_periods=1:...'

**Root cause:** the function built the filter string as::

    parts = ["silenceremove"]
    parts.append("start_periods=1:start_duration=0.5:start_threshold=-40dB")
    af = ":".join(parts)
    # -> "silenceremove:start_periods=1:..."

But ffmpeg's filter syntax requires ``=`` between the filter name
and its first option, not ``:``::

    silenceremove=start_periods=1:start_duration=0.5:start_threshold=-40dB

**Fix:** join the option groups with ``:``, then prepend
``"silenceremove="``::

    af = "silenceremove=" + ":".join(options)

The function had been broken from inception; no caller had verified
it actually produced output.

## Bug 3 (open): `normalize_audio` is single-pass loudnorm

**Symptom:** ``normalize_audio(target_lufs=-16.0)`` on
``music_cinematic_short.mp3`` produced an output measuring **-13.6
LUFS** when probed with ``ebur128`` -- 2.4 LU above the target.

**Root cause:** the function uses single-pass ffmpeg ``loudnorm``::

    -af loudnorm=I=-16:TP=-1.5:LRA=11

ffmpeg's documentation explicitly warns that single-pass loudnorm
applies *dynamic* loudness adjustment but doesn't hit the integrated
target accurately.  EBU R128 conformant normalization requires two
passes:

1. **Measurement pass** -- run loudnorm with ``print_format=json`` to
   measure ``input_i``, ``input_tp``, ``input_lra``, ``input_thresh``.
2. **Apply pass** -- run loudnorm again with those measurements
   passed back as ``measured_i``, ``measured_tp``, etc.

**Fix (deferred):** rewrite ``normalize_audio`` to do the two-pass
flow.  Worth doing before anyone relies on the function for true
broadcast/streaming-platform conformance.  Tracked here rather than
in code because the current single-pass behaviour is "close enough"
for many use cases and a rewrite would change the function
signature/timing characteristics.

## Why these were missed by existing tests

There were no integration tests for the audio adapter prior to
``test_audio_ffmpeg_smoke.py``.  Unit tests around the runner used
mock subprocesses and never invoked real ffmpeg, so neither the
filter-syntax bug nor the missing ``-vn`` was exercised.

## Lesson for future adapters

Any ffmpeg adapter function that builds a filter string from
parameters MUST have an integration test that:

1. Runs against a real input fixture (audio for audio adapters,
   video for video adapters).
2. Verifies the output exists and is non-empty.
3. Where a parameter has a measurable target (LUFS, sample rate,
   duration), uses ``ffprobe`` or an analysis filter to confirm the
   target was hit -- not just "ffmpeg returned 0".

The structural assertion ("file exists, non-zero bytes") catches
syntax bugs and missing flags but doesn't catch incorrect
parameter mappings (e.g. the loudnorm two-pass shortfall).

## Related

- [[kdenlive-smoke-test-visible-values]] -- the analogous lesson on
  the kdenlive side (subtle parameter values can't be visually
  distinguished from a no-op)
- ``tests/integration/test_audio_ffmpeg_smoke.py`` -- the smoke
  suite added during this debugging session
