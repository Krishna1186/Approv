"""Replay saved sessions using the archived implementation that produced them."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from approv.harness.shopping import digest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pack',required=True);p.add_argument('--runs',required=True);p.add_argument('--archives',required=True)
    a=p.parse_args();pack=json.loads(Path(a.pack).read_text(encoding='utf-8'))
    if digest({k:v for k,v in pack.items() if k!='content_hash'})!=pack['content_hash']:
        raise ValueError('pack hash mismatch')
    tasks={t['case']['id']:t for t in pack['tasks']};archives={}
    manifest=json.loads((Path(a.runs)/'manifest.json').read_text(encoding='utf-8'))
    if manifest['pack_hash']!=pack['content_hash']:raise ValueError('Run pack differs from replay pack')
    for folder in Path(a.archives).glob('runtime*'):
        root=folder/'approv'
        files=sorted(f for directory in ('algebra','harness','types') for f in (root/directory).glob('*.py'))
        if files:archives.setdefault(digest({f.relative_to(root).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files}),[]).append(folder)
    verified=0
    code='''import json,sys
sys.path.insert(0,sys.argv[1])
from approv.harness.shopping import Inventory,ShoppingCase,replay,digest
payload=json.load(sys.stdin);r=payload['record']
if digest({k:v for k,v in r.items() if k!='record_hash'})!=r['record_hash']:raise ValueError('record hash mismatch')
replay(r['result'],Inventory.model_validate(payload['inventory']),ShoppingCase.model_validate(r['case']))
'''
    for file in Path(a.runs).glob('*.json'):
        record=json.loads(file.read_text(encoding='utf-8'))
        if 'result' not in record:continue
        candidates=archives.get(record['result']['binding']['implementation']['source_hash'],[])
        runtime=next((folder for folder in candidates if not manifest.get('driver_sha256') or
            hashlib.sha256((folder/'run_study.py').read_bytes()).hexdigest()==manifest['driver_sha256']),None)
        if runtime is None:raise ValueError('Missing archived implementation: '+str(file))
        if manifest.get('driver_sha256') and hashlib.sha256((runtime/'run_study.py').read_bytes()).hexdigest()!=manifest['driver_sha256']:
            raise ValueError('Archived observation driver differs from manifest')
        task=tasks[record['source_case_id']]
        payload={'record':record,'inventory':task.get('inventory',pack.get('inventory'))}
        subprocess.run([sys.executable,'-c',code,str(runtime.resolve())],input=json.dumps(payload),text=True,check=True,
                       encoding='utf-8',capture_output=True)
        verified+=1
    print('Replayed',verified,'sessions against archived code and original inventory.')
