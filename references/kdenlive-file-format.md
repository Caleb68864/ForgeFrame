# Kdenlive .kdenlive File Format -- Source Code Research

Research from Kdenlive source (invent.kde.org/multimedia/kdenlive).

## Required Root Attributes

```xml
<mlt LC_NUMERIC="C" producer="main_bin" version="7.x">
```

## Producer Required Properties

Every producer in the bin MUST have:
- `kdenlive:id` -- integer, sequential starting at 2, MUST be unique
- `kdenlive:uuid` -- braced UUID `{xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}`
- `kdenlive:clip_type` -- integer from ClipType::ProducerType enum:
  - 0 = Unknown
  - 1 = Audio
  - 2 = Video
  - 3 = AV (audio+video, e.g., avformat)
  - 4 = Color
  - 5 = Image
  - 6 = Text (kdenlivetitle)
  - 7 = SlideShow
  - 9 = Playlist
  - 15 = QML
  - 17 = Timeline
- `kdenlive:folderid` -- bin folder, `-1` for root

### mlt_service to clip_type mapping
- `avformat` / `avformat-novalidate` → 3 (AV)
- `kdenlivetitle` → 6 (Text)
- `color` → 4 (Color)
- `qimage` / `pixbuf` → 5 (Image)
- `xml` / `consumer` → 9 (Playlist)
- audio-only → 1 (Audio)

## Main Bin Playlist

```xml
<playlist id="main_bin">
  <property name="kdenlive:docproperties.version">1.1</property>
  <property name="kdenlive:docproperties.profile">atsc_1080p_30</property>
  <property name="kdenlive:docproperties.uuid">{project-uuid}</property>
  <entry producer="clip0"/>
  <entry producer="clip1"/>
  <!-- ALL producers must be listed here -->
</playlist>
```

Clips in timeline NOT in main_bin → "Project corrupted" error.

## Track Structure (from av.kdenlive fixture)

Each "track" in the master tractor is actually a **sub-tractor** wrapping a playlist pair:

```xml
<!-- Sub-tractor for one audio track -->
<tractor id="tractor0">
  <track producer="playlist0"/>      <!-- content -->
  <track producer="playlist1"/>      <!-- pair (empty) -->
  <filter>
    <property name="mlt_service">volume</property>
    <property name="internal_added">237</property>
  </filter>
  <filter>
    <property name="mlt_service">panner</property>
    <property name="internal_added">237</property>
  </filter>
</tractor>

<!-- Master tractor references sub-tractors -->
<tractor id="main_timeline">
  <track producer="black_track" hide="video"/>
  <track producer="tractor0" hide="video"/>     <!-- audio track -->
  <track producer="tractor2" hide="audio"/>     <!-- video track -->
  <!-- Internal transitions reference master tractor indices -->
</tractor>
```

Audio tracks: `hide="video"` (show audio only)
Video tracks: `hide="audio"` (show video only)

## Track Index Numbering

Master tractor index 0 = black_track (always). User tracks start at index 1.
`getTrackMltIndex()`: "Because of the black track that we insert in first position, the mlt index is the position + 1."

## Internal Transitions (REQUIRED per content track)

Audio tracks:
```xml
<transition>
  <property name="mlt_service">mix</property>
  <property name="a_track">0</property>
  <property name="b_track">{master_tractor_index}</property>
  <property name="always_active">1</property>
  <property name="sum">1</property>
  <property name="internal_added">237</property>
</transition>
```

Video tracks:
```xml
<transition>
  <property name="mlt_service">frei0r.cairoblend</property>
  <property name="a_track">0</property>
  <property name="b_track">{master_tractor_index}</property>
  <property name="always_active">1</property>
  <property name="internal_added">237</property>
</transition>
```

`internal_added=237` marks Kdenlive-managed transitions. Without it, they're treated as user compositions.

## User Compositions (dissolves, wipes)

- `b_track` = track the composition lives on
- `a_track` = track it composites WITH
- **a_track MUST NOT equal b_track** (assertion in source: `Q_ASSERT(trackId != getCurrentTrackId())`)
- Same-track dissolves use `kdenlive:mixcut` mechanism, NOT luma transitions

## Validation Code Path (kdenlivedoc.cpp Open())

1. Parse XML
2. `DocumentValidator::isProject()` -- checks `<mlt>` root
3. `DocumentValidator::validate()` -- version upgrades
4. `DocumentChecker::hasErrorInProject()` -- validates media, finds orphans
5. `checkOrphanedProducers()` -- removes unreferenced producers
