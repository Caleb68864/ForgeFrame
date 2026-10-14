# Kdenlive 26.08 differential check (2026-10-13)

Method: `scripts/kdenlive_check_pack.py` builds 7 cumulative projects through the
real MCP tools (clip_insert x2, clip_speed, transitions_apply_between, audio_fade,
effect_add avfilter.gblur, title_card_add). Each is rendered twice:
`melt <project>` (what ForgeFrame's own renderer sees) and
`xvfb-run -a kdenlive --render <project> out.mp4` (Kdenlive 26.08.2's headless
loader + `kdenlive_render`). Frames/audio are compared.

| Step | Kdenlive vs melt | Finding |
| --- | --- | --- |
| 01 single clip | match (PSNR 36) | ok |
| 02 two clips | match (PSNR 38) | ok |
| 03 speed 2x | match, 6.0 s | ok (timewarp honoured) |
| 04 dissolve | **differs** (PSNR 28) | melt blends at 3.6 s, Kdenlive hard-cuts. Not dropped: hidden under the left clip (`a_track=0`, planted after the compositors) and the left clip ran past its media. **Fixed 2026-10-14** -- both now render the same full dissolve (PSNR 36.6). |
| 05 audio fade | Not measured (melt aborts rc -6; Kdenlive aborts rc 1) | Renderers could not produce outputs on this host; audio pairing/fade are covered by unit checks, but real-render levels remain unverified. |
| 06 gblur | **differs** (PSNR 25) | melt blurs, Kdenlive renders sharp: **entry filter dropped by Kdenlive** |
| 07 title | match | title renders in Kdenlive |

Defects found in the generated XML (06_effect_blur.kdenlive):

1. **Audio lost.** `clip_insert` leaves `playlist_audio` empty and the video
   track carries `hide="audio"`, so inserted clips are silent in both renderers
   (mean volume -91 dB). The audio fade lands on the video entry where it is muted.
2. **`kdenlive:id` 3 used by a media clip** (`b_blue`) -- reserved for the main
   sequence (CLAUDE.md hard rule 9).
3. **`main_bin` entries have `out="0"`** (hard rule 5 expects `length-1`).
4. **Timeline `<entry>` elements carry no `kdenlive:id` property** (hard rule 7).
5. **The timewarp variant is registered in `main_bin`** with its own id (the
   vault speed pattern keeps the bin clip unchanged).
6. **`effect_add` filter lacks Kdenlive effect identity** (`kdenlive_id`, etc.);
   Kdenlive drops it on load.

`kdenlive --render` does not report any of this (rc 0); only the render
differential exposes it. Next: turn the differential into a `requires_kdenlive`
external test and fix the serializer/intents against Kdenlive 26.08 until every
step matches. A GUI pass over the pack is still needed for load dialogs.
