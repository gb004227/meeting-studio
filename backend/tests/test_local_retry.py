import wave
import pytest
from meeting_app import jobs as jobs_module
from meeting_app.audio import duration_ms
from meeting_app.store import Store
from meeting_app.vault import Vault


def write_audio(path,seconds):
    with wave.open(str(path),'wb') as output:
        output.setparams((1,2,16000,0,'NONE','not compressed'));output.writeframes(bytes(round(seconds*32000)))


@pytest.mark.asyncio
async def test_empty_failed_transcript_retry_shows_each_cpu_chunk_while_processing(tmp_path,monkeypatch):
    store=Store(tmp_path)
    store.save_settings({'moss_path':str(tmp_path/'missing-model')})
    mid=store.create_meeting('文件恢复','file','moss',auto_minutes=False)
    folder=tmp_path/mid;folder.mkdir();audio=folder/'audio.wav';write_audio(audio,121)
    empty=store.new_version(mid,'moss')
    store.update_meeting(mid,audio_path=str(audio),status='failed',error='Separator is not found, and chunk exceed the limit')
    snapshots=[];durations=[];events=[]
    def convert(source,destination,start,duration):write_audio(destination,min(duration,121-start))
    monkeypatch.setattr(jobs_module,'convert_audio',convert)
    class Model:
        async def transcribe(self,path,*args,**kwargs):
            length=duration_ms(path);durations.append(length)
            await kwargs['on_partial']('正在显示当前分段')
            meeting=store.meeting(mid)
            snapshots.append((meeting['current_version'],len(meeting['segments'])))
            return {'segments':[{'start_ms':0,'end_ms':length,'speaker':'S01','text':'这一分段已经完整识别。'}]}
        async def close(self):pass
    async def notify(mid,event):events.append(event)
    jobs=jobs_module.Jobs(store,Vault(tmp_path),tmp_path,notify);jobs.moss=Model()
    task=jobs.submit(mid,'transcribe')
    await jobs.active[task]
    meeting=store.meeting(mid)
    assert len(durations)==3 and max(durations)<=60000
    assert all(version!=empty for version,count in snapshots)
    assert [count for version,count in snapshots]==[0,1,2]
    assert any(event.get('partial')=='正在显示当前分段' for event in events)
    assert meeting['status']=='transcribed' and len(meeting['segments'])==3
    await jobs.close()
