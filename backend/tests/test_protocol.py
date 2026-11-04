import gzip,json,struct
import pytest
from meeting_app.doubao import pack,unpack,normalize,SpeechError


def test_binary_request_has_length_and_compressed_json():
    value={'audio':{'rate':16000},'request':{'model_name':'bigmodel'}}
    frame=pack(value)
    assert frame[:4]==bytes([0x11,0x10,0x11,0])
    assert struct.unpack('>I',frame[4:8])[0]==len(frame)-8
    assert json.loads(gzip.decompress(frame[8:]))==value


def test_final_audio_packet_has_last_flag():
    frame=pack(b'\0\0'*3200,audio=True,last=True)
    assert frame[1]==0x22
    assert gzip.decompress(frame[8:])==b'\0\0'*3200


def test_real_protocol_uses_monotonic_signed_sequence():
    frame=pack(b'\0\0',audio=True,last=True,sequence=8)
    assert frame[1]==0x23
    assert struct.unpack('>i',frame[4:8])[0]==-8
    assert struct.unpack('>I',frame[8:12])[0]==len(frame)-12


def test_vendor_sequence_response_is_decoded():
    value={'result':{'text':'你好'}}
    payload=gzip.compress(json.dumps(value).encode())
    frame=bytes([0x11,0x93,0x11,0])+struct.pack('>iI',-3,len(payload))+payload
    assert unpack(frame)==value


def test_vendor_error_packet_is_not_success():
    payload=json.dumps({'message':'resource not enabled'}).encode()
    frame=bytes([0x11,0xf0,0x10,0])+struct.pack('>II',45000030,len(payload))+payload
    with pytest.raises(SpeechError,match='45000030'): unpack(frame)


def test_unstable_sentence_does_not_become_saved_text():
    value={'result':{'utterances':[{'start_time':0,'end_time':2000,'text':'稳定句','definite':True,'additions':{'speaker':'2'}},{'start_time':2000,'end_time':2600,'text':'未定','definite':False}]}}
    parts,partial=normalize(value,offset=5000,final_only=True)
    assert len(parts)==1 and parts[0]['start_ms']==5000 and parts[0]['speaker']=='2'
    assert partial=='未定'


def test_actual_asr2_speaker_field_is_normalized():
    value={'result':{'utterances':[{'start_time':0,'end_time':2000,'text':'实际结果','definite':True,'additions':{'speaker_id':'0'}}]}}
    parts,_=normalize(value,final_only=True)
    assert parts[0]['speaker']=='0'


def test_early_cloud_text_is_visible_before_utterance_metadata_arrives():
    parts,partial=normalize({'result':{'text':'正在实时识别'}},final_only=True)
    assert not parts and partial=='正在实时识别'


def test_cloud_partial_does_not_repeat_committed_prefix():
    parts,partial=normalize({'result':{'text':'已经确认。继续说话','utterances':[{'start_time':0,'end_time':1000,'text':'已经确认。','definite':True}]}},final_only=True)
    assert len(parts)==1 and partial=='继续说话'
