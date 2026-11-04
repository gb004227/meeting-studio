import importlib
import io
import wave
import pytest
from fastapi.testclient import TestClient
from meeting_app.store import Store
from meeting_app.vault import Vault
from meeting_app.jobs import Jobs


@pytest.fixture
def client(tmp_path,monkeypatch):
    service=importlib.import_module('meeting_app.app')
    monkeypatch.setattr(service,'DATA',tmp_path)
    monkeypatch.setattr(service,'TOKEN','test-local-token')
    monkeypatch.setattr(service,'store',Store(tmp_path))
    service.store.save_settings({'moss_path':str(tmp_path/'uninstalled-model')})
    monkeypatch.setattr(service,'vault',Vault(tmp_path))
    monkeypatch.setattr(service,'jobs',Jobs(service.store,service.vault,tmp_path,service.notify))
    with TestClient(service.app,headers={'x-meeting-token':'test-local-token'}) as c:
        yield c,service


def test_loopback_api_still_requires_session_token(client):
    c,service=client
    assert c.get('/api/settings',headers={'x-meeting-token':'wrong'}).status_code==401


def test_desktop_file_origin_can_preflight_without_leaking_access(client):
    c,service=client
    r=c.options('/api/settings',headers={'Origin':'null','Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'x-meeting-token,content-type','x-meeting-token':''})
    assert r.status_code==200
    assert r.headers['access-control-allow-origin']=='null'
    assert c.get('/api/settings',headers={'Origin':'null','x-meeting-token':''}).status_code==401


def test_settings_never_return_key(client):
    c,service=client
    assert c.put('/api/settings',json={'doubao_api_key':'not-real-test-key'}).status_code==200
    value=c.get('/api/settings').json()
    assert value['secrets']['doubao_api_key'] is True
    assert 'not-real-test-key' not in str(value)


def test_meeting_and_actions_empty_are_real_empty_states(client):
    c,service=client
    assert c.get('/api/meetings').json()==[]
    assert c.get('/api/actions').json()==[]
    m=c.post('/api/meetings',json={'title':'test','mode':'file','engine':'moss'}).json()
    assert c.get('/api/meetings/'+m['id']).json()['segments']==[]


def test_rename_and_export_use_same_person_record(client):
    c,service=client
    m=c.post('/api/meetings',json={'title':'校对会议','mode':'file','engine':'moss'}).json()
    vid=service.store.new_version(m['id'],'moss')
    service.store.add_segments(m['id'],vid,[{'start_ms':10,'end_ms':2000,'text':'我负责提交测试结果。','speaker':'S01'}],'file')
    detail=c.get('/api/meetings/'+m['id']).json()
    sid=detail['speakers'][0]['id']
    assert c.patch(f"/api/meetings/{m['id']}/speakers/{sid}",json={'name':'王工'}).status_code==200
    response=c.get(f"/api/meetings/{m['id']}/export/txt")
    assert response.status_code==200 and '王工' in response.text
    assert '我负责提交测试结果。' in response.text


def test_binary_audio_is_saved_independent_of_cloud(client):
    c,service=client
    m=c.post('/api/meetings',json={'title':'仅测试存盘','mode':'realtime','engine':'moss','auto_minutes':False}).json()
    with c.websocket_connect(f"/api/meetings/{m['id']}/record?token=test-local-token") as ws:
        assert ws.receive_json()['type']=='ready'
        ws.send_bytes(b'\0\0'*1600)
        ws.send_text('{"type":"stop"}')
        assert ws.receive_json()['type']=='saved'
    detail=c.get('/api/meetings/'+m['id']).json()
    assert detail['duration_ms']==100
    with wave.open(detail['audio_path'],'rb') as w: assert w.getnframes()==1600
