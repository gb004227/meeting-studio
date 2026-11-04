"""Create a self-contained Windows desktop folder with its own Python runtime."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--full',action='store_true',help='Include standalone MOSS Python and all local models')
args=parser.parse_args()
version=json.loads((root/'package.json').read_text('utf-8'))['version']
output=root/'release'/(f'听会-{version}-Windows-x64-完整版' if args.full else '听会 Windows')
if not output.resolve().is_relative_to((root/'release').resolve()): raise ValueError('Invalid output directory')
electron=root/'node_modules'/'electron'/'dist'
if not (electron/'electron.exe').exists(): raise RuntimeError('Electron is not installed')
shutil.copytree(electron,output,dirs_exist_ok=True)
application=output/'resources'/'app'
application.mkdir(parents=True,exist_ok=True)
for folder in ('dist','electron'):
    shutil.copytree(root/folder,application/folder,dirs_exist_ok=True)
manifest=json.loads((root/'package.json').read_text('utf-8'))
(application/'package.json').write_text(json.dumps({'name':manifest['name'],'version':manifest['version'],'main':'electron/main.cjs','productName':'听会'},ensure_ascii=False),'utf-8')
resources=output/'resources'
shutil.copytree(root/'backend',resources/'backend',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','tests','*.egg-info'))
shutil.copytree(root/'scripts',resources/'scripts',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
base=Path(subprocess.check_output([str(root/'.venv'/'Scripts'/'python.exe'),'-c','import sys;print(sys.base_prefix)'],text=True).strip())
python_target=resources/'python'
shutil.copytree(base,python_target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','test','tests','Doc','Tools'))
site=root/'.venv'/'Lib'/'site-packages'
shutil.copytree(site,python_target/'Lib'/'site-packages',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','tests','test','pytest*','_pytest','pygments','*.egg-info','__editable__*'))
exe=output/'electron.exe'
target=output/'听会.exe'
if exe.exists():
    if target.exists(): target.unlink()
    exe.rename(target)
shutil.copy2(root/'README.md',output/'使用说明.md')
if (root/'交付与验证.md').exists():shutil.copy2(root/'交付与验证.md',output/'交付与验证.md')
shutil.copy2(root/'assets'/'app.ico',output/'听会.ico')
if args.full:
    moss_python=root/'.moss-venv'/'Scripts'/'python.exe'
    moss_base=Path(subprocess.check_output([str(moss_python),'-c','import sys;print(sys.base_prefix)'],text=True).strip())
    moss_target=resources/'moss-python'
    print('Copying standalone local inference runtime...',flush=True)
    shutil.copytree(moss_base,moss_target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','test','tests','Doc','Tools'))
    shutil.copytree(root/'.moss-venv'/'Lib'/'site-packages',moss_target/'Lib'/'site-packages',dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__','test','tests','*.egg-info','__editable__*','_virtualenv*'))
    shutil.copytree(root/'vendor'/'moss'/'moss_transcribe_diarize',moss_target/'Lib'/'site-packages'/'moss_transcribe_diarize',dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
    license_file=root/'vendor'/'moss'/'LICENSE'
    if license_file.exists():shutil.copy2(license_file,moss_target/'MOSS-LICENSE.txt')
    source_models=Path(r'K:\工具箱\MOSS model')
    models=resources/'models'
    print('Copying MOSS and offline streaming models...',flush=True)
    shutil.copytree(source_models/'MOSS-Transcribe-Diarize',models/'MOSS-Transcribe-Diarize',dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('.cache','__pycache__','.git','*.part'))
    shutil.copytree(source_models/'auxiliary'/'paraformer-streaming',models/'auxiliary'/'paraformer-streaming',dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('*.part'))
    cam_name='3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx'
    cam_target=models/'auxiliary'/'camplusplus'
    cam_target.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source_models/'auxiliary'/'camplusplus'/cam_name,cam_target/cam_name)
    checks={
        'MOSS-Transcribe-Diarize/model-00000-of-00001.safetensors':'9a0ceb4ab7330357db3ff583dba8d83625d5b733b00e1d55d6970e11b07026c4',
        'auxiliary/paraformer-streaming/encoder.int8.onnx':'81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a',
        'auxiliary/paraformer-streaming/decoder.int8.onnx':'f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f',
        f'auxiliary/camplusplus/{cam_name}':'f682b514c05d947ee3fa91cd6ec6c5c7543479a128373fa29b1faedccd21fd11',
    }
    for name,digest in checks.items():
        with (models/name).open('rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest()!=digest:raise ValueError('Model integrity check failed: '+name)
    (models/'manifest.json').write_text(json.dumps({'sha256':checks},indent=2),'utf-8')
    crt=Path(r'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Redist\MSVC\14.51.36231\x64\Microsoft.VC145.CRT')
    if not crt.is_dir():raise RuntimeError('The build host is missing the redistributable MSVC runtime')
    for runtime in (python_target,moss_target):
        for library in crt.glob('*.dll'):shutil.copy2(library,runtime/library.name)
    licenses=output/'第三方许可'
    licenses.mkdir(exist_ok=True)
    shutil.copy2(crt.parents[5]/'Licenses'/'2052'/'Redist.txt',licenses/'MSVC-Redist.txt')
    shutil.copy2(root/'换电脑使用说明.md',output/'先读我-换电脑使用说明.md')
    shutil.copy2(root/'换电脑使用说明.md',output/'先读我-换电脑使用说明.txt')
print(str(target),flush=True)
