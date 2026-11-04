import asyncio
import json
import os
from pathlib import Path
import sys
from .config import ROOT,DATA,model_files_ready
from .store import uid


class MossRunner:
    def __init__(self):
        self.process=None
        self.lock=asyncio.Lock()
        self.log=None

    async def transcribe(self,path,settings,hotwords='',embeddings=False,speaker_segments=None,on_partial=None,partial_after_ms=0):
        async with self.lock:
            model=Path(settings['moss_path'])
            if speaker_segments is None and not model_files_ready(model):
                raise ValueError('本地 MOSS 模型尚未准备好。请运行“安装本地模型.cmd”，或在设置中选择已有模型目录。')
            python=Path(settings.get('moss_python') or sys.executable)
            if not python.exists(): raise ValueError('MOSS Python 环境不存在，请先安装本地模型。')
            if self.process is None or self.process.returncode is not None:
                self.log=open(DATA/'moss-worker.log','ab')
                env=os.environ|{'PYTHONUTF8':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
                self.process=await asyncio.create_subprocess_exec(str(python),str(ROOT/'backend'/'moss_worker.py'),stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,stderr=self.log,env=env,limit=16*1024*1024,creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0))
            from .audio import duration_ms
            duration=duration_ms(path)/1000
            budget=min(65536,max(1024,int(duration*18)))
            job={'job_id':uid(),'model_path':str(model),'audio_path':str(path),'hotwords':hotwords,
                 'device':settings.get('moss_device','cpu'),'max_new_tokens':budget,'embeddings':embeddings}
            if speaker_segments is not None:job.update(task='speaker_embeddings',segments=speaker_segments)
            if on_partial is not None:job.update(stream=True,partial_after_ms=partial_after_ms)
            self.process.stdin.write((json.dumps(job,ensure_ascii=False)+'\n').encode('utf-8'))
            await self.process.stdin.drain()
            while True:
                line=await self.process.stdout.readline()
                if not line: raise ValueError('本地推理进程已退出；录音仍保留，可重新转写。')
                try: result=json.loads(line)
                except ValueError: continue
                if result.get('job_id')!=job['job_id']: continue
                if result.get('event')=='partial':
                    if on_partial is not None:await on_partial(result.get('partial',''))
                    continue
                if not result.get('ok'):
                    message=result.get('error','未知错误')
                    await self.close()
                    raise ValueError('MOSS 推理失败：'+message)
                if result.get('truncated'): raise ValueError('模型输出达到预算，结果可能不完整。请缩短切片后重试。')
                return result

    async def close(self):
        if self.process:
            if self.process.returncode is None:
                if os.name=='nt':
                    killer=await asyncio.create_subprocess_exec('taskkill.exe','/PID',str(self.process.pid),'/T','/F',stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,creationflags=__import__('subprocess').CREATE_NO_WINDOW)
                    await killer.wait()
                else:self.process.terminate()
            await asyncio.gather(self.process.stdout.read(),self.process.wait(),return_exceptions=True)
            self.process=None
        if self.log: self.log.close()
