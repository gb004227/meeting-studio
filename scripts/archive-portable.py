"""Archive the complete Windows folder with ZIP64 and verify every entry's CRC."""
from pathlib import Path
import hashlib
import json
import zipfile

root=Path(__file__).resolve().parents[1]
version=json.loads((root/'package.json').read_text('utf-8'))['version']
folder=root/'release'/f'听会-{version}-Windows-x64-完整版'
if not (folder/'resources/models/manifest.json').is_file():raise ValueError('Build the complete package first')
destination=folder.parent/(folder.name+'.zip')
temporary=destination.with_suffix('.zip.part')
files=[p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and not p.is_relative_to(folder/'resources'/'artifacts')]
total=sum(p.stat().st_size for p in files)
written=0
with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
    for index,path in enumerate(files,1):
        archive.write(path,path.relative_to(folder.parent),compress_type=zipfile.ZIP_STORED if path.suffix=='.safetensors' else zipfile.ZIP_DEFLATED)
        written+=path.stat().st_size
        if index%1000==0:print(f'Archived {index}/{len(files)} files, {written*100/max(total,1):.0f}% of bytes',flush=True)
print('Verifying archive CRC...',flush=True)
with zipfile.ZipFile(temporary) as archive:
    failure=archive.testzip()
    if failure:raise ValueError('ZIP integrity check failed: '+failure)
temporary.replace(destination)
with destination.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
destination.with_suffix('.zip.sha256.txt').write_text(f'{digest}  {destination.name}\n','utf-8')
print(json.dumps({'archive':str(destination),'compressed_bytes':destination.stat().st_size,'uncompressed_bytes':total,'files':len(files),'sha256':digest},ensure_ascii=False),flush=True)
