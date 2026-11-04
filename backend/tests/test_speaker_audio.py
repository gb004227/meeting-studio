import numpy as np
from meeting_app.speaker_audio import enough_speech_for_embedding


def test_short_word_with_long_silence_is_not_a_reliable_person_sample():
    audio=np.zeros(40000,dtype=np.float32)
    audio[:6400]=.1*np.sin(np.arange(6400)*.1)
    assert not enough_speech_for_embedding(audio,16000)


def test_clear_longer_utterance_is_eligible_for_voice_matching():
    audio=.1*np.sin(np.arange(32000)*.1)
    assert enough_speech_for_embedding(audio,16000)
