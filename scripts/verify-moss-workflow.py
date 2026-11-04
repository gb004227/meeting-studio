import importlib,json,sys,tempfile,time
from pathlib import Path
from fastapi.testclient import TestClient
sys.stdout.reconfigure(encoding='utf-8')
from meeting_app.config import ROOT,DATA
from meeting_app.store import Store
from meeting_app.vault import Vault
from meeting_app.jobs import Jobs

audio_path=Path(sys.argv[1]) if len(sys.argv)>1 else DATA/'synthetic-probe-16k.wav'
two_speakers=len(sys.argv)>1

with tempfile.TemporaryDirectory(prefix='meeting-moss-workflow-') as directory:
    service=importlib.import_module('meeting_app.app')
    service.DATA=Path(directory);service.TOKEN='local-moss-smoke'
    service.store=Store(Path(directory));service.vault=Vault(Path(directory))
    service.store.save_settings({'moss_python':str(ROOT/'.moss-venv'/'Scripts'/'python.exe')})
    service.jobs=Jobs(service.store,service.vault,Path(directory),service.notify)
    with TestClient(service.app,headers={'x-meeting-token':'local-moss-smoke'}) as client:
        meeting=client.post('/api/meetings',json={'title':'本地联调 · 系统合成语音','mode':'file','engine':'moss','auto_minutes':True,'hotwords':'会议录音软件,李四'}).json()
        started=time.monotonic()
        with audio_path.open('rb') as audio:
            result=client.post(f"/api/meetings/{meeting['id']}/file",files={'file':('synthetic.wav',audio,'audio/wav')})
        assert result.status_code==200,result.text
        while time.monotonic()-started<300:
            detail=client.get('/api/meetings/'+meeting['id']).json()
            if detail['status'] in ('completed','failed','partial_failed'):break
            if detail['tasks'] and all(t['state'] in ('completed','failed') for t in detail['tasks']):break
            time.sleep(1)
        assert detail['status']=='completed',detail.get('error')
        assert detail['segments'] and detail['minutes']
        assert any('负责' in s['text'] for s in detail['segments'])
        if two_speakers:
            turns=json.loads((audio_path.parent/'turns.json').read_text('utf-8'))
            labels=[]
            for turn in turns:
                overlap={}
                for segment in detail['segments']:
                    amount=max(0,min(segment['end_ms'],turn['end_ms'])-max(segment['start_ms'],turn['start_ms']))
                    if amount and segment['speaker_id']:overlap[segment['speaker_id']]=overlap.get(segment['speaker_id'],0)+amount
                assert overlap
                labels.append(max(overlap,key=overlap.get))
            assert labels[0]==labels[2] and labels[1]==labels[3] and labels[0]!=labels[1],labels
        responses=[json.loads(file.read_text('utf-8')) for file in Path(directory).glob('*/run_*.response.json')]
        assert any(segment.get('embedding') for result in responses for segment in result['segments'])
        sid=detail['speakers'][0]['id']
        assert client.patch(f"/api/meetings/{meeting['id']}/speakers/{sid}",json={'name':'本地主持人'}).status_code==200
        assert '本地主持人' in client.get(f"/api/meetings/{meeting['id']}/export/txt").text
        report={'status':'PASS','device':'cpu','cloud_asr_key_configured':False,'seconds':round(time.monotonic()-started,2),
                'audio_seconds':detail['duration_ms']/1000,'segments':len(detail['segments']),'speakers':len(detail['speakers']),
                'action_items':len(detail['minutes']['data']['action_items']),'local_prompt':'official default; hotwords not applied',
                'speaker_embeddings':sum(bool(segment.get('embedding')) for result in responses for segment in result['segments']),
                'transcript':''.join(s['text'] for s in detail['segments']),
                'checks':['local file import','MOSS actual inference','CAM++ embeddings','minutes and candidate actions','rename persistence','export']}
        if two_speakers:report['turn_speakers']=[0 if label==labels[0] else 1 for label in labels]
        (ROOT/'artifacts'/('moss-two-speaker-smoke.json' if two_speakers else 'moss-workflow.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
