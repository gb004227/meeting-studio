"""Build independent program/model ZIPs with a shared, documented install layout."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

root=Path(__file__).resolve().parents[1]
version=json.loads((root/'package.json').read_text('utf-8'))['version']
bundle=root/'release'/f'听会-{version}-Windows-x64-完整版'
models=bundle/'resources'/'models'
if not (models/'manifest.json').is_file():raise ValueError('Build and verify the full portable folder first')
output=root/'release'/'github'/f'v{version}'
output.mkdir(parents=True,exist_ok=True)
application=f'听会-{version}-Windows-x64'
paths=[p for p in bundle.rglob('*') if p.is_file() and '__pycache__' not in p.parts and not p.is_relative_to(bundle/'resources'/'artifacts')]
groups={'program':[p for p in paths if not p.is_relative_to(models)],'models':[p for p in paths if p.is_relative_to(models)]}
archives=[]
for kind,files in groups.items():
    name=f'TingHui-{version}-Windows-x64-program.zip' if kind=='program' else f'TingHui-{version}-models.zip'
    destination=output/name;partial=destination.with_suffix('.zip.part')
    print(f'Preparing {kind}: {len(files)} files',flush=True)
    with zipfile.ZipFile(partial,'w',zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
        for index,path in enumerate(files,1):
            member=Path('models')/path.relative_to(models) if kind=='models' else Path(application)/path.relative_to(bundle)
            if kind=='program' and path.name in ('先读我-换电脑使用说明.md','先读我-换电脑使用说明.txt'):
                archive.writestr(str(member).replace('\\','/'),(root/'GITHUB安装说明.md').read_text('utf-8'))
            elif kind=='program' and path.name=='使用说明.md':
                archive.writestr(str(member).replace('\\','/'),(root/'README.md').read_text('utf-8'))
            else:archive.write(path,member,compress_type=zipfile.ZIP_STORED if path.suffix=='.safetensors' else zipfile.ZIP_DEFLATED)
            if index%2000==0:print(f'{kind}: {index}/{len(files)} files',flush=True)
        prefix=Path('models') if kind=='models' else Path(application)
        archive.write(root/'THIRD_PARTY_NOTICES.md',prefix/'THIRD_PARTY_NOTICES.md')
        if kind=='models':archive.write(root/'vendor'/'moss'/'LICENSE',prefix/'LICENSE-APACHE-2.0.txt')
    if partial.stat().st_size>=2*1024**3:raise ValueError('Release asset reaches the GitHub 2 GiB limit: '+name)
    print(f'Checking {kind} ZIP integrity...',flush=True)
    with zipfile.ZipFile(partial) as archive:
        if error:=archive.testzip():raise ValueError('Corrupt member: '+error)
        names=archive.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP members')
        if kind=='models':assert 'models/MOSS-Transcribe-Diarize/config.json' in names
        else:
            for required in ('听会.exe','resources/python/python.exe','resources/moss-python/python.exe','resources/python/msvcp140.dll','resources/moss-python/vcruntime140_threads.dll'):
                assert application+'/'+required in names,required
            assert not any('/resources/models/' in name for name in names)
    partial.replace(destination)
    with destination.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    archives.append({'name':name,'bytes':destination.stat().st_size,'sha256':digest,'files':len(names)})
    print(json.dumps(archives[-1]),flush=True)
shutil.copy2(root/'GITHUB安装说明.md',output/'INSTALL.zh-CN.txt')
(output/'SHA256SUMS.txt').write_text(''.join(f"{item['sha256']}  {item['name']}\n" for item in archives),'utf-8')
(output/'release-manifest.json').write_text(json.dumps({'version':version,'assets':archives},ensure_ascii=False,indent=2),'utf-8')
print('GitHub release files are ready.',flush=True)
