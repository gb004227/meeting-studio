"""Explicit paid smoke test using only a synthetic fixture, never the user's microphone."""
import importlib
import json
from pathlib import Path
import tempfile
import time
import sys
from fastapi.testclient import TestClient

sys.stdout.reconfigure(encoding='utf-8')
from meeting_app.config import DATA
from meeting_app.vault import Vault
from meeting_app.store import Store
from meeting_app.jobs import Jobs

source=DATA/'synthetic-probe-16k.wav'
key=Vault(DATA).get('doubao_api_key')
report={}
with tempfile.TemporaryDirectory(prefix='meeting-studio-smoke-') as directory:
    service=importlib.import_module('meeting_app.app')
    service.DATA=Path(directory)
    service.TOKEN='smoke-local-only'
    service.store=Store(Path(directory))
    service.vault=Vault(Path(directory))
    service.vault.set('doubao_api_key',key)
    service.jobs=Jobs(service.store,service.vault,Path(directory),service.notify)
    with TestClient(service.app,headers={'x-meeting-token':'smoke-local-only'}) as client:
        m=client.post('/api/meetings',json={'title':'系统合成语音 · 云端联调','mode':'file','engine':'doubao','auto_minutes':True}).json()
        started=time.monotonic()
        with source.open('rb') as stream:
            response=client.post(f"/api/meetings/{m['id']}/file",files={'file':('synthetic.wav',stream,'audio/wav')})
        assert response.status_code==200,response.text
        while time.monotonic()-started<150:
            meeting=client.get('/api/meetings/'+m['id']).json()
            if meeting['status'] in ('completed','failed','partial_failed'): break
            time.sleep(.3)
        assert meeting['status']=='completed',meeting.get('error')
        assert len(meeting['segments'])>=3
        assert len(meeting['speakers'])>=1
        assert len(meeting['minutes']['data']['action_items'])>=2
        sid=meeting['speakers'][0]['id']
        assert client.patch(f"/api/meetings/{m['id']}/speakers/{sid}",json={'name':'测试主持人'}).status_code==200
        for kind in ('txt','md','csv'):
            exported=client.get(f"/api/meetings/{m['id']}/export/{kind}")
            assert exported.status_code==200
            assert '测试主持人' in exported.text
        action=meeting['minutes']['data']['action_items'][0]
        assert client.patch(f"/api/meetings/{m['id']}/actions/{action['id']}",json={'status':'done'}).status_code==200
        assert client.get('/api/actions').json()[0]['status']=='done'
        assert client.get(f"/api/meetings/{m['id']}/audio",headers={'Range':'bytes=0-127'}).status_code==206
        report={'status':'PASS','audio_source':'Windows SAPI synthetic Chinese; no microphone capture',
                'file_asr_resource':'volc.seedasr.sauc.duration','seconds':round(time.monotonic()-started,2),
                'segments':len(meeting['segments']),'speakers':len(meeting['speakers']),
                'action_items':len(meeting['minutes']['data']['action_items']),
                'transcript':''.join(s['text'] for s in meeting['segments']),
                'checks':['file import','real ASR result','speaker labels','extractive minutes','action items','persistent rename','all three exports','task status','audio range playback']}
output=Path(__file__).resolve().parents[1]/'artifacts'
output.mkdir(exist_ok=True)
(output/'cloud-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=False))
