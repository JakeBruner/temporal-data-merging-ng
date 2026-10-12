"""Frozen external fixture driver: only candidate CLI executes in work cell."""
import base64
import copy
import hashlib
import json
from ormas_acceptance import run

COMPILER = '6208cd158fe74d2e71f0917f85bd761c7df118b1b930a3280353412de7add9ff'
NOW = '2026-10-12T20:00:00Z'
NODE = 'linux-node-test-v1'
PYTHON = 'linux-python-pytest-v1'

def catalog():
    return {'schema_version':'outcomes.support-catalog.v1','revision':'2026-10-04.1','verifier_compiler_sha256':COMPILER,'profiles':[
      {'profile_id':NODE,'status':'development','lock_format':'npm-lock-v3','limits':{'max_files':10000,'max_bytes':67108864}},
      {'profile_id':PYTHON,'status':'development','lock_format':'pip-hashes-v1','limits':{'max_files':10000,'max_bytes':67108864,'source_max_bytes':134217728}}]}

def digest(cat):
    return 'sha256:'+hashlib.sha256(json.dumps(cat,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def capacity(cat=None, profile=NODE):
    return {'schema_version':'ormas.offline-capacity.v1','catalog_digest':digest(cat or catalog()),'profile_id':profile,'observed_at':NOW,'project_admitted':True,'qualified_miners':2,'miners_with_cells':1,'qualified_checkers':2,'required_validators':1}

def npm_files():
    deps={'demo':'1.2.3'}
    manifest={'name':'fixture','version':'1.0.0','dependencies':deps}
    lock={'name':'fixture','lockfileVersion':3,'packages':{'':{'dependencies':deps},'node_modules/demo':{'version':'1.2.3','resolved':'https://registry.npmjs.org/demo/-/demo-1.2.3.tgz','integrity':'sha512-'+base64.b64encode(b'x'*64).decode()}}}
    return {'package.json':json.dumps(manifest),'package-lock.json':json.dumps(lock),'src/app.js':'export const ready = true;\n'}

def scenario(profile=NODE, with_capacity=True):
    files=npm_files() if profile==NODE else {'requirements.lock':'pytest==8.4.2 --hash=sha256:'+'a'*64+'\n','app.py':'answer = 42\n'}
    return {'profile':profile,'catalog':catalog(),'files':files,'inventory':list(files),'capacity':capacity(profile=profile) if with_capacity else None,'now':NOW}

_SCRIPT = r"""
import hashlib, json, os, pathlib, subprocess, sys, tempfile
spec=json.loads(sys.argv[1])
cli=str(pathlib.Path('tools/ormas_readiness.py').absolute())
with tempfile.TemporaryDirectory(prefix='ormas-readiness-') as td:
    temp=pathlib.Path(td); repo=temp/'repo'; repo.mkdir()
    for name,data in spec.get('files',{}).items():
        path=repo/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(data)
    for name,size in spec.get('sparse',{}).items():
        path=repo/name; path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('wb') as fh: fh.truncate(size)
    for name,target in spec.get('symlinks',{}).items():
        path=repo/name; path.parent.mkdir(parents=True,exist_ok=True); path.symlink_to(target)
    catalog=temp/'catalog.json'; catalog.write_text(spec.get('catalog_raw',json.dumps(spec['catalog'])))
    argv=[sys.executable,cli,'--repo',str(repo),'--catalog',str(catalog),'--profile',spec['profile'],'--now',spec.get('now','2026-10-12T20:00:00Z')]
    if 'inventory' in spec:
        inventory=temp/'inventory.json'; inventory.write_text(spec.get('inventory_raw',json.dumps(spec['inventory']))); argv+=['--inventory',str(inventory)]
    if spec.get('capacity') is not None or 'capacity_raw' in spec:
        cap=temp/'capacity.json'; cap.write_text(spec.get('capacity_raw',json.dumps(spec.get('capacity')))); argv+=['--capacity',str(cap)]
    for kind in spec.get('oversized_inputs', []):
        target={'catalog':catalog,'inventory':temp/'inventory.json','capacity':temp/'capacity.json'}[kind]
        with target.open('a') as fh: fh.write(' '*(4*1024*1024+1))
    def fingerprint():
        result={}
        for p in sorted(temp.rglob('*')):
            name=p.relative_to(temp).as_posix()
            if p.is_symlink(): result[name]=['link',os.readlink(p)]
            elif p.is_file():
                st=p.stat(); result[name]=[st.st_size,st.st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest() if st.st_size<=4*1024*1024 else None]
            elif p.is_dir(): result[name]=['dir']
        return result
    before=fingerprint()
    child_env=os.environ.copy(); child_env['PYTHONDONTWRITEBYTECODE']='1'
    if spec.get('no_git'): child_env['PATH']=''
    result=subprocess.run(argv,capture_output=True,text=True,timeout=15,env=child_env)
    after=fingerprint()
    repeated=None
    if spec.get('repeat'):
        again=subprocess.run(argv,capture_output=True,text=True,timeout=15,env=child_env)
        repeated={'returncode':again.returncode,'stdout':again.stdout,'stderr':again.stderr}
        after=fingerprint()
    print(json.dumps({'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'before':before,'after':after,'repeated':repeated}))
"""

def invoke(spec):
    observed=run(['python3','-c',_SCRIPT,json.dumps(spec)],timeout_s=30)
    assert observed['returncode']==0, 'fixture driver failed: '+observed.get('output','')[-400:]
    try:
        result=json.loads(observed['output'])
        report=json.loads(result['stdout'])
    except (ValueError,KeyError,TypeError):
        assert False, 'CLI must emit one JSON object'
    assert isinstance(report,dict), 'CLI JSON must be an object'
    assert result['stderr']=='', 'CLI must not emit raw errors'
    return result,report

def codes(report,section):
    entries=report.get(section,{}).get('findings',[])
    assert isinstance(entries,list), 'findings must be a list'
    assert all(isinstance(x,dict) and isinstance(x.get('code'),str) for x in entries), 'findings require codes'
    return [x['code'] for x in entries]
