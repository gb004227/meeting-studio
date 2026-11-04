import pytest
from meeting_app.minutes import extract_minutes


@pytest.mark.parametrize('expression,expected',[
    ('本周五','2026-11-06'),('本周日','2026-11-08'),
    ('本周天','2026-11-08'),('大后天','2026-11-06'),
])
def test_action_dates_use_chinese_weekday_and_relative_day_meanings(expression,expected):
    meeting={'id':'m','title':'日期验证','created_at':'2026-11-03T03:00:00+00:00','current_version':'v','speakers':[],
             'segments':[{'id':'segment','speaker_id':None,'text':f'我负责整理材料，{expression}前提交。'}]}
    result=extract_minutes(meeting)
    assert result['action_items'][0]['due_date']==expected
