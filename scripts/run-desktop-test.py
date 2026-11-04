import os
import subprocess
import sys
import tempfile
from pathlib import Path
from meeting_app.config import ROOT,DATA

env=os.environ.copy()
env.pop('ELECTRON_RUN_AS_NODE',None)
profile=('packaged-ui-test' if len(sys.argv)>1 else 'ui-test')+('-moss' if env.get('MEETING_SMOKE_ENGINE')=='moss' else '')
folder=Path(tempfile.mkdtemp(prefix=profile+'-',dir=ROOT/'runtime'))
from meeting_app.vault import Vault
from meeting_app.store import Store
Vault(folder).set('doubao_api_key','' if env.get('MEETING_SMOKE_ENGINE')=='moss' else Vault(DATA).get('doubao_api_key'))
resources=Path(sys.argv[1]).resolve().parent/'resources' if len(sys.argv)>1 else ROOT
if (resources/'moss-python'/'python.exe').is_file():
    # Simulate persisted settings from a laptop whose install no longer exists.
    Store(folder).save_settings({'moss_python':str(folder/'previous-laptop'/'python.exe'),'moss_path':str(folder/'previous-laptop'/'model')})
    env['MEETING_SMOKE_BUNDLED']='1'
    env['HF_HOME']=str(folder/'empty-huggingface-cache')
else:Store(folder).save_settings({'moss_python':str(ROOT/'.moss-venv'/'Scripts'/'python.exe')})
env.update(MEETING_SMOKE='1',MEETING_DATA_DIR=str(folder),MEETING_FAKE_AUDIO=str(DATA/'synthetic-probe-16k.wav'))
args=[sys.argv[1]] if len(sys.argv)>1 else [str(ROOT/'node_modules'/'electron'/'dist'/'electron.exe'),'.']
raise SystemExit(subprocess.call(args,cwd=ROOT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
