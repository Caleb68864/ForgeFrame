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
| 05 audio fade | match (PSNR 36.59) | Measured 2026-11-02 at -24.7 dB in both. First 0.5 s -35.6 dB, seconds 2-3 -24.1 dB, in both renderers. |
| 06 gblur | match (PSNR 36.65) | Measured 2026-11-02: blurred in both, rc 0. Edge energy 0.72 without the effect, 0.50 with it. |
| 07 title | match (PSNR 43.19) | Measured 2026-11-02, rc 0. |

Defects found in the generated XML (06_effect_blur.kdenlive):

1. **Audio lost.** `clip_insert` leaves `playlist_audio` empty and the video
   track carries `hide="audio"`, so inserted clips are silent in both renderers
   (mean volume -91 dB). The audio fade lands on the video entry where it is muted.
2. ~~**`kdenlive:id` 3 used by a media clip** (`b_blue`) -- reserved for the main
   sequence (CLAUDE.md hard rule 9).~~ **Fixed 2026-10-14:** generated user clip
   IDs start at 4 and the main sequence uses 3.
3. ~~**`main_bin` entries have `out="0"`** (hard rule 5 expects `length-1`).~~
   **Fixed 2026-10-14:** the serializer emits each media entry through its
   effective producer length; the sequence entry remains `out="0"` by design.
4. ~~**Timeline `<entry>` elements carry no `kdenlive:id` property** (hard rule 7).~~
   **Fixed 2026-10-14:** every modelled timeline use carries the bin clip ID as
   its first property; preserved native producers use their stored ID.
5. ~~**The timewarp variant is registered in `main_bin`** with its own id.~~
   **Fixed 2026-10-14:** speed and timeremap variants share the base clip ID and
   are omitted from `main_bin`.
6. **Fixed 2026-10-14.** `effect_add` and other clip-filter builders resolve Kdenlive's registry id. A missing id is omitted, and unknown ids are normalized or removed by the serializer safety net.

The differential is automated in `tests/integration/external/test_kdenlive_differential.py`. All 21 cases pass as of 2026-11-02; the earlier "host binaries abort" blocker no longer reproduces (MLT 7.42, Kdenlive 26.08.2). A GUI pass over the pack is still outstanding (prompt 06 Part A).

## Addendum 2026-11-02: Kdenlive audio was still silent

Defect 1's fix made melt audible, but `kdenlive --render` stayed at -91 dB on every step, against -24.1 dB in melt. `test_audio_audible` failed all seven steps. Kdenlive recognises an audio track by `kdenlive:audio_track=1`, not by `hide="video"` lanes, so our audio track loaded as a video track. Marking it exposed a second defect: a `timewarp` producer shared by an audio and a video track loads with both streams disabled on its second use, so the dissolve's video went black (PSNR 17). The serializer now marks audio tracks and emits a per-track copy of such producers.

| Step | PSNR | Frames K/M | Mean volume K/M (dB) |
| --- | --- | --- | --- |
| 01 single clip | 35.20 | 100/100 | -24.1 / -24.1 |
| 02 two clips | 37.41 | 200/200 | -24.1 / -24.1 |
| 03 speed 2x | 36.54 | 150/150 | -24.1 / -24.1 |
| 04 dissolve | 36.59 | 126/126 | -24.1 / -24.1 |
| 05 audio fade | 36.59 | 126/126 | -24.7 / -24.7 |
| 06 gblur | 36.65 | 126/126 | -24.7 / -24.7 |
| 07 title | 43.19 | 126/126 | -24.7 / -24.7 |

The prompt 05 generated `03_speed.kdenlive` has `a_bars` ID 4 and `b_blue`
ID 5 in `main_bin`; `b_blue_tw2` is absent there, carries ID 5, and its
timeline entries carry ID 5 as their first property. Its emitted resource is
still `2:<path>`. The required post-fix Kdenlive rebuilt-playlist capture could
not be collected: `timeout 300 xvfb-run -a kdenlive --render ...` aborted with
exit 1 before producing a rebuilt MLT file. Before the fix, Kdenlive 26.08.2
rebuilt the variant as a separate bin clip and mangled its resource by
prefixing the project root. Whether removing it from `main_bin` prevents that
behavior remains unverified on this host.
