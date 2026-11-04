"""Download the official quantized, bilingual Paraformer preview model."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

repository='csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en'
revision='8e40c43232a1c5c66c82111efc5820d3accca11b'
directory=Path(r'K:\工具箱\MOSS model\auxiliary\paraformer-streaming')
files={
    'encoder.int8.onnx':(165462184,'81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a'),
    'decoder.int8.onnx':(71664561,'f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f'),
    'tokens.txt':(75756,'57bc045ddda0434ed4440c38e14287c595b258d9'),
}


def valid(path,size,digest):
    if not path.exists() or path.stat().st_size!=size:return False
    if len(digest)==40:
        return hashlib.sha1(f'blob {size}\0'.encode()+path.read_bytes()).hexdigest()==digest
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()==digest


def download(name,metadata):
    size,digest=metadata;destination=directory/name;partial=directory/(name+'.part')
    if valid(destination,size,digest):return
    for attempt in range(3):
        offset=partial.stat().st_size if partial.exists() else 0
        request=urllib.request.Request(f'https://huggingface.co/{repository}/resolve/{revision}/{name}',headers={'Range':f'bytes={offset}-'} if offset else {})
        try:
            with urllib.request.urlopen(request,timeout=90) as response:
                append=offset>0 and response.status==206
                with partial.open('ab' if append else 'wb') as output:
                    while block:=response.read(1024*1024):output.write(block)
            if not valid(partial,size,digest):raise ValueError('Model download integrity check failed: '+name)
            partial.replace(destination)
            print('Verified local subtitle model:',name,flush=True)
            return
        except Exception:
            if attempt==2:raise


directory.mkdir(parents=True,exist_ok=True)
with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda item:download(*item),files.items()))
(directory/'ready.json').write_text(json.dumps({'repository':repository,'revision':revision,'files':files},indent=2),'utf-8')
print('Offline streaming subtitles are ready.',flush=True)
