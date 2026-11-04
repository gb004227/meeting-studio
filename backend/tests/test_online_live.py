import asyncio
import wave
import pytest
from meeting_app.live import LiveRecording
from meeting_app.store import Store
from meeting_app.vault import Vault


@pytest.mark.asyncio
async def test_local_online_caption_updates_before_stop_and_queues_moss_refinement(tmp_path):
    store=Store(tmp_path);mid=store.create_meeting('本地流式','realtime','moss',auto_minutes=False)
    events=[];submitted=[]
    class Session:
        count=0
        def accept(self,data=b'',final=False,offset_ms=None):
            if final:return {'text':'','endpoint':True,'start_ms':400,'end_ms':400}
            self.count+=1
            return {'text':'正在说的话','endpoint':self.count==2,'start_ms':0,'end_ms':self.count*200}
    class Jobs:
        def online_ready(self,settings):return True
        def speaker_helper_ready(self,settings):return False
        async def open_local_stream(self,settings):return Session()
        def submit(self,*args):submitted.append(args)
    async def notify(mid,event):events.append(event)
    recording=LiveRecording(mid,store,Vault(tmp_path),Jobs(),tmp_path,notify)
    await recording.start()
    try:
        await recording.audio(b'\0\0'*3200)
        await asyncio.sleep(.05)
        assert any(event.get('partial')=='正在说的话' and event.get('refresh') is False for event in events)
        assert store.meeting(mid)['segments']==[]
        await recording.audio(b'\0\0'*3200)
        await asyncio.sleep(.05)
        assert store.meeting(mid)['segments'][0]['text']=='正在说的话'
    finally:await recording.stop()
    assert submitted[0][1:] == ('transcribe',{'engine':'moss'})
    with wave.open(str(recording.path),'rb') as audio:assert audio.getnframes()==6400
