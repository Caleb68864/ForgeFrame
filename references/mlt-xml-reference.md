# MLT XML Reference -- Filters, Transitions, and Document Structure

## Document Hierarchy

```
<mlt>
  <producer id="..." />        <!-- media source -->
  <playlist id="..." />        <!-- sequence of entries -->
  <tractor id="...">           <!-- multi-track composition -->
    <multitrack>
      <track producer="..." /> <!-- reference to playlist/producer -->
    </multitrack>
    <filter ... />             <!-- effects applied to tracks -->
    <transition ... />         <!-- compositions between tracks -->
  </tractor>
</mlt>
```

## Filter Element

Filters apply effects to tracks within a tractor. They are children of the `<tractor>` element, placed after `<multitrack>`.

### Structure

```xml
<filter id="filter0">
  <property name="track">0</property>
  <property name="mlt_service">greyscale</property>
</filter>
```

Or using attributes:
```xml
<filter id="filter0" mlt_service="greyscale" track="0"/>
```

### Key Properties

| Property | Description |
|----------|-------------|
| `mlt_service` | Identifies the filter implementation (e.g., `greyscale`, `volume`, `brightness`) |
| `track` | Zero-based track index this filter applies to |
| `in` / `out` | Optional frame range the filter is active (omit for full duration) |

### Adding Custom Properties

Effect parameters are added as `<property>` children:
```xml
<filter id="effect_0_0_brightness" mlt_service="brightness" track="0">
  <property name="av.brightness">0.1</property>
</filter>
```

## Transition Element

Transitions compose two tracks over a frame range. They are also children of `<tractor>`, placed after filters.

### Structure

```xml
<transition id="transition0" in="50" out="74">
  <property name="a_track">0</property>
  <property name="b_track">1</property>
  <property name="mlt_service">luma</property>
</transition>
```

Or using attributes:
```xml
<transition mlt_service="luma" in="25" out="49" a_track="0" b_track="1"/>
```

### Key Properties

| Property | Description |
|----------|-------------|
| `mlt_service` | Transition type: `luma` (wipe/dissolve), `composite` (PiP), `mix` (audio crossfade) |
| `a_track` | First (lower) track index |
| `b_track` | Second (upper) track index |
| `in` | Start frame |
| `out` | End frame |

### Common Transition Types

| mlt_service | Description | Extra Properties |
|-------------|-------------|-----------------|
| `luma` | Dissolve or wipe between tracks | `resource` (empty = dissolve, path to .pgm = wipe pattern) |
| `composite` | Picture-in-picture overlay | `geometry` (`"x/y:wxh:opacity"`, e.g., `"1420/790:480x270:100"`) |
| `mix` | Audio crossfade | `start` (begin level), `end` (end level) |

### Dissolve Example (no resource = pure dissolve)

```xml
<transition mlt_service="luma" in="50" out="74">
  <property name="a_track">0</property>
  <property name="b_track">1</property>
  <property name="resource"></property>
</transition>
```

### Wipe Example (with luma pattern)

```xml
<transition mlt_service="luma" in="50" out="74">
  <property name="a_track">0</property>
  <property name="b_track">1</property>
  <property name="resource">/usr/share/kdenlive/lumas/HD/luma01.pgm</property>
</transition>
```

### PiP Composite Example

```xml
<transition mlt_service="composite" in="0" out="150">
  <property name="a_track">0</property>
  <property name="b_track">1</property>
  <property name="geometry">1420/790:480x270:100</property>
</transition>
```

## Playlist Element

```xml
<playlist id="playlist0">
  <entry producer="producer0" in="0" out="2999"/>
  <blank length="1000"/>
  <entry producer="producer1" in="0" out="999"/>
</playlist>
```

## Complete Example

```xml
<mlt>
  <producer id="producer0">
    <property name="resource">clip1.mp4</property>
  </producer>
  <producer id="producer1">
    <property name="resource">clip2.mp4</property>
  </producer>
  <playlist id="playlist0">
    <entry producer="producer0" in="0" out="2999"/>
  </playlist>
  <playlist id="playlist1">
    <blank length="2950"/>
    <entry producer="producer1" in="0" out="999"/>
  </playlist>
  <tractor id="tractor0">
    <multitrack>
      <track producer="playlist0"/>
      <track producer="playlist1"/>
    </multitrack>
    <filter mlt_service="greyscale">
      <property name="track">0</property>
    </filter>
    <transition in="50" out="74">
      <property name="a_track">0</property>
      <property name="b_track">1</property>
      <property name="mlt_service">luma</property>
    </transition>
    <transition in="50" out="74">
      <property name="a_track">0</property>
      <property name="b_track">1</property>
      <property name="mlt_service">mix</property>
      <property name="start">0.0</property>
      <property name="end">1.0</property>
    </transition>
  </tractor>
</mlt>
```

---

**Sources:**
- [MLT XML Document](https://www.mltframework.org/docs/mltxml/)
- [MLT XML DTD](https://github.com/mltframework/mlt/blob/master/src/modules/xml/mlt-xml.dtd)
- [MLT Framework Documentation](https://www.mltframework.org/docs/framework/)
