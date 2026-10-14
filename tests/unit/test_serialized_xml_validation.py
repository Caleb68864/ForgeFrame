"""Exercise serialized shape checks with independently corrupted XML."""
import copy
import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.core.models.kdenlive import KdenliveProject, Playlist, PlaylistEntry, Producer, Track
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_serialized_xml


def prop(node, name, value):
    found = node.find(f"property[@name='{name}']")
    if found is None:
        found = ET.SubElement(node, 'property', name=name)
    found.text = value


@pytest.fixture
def document(tmp_path):
    project = KdenliveProject(title='validation', producers=[
        Producer(id='clip', resource='/media/clip.mp4', properties={'mlt_service': 'avformat'})],
        playlists=[Playlist(id='video', entries=[PlaylistEntry(producer_id='clip', in_point=0, out_point=99)])],
        tracks=[Track(id='video', track_type='video')])
    path = tmp_path / 'draft.kdenlive'
    serialize_project(project, path)
    return ET.parse(path).getroot()


def test_serializer_output_passes(document):
    assert validate_serialized_xml(document).items == []


@pytest.mark.parametrize('corruption,expected', [
    ('duplicate', 'Duplicate XML id'), ('profile', 'positive integer'),
    ('uuid', 'belongs only'), ('reference', 'Unknown producer reference'),
    ('range', 'beyond length'), ('bin', 'no matching registered bin'),
    ('folder_id', 'Sequences folder id'), ('main_bin_out', 'must end at length - 1'),
    ('lanes', 'two existing playlist lanes'),
])
def test_corruption_is_blocking(document, corruption, expected):
    media = document.find("producer[@id='clip']")
    entry = next(e for p in document.findall('playlist') if p.get('id') != 'main_bin'
                 for e in p.findall('entry') if e.get('producer') == 'clip')
    if corruption == 'duplicate':
        document.append(copy.deepcopy(media))
    elif corruption == 'profile':
        document.find('profile').set('frame_rate_den', '0')
    elif corruption == 'uuid':
        prop(media, 'kdenlive:uuid', 'wrong')
    elif corruption == 'reference':
        entry.set('producer', 'missing')
    elif corruption == 'range':
        prop(media, 'length', '99')
    elif corruption == 'folder_id':
        prop(media, 'kdenlive:id', '2')
    elif corruption == 'main_bin_out':
        document.find("playlist[@id='main_bin']").find("entry[@producer='clip']").set('out', '98')
    elif corruption == 'bin':
        main = document.find("playlist[@id='main_bin']")
        main.remove(main.find("entry[@producer='clip']"))
    elif corruption == 'lanes':
        lane = next(t for t in document.findall('tractor') if len(t.findall('track')) == 2)
        lane.remove(lane.findall('track')[1])
    report = validate_serialized_xml(document)
    assert any(expected in item.message for item in report.items), report
    assert all(item.severity == 'blocking_error' for item in report.items)


def test_twin_shape_acceptance_and_missing_twin(document):
    media = document.find("producer[@id='clip']")
    media.tag = 'chain'
    prop(media, 'mlt_service', 'avformat-novalidate')
    prop(media, 'kdenlive:id', '4')
    prop(media, 'kdenlive:control_uuid', 'shared')
    prop(media, 'kdenlive:kextractor', '1')
    prop(media, 'length', '100')
    twin = copy.deepcopy(media)
    twin.set('id', 'clip_bin')
    prop(twin, 'mlt_service', 'avformat')
    prop(twin, 'kdenlive:monitorPosition', '0')
    document.append(twin)
    main = document.find("playlist[@id='main_bin']")
    main.find("entry[@producer='clip']").set('producer', 'clip_bin')
    main.find("entry[@producer='clip_bin']").set('out', '99')
    for playlist in document.findall('playlist'):
        if playlist is not main:
            for entry in playlist.findall("entry[@producer='clip']"):
                prop(entry, 'kdenlive:id', '4')
    assert validate_serialized_xml(document).items == []
    document.remove(twin)
    assert any('AV media requires' in item.message for item in validate_serialized_xml(document).items)


def test_concurrent_version_allocation_is_unique(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
    def allocate(index):
        project = KdenliveProject(title=f'Version {index}')
        return serialize_versioned(project, tmp_path, 'edit')
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(allocate, range(8)))
    assert len(set(paths)) == 8
    assert {path.name for path in paths} == {f'edit_v{index}.kdenlive' for index in range(1, 9)}
    assert all(not validate_serialized_xml(ET.parse(path).getroot()).items for path in paths)


def test_unused_native_chain_does_not_change_generated_document_contract(document):
    chain = ET.SubElement(document, 'chain', id='preserved_native_bin', out='00:00:03.937')
    prop(chain, 'mlt_service', 'avformat-novalidate')
    prop(chain, 'kdenlive:control_uuid', 'native-bin-control')
    prop(chain, 'kdenlive:id', '4')
    assert validate_serialized_xml(document).items == []


def test_pre_sequences_document_may_register_media_with_id_two(document):
    media = document.find("producer[@id='clip']")
    prop(media, 'kdenlive:id', '2')
    timeline = next(p for p in document.findall('playlist') if p.get('id') != 'main_bin')
    prop(timeline.find("entry[@producer='clip']"), 'kdenlive:id', '2')
    main = document.find("playlist[@id='main_bin']")
    for folder_property in main.findall("property"):
        if folder_property.get('name') in {'kdenlive:sequenceFolder', 'kdenlive:folder.-1.2'}:
            main.remove(folder_property)
    assert validate_serialized_xml(document).items == []


def test_timewarp_variant_outside_main_bin_shares_registered_id(document):
    timeline = next(p for p in document.findall('playlist') if p.get('id') != 'main_bin')
    entry = timeline.find("entry[@producer='clip']")
    entry.set('producer', 'clip_tw2')
    entry.set('out', '49')
    prop(entry, 'kdenlive:id', '4')
    variant = ET.SubElement(document, 'producer', id='clip_tw2')
    prop(variant, 'mlt_service', 'timewarp')
    prop(variant, 'length', '50')
    prop(variant, 'kdenlive:id', '4')
    assert validate_serialized_xml(document).items == []
    prop(variant, 'kdenlive:id', '8')
    prop(entry, 'kdenlive:id', '8')
    assert any('no matching registered bin clip' in item.message
               for item in validate_serialized_xml(document).items)


@pytest.mark.parametrize('entry_id', [None, '5'])
def test_timeline_entry_id_must_match_registered_clip(document, entry_id):
    timeline = next(p for p in document.findall('playlist') if p.get('id') != 'main_bin')
    entry = timeline.find("entry[@producer='clip']")
    found = entry.find("property[@name='kdenlive:id']")
    if found is not None:
        entry.remove(found)
    if entry_id is not None:
        prop(entry, 'kdenlive:id', entry_id)
    report = validate_serialized_xml(document)
    assert any("must carry its bin clip's kdenlive:id (4)" in item.message
               for item in report.items), report
