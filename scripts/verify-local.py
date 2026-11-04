import asyncio,json,sys,time
sys.stdout.reconfigure(encoding='utf-8')
from meeting_app.config import DATA,ROOT
from meeting_app.store import Store
from meeting_app.local import MossRunner

async def main():
    runner=MossRunner()
    results=[]
    try:
        for index in range(2):
            started=time.monotonic()
            result=await runner.transcribe(DATA/'synthetic-probe-moss.wav',Store(DATA).settings(),'',index==1)
            record={'run':index+1,'wall_seconds':round(time.monotonic()-started,3),'timings':result.get('timings'),'segments':result['segments']}
            results.append(record)
            print(json.dumps(record,ensure_ascii=False),flush=True)
    finally:await runner.close()
    output={'status':'PASS','audio_seconds':4,'device':'cpu','runs':results}
    (ROOT/'artifacts'/'moss-warm-smoke.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),'utf-8')
asyncio.run(main())
