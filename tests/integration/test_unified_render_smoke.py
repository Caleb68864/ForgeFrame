"""Real FFmpeg and MLT outputs through the shared preview/final executor."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.render.profiles import RenderProfile
from workshop_video_brain.edit_mcp.pipelines import render_final as final_module
from workshop_video_brain.edit_mcp.pipelines.render_pipeline import list_renders, run_render

pytestmark = pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')


def probe(path):
    return json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                                    capture_output=True, text=True, check=True, timeout=10).stdout)


@pytest.fixture
def source(tmp_path):
    (tmp_path / 'workspace.yaml').write_text('title: render-smoke\n')
    path = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=160x96:r=30000/1001:d=1',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True, timeout=30)
    return path


def profile():
    return RenderProfile(name='smoke', width=160, height=96, fps=29.97,
                         container='mkv', disable_audio=True, video_bitrate='300k', pix_fmt='yuv420p')


def test_direct_preview_and_final_preserve_fractional_rate_container(source, monkeypatch):
    setting = profile()
    preview = run_render(source.parent, source, 'smoke', loaded_profile=setting)
    assert preview.status == 'succeeded', preview.error_message
    monkeypatch.setattr(final_module, 'load_profile', lambda name: setting)
    final = final_module.render_final(source.parent, 'smoke', project_file=str(source))
    for output in [Path(preview.output_path), final.output_path]:
        data = probe(output)
        video = next(stream for stream in data['streams'] if stream['codec_type'] == 'video')
        assert video['avg_frame_rate'] == '30000/1001'
        assert output.suffix == '.mkv'
        assert 'matroska' in data['format']['format_name']
        assert float(data['format']['duration']) == pytest.approx(1, abs=.08)
    assert final.duration_seconds > 0
    assert final.file_size_bytes > 0
    assert len(list_renders(source.parent)) == 2


@pytest.mark.skipif(not shutil.which('melt'), reason='MLT required')
def test_mlt_output_preserves_fractional_rate_and_container(source, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    project = source.parent / 'cut.kdenlive'
    project.write_text(f'''<mlt producer="timeline">
<profile width="160" height="96" frame_rate_num="30000" frame_rate_den="1001"
 progressive="1" sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="16" display_aspect_den="9" colorspace="709"/>
<producer id="clip"><property name="mlt_service">avformat</property><property name="resource">{source}</property></producer>
<playlist id="timeline"><entry producer="clip" in="0" out="29"/></playlist></mlt>''')
    job = run_render(source.parent, project, 'smoke', mode='proxy', loaded_profile=profile(), timeout_seconds=30)
    assert job.status == 'succeeded', job.error_message
    data = probe(job.output_path)
    video = next(stream for stream in data['streams'] if stream['codec_type'] == 'video')
    assert video['avg_frame_rate'] == '30000/1001'
    assert 'matroska' in data['format']['format_name']
    assert job.duration_seconds == pytest.approx(1, abs=.08)


def test_failed_encoding_removes_partial_and_records_failure(source):
    setting = profile().model_copy(update={'video_codec': 'encoder_that_does_not_exist'})
    job = run_render(source.parent, source, 'smoke', loaded_profile=setting)
    assert job.status == 'failed'
    assert not Path(job.output_path).exists()
    assert list_renders(source.parent)[0].status == 'failed'
    assert Path(job.log_path).is_file()


@pytest.mark.skipif(not shutil.which('melt'), reason='MLT required')
def test_final_uses_original_while_explicit_proxy_preview_uses_proxy(source, monkeypatch):
    from workshop_video_brain.core.models.kdenlive import KdenliveProject, Playlist, PlaylistEntry, Producer, ProjectProfile, Track
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    proxy = source.parent / 'proxy.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x96:r=30000/1001:d=1',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(proxy)], check=True, timeout=30)
    project = KdenliveProject(title='proxy smoke', profile=ProjectProfile(width=160, height=96, fps=29.97),
        producers=[Producer(id='clip', resource=str(proxy), properties={
            'resource': str(proxy), 'mlt_service': 'avformat', 'length': '30',
            'kdenlive:proxy': str(proxy), 'kdenlive:originalurl': str(source)})],
        playlists=[Playlist(id='video', entries=[PlaylistEntry(producer_id='clip', in_point=0, out_point=29)])],
        tracks=[Track(id='video', track_type='video')])
    project_path = source.parent / 'proxy-cut.kdenlive'
    serialize_project(project, project_path)
    before = project_path.read_bytes()
    preview = run_render(source.parent, project_path, 'smoke', mode='proxy', loaded_profile=profile(), timeout_seconds=30)
    assert preview.status == 'succeeded', preview.error_message
    monkeypatch.setattr(final_module, 'load_profile', lambda name: profile())
    final = final_module.render_final(source.parent, 'smoke', project_file=str(project_path))
    def pixel(output):
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output), '-frames:v', '1', '-vf', 'scale=1:1',
                              '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True, timeout=10).stdout
        return tuple(raw[:3])
    red = pixel(final.output_path)
    blue = pixel(preview.output_path)
    assert red[0] > 150 and red[2] < 50, red
    assert blue[2] > 150 and blue[0] < 50, blue
    assert project_path.read_bytes() == before
    assert all(job.project_path == str(project_path.resolve()) for job in list_renders(source.parent))
