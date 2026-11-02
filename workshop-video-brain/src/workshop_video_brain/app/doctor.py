"""Bounded, offline environment diagnostics. Never initialize/download models."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess


def _probe(binary: str, arguments: list[str]) -> dict:
    executable = shutil.which(binary)
    if not executable:
        return {'available': False, 'path': None, 'error': 'not found on PATH'}
    try:
        result = subprocess.run([executable, *arguments], capture_output=True, text=True,
                                timeout=10, env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'})
        return {'available': result.returncode == 0, 'path': executable,
                'returncode': result.returncode, 'output': (result.stdout + result.stderr)[-65536:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'available': False, 'path': executable, 'error': str(exc)}


def _auto_editor_ready() -> bool:
    from workshop_video_brain.edit_mcp.adapters.autoeditor.cli import resolve_binary

    binary = resolve_binary()
    return binary is not None and _probe(str(binary), ['--version'])['available']


def _mlt_effects_report() -> dict:
    from workshop_video_brain.edit_mcp.adapters.mlt.registry import get_registry

    registry = get_registry(refresh=True)
    if registry is None:
        return {'available': False, 'engine': None, 'mlt_version': None, 'counts': {}}
    return {'available': True, 'engine': registry.engine, 'mlt_version': registry.mlt_version,
            'counts': {kind: len(names) for kind, names in registry.services.items()}}


def _mlt_bindings_report() -> dict:
    from workshop_video_brain.edit_mcp.adapters.mlt.engine import find_mlt_python

    try:
        found = find_mlt_python(refresh=True)
    except Exception as exc:  # noqa: BLE001 -- doctor reports, it never fails
        return {'available': False, 'python': None, 'mlt_version': None, 'error': str(exc)}
    if found is None:
        return {'available': False, 'python': None, 'mlt_version': None,
                'error': "no interpreter can import the MLT bindings (install python3-mlt or set WVB_MLT_PYTHON)"}
    return {'available': True, 'python': found.path, 'mlt_version': found.mlt_version, 'error': None}


def environment_report() -> dict:
    binaries = {name: _probe(name, ['-version'] if name in ('ffmpeg', 'ffprobe') else ['--version'])
                for name in ('ffmpeg', 'ffprobe', 'melt', 'tesseract')}
    encoders = _probe('ffmpeg', ['-hide_banner', '-encoders'])
    effects = _mlt_effects_report()
    optional = {name: importlib.util.find_spec(module) is not None for name, module in
                {'transcription': 'faster_whisper', 'research': 'numpy', 'images': 'PIL',
                 'ocr': 'pytesseract', 'ai_mask': 'rembg', 'onnx': 'onnxruntime',
                 'ai_mask_heavy': 'ultralytics', 'motion_track': 'cv2',
                 'scene_detect': 'scenedetect', 'auto_editor': 'auto_editor'}.items()}
    hf_cache = Path(os.environ.get('HF_HUB_CACHE',
                    str(Path(os.environ.get('HF_HOME', str(Path.home() / '.cache/huggingface'))) / 'hub')))
    whisper_models = []
    selected_model = os.environ.get('WVB_WHISPER_MODEL', 'small')
    if hf_cache.is_dir():
        for model in sorted(hf_cache.glob('models--*whisper*')):
            if any(all((snapshot / name).is_file() and (snapshot / name).stat().st_size > 0
                       for name in ('model.bin', 'config.json', 'tokenizer.json'))
                   for snapshot in (model / 'snapshots').glob('*')):
                whisper_models.append(model.name)
    selected_cached = any(name.endswith('--faster-whisper-' + selected_model) for name in whisper_models)
    selected_path = Path(selected_model)
    if selected_path.is_dir():
        selected_cached = all((selected_path / name).is_file()
                              and (selected_path / name).stat().st_size > 0
                              for name in ('model.bin', 'config.json', 'tokenizer.json'))
    mask_cache = Path(os.environ.get('U2NET_HOME', str(Path.home() / '.u2net')))
    mask_models = [p.name for p in sorted(mask_cache.glob('*.onnx')) if p.stat().st_size > 0]
    ffmpeg = binaries['ffmpeg']['available'] and binaries['ffprobe']['available']
    mlt_bindings = _mlt_bindings_report()
    return {'binaries': binaries, 'encoders': encoders, 'mlt_effects': effects,
            'optional_engines': optional, 'mlt_bindings': mlt_bindings,
            'model_cache': {'whisper': whisper_models, 'rembg': mask_models,
                            'selected_whisper_model': selected_model, 'selected_whisper_cached': selected_cached,
                            'note': 'Cached files only; no model is loaded or downloaded.'},
            'features': {'media_processing': ffmpeg,
                         'timeline_render': ffmpeg and binaries['melt']['available'],
                         'transcription_engine': ffmpeg and optional['transcription'],
                         'transcription_offline': ffmpeg and optional['transcription'] and selected_cached,
                         'ai_mask_engine': ffmpeg and optional['ai_mask'] and optional['onnx'],
                         'ai_mask_offline': ffmpeg and optional['ai_mask'] and optional['onnx'] and bool(mask_models),
                         'motion_track_python': ffmpeg and optional['motion_track'],
                         'scene_detect_pyscenedetect': optional['scene_detect'] and importlib.util.find_spec('cv2') is not None,
                         'silence_cut_auto_editor': _auto_editor_ready(),
                         'mlt_bindings': mlt_bindings['available'],
                         'ocr': optional['ocr'] and binaries['tesseract']['available']},
            'suggestions': {
                'binaries': 'Install missing FFmpeg/ffprobe and MLT melt binaries and expose them on PATH.',
                'optional_engines': 'Use uv sync --extra research / ai-mask / ai-mask-heavy / motion-track / scene-detect / auto-editor as needed.',
                'auto_editor': 'After installing the auto-editor extra, run auto-editor --version once: it downloads its native binary.',
                'transcription': 'Install faster-whisper and cache the WVB_WHISPER_MODEL model before offline use.',
            }}
