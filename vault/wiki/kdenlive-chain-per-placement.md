# One producer per placement? (experiment, prompt 24)

Run 2026-11-22 with melt 7.42.0 and `kdenlive --render` (Kdenlive 26.08.x, under `xvfb-run`). Harness: `scripts/chain_placement_experiment.py` (variants built by post-processing serializer output in `tests/integration/external/_chain_layout.py`; the serializer was not changed).

## The claim

Another Kdenlive MCP project says Kdenlive's loader silently strips timeline clips when one media `<chain>` is referenced from more than one playlist, so every timeline placement must get its own chain (all sharing `kdenlive:control_uuid`, plus a bin chain). ForgeFrame does the opposite: one producer per media file, used by `main_bin` and every track and placement, with `length` raised to cover the largest out-point (hard rule 14).

## What Kdenlive's own saves show

- `tests/fixtures/kdenlive_references/cross_dissolve_native.kdenlive`: one media file on an audio track (`playlist0` -> `chain0`) and a video track (`playlist6` -> `chain2`): two `avformat-novalidate` chains with the same `kdenlive:id` (4) and `kdenlive:control_uuid`, plus a bin chain `chain3`.
- `multi_clip_and_title_native.kdenlive`: the same media on two tracks gets one chain per track (`chain0`, `chain1`, `kdenlive:id` 6) plus bin chain `chain5`.
- No native fixture places the same media twice on one track, so "per track" and "per placement" were not distinguished until this run.

## Scenarios and variants

Media: four 2 s solid segments (red, green, blue, white; 25 fps) plus a sine. S1 one A/V placement; S2 the same media twice on one track (source 0-49 then 100-149, red then blue); S2short the same with the shared producer's `length` forced to 50 (the rule-14 control); S3 frames 0-49 and 150-199 on two video tracks at once (the upper track, v2, wins: white); S4 one normal and one 2x (timewarp) placement. Variants: V0 shared (our output), V1 one clone per track, V2 one clone per placement, V1u / V2u the same plus one shared `kdenlive:control_uuid`. Clones cover only their own entries; the bin element keeps its length.

## Results

Colour at the middle of each placement, duration; audio was -24 dB in every render (-27 dB for melt S2short V0).

| Scenario | Variant | Expected | melt | kdenlive --render |
| --- | --- | --- | --- | --- |
| S1_av | V0 | red | ok: red; 2.01 s | ok: red; 2.01 s |
| S1_av | V1 | red | ok: red; 2.01 s | ok: red; 2.01 s |
| S1_av | V2 | red | ok: red; 2.01 s | ok: red; 2.01 s |
| S1_av | V1u | red | ok: red; 2.01 s | ok: red; 2.01 s |
| S1_av | V2u | red | ok: red; 2.01 s | ok: red; 2.01 s |
| S2_twice | V0 | red, blue | ok: red, blue; 4.01 s | ok: red, blue; 4.01 s |
| S2_twice | V1 | red, blue | ok: red, blue; 4.01 s | ok: red, blue; 4.01 s |
| S2_twice | V2 | red, blue | ok: red, blue; 4.01 s | **FAIL**: red, missing; 2.05 s |
| S2_twice | V1u | red, blue | ok: red, blue; 4.01 s | ok: red, blue; 4.01 s |
| S2_twice | V2u | red, blue | ok: red, blue; 4.01 s | **FAIL**: red, missing; 2.05 s |
| S2short_twice_len50 | V0 | red, blue | **FAIL**: red, black; 4.01 s | **FAIL**: red, missing; 2.05 s |
| S2short_twice_len50 | V1 | red, blue | ok: red, blue; 4.01 s | ok: red, blue; 4.01 s |
| S2short_twice_len50 | V2 | red, blue | ok: red, blue; 4.01 s | **FAIL**: red, missing; 2.05 s |
| S2short_twice_len50 | V1u | red, blue | ok: red, blue; 4.01 s | ok: red, blue; 4.01 s |
| S2short_twice_len50 | V2u | red, blue | ok: red, blue; 4.01 s | **FAIL**: red, missing; 2.05 s |
| S3_two_tracks | V0 | white | ok: white; 2.01 s | ok: white; 2.01 s |
| S3_two_tracks | V1 | white | ok: white; 2.01 s | ok: white; 2.01 s |
| S3_two_tracks | V2 | white | ok: white; 2.01 s | ok: white; 2.01 s |
| S3_two_tracks | V1u | white | ok: white; 2.01 s | ok: white; 2.01 s |
| S3_two_tracks | V2u | white | ok: white; 2.01 s | ok: white; 2.01 s |
| S4_speed | V0 | red, blue | ok: red, blue; 3.01 s | ok: red, blue; 3.01 s |
| S4_speed | V1 | red, blue | ok: red, blue; 3.01 s | ok: red, blue; 3.01 s |
| S4_speed | V2 | red, blue | ok: red, blue; 3.01 s | ok: red, blue; 3.01 s |
| S4_speed | V1u | red, blue | ok: red, blue; 3.01 s | ok: red, blue; 3.01 s |
| S4_speed | V2u | red, blue | ok: red, blue; 3.01 s | ok: red, blue; 3.01 s |

## Decision

**Claim refuted for rendering.** Our shared producer (V0) renders every placement correctly in Kdenlive for S1-S4. The layout the claim recommends, one producer per placement (V2/V2u), is the one that **loses** a clip in Kdenlive: the second placement of the same media on one track is missing and the render is 2 s short. Per track (V1/V1u, the shape Kdenlive saves) is also correct. Keep the shared producer; no serializer change.

**Rule 14 still holds in Kdenlive 26.08**: with the shared producer's `length` at 50 (S2short V0), Kdenlive drops the second placement (render 2.05 s) and melt renders it black. V1 clones that cover their own entries avoid it, which is why the per-track shape works.

## Pending: the GUI pass

`kdenlive --render` returns 0 even when it drops things, and it does not show dialogs. Open the files listed in `kdenlive-chain-experiment/CHECKLIST.md` (regenerate with the script) in Kdenlive 26.08, record any dialog, count clips per track and bin clips, and Save As `<name>_resaved.kdenlive`; then `--analyze-resaved` prints the layout Kdenlive rewrote each file into. Status: renders conclusive, GUI pass pending. The KDE source check (meltBuilder.cpp / projectclip.cpp) was not done.
