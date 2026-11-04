import numpy as np
from meeting_app.moss_stream import CaptionStreamer,caption_text


def test_caption_removes_timestamps_and_unfinished_control_tokens():
    assert caption_text('[0.13][S01]大家好。[3.41][4.')=='大家好。'


def test_sliding_preview_does_not_repeat_already_saved_segments():
    assert caption_text('[0.0][S01]已保存。[2.0][3.0][S02]新的字幕[5.0]',2000)=='新的字幕'


def test_caption_is_emitted_before_generation_finishes():
    class Tokenizer:
        def decode(self,tokens,**kwargs):return ''.join({1:'[0.0]',2:'[S01]',3:'大家',4:'好。',5:'[2.0]'}[token] for token in tokens)
    captions=[]
    observer=CaptionStreamer(Tokenizer(),captions.append)
    observer.put(np.array([[999]]))
    for token in (1,2,3):observer.put(np.array([token]))
    assert captions==['大家']
    for token in (4,5):observer.put(np.array([token]))
    observer.end()
    assert captions[-1]=='大家好。'
