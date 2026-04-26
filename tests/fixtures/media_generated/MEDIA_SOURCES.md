# Test media sources

Provenance of any test-fixture media that was downloaded from external
sources (vs generated locally by the `generate_test_*.sh` scripts).

## `greenscreen_reporter_720.mp4`

* **Source**: [Mixkit](https://mixkit.co/free-stock-video/female-reporter-reporting-with-microphone-in-hand-on-a-chroma-green-background-28293/)
* **Direct CDN URL** (saved 2026-04-26): `https://assets.mixkit.co/videos/28293/28293-720.mp4`
* **License**: [Mixkit License](https://mixkit.co/license/) -- free for commercial and non-commercial use, no attribution required, no watermark
* **Why**: smoke tests 054 (chroma key) and 055 (lumakey) need source footage with a clear green-screen subject so the keying effect is visibly verifiable.  None of the locally-generated test clips have green-screen content.
* **Properties**: 1280x720, 60 fps, ~20 seconds, 5.94 MB.

## Locally generated fixtures

The other files in this directory are produced by the `generate_*.sh`
scripts and are deterministic ffmpeg outputs (test patterns, silent
audio, etc.) rather than downloaded media.
