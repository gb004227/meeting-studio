"""Check imported Visual C++ DLL names against each bundled Python's local DLLs."""
from pathlib import Path
import json
import mmap
import struct

root=Path(__file__).resolve().parents[1]
version=json.loads((root/'package.json').read_text('utf-8'))['version']
folder=root/'release'/f'听会-{version}-Windows-x64-完整版'


def imports(path):
    with path.open('rb') as source,mmap.mmap(source.fileno(),0,access=mmap.ACCESS_READ) as data:
        if data[:2]!=b'MZ':return []
        pe=struct.unpack_from('<I',data,0x3c)[0]
        count=struct.unpack_from('<H',data,pe+6)[0]
        size=struct.unpack_from('<H',data,pe+20)[0]
        optional=pe+24
        directory=optional+(112 if struct.unpack_from('<H',data,optional)[0]==0x20b else 96)
        rva=struct.unpack_from('<I',data,directory+8)[0]
        if not rva:return []
        sections=[]
        for index in range(count):
            virtual_size,address,raw_size,raw=struct.unpack_from('<IIII',data,optional+size+index*40+8)
            sections.append((address,max(virtual_size,raw_size),raw))
        def offset(value):
            for address,length,raw in sections:
                if address<=value<address+length:return raw+value-address
            raise ValueError(f'Invalid import address in {path.name}')
        position=offset(rva);names=[]
        while any(data[position:position+20]):
            name=offset(struct.unpack_from('<I',data,position+12)[0])
            names.append(data[name:data.find(b'\0',name)].decode().lower())
            position+=20
        return names


results=[]
for name in ('python','moss-python'):
    runtime=folder/'resources'/name
    required=set();present=set();files=0
    for path in runtime.rglob('*'):
        if path.suffix.lower() not in ('.pyd','.dll'):continue
        files+=1
        present.add(path.name.lower())
        required.update(value for value in imports(path) if value.startswith(('msvcp','vcruntime','concrt','vcomp','vcamp')))
    missing=sorted(required-present)
    if missing:raise ValueError(f'Missing C++ libraries in {name}: {missing}')
    results.append({'runtime':name,'native_files_checked':files,'required_runtime_dlls':sorted(required)})
report={'status':'PASS','version':version,'runtimes':results}
(root/'artifacts'/'full-portable-native-deps.json').write_text(json.dumps(report,indent=2),'utf-8')
print(json.dumps(report),flush=True)
