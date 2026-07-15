#!/usr/bin/env python3
"""Generate 3 candidate repaired copies of smoke_test_full.kdenlive.

Each tests a distinct hypothesis about why Kdenlive 26.04.2 strips the clips.
All must still load in melt (verified separately).
"""
from pathlib import Path

WC = Path("/home/caleb/Projects/ForgeFrame/smoke-test/smoke-test-video/"
          "projects/working_copies")
CAND = WC / "candidates"
ORIG = (WC / "smoke_test_full.kdenlive").read_text()

# Deterministic ids from the original file
SEQ_UUID = "{03deb14e-cbfa-5108-9886-d52292128241}"
MEDIA = [
    # (producer id, resource, length, kdenlive:id, control_uuid == kdenlive:uuid)
    ("producer0",
     "/home/caleb/Projects/ForgeFrame/smoke-test/smoke-test-video/media/raw/clip_intro.mp4",
     250, 2, "{0e597a2b-67d8-5afa-92a4-72834c4bc6d3}"),
    ("producer1",
     "/home/caleb/Projects/ForgeFrame/smoke-test/smoke-test-video/media/raw/clip_step1.mp4",
     375, 3, "{7c84a0d8-682f-536e-8580-3dbe43fb5c23}"),
    ("producer2",
     "/home/caleb/Projects/ForgeFrame/smoke-test/smoke-test-video/media/raw/clip_closeup.mp4",
     200, 4, "{20fcd154-644f-55bb-934e-cb43ec88a194}"),
]

# underscore -> dot effect-id repairs (repository keys on dot form)
EFFECT_ID_FIX = {
    'kdenlive_id">avfilter_exposure<': 'kdenlive_id">avfilter.exposure<',
    'kdenlive_id">frei0r_glitch0r<': 'kdenlive_id">frei0r.glitch0r<',
    'kdenlive_id">frei0r_pixeliz0r<': 'kdenlive_id">frei0r.pixeliz0r<',
    'kdenlive_id">frei0r_rgbsplit0r<': 'kdenlive_id">frei0r.rgbsplit0r<',
    'kdenlive_id">frei0r_scanline0r<': 'kdenlive_id">frei0r.scanline0r<',
}


def fix_effect_ids(text: str) -> str:
    for u, d in EFFECT_ID_FIX.items():
        text = text.replace(u, d)
    return text


def add_control_uuid(text: str) -> str:
    """Insert kdenlive:control_uuid after each producer's kdenlive:uuid."""
    for _pid, _res, _len, _kid, cu in MEDIA:
        needle = (f'<property name="kdenlive:uuid">{cu}</property>')
        repl = (needle +
                f'\n    <property name="kdenlive:control_uuid">{cu}'
                f'</property>')
        text = text.replace(needle, repl)
    return text


# ---------------------------------------------------------------------------
# Candidate A: minimal - control_uuid + dot-form effect ids only.
#   Hypothesis: the ONLY corruption causes are (1) missing kdenlive:control_uuid
#   on bin producers (binIdCorresp is keyed by control_uuid) and (2) underscore
#   effect ids. Legacy single-tractor timeline is tolerated by 26.04's importer.
# ---------------------------------------------------------------------------
a = add_control_uuid(fix_effect_ids(ORIG))
# also give the orphan user transition a resolvable kdenlive_id
a = a.replace(
    '<transition mlt_service="frei0r.cairoblend">\n'
    '    <property name="a_track">0</property>',
    '<transition mlt_service="frei0r.cairoblend">\n'
    '    <property name="kdenlive_id">frei0r.cairoblend</property>\n'
    '    <property name="a_track">0</property>')
(CAND / "smoke_test_full_candA_control_uuid.kdenlive").write_text(a)

# ---------------------------------------------------------------------------
# Candidate C: A + promote the legacy tractor0 into a REGISTERED sequence
#   (uuid/control_uuid/producer_type/sequenceproperties), main_bin sequence
#   entry + Sequences folder + opensequences/activetimeline, and a
#   projectTractor wrapper - but KEEP the flat playlist-as-track structure.
#   Hypothesis: sequence *registration* (not the nested track-tractor lanes)
#   is what 26.04 needs on top of A.
# ---------------------------------------------------------------------------
c = a
# 1. rename the legacy tractor's element id to the sequence uuid (so the
#    main_bin entry + projectTractor references resolve) and attach sequence
#    properties.
c = c.replace(
    '<tractor id="tractor0" in="0" out="824">',
    f'<tractor id="{SEQ_UUID}" in="0" out="824">\n'
    f'    <property name="kdenlive:uuid">{SEQ_UUID}</property>\n'
    f'    <property name="kdenlive:control_uuid">{SEQ_UUID}</property>\n'
    f'    <property name="kdenlive:clipname">Sequence 1</property>\n'
    f'    <property name="kdenlive:producer_type">17</property>\n'
    f'    <property name="kdenlive:clip_type">2</property>\n'
    f'    <property name="kdenlive:id">5</property>\n'
    f'    <property name="kdenlive:folderid">2</property>\n'
    f'    <property name="kdenlive:sequenceproperties.hasVideo">1</property>\n'
    f'    <property name="kdenlive:sequenceproperties.hasAudio">0</property>\n'
    f'    <property name="kdenlive:sequenceproperties.tracksCount">2</property>\n'
    f'    <property name="kdenlive:sequenceproperties.documentuuid">{SEQ_UUID}</property>\n'
    f'    <property name="kdenlive:sequenceproperties.activeTrack">1</property>')
# 2. main_bin: Sequences folder + sequence entry + open/active timeline
c = c.replace(
    '<property name="kdenlive:docproperties.uuid">'
    f'{SEQ_UUID}</property>',
    '<property name="kdenlive:folder.-1.2">Sequences</property>\n'
    '    <property name="kdenlive:sequenceFolder">2</property>\n'
    '    <property name="kdenlive:docproperties.opensequences">'
    f'{SEQ_UUID}</property>\n'
    '    <property name="kdenlive:docproperties.activetimeline">'
    f'{SEQ_UUID}</property>\n'
    '    <property name="kdenlive:docproperties.uuid">'
    f'{SEQ_UUID}</property>')
c = c.replace(
    '<entry producer="producer2" in="0" out="0" />\n  </playlist>',
    '<entry producer="producer2" in="0" out="0" />\n'
    f'    <entry producer="{SEQ_UUID}" in="0" out="0" />\n  </playlist>')
# 3. projectTractor wrapper before </mlt>
c = c.replace(
    '</mlt>',
    f'  <tractor id="tractor_project" in="0" out="824">\n'
    f'    <property name="kdenlive:projectTractor">1</property>\n'
    f'    <track producer="{SEQ_UUID}" in="0" out="824" />\n'
    f'  </tractor>\n</mlt>')
(CAND / "smoke_test_full_candC_seq_registered.kdenlive").write_text(c)

print("wrote A and C")

# ---------------------------------------------------------------------------
# Candidate B: full modern sequence architecture mirroring
#   empty_from_user.kdenlive (the pristine 26.04.2 ground truth), populated
#   with the 3 media clips + the 6 effects (dot-form ids) nested in the first
#   clip. black_track is producer0; media are chains; timeline tracks are
#   track-tractors (2 playlists each); a sequence tractor carries the
#   sequenceproperties/control_uuid; a projectTractor is the render root.
#   Hypothesis: 26.04 requires the full sequence-clip bin architecture.
# ---------------------------------------------------------------------------
EFFECTS = '''\
        <filter mlt_service="avfilter.exposure">
         <property name="mlt_service">avfilter.exposure</property>
         <property name="kdenlive_id">avfilter.exposure</property>
         <property name="av.exposure">0.9000</property>
        </filter>
        <filter mlt_service="rotoscoping">
         <property name="mlt_service">rotoscoping</property>
         <property name="kdenlive_id">rotoscoping</property>
         <property name="mode">alpha</property>
         <property name="alpha_operation">add</property>
         <property name="feather">5</property>
         <property name="spline">{"0": [[[0.2, 0.2], [0.2, 0.2], [0.2, 0.2]], [[0.8, 0.2], [0.8, 0.2], [0.8, 0.2]], [[0.8, 0.8], [0.8, 0.8], [0.8, 0.8]], [[0.2, 0.8], [0.2, 0.8], [0.2, 0.8]]]}</property>
        </filter>
        <filter mlt_service="frei0r.pixeliz0r">
         <property name="mlt_service">frei0r.pixeliz0r</property>
         <property name="kdenlive_id">frei0r.pixeliz0r</property>
         <property name="0">0.1400</property>
         <property name="1">0.1400</property>
        </filter>
        <filter mlt_service="frei0r.glitch0r">
         <property name="mlt_service">frei0r.glitch0r</property>
         <property name="kdenlive_id">frei0r.glitch0r</property>
         <property name="0">0.6000</property>
         <property name="3">0.6000</property>
        </filter>
        <filter mlt_service="frei0r.rgbsplit0r">
         <property name="mlt_service">frei0r.rgbsplit0r</property>
         <property name="kdenlive_id">frei0r.rgbsplit0r</property>
         <property name="1">0.6200</property>
         <property name="0">0.6200</property>
        </filter>
        <filter mlt_service="frei0r.scanline0r">
         <property name="mlt_service">frei0r.scanline0r</property>
         <property name="kdenlive_id">frei0r.scanline0r</property>
        </filter>
        <filter mlt_service="affine">
         <property name="mlt_service">affine</property>
         <property name="kdenlive_id">transform</property>
         <property name="transition.rect">00:00:00.000=0 0 1920 1080 1</property>
        </filter>'''


def media_producer(pid, res, length, kid, cu):
    out = length - 1
    return f'''\
 <producer id="{pid}" in="0" out="{out}">
  <property name="length">{length}</property>
  <property name="eof">pause</property>
  <property name="resource">{res}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="kdenlive:clip_type">2</property>
  <property name="kdenlive:id">{kid}</property>
  <property name="kdenlive:uuid">{cu}</property>
  <property name="kdenlive:control_uuid">{cu}</property>
  <property name="kdenlive:folderid">-1</property>
 </producer>
'''


def clip_entries(with_effects):
    rows = []
    for i, (pid, _res, length, _kid, _cu) in enumerate(MEDIA):
        out = length - 1
        fx = ("\n" + EFFECTS) if (with_effects and i == 0) else ""
        rows.append(
            f'  <entry producer="{pid}" in="0" out="{out}">{fx}\n  </entry>')
    return "\n".join(rows)


producers_xml = "".join(
    media_producer(p, r, l, k, c) for (p, r, l, k, c) in MEDIA)

B = f'''<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" producer="main_bin" root="{WC}" version="7.40.0">
 <profile width="1920" height="1080" frame_rate_num="25" frame_rate_den="1" progressive="1" sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="16" display_aspect_den="9" colorspace="709"/>
 <producer id="producer_black" in="0" out="824">
  <property name="length">2147483647</property>
  <property name="eof">continue</property>
  <property name="resource">black</property>
  <property name="aspect_ratio">1</property>
  <property name="mlt_service">color</property>
  <property name="kdenlive:playlistid">black_track</property>
  <property name="mlt_image_format">rgba</property>
  <property name="set.test_audio">0</property>
 </producer>
{producers_xml}\
 <playlist id="playlist_v1a">
{clip_entries(with_effects=True)}
 </playlist>
 <playlist id="playlist_v1b"/>
 <tractor id="tractor_v1" in="0" out="824">
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:thumbs_format"/>
  <property name="kdenlive:audio_rec"/>
  <track hide="audio" producer="playlist_v1a"/>
  <track hide="audio" producer="playlist_v1b"/>
 </tractor>
 <playlist id="playlist_v2a">
{clip_entries(with_effects=False)}
 </playlist>
 <playlist id="playlist_v2b"/>
 <tractor id="tractor_v2" in="0" out="824">
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:thumbs_format"/>
  <property name="kdenlive:audio_rec"/>
  <track hide="audio" producer="playlist_v2a"/>
  <track hide="audio" producer="playlist_v2b"/>
 </tractor>
 <tractor id="{SEQ_UUID}" in="0" out="824">
  <property name="kdenlive:sequenceproperties.hasAudio">0</property>
  <property name="kdenlive:sequenceproperties.hasVideo">1</property>
  <property name="kdenlive:clip_type">2</property>
  <property name="kdenlive:uuid">{SEQ_UUID}</property>
  <property name="kdenlive:clipname">Sequence 1</property>
  <property name="kdenlive:sequenceproperties.tracksCount">2</property>
  <property name="kdenlive:sequenceproperties.documentuuid">{SEQ_UUID}</property>
  <property name="kdenlive:control_uuid">{SEQ_UUID}</property>
  <property name="kdenlive:duration">00:00:33;00</property>
  <property name="kdenlive:maxduration">825</property>
  <property name="kdenlive:producer_type">17</property>
  <property name="kdenlive:id">5</property>
  <property name="kdenlive:file_size">0</property>
  <property name="kdenlive:folderid">2</property>
  <property name="kdenlive:sequenceproperties.activeTrack">1</property>
  <property name="kdenlive:sequenceproperties.groups">[
]
</property>
  <property name="kdenlive:sequenceproperties.guides">[
]
</property>
  <track producer="producer_black"/>
  <track producer="tractor_v1"/>
  <track producer="tractor_v2"/>
  <transition id="transition0">
   <property name="a_track">0</property>
   <property name="b_track">1</property>
   <property name="compositing">0</property>
   <property name="mlt_service">qtblend</property>
   <property name="kdenlive_id">qtblend</property>
   <property name="internal_added">237</property>
   <property name="always_active">1</property>
  </transition>
  <transition id="transition1">
   <property name="a_track">0</property>
   <property name="b_track">2</property>
   <property name="compositing">0</property>
   <property name="mlt_service">qtblend</property>
   <property name="kdenlive_id">qtblend</property>
   <property name="internal_added">237</property>
   <property name="always_active">1</property>
  </transition>
 </tractor>
 <playlist id="main_bin">
  <property name="kdenlive:folder.-1.2">Sequences</property>
  <property name="kdenlive:sequenceFolder">2</property>
  <property name="kdenlive:docproperties.audioChannels">2</property>
  <property name="kdenlive:docproperties.documentid">1783108071607</property>
  <property name="kdenlive:docproperties.kdenliveversion">26.04.2</property>
  <property name="kdenlive:docproperties.profile">1920x1080_fps25</property>
  <property name="kdenlive:docproperties.uuid">{SEQ_UUID}</property>
  <property name="kdenlive:docproperties.version">1.1</property>
  <property name="kdenlive:docproperties.opensequences">{SEQ_UUID}</property>
  <property name="kdenlive:docproperties.activetimeline">{SEQ_UUID}</property>
  <property name="kdenlive:documentnotes"/>
  <property name="kdenlive:documentnotesversion">2</property>
  <property name="kdenlive:expandedFolders"/>
  <property name="kdenlive:binZoom">4</property>
  <property name="kdenlive:extraBins">project_bin:-1:0</property>
  <property name="xml_retain">1</property>
  <entry producer="producer0" in="0" out="0"/>
  <entry producer="producer1" in="0" out="0"/>
  <entry producer="producer2" in="0" out="0"/>
  <entry producer="{SEQ_UUID}" in="0" out="0"/>
 </playlist>
 <tractor id="tractor_project" in="0" out="824">
  <property name="kdenlive:projectTractor">1</property>
  <track producer="{SEQ_UUID}" in="0" out="824"/>
 </tractor>
</mlt>
'''
(CAND / "smoke_test_full_candB_full_sequence.kdenlive").write_text(B)
print("wrote B")

