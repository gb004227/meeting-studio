from meeting_app import config
from meeting_app.store import Store


def model_at(path):
    path.mkdir(parents=True)
    (path/'config.json').write_text('{}')
    (path/'model.safetensors').write_bytes(b'model')
    return path


def test_moved_installation_recovers_bundled_paths_without_losing_other_settings(tmp_path,monkeypatch):
    model=model_at(tmp_path/'new-folder/models/MOSS-Transcribe-Diarize')
    python=tmp_path/'new-folder/moss-python/python.exe'
    python.parent.mkdir();python.write_bytes(b'python')
    monkeypatch.setattr(config,'BUNDLED_MODEL',model)
    monkeypatch.setattr(config,'BUNDLED_PYTHON',python)
    store=Store(tmp_path/'data')
    store.save_settings({'moss_path':str(tmp_path/'old-computer/model'),'moss_python':str(tmp_path/'old-computer/python.exe'),'doubao_file_mode':'flash'})
    settings=store.settings()
    assert settings['moss_path']==str(model)
    assert settings['moss_python']==str(python)
    assert settings['doubao_file_mode']=='flash'


def test_valid_custom_paths_are_kept_when_bundled_resources_exist(tmp_path,monkeypatch):
    bundled=model_at(tmp_path/'bundled-model')
    custom=model_at(tmp_path/'custom-model')
    python=tmp_path/'python.exe';python.write_bytes(b'python')
    monkeypatch.setattr(config,'BUNDLED_MODEL',bundled)
    monkeypatch.setattr(config,'BUNDLED_PYTHON',python)
    settings=config.resolve_local_paths({'moss_path':str(custom),'moss_python':str(python)})
    assert settings=={'moss_path':str(custom),'moss_python':str(python)}


def test_missing_paths_stay_visible_when_no_bundle_is_available(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'BUNDLED_MODEL',tmp_path/'not-bundled')
    monkeypatch.setattr(config,'BUNDLED_PYTHON',tmp_path/'not-bundled.exe')
    settings={'moss_path':str(tmp_path/'missing'),'moss_python':str(tmp_path/'missing.exe')}
    assert config.resolve_local_paths(settings)==settings
