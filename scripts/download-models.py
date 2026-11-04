from pathlib import Path
import os
import json
import subprocess
import sys
import urllib.request

os.environ.setdefault('HF_HOME',r'K:\工具箱\MOSS model\.cache\huggingface')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
root=Path(r'K:\工具箱\MOSS model')
revision=json.loads((Path(__file__).parent/'model-revisions.json').read_text('utf-8'))['moss_model_revision']
metadata=json.load(urllib.request.urlopen('https://huggingface.co/api/models/OpenMOSS-Team/MOSS-Transcribe-Diarize/revision/'+revision,timeout=45))
model_root=root/'MOSS-Transcribe-Diarize'
model_root.mkdir(parents=True,exist_ok=True)
for entry in metadata['siblings']:
    name=entry['rfilename']
    if name.endswith(('.md','.png','.jpg','.safetensors')): continue
    destination=(model_root/name).resolve()
    if not destination.is_relative_to(model_root.resolve()): raise ValueError('Invalid model file path')
    if not destination.exists():
        print('Downloading model metadata:',name,flush=True)
        with urllib.request.urlopen(f'https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize/resolve/{revision}/{name}',timeout=120) as response:
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(response.read())
subprocess.run([sys.executable,str(Path(__file__).parent/'download-weight.py')],check=True)
from modelscope import snapshot_download as download_component
download_component('iic/speech_campplus_sv_zh-cn_16k-common',local_dir=str(root/'auxiliary'/'camplusplus'))
subprocess.run([sys.executable,str(Path(__file__).parent/'download-live-model.py')],check=True)
subprocess.run([sys.executable,str(Path(__file__).parent/'download-speaker-model.py')],check=True)
print('MOSS and CAM++ downloaded. Local transcription does not send audio to the cloud.')
