# Kdenlive audio fade pattern (`volume` filter inside the entry)

Audio fade-in / fade-out in Kdenlive 25.x is a `<filter mlt_service="volume">` child of the playlist `<entry>` element. Verified against `audio-mix.kdenlive` from the KDE Kdenlive test suite. The legacy opaque-XML form our patcher used to emit (with `level="0=0;duration=1"` keyframe-style ramps at document root) is rejected by Kdenlive's bin loader and silently dropped.

## Producer-level vs entry-level — entry wins

The fade lives on the playlist `<entry>` (the clip use), not on the `<chain>` (the bin clip). This means:

- Different entries of the same source clip can have different fade settings.
- Removing the entry removes the fade automatically; nothing else has to be cleaned up.
- The bin chain is untouched, so the bin clip still represents the unfaded source.

## Fade-in shape

```xml
<entry in="00:00:00.000" out="<entry-end>" producer="<chain-id>">
  <filter id="audiofade_in_..." out="<fade-end-frame>">
    <property name="window">75</property>
    <property name="max_gain">20dB</property>
    <property name="mlt_service">volume</property>
    <property name="kdenlive_id">fadein</property>
    <property name="gain">0</property>
    <property name="end">1</property>
    <property name="kdenlive:collapsed">0</property>
  </filter>
</entry>
```

- Filter `out` attribute = last frame of the fade (entry-local). No `in` attribute means the fade starts at frame 0.
- `gain` = volume multiplier at the start of the fade window (0 = silent).
- `end` = volume multiplier at the end of the fade window (1 = full volume).
- MLT interpolates linearly from `gain` to `end` across `[in,out]`.

## Fade-out shape

```xml
<entry in="00:00:00.000" out="<entry-end>" producer="<chain-id>">
  <filter id="audiofade_out_..." in="<fade-start-frame>" out="<entry-end-frame>">
    <property name="window">75</property>
    <property name="max_gain">20dB</property>
    <property name="mlt_service">volume</property>
    <property name="kdenlive_id">fadeout</property>
    <property name="gain">1</property>
    <property name="end">0</property>
    <property name="kdenlive:collapsed">0</property>
  </filter>
</entry>
```

- Both `in` and `out` are set, positioning the fade window at the tail of the entry.
- `gain=1` (full volume) → `end=0` (silent).

## Critical contract details

1. **NOT a keyframe string**. The `gain`/`end` are scalar floats, NOT `"frame=value;frame=value"` keyframe ramps like `qtblend` `rect`. MLT's `volume` service interpolates internally.
2. **Filter `in`/`out` are XML element attributes**, not `<property>` children. The serializer's `EntryFilter.in_frame` / `out_frame` fields map to these attributes.
3. **Frame indices are entry-local**, not absolute sequence frames. Fade-in starts at frame 0 of the entry; fade-out ends at the entry's final frame.
4. **`kdenlive_id` is the discriminator**: `fadein` or `fadeout`. The semantically-correct `gain`/`end` pair (`0`→`1` for in, `1`→`0` for out) must agree with the `kdenlive_id` -- mismatching them works in MLT but the Kdenlive UI shows the wrong fade direction.
5. **`window=75`, `max_gain=20dB`** are the standard volume-filter parameters. Kdenlive writes them on every audio fade; omitting them probably still works but matching is safer.

## Implementation in this repo

- Model: `EntryFilter.in_frame` / `EntryFilter.out_frame` (added with this pattern). The serializer writes them as element attributes.
- Patcher: `_apply_audio_fade()` constructs an `EntryFilter` with the right shape and appends it to the entry's `filters` list. No more opaque-XML emission.
- Smoke output: `tests/integration/test_v25_kdenlive_smoke_8.py` writes 025-audio-fade-in-out and 026-audio-fade-in-music-bed.

## Sources

- KDE Kdenlive test suite: https://raw.githubusercontent.com/KDE/kdenlive-test-suite/master/projects/audio-mix.kdenlive
- Kdenlive `dev-docs/fileformat.md`: https://github.com/KDE/kdenlive/blob/master/dev-docs/fileformat.md

## Related

- [[kdenlive-image-and-qtblend-pattern]] — the qtblend transform also uses entry-level filters but with keyframe-string-based parameters.
- [[external-kdenlive-examples-survey]] — the broader backlog this fix came from.
