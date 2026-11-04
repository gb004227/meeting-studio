import asyncio
from contextlib import asynccontextmanager
import csv
import io
import json
from pathlib import Path
import shutil
import wave
from fastapi import FastAPI,Request,HTTPException,WebSocket,WebSocketDisconnect,UploadFile,File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse,Response
from .config import DATA,TOKEN,model_files_ready
from .store import Store
from .vault import Vault
from .jobs import Jobs
from .live import LiveRecording
from .doubao import transcribe_flash,open_stream,send_audio,unpack

store=Store(DATA); vault=Vault(DATA)
subscribers={}; recordings={}


async def notify(mid,event):
    for ws in list(subscribers.get(mid,set())):
        try: await ws.send_json(event)
        except Exception: subscribers.get(mid,set()).discard(ws)


jobs=Jobs(store,vault,DATA,notify)


@asynccontextmanager
async def lifespan(app):
    await jobs.recover()
    yield
    for recording in list(recordings.values()): await recording.stop()
    await jobs.close()


app=FastAPI(title='听会本地服务',lifespan=lifespan,docs_url=None,redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5173','http://localhost:5173','null'],allow_credentials=False,allow_methods=['*'],allow_headers=['*'])


@app.middleware('http')
async def authorization(request:Request,call_next):
    if request.method=='OPTIONS':
        return await call_next(request)
    if request.url.path!='/health' and TOKEN and request.headers.get('x-meeting-token')!=TOKEN and request.query_params.get('token')!=TOKEN:
        return Response('Unauthorized',401)
    return await call_next(request)


@app.exception_handler(ValueError)
async def bad_input(request,error): return Response(json.dumps({'detail':str(error)},ensure_ascii=False),status_code=400,media_type='application/json')


@app.exception_handler(KeyError)
async def not_found(request,error): return Response(json.dumps({'detail':str(error)},ensure_ascii=False),status_code=404,media_type='application/json')


@app.get('/health')
def health(): return {'ok':True,'version':'0.1.2'}


@app.post('/api/shutdown')
async def shutdown():
    for recording in list(recordings.values()): await recording.stop()
    await jobs.close()
    return {'ok':True}


@app.get('/api/settings')
def get_settings():
    s=store.settings()
    return s|{'secrets':{k:vault.configured(k) for k in ('doubao_api_key','llm_api_key','tos_access_key','tos_secret_key')},
              'moss_ready':model_files_ready(s['moss_path']) and Path(s['moss_python']).exists(),
              'speaker_helper_ready':jobs.speaker_helper_ready(s),
              'local_live_ready':jobs.online_ready(s),
              'data_directory':str(DATA)}


@app.put('/api/settings')
async def put_settings(request:Request):
    values=await request.json()
    for key in ('doubao_api_key','llm_api_key','tos_access_key','tos_secret_key'):
        if key in values and values[key] is not None: vault.set(key,str(values.pop(key)).strip())
    store.save_settings(values)
    return get_settings()


@app.post('/api/settings/check')
async def check_settings(request:Request):
    kind=(await request.json()).get('kind','realtime')
    settings=store.settings()
    if kind=='moss':
        return {'ok':get_settings()['moss_ready'],'message':'模型与运行环境已准备；CPU 的实时速度仍需实际测量。' if get_settings()['moss_ready'] else '模型或运行环境尚未安装，请运行“安装本地模型.cmd”。'}
    path=DATA/'connection-check.wav'
    with wave.open(str(path),'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed')); w.writeframes(bytes(16000))
    try:
        key=vault.get('doubao_api_key')
        if kind=='file':
            await transcribe_flash(path,key,settings['doubao_file_resource'])
        else:
            ws=await open_stream(key,settings['doubao_realtime_resource'])
            try:
                await send_audio(ws,bytes(16000),True)
                unpack(await asyncio.wait_for(ws.recv(),30))
            finally: await ws.close()
        return {'ok':True,'message':'语音服务鉴权及协议检查通过。'}
    except Exception as error: return {'ok':False,'message':str(error)}
    finally: path.unlink(missing_ok=True)


@app.get('/api/meetings')
def list_meetings(): return store.list_meetings()


@app.get('/api/actions')
def all_actions():
    result=[]
    for metadata in store.list_meetings():
        meeting=store.meeting(metadata['id'])
        if meeting['minutes']:
            names={p['id']:p['name'] for p in meeting['speakers']}
            for action in meeting['minutes']['data'].get('action_items',[]):
                result.append(action|{'meeting_id':meeting['id'],'meeting_title':meeting['title'],
                                     'owner_name':names.get(action.get('owner_speaker_id'),action.get('owner_mentioned_as') or '未明确')})
    return result


@app.post('/api/meetings')
async def create_meeting(request:Request):
    data=await request.json()
    if data.get('engine') not in ('doubao','moss') or data.get('mode') not in ('realtime','file'): raise ValueError('请选择工作模式和转写引擎')
    mid=store.create_meeting(data.get('title','未命名会议'),data['mode'],data['engine'],data.get('hotwords',''),data.get('auto_minutes',True))
    (DATA/mid).mkdir(exist_ok=True)
    return store.meeting(mid)


@app.get('/api/meetings/{mid}')
def get_meeting(mid:str):
    meeting=store.meeting(mid)
    recording=recordings.get(mid)
    meeting['caption_engine']=('doubao' if meeting['engine']=='doubao' else ('local_stream' if recording.online_enabled else 'moss_batch')) if recording else None
    return meeting


@app.patch('/api/meetings/{mid}')
async def edit_meeting(mid:str,request:Request):
    data=await request.json()
    title=str(data.get('title','')).strip()
    if not title or len(title)>200: raise ValueError('会议标题请填写 1～200 个字符')
    store.update_meeting(mid,title=title)
    return store.meeting(mid)


@app.post('/api/meetings/{mid}/file')
async def upload_file(mid:str,file:UploadFile=File(...)):
    meeting=store.meeting(mid)
    if meeting['audio_path']: raise ValueError('该会议已有文件，请新建会议。')
    suffix=Path(file.filename or 'audio').suffix.lower()
    if suffix not in ('.wav','.mp3','.m4a','.aac','.flac','.ogg','.opus','.mp4','.mov','.mkv','.webm','.wma','.amr'):
        raise ValueError('请选择常见音频或视频文件，例如 WAV、MP3、M4A 或 MP4。')
    folder=DATA/mid; folder.mkdir(exist_ok=True)
    destination=folder/('original'+suffix)
    size=0
    with destination.open('wb') as target:
        while data:=await file.read(1024*1024):
            size+=len(data)
            if size>4*1024**3:
                destination.unlink(missing_ok=True)
                raise ValueError('首版单文件上限为 4GB，请先拆分文件。')
            target.write(data)
    if not size: raise ValueError('音频文件为空')
    store.update_meeting(mid,audio_path=str(destination),filename=file.filename,status='queued')
    tid=jobs.submit(mid,'transcribe')
    return {'task_id':tid}


@app.post('/api/meetings/{mid}/file-path')
async def import_file_path(mid:str,request:Request):
    meeting=store.meeting(mid)
    if meeting['audio_path']: raise ValueError('该会议已有录音，请新建会议。')
    source=Path((await request.json()).get('path','')).resolve()
    allowed={'.wav','.mp3','.m4a','.aac','.flac','.ogg','.opus','.mp4','.mov','.mkv','.webm','.wma','.amr'}
    if not source.is_file() or source.suffix.lower() not in allowed: raise ValueError('请选择有效的音频或视频文件。')
    if not source.stat().st_size or source.stat().st_size>4*1024**3: raise ValueError('文件为空或超过 4GB，请先拆分文件。')
    folder=DATA/mid; folder.mkdir(exist_ok=True)
    destination=folder/('original'+source.suffix.lower())
    await asyncio.to_thread(shutil.copyfile,source,destination)
    store.update_meeting(mid,audio_path=str(destination),filename=source.name,status='queued')
    return {'task_id':jobs.submit(mid,'transcribe')}


@app.post('/api/meetings/{mid}/transcribe')
async def transcribe(mid:str,request:Request):
    data=await request.json()
    if mid in recordings: raise ValueError('请结束录音后再重新转写')
    if not store.meeting(mid)['audio_path']: raise ValueError('尚无录音文件')
    engine=data.get('engine',store.meeting(mid)['engine'])
    if engine not in ('doubao','moss'): raise ValueError('请选择有效的引擎')
    return {'task_id':jobs.submit(mid,'transcribe',{'engine':engine})}


@app.post('/api/meetings/{mid}/minutes')
async def minutes(mid:str):
    if mid in recordings: raise ValueError('请先结束录音')
    if not store.meeting(mid)['segments']: raise ValueError('尚无可生成纪要的文字')
    return {'task_id':jobs.submit(mid,'minutes')}


@app.patch('/api/meetings/{mid}/speakers/{sid}')
async def rename_speaker(mid:str,sid:str,request:Request):
    store.rename_speaker(mid,sid,(await request.json()).get('name',''))
    await notify(mid,{'type':'updated'})
    return store.meeting(mid)


@app.post('/api/meetings/{mid}/speakers')
async def add_speaker(mid:str,request:Request):
    name=str((await request.json()).get('name','')).strip()
    if len(name)>60: raise ValueError('姓名最长 60 字')
    sid=store.create_speaker(mid,name)
    await notify(mid,{'type':'updated'})
    return {'id':sid}


@app.post('/api/meetings/{mid}/speakers/merge')
async def merge_speakers(mid:str,request:Request):
    values=await request.json()
    store.merge_speakers(mid,values['source'],values['target'])
    await notify(mid,{'type':'updated'})
    return store.meeting(mid)


@app.patch('/api/meetings/{mid}/minutes')
async def update_minutes(mid:str,request:Request):
    store.edit_minutes(mid,(await request.json())['summary'])
    await notify(mid,{'type':'updated'})
    return store.meeting(mid)


@app.patch('/api/meetings/{mid}/segments/{segment_id}')
async def edit_segment(mid:str,segment_id:str,request:Request):
    data=await request.json()
    store.edit_segment(mid,segment_id,data.get('text'),data.get('speaker_id'),'speaker_id' in data)
    await notify(mid,{'type':'updated'})
    return store.meeting(mid)


@app.patch('/api/meetings/{mid}/actions/{aid}')
async def edit_action(mid:str,aid:str,request:Request):
    store.edit_action(mid,aid,await request.json())
    await notify(mid,{'type':'updated'})
    return store.meeting(mid)


@app.post('/api/meetings/{mid}/version')
async def select_version(mid:str,request:Request):
    store.activate_version(mid,(await request.json())['version_id'])
    return store.meeting(mid)


@app.get('/api/meetings/{mid}/audio')
def audio(mid:str):
    path=store.meeting(mid)['audio_path']
    if not path or not Path(path).exists(): raise HTTPException(404,'录音尚未保存')
    return FileResponse(path,media_type='audio/wav' if path.endswith('.wav') else None)


def timestamp(ms):
    seconds=int(ms)//1000
    return f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'


@app.get('/api/meetings/{mid}/export/{kind}')
def export(mid:str,kind:str):
    m=store.meeting(mid)
    names={p['id']:p['name'] for p in m['speakers']}
    if kind=='txt':
        content=m['title']+'\n\n'+'\n\n'.join(f"[{timestamp(s['start_ms'])}] {names.get(s['speaker_id'],'待确认')}\n{s['text']}" for s in m['segments'])
        media='text/plain'
    elif kind=='md':
        if not m['minutes']: raise ValueError('尚无会议纪要')
        d=m['minutes']['data']
        content=f"# {m['title']}\n\n来源转写版本：{m['minutes']['source_version']}\n\n## 总结\n\n"+'\n'.join('- '+s for s in d.get('summary',[]))
        content+='\n\n## 决策\n\n'+'\n'.join('- '+s['text'] for s in d.get('decisions',[]))
        content+='\n\n## 行动项\n\n'+'\n'.join(f"- [{'x' if a.get('status')=='done' else ' '}] {a['task']} · 负责人：{names.get(a.get('owner_speaker_id'),a.get('owner_mentioned_as') or '未明确')} · 截止：{a.get('due_date') or '未明确'} · 原文：{','.join(a.get('evidence_segment_ids',[]))}" for a in d.get('action_items',[]))
        media='text/markdown'
    elif kind=='csv':
        buffer=io.StringIO(newline=''); writer=csv.writer(buffer)
        writer.writerow(['任务','负责人','截止日期','交付物','状态','来源转写版本','原文分段'])
        for a in (m['minutes']['data'].get('action_items',[]) if m['minutes'] else []):
            values=[a['task'],names.get(a.get('owner_speaker_id'),a.get('owner_mentioned_as') or '未明确'),a.get('due_date') or '',a.get('deliverable') or '',a.get('status','open'),m['minutes']['source_version'],','.join(a.get('evidence_segment_ids',[]))]
            writer.writerow(["'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v for v in values])
        content=buffer.getvalue(); media='text/csv'
    else: raise HTTPException(404,'导出类型不存在')
    return Response(('\ufeff'+content).encode('utf-8'),media_type=media,headers={'Content-Disposition':f'attachment; filename="meeting-{mid}.{kind}"'})


@app.delete('/api/meetings/{mid}')
async def delete(mid:str):
    if mid in recordings: raise ValueError('请先停止录音再删除会议')
    store.meeting(mid)
    await jobs.cancel_meeting(mid)
    store.delete(mid)
    folder=(DATA/mid).resolve()
    if folder.parent==DATA.resolve() and folder.exists(): shutil.rmtree(folder)
    return {'ok':True}


@app.websocket('/api/meetings/{mid}/events')
async def events(ws:WebSocket,mid:str):
    if TOKEN and ws.query_params.get('token')!=TOKEN: await ws.close(code=1008); return
    await ws.accept(); subscribers.setdefault(mid,set()).add(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: pass
    finally: subscribers.get(mid,set()).discard(ws)


@app.websocket('/api/meetings/{mid}/record')
async def record(ws:WebSocket,mid:str):
    if TOKEN and ws.query_params.get('token')!=TOKEN: await ws.close(code=1008); return
    await ws.accept()
    recording=None
    try:
        if mid in recordings: raise ValueError('该会议已在录音')
        recording=LiveRecording(mid,store,vault,jobs,DATA,notify)
        recordings[mid]=recording
        await recording.start()
        await ws.send_json({'type':'ready'})
        while True:
            message=await ws.receive()
            if message.get('type')=='websocket.disconnect': break
            if message.get('bytes') is not None:
                await recording.audio(message['bytes'])
            elif message.get('text'):
                control=json.loads(message['text'])
                if control.get('type')=='stop': break
        await recording.stop()
        await ws.send_json({'type':'saved'})
    except (WebSocketDisconnect,RuntimeError): pass
    except Exception as error:
        try: await ws.send_json({'type':'error','message':str(error)[:300]})
        except Exception: pass
    finally:
        if recording: await recording.stop()
        recordings.pop(mid,None)
        try: await ws.close()
        except Exception: pass
