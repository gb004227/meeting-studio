import asyncio
import os
import time
import wave
from .doubao import open_stream,send_audio,unpack,normalize
from .store import uid


class LiveRecording:
    def __init__(self,mid,store,vault,jobs,directory,notify):
        self.mid=mid; self.store=store; self.vault=vault; self.jobs=jobs; self.notify=notify
        self.meeting=store.meeting(mid); self.settings=store.settings()
        self.folder=directory/mid; self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'audio.wav'
        if self.path.exists(): raise ValueError('该会议已有录音，请新建会议以防覆盖。')
        self.raw=open(self.path,'w+b'); self.writer=wave.open(self.raw,'wb')
        self.writer.setparams((1,2,16000,0,'NONE','not compressed'))
        self.samples=0; self.last_sync=time.monotonic(); self.local_covered_ms=0
        self.preview_paused=False
        self.queue=asyncio.Queue(maxsize=40); self.preview_task=None
        self.closed=False; self.gaps=False; self.sender=None
        self.vid=store.new_version(mid,'live')
        self.namespace=uid('live_')
        self.speaker_cache={}
        self.pending_speakers={};self.speaker_task=None;self.speaker_error=''
        self.online_enabled=self.meeting['engine']=='moss' and self.jobs.online_ready(self.settings)
        self.online=None
        self.speaker_helper=(self.meeting['engine']=='doubao' or self.online_enabled) and self.jobs.speaker_helper_ready(self.settings)
        store.update_meeting(mid,status='recording',audio_path=str(self.path),error='')

    async def start(self):
        if self.meeting['engine']=='doubao': self.sender=asyncio.create_task(self.send_cloud())
        elif self.online_enabled:
            try:
                self.online=await self.jobs.open_local_stream(self.settings)
                self.sender=asyncio.create_task(self.send_local())
            except Exception:
                self.online_enabled=False;self.speaker_helper=False
                await self.notify(self.mid,{'type':'warning','message':'本地流式字幕组件启动失败，当前使用 MOSS 分段预览；录音会完整保存，可在设置中修复本地模型。'})
        await self.notify(self.mid,{'type':'updated'})

    async def audio(self,data):
        if len(data)%2 or len(data)>320000: raise ValueError('音频包格式不正确')
        offset=self.samples//16
        self.writer.writeframes(data)
        self.samples+=len(data)//2
        if time.monotonic()-self.last_sync>=1:
            self.raw.flush(); os.fsync(self.raw.fileno()); self.last_sync=time.monotonic()
            self.store.update_meeting(self.mid,duration_ms=self.samples//16)
        if self.meeting['engine']=='doubao' or self.online_enabled:
            try: self.queue.put_nowait((data,offset))
            except asyncio.QueueFull:
                if not self.gaps:
                    self.gaps=True
                    await self.notify(self.mid,{'type':'warning','message':'字幕处理积压，完整录音仍在本地保存；结束后可完整转写补齐。'})
        elif not self.preview_paused and self.samples//16-self.local_covered_ms>=3000 and not (self.preview_task and not self.preview_task.done()):
            if not self.jobs.moss.lock.locked():
                end=min(self.samples//16,self.local_covered_ms+7000)
                start=max(0,end-20000)
                self.raw.flush()
                with wave.open(str(self.path),'rb') as source:
                    source.setpos(start*16)
                    pcm=source.readframes((end-start)*16)
                self.preview_task=asyncio.create_task(self.preview(pcm,end))

    async def preview(self,pcm,end):
        path=self.folder/(uid('window_')+'.wav')
        try:
            with wave.open(str(path),'wb') as w:
                w.setparams((1,2,16000,0,'NONE','not compressed')); w.writeframes(pcm)
            offset=end-len(pcm)//32
            stable_end=max((part['end_ms'] for part in self.store.meeting(self.mid)['segments']),default=0)
            async def caption(text):
                if not self.closed:await self.notify(self.mid,{'type':'transcript','partial':text,'refresh':False})
            answer=await self.jobs.moss.transcribe(path,self.settings,self.meeting['hotwords'],False,on_partial=caption,partial_after_ms=max(0,stable_end-offset))
            if self.closed: return
            parts=[s|{'start_ms':s['start_ms']+offset,'end_ms':s['end_ms']+offset} for s in answer['segments']]
            stable=[s for s in parts if s['end_ms']<=end-3000]
            partial=''.join(s['text'] for s in parts if s['end_ms']>end-3000)
            self.store.add_segments(self.mid,self.vid,stable,f'{self.namespace}/{end}',self.vid)
            self.local_covered_ms=end
            lag=(self.samples//16-end)/1000
            await self.notify(self.mid,{'type':'transcript','partial':partial,'latency':round(lag,1)})
            if lag>30:
                self.preview_paused=True
                await self.notify(self.mid,{'type':'warning','message':'本机 CPU 转写已落后录音超过 30 秒，已暂停会中预览以保护录音；结束后将继续本地完整转写。低延迟会议可在新任务中选择豆包。'})
        except Exception as error:
            self.preview_paused=True
            if not self.closed: await self.notify(self.mid,{'type':'warning','message':str(error)[:250]+'；会中预览已暂停，录音持续保存，结束后可完整转写。'})
        finally: path.unlink(missing_ok=True)

    async def send_local(self):
        previous=''
        async def display(result):
            nonlocal previous
            text=result['text']
            if result['endpoint']:
                if text and result['end_ms']>result['start_ms']:
                    part={'text':text,'start_ms':result['start_ms'],'end_ms':result['end_ms'],'speaker':None}
                    self.store.add_segments(self.mid,self.vid,[part],self.namespace,self.vid)
                    if self.speaker_helper:
                        self.pending_speakers[part['start_ms']]=part
                        if not (self.speaker_task and not self.speaker_task.done()):self.speaker_task=asyncio.create_task(self.refine_speakers())
                previous=''
                await self.notify(self.mid,{'type':'transcript','partial':''})
            elif text!=previous:
                previous=text
                await self.notify(self.mid,{'type':'transcript','partial':text,'refresh':False})
        try:
            while True:
                packet=await self.queue.get()
                if packet is None:break
                data,offset=packet
                await display(await asyncio.to_thread(self.online.accept,data,False,offset))
            await display(await asyncio.to_thread(self.online.accept,b'',True))
        except Exception:
            self.gaps=True
            await self.notify(self.mid,{'type':'warning','message':'本地字幕识别中断，原录音继续保存，结束后将由 MOSS 完整转写补齐。'})

    async def send_cloud(self):
        ws=None; receiver=None; base=0; current_namespace=self.namespace
        async def receive(connection,offset,namespace):
            async for raw in connection:
                result=unpack(raw)
                parts,partial=normalize(result,offset,True)
                if not self.raw.closed:self.raw.flush()
                if self.speaker_helper:
                    display=[]
                    for part in parts:
                        key=(part['start_ms'],part['end_ms'],part['text'])
                        cached=self.speaker_cache.get(key)
                        display.append(part|(cached or {'speaker':None}))
                        if cached is None:self.pending_speakers[part['start_ms']]=part
                    self.store.add_segments(self.mid,self.vid,display,self.namespace,self.vid)
                    if self.pending_speakers and not (self.speaker_task and not self.speaker_task.done()):
                        self.speaker_task=asyncio.create_task(self.refine_speakers())
                else:self.store.add_segments(self.mid,self.vid,parts,namespace,self.vid)
                await self.notify(self.mid,{'type':'transcript','partial':partial})
                if isinstance(raw,bytes) and raw[1]&2:break
        try:
            while True:
                packet=await self.queue.get()
                if packet is None: break
                data,offset=packet
                try:
                    if receiver and receiver.done():
                        receiver.result(); ws=None
                    if ws is None:
                        ws=await open_stream(self.vault.get('doubao_api_key'),self.settings['doubao_realtime_resource'],self.meeting['hotwords'])
                        base=offset; current_namespace=uid('connection_')
                        receiver=asyncio.create_task(receive(ws,base,current_namespace))
                    await asyncio.wait_for(send_audio(ws,data),3)
                except Exception as error:
                    self.gaps=True
                    await self.notify(self.mid,{'type':'warning','message':str(error)[:240]+'；完整音频正在本地保存。'})
                    if ws:
                        try: await ws.close()
                        except Exception: pass
                    if receiver and not receiver.done(): receiver.cancel()
                    ws=None
                    if not self.closed: await asyncio.sleep(2)
            if ws:
                await send_audio(ws,b'',True)
                if receiver:
                    try: await asyncio.wait_for(receiver,12)
                    except (asyncio.TimeoutError,Exception): self.gaps=True
        finally:
            if receiver and not receiver.done(): receiver.cancel()
            if ws:
                try: await ws.close()
                except Exception: pass

    async def refine_speakers(self):
        try:
            while self.pending_speakers:
                parts=list(self.pending_speakers.values());self.pending_speakers.clear()
                parts=await self.jobs.cloud_speakers(self.path,parts,self.settings,self.speaker_cache)
                self.store.add_segments(self.mid,self.vid,parts,self.namespace,self.vid)
                await self.notify(self.mid,{'type':'updated'})
        except Exception:
            self.speaker_error='说话人辅助校正未完成，文字与录音已保留，可重新转写或手动分配人员。'
            await self.notify(self.mid,{'type':'warning','message':self.speaker_error})

    async def stop(self):
        if self.closed: return
        self.closed=True
        self.writer.close(); self.raw.flush(); os.fsync(self.raw.fileno()); self.raw.close()
        if self.sender:
            if self.queue.full():
                self.queue.get_nowait(); self.gaps=True
            self.queue.put_nowait(None)
            try: await asyncio.wait_for(self.sender,18)
            except (asyncio.TimeoutError,Exception): self.gaps=True
        if self.speaker_task and not self.speaker_task.done():
            try:await asyncio.wait_for(self.speaker_task,60)
            except (asyncio.TimeoutError,Exception):self.speaker_error='说话人辅助校正未完成，音频与文字已保留，可重新转写。'
        self.store.publish(self.vid)
        self.store.update_meeting(self.mid,duration_ms=self.samples//16,status='transcribed',error='实时识别有中断，请重新转写以补齐。' if self.gaps else self.speaker_error)
        if self.meeting['engine']=='moss' and self.samples:
            self.jobs.submit(self.mid,'transcribe',{'engine':'moss'})
        elif self.meeting['auto_minutes'] and self.store.meeting(self.mid)['segments']:
            self.jobs.submit(self.mid,'minutes')
        await self.notify(self.mid,{'type':'saved'})
