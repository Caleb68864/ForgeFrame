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
| 06 gblur | Not measured (Kdenlive aborts; `xvfb-run` rc 1; melt process rc -6, `xvfb-run` rc 1) | `kdenlive_id=avfilter.gblur` is now emitted and captured in the check-pack project; render comparison remains blocked by the host binaries |
| 07 title | Not measured (Kdenlive aborts; `xvfb-run` rc 1; melt process rc -6, `xvfb-run` rc 1) | Existing title differential check remains enabled; render comparison remains blocked by the host binaries |

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

The differential is automated in `tests/integration/external/test_kdenlive_differential.py`. Real render comparisons for steps 05-07 remain unavailable on this host because Kdenlive and melt abort. A GUI pass over the pack is still needed for load dialogs.

The prompt 05 generated `03_speed.kdenlive` has `a_bars` ID 4 and `b_blue`
ID 5 in `main_bin`; `b_blue_tw2` is absent there, carries ID 5, and its
timeline entries carry ID 5 as their first property. Its emitted resource is
still `2:<path>`. The required post-fix Kdenlive rebuilt-playlist capture could
not be collected: `timeout 300 xvfb-run -a kdenlive --render ...` aborted with
exit 1 before producing a rebuilt MLT file. Before the fix, Kdenlive 26.08.2
rebuilt the variant as a separate bin clip and mangled its resource by
prefixing the project root. Whether removing it from `main_bin` prevents that
behavior remains unverified on this host.
