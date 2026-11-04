from meeting_app.store import Store


def test_acoustic_correction_can_split_provider_merged_people_without_losing_name(tmp_path):
    store=Store(tmp_path)
    mid=store.create_meeting('分人校正','file','doubao')
    original=store.new_version(mid,'doubao')
    store.add_segments(mid,original,[
        {'start_ms':0,'end_ms':2000,'text':'女声发言','speaker':'0'},
        {'start_ms':3000,'end_ms':5000,'text':'男声发言','speaker':'0'},
    ],'provider')
    first=store.meeting(mid)['speakers'][0]['id']
    store.rename_speaker(mid,first,'主持人')
    corrected=store.new_version(mid,'doubao',original)
    store.add_segments(mid,corrected,[
        {'start_ms':0,'end_ms':2000,'text':'女声发言','speaker':'acoustic/0','embedding':[1,0],'prefer_embedding':True},
        {'start_ms':3000,'end_ms':5000,'text':'男声发言','speaker':'acoustic/3000','embedding':[0,1],'prefer_embedding':True},
        {'start_ms':6000,'end_ms':8000,'text':'女声再次发言','speaker':'acoustic/6000','embedding':[1,0],'prefer_embedding':True},
    ],'acoustic',original)
    meeting=store.meeting(mid)
    assert len(meeting['speakers'])==2
    assert meeting['segments'][0]['speaker_id']==meeting['segments'][2]['speaker_id']==first
    assert meeting['segments'][1]['speaker_id']!=first
    assert next(p['name'] for p in meeting['speakers'] if p['id']==first)=='主持人'
