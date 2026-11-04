import asyncio
import base64
import gzip
import json
import inspect
from pathlib import Path
import struct
import uuid
import httpx
from websockets.asyncio.client import connect

WS_URL = 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async'
FLASH_URL = 'https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash'
STANDARD_URL = 'https://openspeech.bytedance.com/api/v3/auc/bigmodel/'


class SpeechError(RuntimeError):
    pass


def headers(key, resource, request_id=None):
    if not key:
        raise SpeechError('请先在设置中保存豆包语音识别 API Key。')
    return {'X-Api-Key':key,'X-Api-Resource-Id':resource,'X-Api-Request-Id':request_id or str(uuid.uuid4()),'X-Api-Connect-Id':str(uuid.uuid4())}


def request_options(hotwords='', file_mode=False):
    value = {'model_name':'bigmodel','enable_itn':True,'enable_punc':True,'enable_ddc':False,
             'enable_speaker_info':True,'show_utterances':True}
    if file_mode:
        value['ssd_version']='300'
    else:
        value['ssd_version']='200'
        value.update(enable_nonstream=True,result_type='full',end_window_size=800)
    words = [word.strip() for word in hotwords.replace('，',',').replace('\n',',').split(',') if word.strip()]
    if words:
        value['corpus']={'context':json.dumps({'hotwords':[{'word':w} for w in words]},ensure_ascii=False)}
    return value


def pack(payload, audio=False, last=False, sequence=None):
    raw = payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False).encode('utf-8')
    raw = gzip.compress(raw)
    flags=(3 if last else 1) if sequence is not None else (2 if last else 0)
    header=bytes([0x11,((2 if audio else 1)<<4)|flags,0x01 if audio else 0x11,0])
    if sequence is not None: header+=struct.pack('>i',-abs(sequence) if last else sequence)
    return header+struct.pack('>I',len(raw))+raw


def unpack(data):
    if isinstance(data,str): return json.loads(data)
    if len(data)<8: raise SpeechError('豆包返回了不完整的协议包。')
    offset=(data[0]&15)*4
    kind=data[1]>>4
    flags=data[1]&15
    code=0
    if kind==15:
        code=struct.unpack_from('>I',data,offset)[0]; offset+=4
    elif flags&1:
        offset+=4
    size=struct.unpack_from('>I',data,offset)[0]; offset+=4
    raw=data[offset:offset+size]
    if data[2]&15==1: raw=gzip.decompress(raw)
    try: value=json.loads(raw)
    except (ValueError,UnicodeDecodeError): raise SpeechError('豆包返回了无法解析的识别结果。')
    if code or value.get('code',1000) not in (0,1000,20000000):
        raise SpeechError(f"豆包语音服务返回错误 {code or value.get('code')}：{str(value.get('message','请检查资源权限与余额'))[:240]}")
    return value


def normalize(payload, offset=0, final_only=False):
    result=payload.get('result',{})
    if isinstance(result,list): result=result[0] if result else {}
    segments=[]
    partial=[]
    for item in result.get('utterances',[]) or []:
        if final_only and not item.get('definite',False):
            partial.append(item.get('text','')); continue
        additions=item.get('additions') or {}
        speaker=additions.get('speaker',additions.get('speaker_id',item.get('speaker_id',item.get('speaker'))))
        segments.append({'start_ms':offset+int(item.get('start_time',0)),'end_ms':offset+int(item.get('end_time',0)),
                         'text':item.get('text',''),'speaker':speaker})
    preview=''.join(partial)
    if final_only and not preview:
        text=result.get('text','')
        committed=''.join(part['text'] for part in segments)
        if text.startswith(committed):preview=text[len(committed):].strip()
    return segments,preview


def check_response(response):
    code=response.headers.get('X-Api-Status-Code','')
    if code in ('20000000','20000001','20000002','20000003'):
        return code
    if response.status_code in (401,403) or code.startswith('45'):
        raise SpeechError(f'豆包鉴权或资源权限不足（HTTP {response.status_code} / {code or "无状态码"}）。请确认该语音 Key 已开通当前所选资源。')
    if response.status_code>=400 or code:
        raise SpeechError(f'豆包文件识别失败（HTTP {response.status_code} / {code or "服务异常"}），请检查余额和资源配置。')
    raise SpeechError('语音服务未返回业务状态码，请检查网络代理和接口配置。')


async def transcribe_flash(path: Path, key, resource, hotwords=''):
    payload={'user':{'uid':'meeting_studio'},'audio':{'data':base64.b64encode(path.read_bytes()).decode('ascii')},
             'request':request_options(hotwords,True)}
    async with httpx.AsyncClient(timeout=httpx.Timeout(900,connect=30)) as client:
        response=await client.post(FLASH_URL,headers=headers(key,resource)|{'X-Api-Sequence':'-1'},json=payload)
    code=check_response(response)
    if code=='20000003': return {}
    return response.json()


async def transcribe_standard(url,key,resource,hotwords='',on_submitted=None,request_id=None):
    rid=request_id or str(uuid.uuid4())
    h=headers(key,resource,rid)
    async with httpx.AsyncClient(timeout=90) as client:
        if not request_id:
            response=await client.post(STANDARD_URL+'submit',headers=h|{'X-Api-Sequence':'-1'},json={
                'user':{'uid':'meeting_studio'},'audio':{'url':url},'request':request_options(hotwords,True)})
            check_response(response)
            if on_submitted: on_submitted(rid)
        for attempt in range(720):
            await asyncio.sleep(min(2+attempt//3,10))
            response=await client.post(STANDARD_URL+'query',headers=h,json={})
            code=check_response(response)
            if code=='20000000': return response.json()
            if code=='20000003': return {}
    raise SpeechError('云端任务仍在处理，请稍后重试查询；请勿重复提交同一文件。')


async def open_stream(key,resource,hotwords=''):
    for attempt in range(3):
        ws=None
        try:
            ws=await connect(WS_URL,additional_headers=headers(key,resource),open_timeout=30,ping_interval=None,max_size=16*1024*1024)
            ws.meeting_sequence=1
            await ws.send(pack({'user':{'uid':'meeting_studio'},'audio':{'format':'pcm','rate':16000,'bits':16,'channel':1},'request':request_options(hotwords)},sequence=1))
            return ws
        except Exception as exc:
            if ws:
                try: await ws.close()
                except Exception: pass
            if isinstance(exc,SpeechError): raise
            status=getattr(getattr(exc,'response',None),'status_code',None)
            # Retry only before audio is sent; do not resend a charged recording.
            if status not in (400,401,403) and attempt<2:
                await asyncio.sleep(attempt+1)
                continue
            reason='（连接超时）' if isinstance(exc,TimeoutError) else ''
            raise SpeechError(f'无法连接豆包实时识别{f"（HTTP {status}）" if status else reason}。请检查语音 Key、实时资源权限和网络。') from None


async def send_audio(ws,data,last=False):
    ws.meeting_sequence+=1
    await ws.send(pack(data,audio=True,last=last,sequence=ws.meeting_sequence))


async def transcribe_stream_file(pcm,key,resource,hotwords='',on_result=None,on_progress=None):
    """Same ASR 2.0 resource as live recording; does not require file API permission."""
    ws=await open_stream(key,resource,hotwords)
    final_payload={}
    received_final=False
    async def receive():
        nonlocal final_payload,received_final
        async for raw in ws:
            payload=unpack(raw)
            if payload.get('result'):
                final_payload=payload
                if on_result:
                    response=on_result(payload)
                    if inspect.isawaitable(response):await response
            if isinstance(raw,bytes) and raw[1]&2:
                received_final=True
                break
    receiver=asyncio.create_task(receive())
    try:
        for index in range(0,len(pcm),6400):
            if receiver.done():
                receiver.result()
                raise SpeechError('语音服务在文件发送完成前结束，当前结果可能不完整；音频已保留，请重新转写。')
            chunk=pcm[index:index+6400]
            await send_audio(ws,chunk)
            if on_progress and index%64000==0: on_progress(min(99,round(100*index/max(len(pcm),1))))
            # This resource requires real-time pacing even for existing files.
            # Sending faster can silently lose later audio at the service.
            await asyncio.sleep(len(chunk)/32000)
        await send_audio(ws,b'',True)
        try:
            await asyncio.wait_for(receiver,120)
        except asyncio.TimeoutError:
            raise SpeechError('音频已发送，但等待云端最终结果超时；音频和已收到的文字仍保留，请检查网络后重试。') from None
        if not received_final:
            raise SpeechError('语音连接未返回完整结束结果，已保留音频及收到的文字，请重新转写。')
        return final_payload
    finally:
        if not receiver.done(): receiver.cancel()
        await ws.close()
