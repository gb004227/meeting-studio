"""Install the verified CAM++ ONNX model used without a Torch worker."""
import hashlib
from pathlib import Path
import urllib.request

repository='csukuangfj/speaker-embedding-models'
revision='0743f301363dec56491a490f6d6cbc9d67f9a3bf'
name='3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx'
digest='f682b514c05d947ee3fa91cd6ec6c5c7543479a128373fa29b1faedccd21fd11'
directory=Path(r'K:\工具箱\MOSS model\auxiliary\camplusplus')
directory.mkdir(parents=True,exist_ok=True)
destination=directory/name

def valid(path):
    if not path.exists() or path.stat().st_size!=28281138:return False
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()==digest

if not valid(destination):
    partial=destination.with_suffix('.onnx.part')
    with urllib.request.urlopen(f'https://huggingface.co/{repository}/resolve/{revision}/{name}?download=true',timeout=90) as response,partial.open('wb') as output:
        while block:=response.read(1024*1024):output.write(block)
    if not valid(partial):raise ValueError('CAM++ model integrity check failed')
    partial.replace(destination)
print('Verified local ONNX speaker model is ready.',flush=True)
