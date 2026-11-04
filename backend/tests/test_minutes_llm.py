import json
import httpx
import pytest
from meeting_app import minutes
from meeting_app.store import Store


@pytest.mark.asyncio
async def test_text_model_adapter_sends_evidence_and_returns_structured_minutes(tmp_path,monkeypatch):
    store=Store(tmp_path)
    mid=store.create_meeting('需求会议','file','moss')
    vid=store.new_version(mid,'moss')
    store.add_segments(mid,vid,[{'start_ms':0,'end_ms':3000,'speaker':'S01','text':'我负责提交会议方案。'}],'test')
    meeting=store.meeting(mid);segment=meeting['segments'][0]
    calls=[]
    def respond(request):
        calls.append(request)
        body=json.loads(request.content)
        material=json.loads(body['messages'][1]['content'])
        assert material['segments'][0]['id']==segment['id']
        answer={'summary':['明确由发言人提交会议方案。'],'topics':[],'decisions':[],
                'action_items':[{'task':'提交会议方案','owner_speaker_id':segment['speaker_id'],
                                 'due_date':None,'evidence_segment_ids':[segment['id']]}],'pending_questions':[]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(answer)}}]})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(minutes.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(respond),**kwargs))
    result,source=await minutes.generate_minutes(meeting,{'llm_base_url':'https://text-model.example/api/v3','llm_model':'test-model'},'test-text-key')
    assert str(calls[0].url)=='https://text-model.example/api/v3/chat/completions'
    assert calls[0].headers['Authorization']=='Bearer test-text-key'
    assert result['generator']=='ai' and source=='ai'
    assert result['action_items'][0]['source_transcript_version_id']==vid
    assert result['action_items'][0]['evidence_segment_ids']==[segment['id']]
