"""Fallback download with the checksum distributed by Electron's npm package."""
from pathlib import Path
import hashlib
import json
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor,as_completed
import shutil

root=Path(__file__).resolve().parents[1]
module=root/'node_modules'/'electron'
version=json.loads((module/'package.json').read_text('utf-8'))['version']
name=f'electron-v{version}-win32-x64.zip'
expected=json.loads((module/'checksums.json').read_text('utf-8'))[name]
cache=root/'runtime'/'downloads'
cache.mkdir(parents=True,exist_ok=True)
target=cache/name
if not target.exists():
    # The current network drops large continuous release downloads. Bounded,
    # verified ranges from the official release avoid that transport limitation.
    url=f'https://github.com/electron/electron/releases/download/v{version}/{name}'
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':'bytes=0-1023'}),timeout=45) as response:
        total=int(response.headers['Content-Range'].split('/')[-1])
        response.read()
    parts=cache/(name+'.parts')
    parts.mkdir(exist_ok=True)
    block=2*1024*1024
    count=(total+block-1)//block
    def fetch(index):
        start=index*block;end=min(total,(index+1)*block)-1
        out=parts/f'{index:05d}'
        if out.exists() and out.stat().st_size==end-start+1:return
        for attempt in range(4):
            try:
                request=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'})
                with urllib.request.urlopen(request,timeout=60) as response:
                    if response.status!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):
                        raise ValueError('Release server returned an incorrect range')
                    data=response.read()
                if len(data)!=end-start+1: raise ValueError('Incomplete release range')
                out.write_bytes(data)
                return
            except Exception:
                if attempt==3:raise
                time.sleep(2)
    with ThreadPoolExecutor(max_workers=5) as executor:
        pending=[executor.submit(fetch,index) for index in range(count)]
        for completed,future in enumerate(as_completed(pending),1):
            future.result()
            if completed%8==0 or completed==count:
                print(f'Electron release: {completed}/{count} verified ranges',flush=True)
    partial=target.with_suffix('.partial')
    with partial.open('wb') as stream:
        for index in range(count):
            with (parts/f'{index:05d}').open('rb') as part:shutil.copyfileobj(part,stream)
    with partial.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=expected: raise ValueError('Electron checksum mismatch')
    partial.replace(target)
with target.open('rb') as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest()!=expected: raise ValueError('Electron checksum mismatch')
destination=module/'dist'
with zipfile.ZipFile(target) as archive:
    for item in archive.infolist():
        out=(destination/item.filename).resolve()
        if not out.is_relative_to(destination.resolve()): raise ValueError('Unsafe archive path')
    archive.extractall(destination)
(module/'path.txt').write_text('electron.exe','utf-8')
print('Electron installed; archive checksum verified against official npm package.',flush=True)
