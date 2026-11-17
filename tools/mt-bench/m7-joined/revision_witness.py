"""Optional finite synthetic revision witness on the existing prepare/run path."""
import hashlib
import json
from pathlib import Path
from contract import require

DEST='/run/ns-revision-witness'
FILES=('lib/pgstream/realtime-output.js','lib/server/realtime/runtime.js','lib/pgstream/typed-checkpoint.js','lib/pgstream/realtime-receipt.js','lib/pgstream/activity-scheduler.js')
HELPERS=('revision-witness.cjs','revision-witness-preload.cjs')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def install(config,d,m,targets_file):
    if not targets_file:return
    d=Path(d)
    require(m.get('runPurpose')=='discovery' and m.get('profile')=='pgstream-sample','M7_REVISION_SCOPE')
    data=Path(targets_file).read_bytes();require(len(data)<=1024,'M7_REVISION_TARGET_BOUND')
    targets=json.loads(data)
    import re
    require(isinstance(targets,list) and 1<=len(targets)<=2 and all(isinstance(t,dict) and set(t)=={'tenant','storedId'} and re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',t['tenant']) and t['tenant']!='00000000-0000-0000-0000-000000000000' and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',t['storedId']) for t in targets) and len({t['tenant'] for t in targets})==len(targets),'M7_REVISION_TARGETS')
    source_files={file:sha(d/'core'/file) for file in FILES}
    directory=d/'state/revision-witness';directory.mkdir(mode=0o700)
    for helper in HELPERS:(directory/helper).write_bytes(Path(__file__).with_name(helper).read_bytes())
    record={'targets':targets,'sourceFiles':source_files,'helpers':{name:sha(directory/name) for name in HELPERS},'maxEvents':64,'maxBytes':65536,'scope':'selected synthetic IDs; no general telemetry, source replacement or clock synchronization'}
    for role in ('evaluator','realtime'):
        spec=config['services'][role];command=['node','deploy/multitenant/entrypoint.js',role]
        require(spec.get('command')==command and not spec.get('entrypoint') and not spec.get('environment',{}).get('NODE_OPTIONS'),'M7_REVISION_COMMAND')
        spec['command']=['node','--require',DEST+'/revision-witness-preload.cjs',*command[1:]]
        spec.setdefault('environment',{})['M7_REVISION_WITNESS_CONFIG']=DEST+'/'+role+'.json'
        spec.setdefault('volumes',[]).append({'type':'bind','source':str(directory),'target':DEST,'read_only':True})
        value={'root':'/opt/app','out':'/run/ns-ipc/revision-witness-'+role+'.json','owner':m['owner'],'source':m['pair']['core'],'targets':targets,'sourceFiles':source_files}
        (directory/(role+'.json')).write_text(json.dumps(value)+'\n')
    value={'root':str(d/'core'),'out':str(d/'load/revision-witness-client.json'),'owner':m['owner'],'source':m['pair']['core'],'targets':targets,'sourceFiles':source_files}
    (directory/'client.json').write_text(json.dumps(value)+'\n')
    record['configs']={name:sha(directory/(name+'.json')) for name in ('evaluator','realtime','client')}
    m['revisionWitness']=record

def verify(config,d,m):
    record=m.get('revisionWitness');d=Path(d)
    for role in ('evaluator','realtime'):
        spec=config.get('services',{}).get(role,{})
        if not record:
            require('M7_REVISION_WITNESS_CONFIG' not in spec.get('environment',{}) and DEST+'/revision-witness-preload.cjs' not in spec.get('command',[]) and not any(v.get('target')==DEST for v in spec.get('volumes',[])),'M7_REVISION_RECORD_REQUIRED');continue
        require(spec.get('command')==['node','--require',DEST+'/revision-witness-preload.cjs','deploy/multitenant/entrypoint.js',role] and spec.get('environment',{}).get('M7_REVISION_WITNESS_CONFIG')==DEST+'/'+role+'.json','M7_REVISION_COMMAND')
        require([v for v in spec.get('volumes',[]) if v.get('target')==DEST]==[{'type':'bind','source':str(d/'state/revision-witness'),'target':DEST,'read_only':True}],'M7_REVISION_MOUNT')
    if not record:return
    directory=d/'state/revision-witness'
    require(all(sha(directory/name)==value==sha(Path(__file__).with_name(name)) for name,value in record['helpers'].items()),'M7_REVISION_HELPER_BYTES')
    require(all(sha(directory/(name+'.json'))==value for name,value in record['configs'].items()),'M7_REVISION_CONFIG_BYTES')
    require(all(sha(d/'core'/name)==value for name,value in record['sourceFiles'].items()),'M7_REVISION_SOURCE_BYTES')

def probe_environment(d,m):
    return {'M7_REVISION_WITNESS_CONFIG':str(Path(d)/'state/revision-witness/client.json')} if m.get('revisionWitness') else {}

def retain(d,m):
    """Small bounded file capture reduction; source originals remain untouched."""
    if not m.get('revisionWitness'):return None
    import subprocess
    d=Path(d)
    files=sorted([*(d/'state/ipc').glob('revision-witness-*.json.*.json'),*(d/'load').glob('revision-witness-client.json.*.json')])
    if not files:return {'verdict':'UNMEASURED','reasons':['M7_REVISION_NO_CAPTURE']}
    if len(files)>8 or any(file.stat().st_size>70000 for file in files):return {'verdict':'UNMEASURED','reasons':['M7_REVISION_CAPTURE_BOUND']}
    values=[json.loads(file.read_text()) for file in files]
    require(all(value.get('owner')==m['owner'] and value.get('source')==m['pair']['core'] and value.get('version')==1 for value in values),'M7_REVISION_CAPTURE_PROVENANCE')
    script="const w=require(process.argv[1]);let data='';process.stdin.on('data',v=>data+=v);process.stdin.on('end',()=>console.log(JSON.stringify(w.correlate(JSON.parse(data)))));"
    result=json.loads(subprocess.check_output([m['generator']['tools']['node']['path'],'-e',script,str(Path(__file__).with_name('revision-witness.cjs'))],input=json.dumps(values),text=True,timeout=5))
    result['captures']=[{'path':str(file.relative_to(d)),'sha256':sha(file)} for file in files]
    return result
