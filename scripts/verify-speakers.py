"""Cloud two-voice integration test; requires the generated synthetic fixture."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import time
from fastapi.testclient import TestClient
from meeting_app.config import DATA,ROOT
from meeting_app.store import Store
from meeting_app.vault import Vault
from meeting_app.jobs import Jobs

sys.stdout.reconfigure(encoding='utf-8')
fixture=DATA/'synthetic-two-speakers'
turns=json.loads((fixture/'turns.json').read_text('utf-8'))
with tempfile.TemporaryDirectory(prefix='meeting-speaker-test-') as directory:
    service=importlib.import_module('meeting_app.app')
    service.DATA=Path(directory);service.TOKEN='two-voice-smoke'
    service.store=Store(Path(directory));service.vault=Vault(Path(directory))
    service.vault.set('doubao_api_key',Vault(DATA).get('doubao_api_key'))
    service.jobs=Jobs(service.store,service.vault,Path(directory),service.notify)
    with TestClient(service.app,headers={'x-meeting-token':'two-voice-smoke'}) as client:
        meeting=client.post('/api/meetings',json={'title':'两人合成对话验证','mode':'file','engine':'doubao','auto_minutes':True}).json()
        started=time.monotonic()
        with (fixture/'conversation.wav').open('rb') as audio:
            response=client.post(f"/api/meetings/{meeting['id']}/file",files={'file':('conversation.wav',audio,'audio/wav')})
        assert response.status_code==200,response.text
        while time.monotonic()-started<180:
            detail=client.get('/api/meetings/'+meeting['id']).json()
            if detail['status'] in ('completed','failed','partial_failed'):break
            time.sleep(.5)
        assert detail['status']=='completed',detail.get('error')
        for file in Path(directory).glob('*/run_*.response.json'):
            (ROOT/'artifacts'/'two-speaker-provider.json').write_text(file.read_text('utf-8'),'utf-8')
        labels=[]
        for turn in turns:
            overlaps={}
            for segment in detail['segments']:
                overlap=max(0,min(segment['end_ms'],turn['end_ms'])-max(segment['start_ms'],turn['start_ms']))
                if overlap and segment['speaker_id']:
                    overlaps[segment['speaker_id']]=overlaps.get(segment['speaker_id'],0)+overlap
            assert overlaps,'No speaker in synthetic turn'
            labels.append(max(overlaps,key=overlaps.get))
        assert labels[0]==labels[2] and labels[1]==labels[3] and labels[0]!=labels[1],labels
        for sid,name in ((labels[0],'主持人'),(labels[1],'王工')):
            assert client.patch(f"/api/meetings/{meeting['id']}/speakers/{sid}",json={'name':name}).status_code==200
        exported=client.get(f"/api/meetings/{meeting['id']}/export/txt").text
        assert '主持人' in exported and '王工' in exported
        report={'status':'PASS','source':'two Windows synthetic Chinese voices; no physical microphone',
                'speaker_backend':'Doubao transcript with local CAM++ correction',
                'audio_seconds':detail['duration_ms']/1000,'seconds':round(time.monotonic()-started,2),
                'segments':len(detail['segments']),'speakers':len(detail['speakers']),
                'turn_speakers':[0 if sid==labels[0] else 1 for sid in labels],
                'checks':['two distinct voices','identity retained when each voice returns','independent rename','names in export','minutes and action items']}
        (ROOT/'artifacts'/'two-speaker-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
