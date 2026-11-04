import json
from pathlib import Path
import pytest
from meeting_app.store import Store
from meeting_app.minutes import extract_minutes,validate_minutes
from meeting_app.vault import Vault


@pytest.fixture
def meeting(tmp_path):
    store=Store(tmp_path)
    mid=store.create_meeting('项目会议','file','doubao')
    vid=store.new_version(mid,'doubao')
    store.add_segments(mid,vid,[{'start_ms':0,'end_ms':4000,'text':'我负责整理方案，本周五前提交。','speaker':'1'}],'run1')
    return store,mid,vid


def test_name_is_persisted_and_owning_actions_follow_name(meeting,tmp_path):
    store,mid,vid=meeting
    before=store.meeting(mid)
    sid=before['speakers'][0]['id']
    payload=extract_minutes(before)
    assert payload['action_items'][0]['owner_speaker_id']==sid
    store.save_minutes(mid,vid,payload,'extractive')
    store.rename_speaker(mid,sid,'张三')
    restored=Store(tmp_path).meeting(mid)
    assert restored['speakers'][0]['name']=='张三'
    assert restored['minutes']['data']['action_items'][0]['owner_speaker_id']==sid


def test_edit_creates_snapshot_and_leaves_original_evidence(meeting):
    store,mid,original=meeting
    store.publish(original)
    segment=store.meeting(mid)['segments'][0]
    store.edit_segment(mid,segment['id'],text='人工校对后的方案。')
    current=store.meeting(mid)
    assert current['current_version']!=original
    assert current['segments'][0]['text']=='人工校对后的方案。'
    with store.connection() as db:
        assert db.execute('SELECT text FROM segments WHERE version_id=?',(original,)).fetchone()[0]=='我负责整理方案，本周五前提交。'


def test_late_machine_result_cannot_replace_human_edit(meeting):
    store,mid,vid=meeting
    segment=store.meeting(mid)['segments'][0]
    store.edit_segment(mid,segment['id'],text='已确认的文字。')
    store.add_segments(mid,vid,[{'start_ms':0,'end_ms':4000,'text':'迟到的机器结果','speaker':'1'}],'run1')
    assert store.meeting(mid)['segments'][0]['text']=='已确认的文字。'


def test_overlapping_requests_match_utterance_not_label(meeting):
    store,mid,vid=meeting
    sid=store.meeting(mid)['speakers'][0]['id']
    store.rename_speaker(mid,sid,'张三')
    second=store.new_version(mid,'moss',vid)
    store.add_segments(mid,second,[{'start_ms':100,'end_ms':4100,'text':'我负责整理方案，本周五前提交。','speaker':'S09'}],'run2',vid)
    assert store.meeting(mid)['segments'][0]['speaker_id']==sid
    assert store.meeting(mid)['speakers'][0]['name']=='张三'


def test_repeated_final_response_is_idempotent(meeting):
    store,mid,vid=meeting
    store.add_segments(mid,vid,[{'start_ms':0,'end_ms':4000,'text':'我负责整理方案，本周五前提交。','speaker':'1'}],'run1')
    assert len(store.meeting(mid)['segments'])==1


def test_same_number_in_new_request_is_not_identity(meeting):
    store,mid,vid=meeting
    old=store.meeting(mid)['speakers'][0]['id']
    store.add_segments(mid,vid,[{'start_ms':10000,'end_ms':13000,'text':'另一个人的发言。','speaker':'1'}],'different-request')
    assert store.meeting(mid)['segments'][1]['speaker_id']!=old


def test_gallery_matches_returning_speaker_without_overlap(tmp_path):
    store=Store(tmp_path); mid=store.create_meeting('test','file','moss'); vid=store.new_version(mid,'moss')
    store.add_segments(mid,vid,[{'start_ms':0,'end_ms':3000,'text':'第一次发言','speaker':'S01','embedding':[1,0,0]}],'chunk1')
    sid=store.meeting(mid)['speakers'][0]['id']
    store.add_segments(mid,vid,[{'start_ms':10000,'end_ms':13000,'text':'中间的另一个人','speaker':'S01','embedding':[0,1,0]}],'chunk2')
    store.add_segments(mid,vid,[{'start_ms':30000,'end_ms':33000,'text':'第一位再次发言','speaker':'S09','embedding':[.99,.01,0]}],'chunk3')
    assert store.meeting(mid)['segments'][-1]['speaker_id']==sid


def test_unknown_owner_is_not_invented(meeting):
    store,mid,vid=meeting
    store.add_segments(mid,vid,[{'start_ms':5000,'end_ms':8000,'text':'这个任务需要提交，但负责人尚未明确。','speaker':'1'}],'run1')
    payload=extract_minutes(store.meeting(mid))
    assert payload['action_items'][1]['owner_speaker_id'] is None
    assert payload['action_items'][1]['due_date'] is None


def test_invalid_ai_evidence_is_rejected(meeting):
    store,mid,vid=meeting
    with pytest.raises(ValueError,match='不存在的原文'):
        validate_minutes({'summary':['总结'],'decisions':[{'text':'无依据决定','evidence_segment_ids':['invented']}],'action_items':[]},store.meeting(mid))


def test_task_survives_restart(meeting,tmp_path):
    store,mid,vid=meeting
    task=store.new_task(mid,'transcribe',{'engine':'moss'})
    assert Store(tmp_path).pending_tasks()[0]['id']==task


def test_dpapi_never_stores_plaintext(tmp_path):
    vault=Vault(tmp_path)
    secret='test-only-secret-not-a-real-key'
    vault.set('test',secret)
    assert secret.encode() not in vault.path.read_bytes()
    assert Vault(tmp_path).get('test')==secret


def test_merge_resolves_old_identity_without_rewriting_evidence(meeting):
    store,mid,vid=meeting
    original=store.meeting(mid)['speakers'][0]['id']
    new=store.create_speaker(mid,'同一位张三')
    store.publish(vid)
    store.merge_speakers(mid,original,new)
    current=store.meeting(mid)
    assert len(current['speakers'])==1
    assert current['segments'][0]['speaker_id']==new
    with store.connection() as db:
        assert db.execute('SELECT speaker_id FROM segments WHERE version_id=?',(vid,)).fetchone()[0]==original
    following=store.new_version(mid,'moss',vid)
    store.add_segments(mid,following,[{'start_ms':0,'end_ms':4000,'text':'同一发言再次识别','speaker':'S09'}],'new',vid)
    assert store.meeting(mid)['segments'][0]['speaker_id']==new


def test_human_minutes_revision_does_not_override_prior_version(meeting):
    store,mid,vid=meeting
    original=extract_minutes(store.meeting(mid))
    old_id=store.save_minutes(mid,vid,original,'extractive')
    store.edit_minutes(mid,['用户整理后的结论'])
    assert store.meeting(mid)['minutes']['data']['summary']==['用户整理后的结论']
    with store.connection() as db:
        saved=json.loads(db.execute('SELECT payload FROM minutes WHERE id=?',(old_id,)).fetchone()[0])
    assert saved['summary']!=['用户整理后的结论']
