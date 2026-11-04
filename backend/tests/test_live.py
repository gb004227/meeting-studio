import asyncio
import wave
import pytest
from meeting_app.store import Store
from meeting_app.vault import Vault
from meeting_app.live import LiveRecording


@pytest.mark.asyncio
async def test_slow_local_preview_never_skips_or_blocks_saved_audio(tmp_path):
    store=Store(tmp_path)
    mid=store.create_meeting('本地录音','realtime','moss')
    requests=[];warnings=[];submitted=[]
    class FakeMoss:
        lock=asyncio.Lock()
        async def transcribe(self,path,*args,**kwargs):
            with wave.open(str(path),'rb') as w:requests.append(w.getnframes())
            await asyncio.sleep(.01)
            return {'segments':[{'start_ms':0,'end_ms':1500,'text':'已识别发言','speaker':'S01'}],'elapsed':1}
    class FakeJobs:
        moss=FakeMoss()
        def online_ready(self,settings):return False
        def submit(self,*args):submitted.append(args)
    async def notify(mid,event):
        if event['type']=='warning':warnings.append(event['message'])
    recording=LiveRecording(mid,store,Vault(tmp_path),FakeJobs(),tmp_path,notify)
    await recording.start()
    try:
        # The producer outruns inference; every audio sample must still reach disk.
        for _ in range(225):await recording.audio(b'\1\0'*3200)
        await asyncio.sleep(.05)
        assert requests==[48000]  # The first 3s, never an arbitrary latest window.
        assert recording.local_covered_ms==3000
        assert recording.preview_paused and warnings
    finally:await recording.stop()
    with wave.open(str(recording.path),'rb') as w:assert w.getnframes()==225*3200
    assert store.meeting(mid)['duration_ms']==45000
    assert submitted[0][1:] == ('transcribe',{'engine':'moss'})
