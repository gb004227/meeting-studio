"""Download the official HF weight with resumable HTTP and SHA-256 verification."""
from pathlib import Path
import hashlib
import json
import time
import urllib.request

folder=Path(r'K:\工具箱\MOSS model\MOSS-Transcribe-Diarize')
folder.mkdir(parents=True,exist_ok=True)
filename='model-00000-of-00001.safetensors'
expected='9a0ceb4ab7330357db3ff583dba8d83625d5b733b00e1d55d6970e11b07026c4'
destination=folder/filename
partial=folder/(filename+'.partial')
if destination.exists() and hashlib.file_digest(destination.open('rb'),'sha256').hexdigest()==expected:
    print('MOSS weight already verified.',flush=True)
    raise SystemExit(0)
for attempt in range(6):
    try:
        offset=partial.stat().st_size if partial.exists() else 0
        manifest=json.loads((Path(__file__).parent/'model-revisions.json').read_text('utf-8'))
        revision=manifest['moss_model_revision']
        url=f'https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize/resolve/{revision}/{filename}?download=true&time={int(time.time())}'
        request=urllib.request.Request(url,headers={'Range':f'bytes={offset}-'} if offset else {})
        with urllib.request.urlopen(request,timeout=120) as response:
            mode='ab' if offset and response.status==206 else 'wb'
            if mode=='wb': offset=0
            last=offset
            with partial.open(mode) as stream:
                while data:=response.read(2*1024*1024):
                    stream.write(data);offset+=len(data)
                    if offset-last>=128*1024*1024:
                        print(f'MOSS weight: {offset//1024**2} MiB downloaded',flush=True);last=offset
        with partial.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=expected: raise ValueError('Weight SHA-256 mismatch; incomplete or incorrect download')
        partial.replace(destination)
        print('MOSS weight downloaded and SHA-256 verified.',flush=True)
        break
    except Exception as error:
        print('Download attempt',attempt+1,type(error).__name__,str(error)[:120],flush=True)
        if attempt==5: raise
        time.sleep(3)
