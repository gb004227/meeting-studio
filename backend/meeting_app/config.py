from pathlib import Path
import os
import json

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('MEETING_DATA_DIR', str(Path(os.environ.get('LOCALAPPDATA', str(ROOT / 'runtime'))) / 'MeetingStudio')))
DATA.mkdir(parents=True, exist_ok=True)
TOKEN = os.environ.get('MEETING_TOKEN', '')
BUNDLED_MODEL = ROOT / 'models' / 'MOSS-Transcribe-Diarize'
BUNDLED_PYTHON = ROOT / 'moss-python' / 'python.exe'
DEFAULTS = {
    'doubao_realtime_resource': 'volc.seedasr.sauc.duration',
    'doubao_file_resource': 'volc.bigasr.auc_turbo',
    'doubao_file_mode': 'stream',
    'moss_path': str(BUNDLED_MODEL) if BUNDLED_MODEL.is_dir() else r'K:\工具箱\MOSS model\MOSS-Transcribe-Diarize',
    'moss_python': str(BUNDLED_PYTHON) if BUNDLED_PYTHON.is_file() else str(ROOT / '.moss-venv' / 'Scripts' / 'python.exe'),
    'moss_device': 'cpu',
    'llm_base_url': '', 'llm_model': '',
    'auto_minutes': True,
    'tos_endpoint': '', 'tos_region': '', 'tos_bucket': '',
}


def model_files_ready(directory):
    path=Path(directory)
    if not (path/'config.json').is_file(): return False
    index=path/'model.safetensors.index.json'
    if index.exists():
        try:
            files=set(json.loads(index.read_text('utf-8'))['weight_map'].values())
            return bool(files) and all((path/name).is_file() and (path/name).stat().st_size>0 for name in files)
        except (ValueError,KeyError): return False
    return (path/'model.safetensors').is_file()


def resolve_local_paths(settings):
    """Recover bundled resources when a saved path belongs to another computer."""
    settings=dict(settings)
    if not model_files_ready(settings['moss_path']) and model_files_ready(BUNDLED_MODEL):
        settings['moss_path']=str(BUNDLED_MODEL)
    if not Path(settings['moss_python']).is_file() and BUNDLED_PYTHON.is_file():
        settings['moss_python']=str(BUNDLED_PYTHON)
    return settings
