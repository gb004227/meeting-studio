"""Check real MOSS generation captions using synthetic audio, without cloud calls."""
import asyncio
import json
import sys
import time
from meeting_app.config import DATA,ROOT
from meeting_app.local import MossRunner
from meeting_app.store import Store

sys.stdout.reconfigure(encoding='utf-8')


async def main():
    runner=MossRunner();started=time.monotonic();captions=[]
    async def caption(text):
        if text:captions.append({'seconds':round(time.monotonic()-started,3),'characters':len(text)})
    try:
        result=await runner.transcribe(DATA/'synthetic-probe-moss.wav',Store(DATA).settings(),embeddings=True,on_partial=caption)
        seconds=time.monotonic()-started
        assert result['segments'] and captions
        assert result['timings']['first_caption']<result['timings']['generation_done']
        assert len(captions)>=2
        report={'status':'PASS','source':'4s Windows synthetic Chinese audio; no microphone or cloud',
                'first_caption_seconds_from_request':captions[0]['seconds'],'worker_first_caption_seconds':result['timings']['first_caption'],
                'worker_generation_finished_seconds':result['timings']['generation_done'],
                'total_seconds':round(seconds,3),'caption_updates':len(captions),'final_segments':len(result['segments'])}
        (ROOT/'artifacts'/'local-stream-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
    finally:await runner.close()

asyncio.run(main())
