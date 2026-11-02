"""Real guided first cut from a cached transcript, without speech-model downloads."""
import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.pipelines.guided_workflow import project_status, run_workflow
from workshop_video_brain.workspace.manager import WorkspaceManager

pytestmark = pytest.mark.skipif(any(not shutil.which(binary) for binary in ('ffmpeg', 'ffprobe', 'melt')), reason='Real media tools required')


def test_guided_workflow_real_first_cut_resume_and_script_invalidation(tmp_path, monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    root = tmp_path / 'workspace'
    WorkspaceManager.create('Sanding tutorial', tmp_path, workspace_root=root)
    fixture = Path(__file__).parents[1] / 'fixtures/media_generated/test_clip_1080p2997_5s.mp4'
    source = root / 'media/raw/sanding.mp4'
    shutil.copyfile(fixture, source)
    text = 'First sand the wooden board smooth with sandpaper. Sand the wooden board smooth with sandpaper.'
    transcript = Transcript(asset_id=uuid4(), engine='manual', raw_text=text, segments=[
        TranscriptSegment(start_seconds=0, end_seconds=4, text=text)])
    (root / 'transcripts/sanding_transcript.json').write_text(transcript.to_json())
    script = root / 'reports/script.json'
    script.write_text(json.dumps({'steps': [{'description': text, 'chapter_title': 'Sand wooden board'}]}))
    def no_transcription(*args, **kwargs):
        pytest.fail('A fresh manual transcript must not invoke a speech model')
    monkeypatch.setattr('workshop_video_brain.edit_mcp.adapters.stt.whisper_engine.transcribe', no_transcription)
    result = run_workflow(root)
    assert result['review_status'] == 'awaiting_human_review'
    assert all(record['status'] == 'completed' for record in result['stages'].values())
    assert result['stages']['footage']['transcribed_count'] == 0
    project = Path(result['project_file'])
    preview = Path(result['stages']['preview']['output_path'])
    review = Path(result['stages']['review']['review_path'])
    assert project.is_file() and preview.stat().st_size > 0 and review.is_file()
    assert (root / 'markers/sanding_markers.json').is_file()
    assert (root / 'clips/sanding_label.json').is_file()
    assert all(project_status(root)['readiness'].values())
    times = {path: path.stat().st_mtime_ns for path in (project, preview, review)}
    resumed = run_workflow(root)
    assert resumed['project_file'] == str(project)
    assert {path: path.stat().st_mtime_ns for path in times} == times
    script.write_text(json.dumps({'steps': [{'description': text, 'chapter_title': 'Updated sanding lesson'}]}))
    readiness = project_status(root)['readiness']
    assert readiness['footage'] and readiness['selects']
    assert not readiness['assembly'] and not readiness['preview'] and not readiness['review']
    rebuilt = run_workflow(root)
    assert rebuilt['project_file'] != str(project)
    assert rebuilt['stages']['preview']['output_path'] != str(preview)
    assert all(project_status(root)['readiness'].values())
