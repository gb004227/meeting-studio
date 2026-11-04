import sys
import wave
import pytest
from meeting_app import local


@pytest.mark.asyncio
@pytest.mark.parametrize('streaming',[False,True])
async def test_local_worker_accepts_large_results_and_separate_caption_events(tmp_path,monkeypatch,streaming):
    backend=tmp_path/'backend';backend.mkdir()
    (backend/'moss_worker.py').write_text('''import json,sys
sys.stdout.reconfigure(encoding='utf-8')
for line in sys.stdin:
    job=json.loads(line)
    if job.get('stream'):
        print(json.dumps({'job_id':job['job_id'],'event':'partial','partial':'生成中的字幕'},ensure_ascii=False),flush=True)
    print(json.dumps({'job_id':job['job_id'],'ok':True,'segments':[{'start_ms':0,'end_ms':2000,'speaker':'S01','text':'长结果'*30000}],'truncated':False},ensure_ascii=False),flush=True)
''','utf-8')
    audio=tmp_path/'audio.wav'
    with wave.open(str(audio),'wb') as output:
        output.setparams((1,2,16000,0,'NONE','not compressed'));output.writeframes(bytes(6400))
    monkeypatch.setattr(local,'ROOT',tmp_path)
    monkeypatch.setattr(local,'model_files_ready',lambda path:True)
    captions=[]
    async def caption(text):captions.append(text)
    runner=local.MossRunner()
    try:
        kwargs={'on_partial':caption} if streaming else {}
        result=await runner.transcribe(audio,{'moss_path':str(tmp_path),'moss_python':sys.executable},**kwargs)
        assert len(result['segments'][0]['text'])==90000
        if streaming:assert captions==['生成中的字幕']
    finally:await runner.close()
