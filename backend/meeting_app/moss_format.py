def generate_with_format_retry(generate,parse,prompt,default_prompt):
    result=generate(prompt)
    segments=parse(result['text'])
    initial=None
    if result['text'].strip() and not segments:
        initial=result['text']
        retry_prompt=default_prompt if prompt!=default_prompt else default_prompt+' 请严格使用[起始秒数][S01]语音原文[结束秒数]的格式，不省略时间戳。'
        result=generate(retry_prompt)
        segments=parse(result['text'])
        if not segments:
            raise ValueError('MOSS 连续两次未返回有效的时间戳格式；音频已保留，可重新转写。')
    return result,segments,initial
