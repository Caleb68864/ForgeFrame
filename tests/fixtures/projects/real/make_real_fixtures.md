# Regenerating the real-Kdenlive round-trip fixtures

`test_kdenlive_fixture_roundtrip.py` parses projects saved by **actual
Kdenlive**, re-serializes them with our serializer, and asserts no element loss
plus melt-acceptance. Those fixtures cannot be hand-authored -- they must be
captured from a real Kdenlive install so they carry the true document format
(`kdenliveversion`, entry-nested `<filter>` clip effects, guides in
`kdenlive:docproperties.guides`, paired playlists, etc.).

This directory (`tests/fixtures/projects/real/`) is empty on purpose; the
round-trip test skips until it is populated. Drop `*.kdenlive` files here to
activate it.

## Procedure

Capture on at least two Kdenlive versions (e.g. 24.12 and a 25.x) so a
document-format bump becomes a fixture drop-in. For each version, build and save
these six scenarios as separate `.kdenlive` files:

1. `empty_<ver>.kdenlive` -- new empty project, default profile, saved as-is.
2. `clip_effects_<ver>.kdenlive` -- one clip with 2-3 stacked clip effects
   (e.g. Lift/Gamma/Gain, blur). This is the entry-nested `<filter>` case §1.2
   is about.
3. `keyframed_<ver>.kdenlive` -- one clip with a keyframed Transform (position
   or opacity) so animated properties are represented.
4. `same_track_mix_<ver>.kdenlive` -- two clips on one track with a same-track
   mix (crossfade) between them.
5. `subtitle_<ver>.kdenlive` -- a project with a subtitle track and at least one
   subtitle event.
6. `multi_sequence_<ver>.kdenlive` -- two sequences (multi-tractor), if the
   version supports it.

Use only the built-in `color`/title producers or clips that point at media
under the repo so the files are self-contained; avoid absolute paths to
personal media (edit the `resource` to a relative/placeholder path if needed --
the round-trip test does not render media, only structure + melt-load).

## Naming

`{scenario}_{kdenliveversion}.kdenlive`, e.g. `clip_effects_2412.kdenlive`. The
test parametrizes over every `*.kdenlive` file it finds here.

## What the test checks

- parse is non-empty (guards `parse_project` swallowing errors, evidence #6),
- `<filter>` count after round-trip >= before (no entry-nested effect loss),
- the round-tripped file still loads in `melt`.
