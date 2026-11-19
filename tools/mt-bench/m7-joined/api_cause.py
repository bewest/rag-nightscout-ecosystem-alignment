"""Explicit source-pinned private API cause observer; no application API or actor."""
import hashlib
import json
from pathlib import Path
import subprocess
from contract import require
DEST='/run/ns-api-cause'
FILES=('lib/server/tenant-app/index.js','lib/server/serve/api-admission.js')
HELPERS=('api-cause.cjs','api-cause-preload.cjs')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _roles(config):
    return [role for role,spec in config.get('services',{}).items() if spec.get('command')==['node','deploy/multitenant/entrypoint.js','api'] or spec.get('command')==['node','--require',DEST+'/api-cause-preload.cjs','deploy/multitenant/entrypoint.js','api']]
def install(config,d,m,enabled=False):
    if not enabled:return
    d=Path(d)
    require(m.get('runPurpose')=='discovery' and m.get('profile')=='pgstream-sample','M7_API_CAUSE_SCOPE')
    roles=_roles(config);require(1<=len(roles)<=2,'M7_API_CAUSE_ROLES')
    source_files={file:sha(d/'core'/file) for file in FILES}
    source=(d/'core'/FILES[0]).read_text()
    require('createTenantApp' in source and 'admitRequest' in source and 'exchange' in source,'M7_API_CAUSE_SOURCE_CONTRACT')
    directory=d/'state/api-cause';directory.mkdir(mode=0o700)
    for helper in HELPERS:(directory/helper).write_bytes(Path(__file__).with_name(helper).read_bytes())
    record={'roles':roles,'sourceFiles':source_files,'helpers':{name:sha(directory/name) for name in HELPERS},'maxEvents':64,'maxBytes':32768,'scope':'fixed admission/exchange outcomes; no error message, stack, SQL, URL, credential or body'}
    for role in roles:
        spec=config['services'][role]
        require(spec.get('command')==['node','deploy/multitenant/entrypoint.js','api'] and not spec.get('entrypoint') and not spec.get('environment',{}).get('NODE_OPTIONS'),'M7_API_CAUSE_COMMAND')
        spec['command']=['node','--require',DEST+'/api-cause-preload.cjs','deploy/multitenant/entrypoint.js','api']
        spec.setdefault('environment',{})['M7_API_CAUSE_CONFIG']=DEST+'/'+role+'.json'
        spec.setdefault('volumes',[]).append({'type':'bind','source':str(directory),'target':DEST,'read_only':True})
        value={'root':'/opt/app','out':'/run/ns-ipc/api-cause-'+role+'.json','owner':m['owner'],'source':m['pair']['core'],'sourceFiles':source_files}
        (directory/(role+'.json')).write_text(json.dumps(value)+'\n')
    record['configs']={role:sha(directory/(role+'.json')) for role in roles};m['apiCause']=record

def verify(config,d,m):
    d=Path(d);record=m.get('apiCause')
    observed=[role for role,s in config.get('services',{}).items() if 'M7_API_CAUSE_CONFIG' in (s.get('environment') or {}) or DEST+'/api-cause-preload.cjs' in (s.get('command') or []) or any(v.get('target')==DEST for v in (s.get('volumes') or []))]
    if not record:require(not observed,'M7_API_CAUSE_RECORD_REQUIRED');return
    require(record.get('roles')==_roles(config) and sorted(observed)==sorted(record['roles']) and 1<=len(observed)<=2,'M7_API_CAUSE_ROLES')
    require(set(record.get('sourceFiles',{}))==set(FILES) and set(record.get('helpers',{}))==set(HELPERS) and record.get('maxEvents')==64 and record.get('maxBytes')==32768,'M7_API_CAUSE_RECORD')
    directory=d/'state/api-cause'
    for role in record['roles']:
        spec=config['services'][role]
        require(spec.get('command')==['node','--require',DEST+'/api-cause-preload.cjs','deploy/multitenant/entrypoint.js','api'] and spec.get('environment',{}).get('M7_API_CAUSE_CONFIG')==DEST+'/'+role+'.json' and not spec.get('entrypoint') and not spec.get('environment',{}).get('NODE_OPTIONS'),'M7_API_CAUSE_COMMAND')
        require([v for v in spec.get('volumes',[]) if v.get('target')==DEST]==[{'type':'bind','source':str(directory),'target':DEST,'read_only':True}],'M7_API_CAUSE_MOUNT')
    require(set(record.get('configs',{}))==set(record['roles']),'M7_API_CAUSE_CONFIG_BYTES')
    require(all(sha(directory/name)==value==sha(Path(__file__).with_name(name)) for name,value in record['helpers'].items()),'M7_API_CAUSE_HELPER_BYTES')
    require(all(sha(directory/(role+'.json'))==value for role,value in record['configs'].items()),'M7_API_CAUSE_CONFIG_BYTES')
    require(all(sha(d/'core'/name)==value for name,value in record['sourceFiles'].items()),'M7_API_CAUSE_SOURCE_BYTES')

def retain(d,m):
    d=Path(d);record=m.get('apiCause')
    if not record:return None
    files=sorted((d/'state/ipc').glob('api-cause-*.json.*.json'))
    if not files:return {'verdict':'UNMEASURED','code':'M7_API_CAUSE_NO_CAPTURE'}
    if len(files)>8 or any(p.stat().st_size>32768 for p in files):return {'verdict':'UNMEASURED','code':'M7_API_CAUSE_CAPTURE_BOUND'}
    try:values=[json.loads(p.read_text()) for p in files]
    except (OSError,ValueError):return {'verdict':'UNMEASURED','code':'M7_API_CAUSE_CAPTURE_UNREADABLE'}
    script="const c=require(process.argv[1]);let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{const v=JSON.parse(s);console.log(JSON.stringify(c.assess(v.states,v.binding)));});"
    binding={'owner':m['owner'],'source':m['pair']['core'],'sourceFiles':record['sourceFiles']}
    result=json.loads(subprocess.check_output([m['generator']['tools']['node']['path'],'-e',script,str(Path(__file__).with_name('api-cause.cjs'))],input=json.dumps({'states':values,'binding':binding}),text=True,timeout=5))
    result['captures']=[{'path':str(p.relative_to(d)),'sha256':sha(p)} for p in files];return result
