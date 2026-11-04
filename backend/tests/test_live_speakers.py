import asyncio
import gzip
import json
import struct
import pytest
from meeting_app import live
from meeting_app.store import Store
from meeting_app.vault import Vault


@pytest.mark.asyncio
async def test_live_text_is_visible_while_voice_matching_is_still_loading(tmp_path,monkeypatch):
    store=Store(tmp_path)
    mid=store.create_meeting('字幕不等分人','realtime','doubao',auto_minutes=False)
    release=asyncio.Event();packets=asyncio.Queue()
    payload={'result':{'utterances':[{'start_time':0,'end_time':2000,'text':'实时显示的完整发言','definite':True,'additions':{'speaker_id':'0'}}]}}
    def response(final=False):
        data=gzip.compress(json.dumps(payload).encode())
        return bytes([0x11,0x93 if final else 0x91,0x11,0])+struct.pack('>iI',-2 if final else 1,len(data))+data
    class Socket:
        meeting_sequence=1
        async def send(self,packet):await packets.put(response(bool(packet[1]&2)))
        async def close(self):await packets.put(None)
        async def __aiter__(self):
            while True:
                value=await packets.get()
                if value is None:return
                yield value
    async def connect(*args):return Socket()
    monkeypatch.setattr(live,'open_stream',connect)
    class FakeJobs:
        def speaker_helper_ready(self,settings):return True
        async def cloud_speakers(self,path,parts,settings,cache):
            await release.wait()
            result=[]
            for part in parts:
                fixed=part|{'speaker':f"acoustic/{part['start_ms']}",'embedding':[1,0],'prefer_embedding':True}
                cache[(part['start_ms'],part['end_ms'],part['text'])]=fixed
                result.append(fixed)
            return result
    async def notify(*args):pass
    recording=live.LiveRecording(mid,store,Vault(tmp_path),FakeJobs(),tmp_path,notify)
    await recording.start()
    try:
        await recording.audio(b'\0\0'*32000)
        await asyncio.sleep(.05)
        before=store.meeting(mid)
        assert before['segments'][0]['text']=='实时显示的完整发言'
        assert before['segments'][0]['speaker_id'] is None
        assert not release.is_set()
        release.set()
        await asyncio.sleep(.05)
        assert store.meeting(mid)['segments'][0]['speaker_id'] is not None
    finally:
        release.set()
        await recording.stop()
    assert store.meeting(mid)['error']==''
