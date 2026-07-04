# Per-track tractor pattern

Each timeline track in Kdenlive 25.x is its own `<tractor>` element wrapping two `<playlist>` children — an "A" content playlist and a "B" empty paired playlist used for mix transitions. The flat MLT shape (one tractor with N tracks pointing directly at playlists) does not work; Kdenlive's timeline parser expects per-track tractors.

## Shape

```xml
<!-- Track A playlist -- carries the actual <entry> clips -->
<playlist id="<track-id>">
  <entry producer="<clip-id>" in="0" out="148"/>
  ...
</playlist>

<!-- Track B playlist -- always empty; exists for mix-transition support -->
<playlist id="<track-id>_kdpair"/>

<!-- Per-track tractor wrapping the pair -->
<tractor id="tractor_track_<track-id>" in="0" out="<frames-1>">
  <property name="kdenlive:trackheight">89</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <property name="kdenlive:track_name">Video</property>     <!-- optional -->
  <track producer="<track-id>"        hide="audio"/>        <!-- video tracks -->
  <track producer="<track-id>_kdpair" hide="audio"/>
  <!-- Audio track tractors add three internal filters here. -->
</tractor>
```

## Hide attribute = track type discriminator

The `<track hide="...">` attribute on the per-track tractor's sub-tracks encodes the track type:

| Track type | `hide` value on both sub-tracks |
|---|---|
| Video track | `audio` (hide audio output, keep video) |
| Audio track | `video` (hide video output, keep audio) |

The parser uses `hide` to recover `Track.track_type` on read-back.

## Audio tracks: required internal filters

Every audio per-track tractor must carry three filters with `internal_added=237`:

```xml
<filter id="...">
  <property name="window">75</property>
  <property name="max_gain">20dB</property>
  <property name="channel_mask">-1</property>
  <property name="mlt_service">volume</property>
  <property name="internal_added">237</property>
  <property name="disable">1</property>
</filter>
<filter ...>
  <property name="channel">-1</property>
  <property name="mlt_service">panner</property>
  <property name="internal_added">237</property>
  <property name="start">0.5</property>
  <property name="disable">1</property>
</filter>
<filter ...>
  <property name="iec_scale">0</property>
  <property name="mlt_service">audiolevel</property>
  <property name="dbpeak">1</property>
  <property name="disable">1</property>
</filter>
```

`internal_added=237` flags these as "Kdenlive-managed, do not show to user" — Kdenlive injects them on save; without them the audio engine logs warnings.

The same trio also belongs on the main sequence tractor (one set, not per-audio-track).

## Wiring into the main sequence

The main sequence tractor lists each per-track tractor as a `<track>` child:

```xml
<tractor id="{<sequence-uuid>}" ...>
  <track producer="black_track" hide="video"/>
  <track producer="tractor_track_<v1-id>"/>
  <track producer="tractor_track_<a1-id>"/>
  ...
  <transition mlt_service="qtblend" a_track="0" b_track="1" .../>   <!-- video composites -->
  <transition mlt_service="mix"     a_track="0" b_track="2" sum="1" .../>  <!-- audio mixes -->
</tractor>
```

`a_track="0"` always points at the black background; `b_track` is the 1-based index of the per-track tractor in the sequence's track list.

## Parser considerations

A tractor at root level can be one of four classes:
- **`per_track`**: id starts with `tractor_track_`, *or* has exactly two `<track>` children where one of them references a `*_kdpair` playlist
- **`sequence`**: id is a UUID, *or* carries `kdenlive:uuid` property
- **`project`**: carries `kdenlive:projectTractor=1`
- **`legacy`**: anything else (the old flat single-tractor shape)

The classifier lives in `parser.py::_classify_tractor`. Without it, the parser would treat every tractor identically and lose track-type information.

## Sources

- Reference: `tests/fixtures/kdenlive_references/single_clip_kdenlive_native.kdenlive` — tractors 0/1 (audio) at lines 20-87 and 2/3 (video) at lines 155-174.

## Related

- [[kdenlive-25-document-shape]]
- [[kdenlive-twin-chain-pattern]]
