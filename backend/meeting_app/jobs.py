import asyncio
import json
from pathlib import Path
from .audio import convert_audio,duration_ms,read_pcm
from .doubao import normalize,transcribe_flash,transcribe_standard,transcribe_stream_file
from .minutes import generate_minutes
from .local import MossRunner
from .store import uid
from .online import LocalCaptionModel,models_ready,model_directory
from .speaker_audio import SpeakerModel,speaker_model_path


class Jobs:
    def __init__(self,store,vault,directory,notify):
        self.store=store; self.vault=vault; self.directory=directory; self.notify=notify
        self.active={}; self.moss=MossRunner()
        self.closing=False
        self.cloud_slots=asyncio.Semaphore(2)
        self.online=None;self.online_lock=asyncio.Lock()
        self.speaker_model=None;self.speaker_lock=asyncio.Lock()

    def submit(self,mid,kind,payload=None):
        tid=self.store.new_task(mid,kind,payload or {})
        self.active[tid]=asyncio.create_task(self._run(tid,mid,kind,payload or {}))
        return tid

    async def recover(self):
        for row in self.store.pending_tasks():
            payload=json.loads(row['payload'])
            meeting=self.store.meeting(row['meeting_id'])
            if row['state']=='running' and row['kind']=='transcribe' and payload.get('engine',meeting['engine'])=='doubao' and not payload.get('request_id'):
                self.store.task_update(row['id'],state='waiting',stage='上次云端转写中断，等待手动重试',error='录音已保留。为避免重复计费，未自动重新发送云端音频。')
                self.store.update_meeting(row['meeting_id'],status='partial_failed' if meeting['segments'] else 'failed',error='上次云端转写被中断，录音已保留，可点击重新转写。')
                continue
            # The same provider request is reused when a standard-file request id exists.
            self.active[row['id']]=asyncio.create_task(self._run(row['id'],row['meeting_id'],row['kind'],payload))

    async def stage(self,tid,mid,text):
        self.store.task_update(tid,state='running',stage=text)
        await self.notify(mid,{'type':'updated'})

    def speaker_helper_ready(self,settings):
        return speaker_model_path(settings).is_file()

    async def attach_speakers(self,path,parts,settings):
        if not self.speaker_helper_ready(settings):return parts
        model_path=speaker_model_path(settings)
        async with self.speaker_lock:
            if self.speaker_model is None or self.speaker_model.path!=model_path:
                self.speaker_model=await asyncio.to_thread(SpeakerModel,model_path)
            return await asyncio.to_thread(self.speaker_model.attach,path,parts)

    def online_ready(self,settings):return models_ready(settings)

    async def open_local_stream(self,settings):
        directory=model_directory(settings)
        async with self.online_lock:
            if self.online is None or self.online.directory!=directory:
                self.online=await asyncio.to_thread(LocalCaptionModel,directory)
            return self.online.session()

    async def cloud_speakers(self,path,parts,settings,cache):
        if not self.speaker_helper_ready(settings):return parts
        def key(part):return (part['start_ms'],part['end_ms'],part['text'])
        fresh=[part for part in parts if key(part) not in cache]
        if fresh:
            result=await self.attach_speakers(path,fresh,settings)
            for part in result:
                cache[key(part)]=part|{'speaker':f"acoustic/{part['start_ms']}" if part.get('embedding') else None,'prefer_embedding':True}
        return [part|cache.get(key(part),{}) for part in parts]

    async def _run(self,tid,mid,kind,payload):
        try:
            if kind=='minutes':
                await self.stage(tid,mid,'正在生成会议纪要')
                meeting=self.store.meeting(mid)
                if not meeting['segments']: raise ValueError('暂无有效转写内容，无法生成纪要。')
                version=meeting['current_version']
                result,source=await generate_minutes(meeting,self.store.settings(),self.vault.get('llm_api_key'))
                self.store.save_minutes(mid,version,result,source)
                if self.store.meeting(mid)['current_version']==version:
                    error=meeting['error']
                    if any(t['kind']=='minutes' and t['state']=='failed' and t['error']==error for t in meeting['tasks']):error=''
                    self.store.update_meeting(mid,status='partial_failed' if error else 'completed',error=error)
            else:
                await self._transcribe(tid,mid,payload)
            self.store.task_update(tid,state='completed',stage='处理完成')
        except asyncio.CancelledError:
            if self.closing:
                meeting=self.store.meeting(mid)
                local=kind=='transcribe' and payload.get('engine',meeting['engine'])=='moss'
                state='queued' if local or payload.get('request_id') else 'waiting'
                self.store.task_update(tid,state=state,stage='应用已关闭，下次恢复' if state=='queued' else '应用已关闭，等待手动重试')
                self.store.update_meeting(mid,status='queued' if state=='queued' else ('partial_failed' if meeting['segments'] else 'failed'),error='' if state=='queued' else '处理因应用关闭而暂停，已保存的音频仍保留，可重新转写或生成纪要。')
            else:self.store.task_update(tid,state='canceled',stage='已取消')
            raise
        except Exception as error:
            message=(str(error).strip() or f'处理未完成（{type(error).__name__}），音频已保留，可重新处理。')[:600]
            # Provider/LLM messages never include request headers or credentials.
            self.store.task_update(tid,state='failed',stage='处理失败',error=message)
            try:
                m=self.store.meeting(mid)
                self.store.update_meeting(mid,status='partial_failed' if m['segments'] else 'failed',error=message)
            except KeyError: pass
        finally:
            await self.notify(mid,{'type':'updated'})
            self.active.pop(tid,None)

    async def _transcribe(self,tid,mid,payload):
        meeting=self.store.meeting(mid)
        settings=self.store.settings()
        engine=payload.get('engine',meeting['engine'])
        folder=self.directory/mid
        source=Path(meeting['audio_path'])
        wave_path=folder/'audio.wav'
        self.store.update_meeting(mid,status='transcribing',error='')
        await self.stage(tid,mid,'正在读取并转换音频')
        if source!=wave_path:
            await asyncio.to_thread(convert_audio,source,wave_path)
        length=duration_ms(wave_path)
        self.store.update_meeting(mid,duration_ms=length,audio_path=str(wave_path))
        previous=meeting['current_version']
        previous_usable=bool(meeting['segments'])
        vid=self.store.new_version(mid,'moss' if engine=='moss' else 'doubao',previous,activate=not previous_usable)
        namespace=uid('run_')
        try:
            if engine=='doubao':
                async with self.cloud_slots:
                    key=self.vault.get('doubao_api_key')
                    mode=settings['doubao_file_mode']
                    if mode=='stream':
                        await self.stage(tid,mid,'豆包 2.0 云端转写（复用实时权限）')
                        def progress(value):
                            self.store.task_update(tid,stage=f'豆包 2.0 云端转写 · 已发送 {value}%')
                        speaker_cache={}
                        async def result(value):
                            parts,_=normalize(value,final_only=True)
                            parts=await self.cloud_speakers(wave_path,parts,settings,speaker_cache)
                            self.store.add_segments(mid,vid,parts,namespace,previous)
                        answer=await transcribe_stream_file(await asyncio.to_thread(read_pcm,wave_path),key,settings['doubao_realtime_resource'],meeting['hotwords'],result,progress)
                        parts,_=normalize(answer)
                        parts=await self.cloud_speakers(wave_path,parts,settings,speaker_cache)
                        self.store.add_segments(mid,vid,parts,namespace,previous)
                        (folder/f'{namespace}.response.json').write_text(json.dumps(answer,ensure_ascii=False),'utf-8')
                    elif mode=='flash':
                        if length>2*60*60*1000: raise ValueError('极速直传最长 2 小时；请选择“豆包2.0流式文件转写”或标准版。')
                        upload=folder/'upload.ogg'
                        await asyncio.to_thread(convert_audio,wave_path,upload,None,None,True)
                        await self.stage(tid,mid,'豆包文件极速版正在识别')
                        answer=await transcribe_flash(upload,key,settings['doubao_file_resource'],meeting['hotwords'])
                        parts,_=normalize(answer)
                        self.store.add_segments(mid,vid,parts,namespace,previous)
                        (folder/f'{namespace}.response.json').write_text(json.dumps(answer,ensure_ascii=False),'utf-8')
                    else:
                        await self.stage(tid,mid,'正在上传至私有临时存储')
                        import tos
                        if not settings.get('tos_bucket'): raise ValueError('标准文件模式需要先配置私有 TOS 临时存储。也可选择无需 TOS 的流式文件通道。')
                        client=tos.TosClientV2(self.vault.get('tos_access_key'),self.vault.get('tos_secret_key'),settings['tos_endpoint'],settings['tos_region'])
                        object_key=f'meeting-studio/{mid}/{tid}.wav'
                        await asyncio.to_thread(client.put_object_from_file,settings['tos_bucket'],object_key,str(wave_path))
                        try:
                            signed=client.pre_signed_url(tos.HttpMethodType.Http_Method_Get,settings['tos_bucket'],object_key,expires=21600).signed_url
                            await self.stage(tid,mid,'云端文件识别 · 等待结果')
                            def submitted(rid):
                                with self.store.connection() as db:
                                    db.execute('UPDATE tasks SET payload=? WHERE id=?',(json.dumps(payload|{'request_id':rid,'object_key':object_key}),tid))
                            answer=await transcribe_standard(signed,key,'volc.seedasr.auc',meeting['hotwords'],submitted,payload.get('request_id'))
                            parts,_=normalize(answer)
                            self.store.add_segments(mid,vid,parts,namespace,previous)
                        finally:
                            try: await asyncio.to_thread(client.delete_object,settings['tos_bucket'],object_key)
                            except Exception: self.store.task_update(tid,stage='转写已完成；云端临时文件删除失败，请在 TOS 中检查')
            else:
                # Bound CPU context and memory; keep overlap for identity alignment.
                window=60 if settings.get('moss_device')=='cpu' else 1200
                overlap=5 if window==60 else 10
                start=0; index=0;processed_until=0
                while start<length/1000:
                    await self.stage(tid,mid,f'MOSS 本地转写 · 第 {index+1} 段 · 已处理 {min(99,round(start*1000/max(length,1)*100))}%（CPU 可能较慢）')
                    chunk=folder/f'moss-chunk-{tid}-{index}.wav'
                    await asyncio.to_thread(convert_audio,wave_path,chunk,start,window)
                    async def caption(text):
                        with self.store.connection() as db:
                            current=db.execute('SELECT current_version FROM meetings WHERE id=?',(mid,)).fetchone()
                        if current and current[0]==vid:await self.notify(mid,{'type':'transcript','partial':text,'refresh':False})
                    answer=await self.moss.transcribe(chunk,settings,meeting['hotwords'],False,on_partial=caption,partial_after_ms=max(0,processed_until-round(start*1000)))
                    answer['segments']=await self.attach_speakers(chunk,answer['segments'],settings)
                    parts=[p|{'start_ms':p['start_ms']+round(start*1000),'end_ms':p['end_ms']+round(start*1000)} for p in answer['segments']]
                    self.store.add_segments(mid,vid,parts,f'{namespace}/{index}',vid if index else previous)
                    (folder/f'{namespace}-{index}.response.json').write_text(json.dumps(answer,ensure_ascii=False),'utf-8')
                    processed_until=max((part['end_ms'] for part in parts),default=processed_until)
                    await self.notify(mid,{'type':'transcript','partial':''})
                    chunk.unlink(missing_ok=True)
                    if (start+window)*1000>=length: break
                    start+=window-overlap; index+=1
            self.store.publish(vid)
            # Preserve user-edited source; offer candidate versions instead of overwriting.
            human=any(s['edited'] for s in self.store.meeting(mid)['segments']) if previous else False
            if not human:
                self.store.activate_version(mid,vid)
            self.store.update_meeting(mid,status='transcribed',error='新转写版本已完成；原稿含人工校对，请在版本菜单选择对比。' if human else '')
            current=self.store.meeting(mid)
            if not current['segments']:
                self.store.update_meeting(mid,status='transcribed',error='未识别到有效发言，录音已保留。')
            elif meeting['auto_minutes'] and not human:
                self.submit(mid,'minutes')
        except Exception:
            # A failed refinement never replaces an existing usable transcript.
            if previous_usable: self.store.activate_version(mid,previous)
            raise

    async def cancel_meeting(self,mid):
        with self.store.connection() as db:
            ids=[r['id'] for r in db.execute("SELECT id FROM tasks WHERE meeting_id=? AND state IN ('queued','running')",(mid,))]
        for tid in ids:
            task=self.active.get(tid)
            if task: task.cancel()
        await asyncio.gather(*(self.active[tid] for tid in ids if tid in self.active),return_exceptions=True)

    async def close(self):
        self.closing=True
        tasks=list(self.active.values())
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await self.moss.close()
