import pytest
from meeting_app.moss_format import generate_with_format_retry


def test_recognized_text_without_timestamps_is_retried_not_discarded():
    calls=[]
    def generate(prompt):
        calls.append(prompt)
        return {'text':'[S01]实际发言' if len(calls)==1 else '[0.1][S01]实际发言[2.0]'}
    def parse(text):
        return [{'text':'实际发言'}] if text.startswith('[0.1]') else []
    result,segments,initial=generate_with_format_retry(generate,parse,'热词提示','标准提示')
    assert calls==['热词提示','标准提示']
    assert segments[0]['text']=='实际发言'
    assert initial=='[S01]实际发言'
    assert result['text'].startswith('[0.1]')


@pytest.mark.parametrize('second',['仍然没有时间戳',''])
def test_repeated_invalid_format_is_failure_instead_of_empty_success(second):
    outputs=iter(['[S01]实际发言',second])
    with pytest.raises(ValueError,match='未返回有效的时间戳'):
        generate_with_format_retry(lambda prompt:{'text':next(outputs)},lambda text:[],'提示','标准提示')


def test_silent_output_does_not_create_invented_segments():
    result,segments,initial=generate_with_format_retry(lambda prompt:{'text':''},lambda text:[],'提示','标准提示')
    assert segments==[] and initial is None
