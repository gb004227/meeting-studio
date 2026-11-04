import pytest
from meeting_app.store import Store
from meeting_app.vault import Vault
from meeting_app.jobs import Jobs


@pytest.mark.asyncio
@pytest.mark.parametrize('minutes_failure',[False,True])
async def test_minutes_success_clears_only_minutes_errors(tmp_path,minutes_failure):
    store=Store(tmp_path)
    mid=store.create_meeting('会议','file','doubao')
    vid=store.new_version(mid,'doubao')
    store.add_segments(mid,vid,[{'start_ms':0,'end_ms':2000,'text':'我负责整理会议方案。','speaker':'0'}],'test')
    store.publish(vid)
    error='上次纪要服务调用失败' if minutes_failure else '实时识别有中断，请重新转写以补齐。'
    store.update_meeting(mid,status='partial_failed',error=error)
    if minutes_failure:
        failed=store.new_task(mid,'minutes',{})
        store.task_update(failed,state='failed',error=error)
    async def notify(*args):pass
    jobs=Jobs(store,Vault(tmp_path),tmp_path,notify)
    task_id=jobs.submit(mid,'minutes')
    await jobs.active[task_id]
    meeting=store.meeting(mid)
    assert meeting['minutes'] is not None
    assert meeting['error']==('' if minutes_failure else error)
    assert meeting['status']==('completed' if minutes_failure else 'partial_failed')
    await jobs.close()
