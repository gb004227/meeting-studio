from types import SimpleNamespace
import pytest
from meeting_app import doubao


@pytest.mark.asyncio
async def test_transient_connection_failure_retries_before_any_audio(monkeypatch):
    calls=[];sent=[]
    class Socket:
        async def send(self,packet):sent.append(packet)
    async def connect(*args,**kwargs):
        calls.append(1)
        if len(calls)==1:raise TimeoutError()
        return Socket()
    async def no_wait(seconds):pass
    monkeypatch.setattr(doubao,'connect',connect)
    monkeypatch.setattr(doubao.asyncio,'sleep',no_wait)
    socket=await doubao.open_stream('test-key','test-resource')
    assert len(calls)==2 and len(sent)==1
    assert socket.meeting_sequence==1 and sent[0][1]>>4==1


@pytest.mark.asyncio
async def test_permission_failure_is_not_retried(monkeypatch):
    calls=[]
    async def connect(*args,**kwargs):
        calls.append(1)
        error=RuntimeError('not permitted')
        error.response=SimpleNamespace(status_code=403)
        raise error
    monkeypatch.setattr(doubao,'connect',connect)
    with pytest.raises(doubao.SpeechError,match='HTTP 403'):
        await doubao.open_stream('test-key','test-resource')
    assert len(calls)==1
