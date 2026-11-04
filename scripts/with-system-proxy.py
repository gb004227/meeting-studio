"""Use Windows Internet Settings for task-owned dependency downloads; never log proxy credentials."""
import os
import subprocess
import sys
import urllib.request

environment=os.environ.copy()
proxies=urllib.request.getproxies()
for scheme in ('http','https'):
    if scheme in proxies and not environment.get(scheme.upper()+'_PROXY'):
        environment[scheme.upper()+'_PROXY']=proxies[scheme]
environment['NO_PROXY']='127.0.0.1,localhost'
environment['NODE_USE_ENV_PROXY']='1'
raise SystemExit(subprocess.call(sys.argv[1:],env=environment))
