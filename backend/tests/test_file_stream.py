import asyncio
import gzip
import json
import struct
import time
import pytest
from meeting_app import doubao


class StreamService:
    def __init__(self,early=False,final=True):
        self.meeting_sequence=1
        self.early=early;self.final=final
        self.ready=asyncio.Event();self.sent=[];self.closed=False

    async def send(self,packet):
        self.sent.append(time.monotonic())
        if self.early or packet[1]&2:self.ready.set()

    async def __aiter__(self):
        await self.ready.wait()
        if self.final:
            payload=gzip.compress(json.dumps({'result':{'text':'完整结果'}}).encode())
            yield bytes([0x11,0x93,0x11,0])+struct.pack('>iI',-1,len(payload))+payload

    async def close(self):self.closed=True


@pytest.mark.asyncio
async def test_file_stream_obeys_real_audio_cadence(monkeypatch):
    service=StreamService()
    async def open_stream(*args):return service
    monkeypatch.setattr(doubao,'open_stream',open_stream)
    result=await doubao.transcribe_stream_file(bytes(12800),'test-key','test-resource')
    assert result['result']['text']=='完整结果'
    assert len(service.sent)==3 and service.sent[1]-service.sent[0]>=.18
    assert service.closed


@pytest.mark.asyncio
async def test_early_final_cannot_mark_unsent_audio_successful(monkeypatch):
    service=StreamService(early=True)
    async def open_stream(*args):return service
    monkeypatch.setattr(doubao,'open_stream',open_stream)
    with pytest.raises(doubao.SpeechError,match='文件发送完成前结束'):
        await doubao.transcribe_stream_file(bytes(12800),'test-key','test-resource')
    assert len(service.sent)==1 and service.closed


@pytest.mark.asyncio
async def test_clean_close_without_final_result_is_incomplete(monkeypatch):
    service=StreamService(final=False)
    async def open_stream(*args):return service
    monkeypatch.setattr(doubao,'open_stream',open_stream)
    with pytest.raises(doubao.SpeechError,match='未返回完整结束结果'):
        await doubao.transcribe_stream_file(bytes(6400),'test-key','test-resource')
    assert service.closed
