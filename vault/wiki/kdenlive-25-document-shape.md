# Kdenlive 25.x document shape

A `.kdenlive` file that Kdenlive 25.x will open is an MLT XML document with a very specific multi-tractor structure. Producing a flat single-tractor MLT (the obvious shape from the MLT docs) makes Kdenlive refuse the file or strip the timeline.

## The shape, in order

```
<mlt LC_NUMERIC="C" producer="main_bin" version="7">
  <profile description="HD 1080p 29.97 fps" width="1920" height="1080"
           frame_rate_num="30000" frame_rate_den="1001" .../>

  <chain id="<clip-id>"        out="<frames-1>"> ... </chain>      # timeline twin
  <chain id="<clip-id>_bin"    out="<frames-1>"> ...               # bin twin
    <property name="kdenlive:kextractor">1</property>
    <property name="kdenlive:monitorPosition">0</property>
  </chain>

  <producer id="black_track" in="0" out="<frames-1>">
    <property name="mlt_service">color</property>
    <property name="resource">black</property>
    <property name="kdenlive:playlistid">black_track</property>
    ...
  </producer>

  <playlist id="<track-id>"> entries... </playlist>                # track A
  <playlist id="<track-id>_kdpair"/>                               # track B (empty)
  <tractor id="tractor_track_<track-id>" in="0" out="<frames-1>">
    <track producer="<track-id>" hide="audio"/>                    # video tracks
    <track producer="<track-id>_kdpair" hide="audio"/>
  </tractor>                                                        # ...one per track

  <tractor id="{<sequence-uuid>}" in="0" out="<frames-1>">          # main sequence
    <property name="kdenlive:uuid">{<sequence-uuid>}</property>
    <property name="kdenlive:sequenceproperties.*">...</property>
    <property name="kdenlive:producer_type">17</property>
    <track producer="black_track" hide="video"/>
    <track producer="tractor_track_<id>"/>          # one per track tractor
    <transition mlt_service="qtblend" .../>         # one per video track
    <transition mlt_service="mix" .../>             # one per audio track
    <filter mlt_service="volume" internal_added="237"/>
    <filter mlt_service="panner" internal_added="237"/>
    <filter mlt_service="audiolevel" internal_added="237"/>
  </tractor>

  <playlist id="main_bin">
    <property name="kdenlive:docproperties.*">...</property>        # ~25 keys
    <property name="kdenlive:docproperties.uuid">{<sequence-uuid>}</property>
    <property name="kdenlive:docproperties.opensequences">{<sequence-uuid>}</property>
    <property name="kdenlive:docproperties.activetimeline">{<sequence-uuid>}</property>
    <property name="xml_retain">1</property>
    <entry producer="{<sequence-uuid>}" in="0" out="0"/>            # sequence
    <entry producer="<clip-id>_bin" in="0" out="<frames-1>"/>       # each bin twin
  </playlist>

  <tractor id="tractor_project" in="0" out="<frames-1>">            # project wrapper
    <property name="kdenlive:projectTractor">1</property>
    <track producer="{<sequence-uuid>}" in="0" out="<frames-1>"/>
  </tractor>
</mlt>
```

## Why each piece exists

- **Per-track tractors** — Kdenlive's timeline model treats each track as its own MLT tractor with two playlists (A/B for mix transitions). Without this, the timeline either renders as one fused track or fails to load.
- **Main sequence tractor with `kdenlive:uuid`** — Kdenlive's timeline opens this specific tractor; `main_bin` references it by UUID.
- **Project tractor wrapper (`kdenlive:projectTractor=1`)** — top-level MLT producer the renderer plays. Kdenlive looks for it explicitly.
- **Twin chains per media** — see [[kdenlive-twin-chain-pattern]] for why one isn't enough.
- **Internal audio filters** — every audio track tractor and the main sequence carry `volume`/`panner`/`audiolevel` filters with `internal_added=237`. Kdenlive injects these on save; without them the audio engine warns or mutes.

## Implementation in this repo

- Serializer: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/serializer.py`
- Parser (handles both legacy flat-tractor and v25 multi-tractor): `.../kdenlive/parser.py`
- Structural test: `tests/unit/test_kdenlive_v25_shape.py` (also asserts on `tests/fixtures/kdenlive_references/single_clip_kdenlive_native.kdenlive`)
- End-to-end smoke: `tests/integration/test_v25_kdenlive_smoke.py`

## Sources

- Reference: a real Kdenlive 25.08.3 / MLT 7.33.0 save at `tests/fixtures/kdenlive_references/single_clip_kdenlive_native.kdenlive`
- Cross-checked against KDE/kdenlive `master` (see [[kdenlive-bin-loader-source-pointers]])

## Related

- [[kdenlive-uuid-vs-control-uuid]] — the trap that breaks bin registration
- [[kdenlive-twin-chain-pattern]] — why each media file needs two `<chain>` elements
- [[kdenlive-per-track-tractor-pattern]] — per-track tractor wiring detail
- [[golden-fixture-testing]] — testing without launching Kdenlive
