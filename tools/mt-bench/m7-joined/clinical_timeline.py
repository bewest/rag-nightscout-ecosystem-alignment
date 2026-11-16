"""Opt-in two-target event tap for one explicit local memory discriminator.

No actor, query, listener or timer is launched here. Existing preparation owns
files; the image still supplies product source and admission. This is a declared
preload/argv/mount instrument delta, not an unchanged-instrument benchmark.
"""
import hashlib
import json
import re
import os
import stat
import shutil
import time
from pathlib import Path
from contract import require
import diagnostic_resources as resources

NAME='two-target-intake-timeline-v1'
RAW_NAME='two-target-intake-timeline-raw-v2'
DEST='/run/ns-intake-timeline'
COMMAND=['node','deploy/multitenant/entrypoint.js','evaluator']
SELECTED=['node','--require',DEST+'/preload.cjs',*COMMAND[1:]]

def sha(file):
    digest=hashlib.sha256()
    with Path(file).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):digest.update(chunk)
    return digest.hexdigest()

def install(config,d,m,selected,sender_binary=None,sender_receipt=None):
    sender_selected=sender_binary is not None or sender_receipt is not None
    require(not sender_selected or (bool(sender_binary) and bool(sender_receipt) and selected==RAW_NAME),'M7_CLINICAL_SENDER_SELECTION')
    if selected=='off':return
    require(selected in (NAME,RAW_NAME) and m.get('runPurpose')=='discovery' and config.get(resources.PROFILE_KEY)==resources.EVALUATOR250_MEMORY512_NAME,'M7_CLINICAL_TIMELINE_SCOPE')
    e=config['services']['evaluator']
    require(e.get('command')==COMMAND and not e.get('entrypoint') and not e.get('environment',{}).get('NODE_OPTIONS'),'M7_CLINICAL_TIMELINE_COMMAND')
    directory=d/'state/clinical-timeline';directory.mkdir(mode=0o700)
    source=Path(__file__).with_name('clinical-intake-timeline.cjs');target=directory/'preload.cjs';target.write_bytes(source.read_bytes());target.chmod(0o600)
    require(not any(v.get('target')==DEST for v in e.get('volumes',[])),'M7_CLINICAL_TIMELINE_MOUNT')
    e['command']=list(SELECTED);e.setdefault('environment',{})['NS_M7_CLINICAL_TIMELINE']='1'
    e.setdefault('volumes',[]).append({'type':'bind','source':str(directory),'target':DEST,'read_only':True})
    if selected==RAW_NAME:e['environment']['NS_M7_CLINICAL_RAW_TIMELINE']='1'
    m['clinicalTimeline']={'selection':selected,'preloadSha256':sha(target),'maxRows':4096,'maxBytes':2097152,'output':'state/ipc/clinical-intake-timeline.jsonl','targets':'UNPUBLISHED','instrumentDelta':'one readonly owned-state preload mount, --require argv, bounded target event observations; product files unchanged','timingScope':'not a pure configuration-only performance comparison'}
    if sender_selected:install_sender(config,d,m,sender_binary,sender_receipt)
    if selected==RAW_NAME:m['clinicalTimeline']['raw']={'maxRows':32768,'maxBytes':8388608,'maxPending':128,'output':'state/ipc/clinical-intake-raw.jsonl','scope':'all private POST metadata, selected target joined after parse; not kernel arrival'}

def verify(config,d,m,teardown=False):
    if not teardown:verify_sender(config,d,m)
    record=m.get('clinicalTimeline')
    if not record:
        e=config.get('services',{}).get('evaluator',{})
        require(e.get('environment',{}).get('NS_M7_CLINICAL_TIMELINE') is None and e.get('environment',{}).get('NS_M7_CLINICAL_RAW_TIMELINE') is None and DEST+'/preload.cjs' not in e.get('command',[]) and not any(v.get('target')==DEST for v in e.get('volumes',[])),'M7_CLINICAL_TIMELINE_RECORD_REQUIRED')
        return
    require(record.get('selection') in (NAME,RAW_NAME) and config.get(resources.PROFILE_KEY)==resources.EVALUATOR250_MEMORY512_NAME,'M7_CLINICAL_TIMELINE_SCOPE')
    require(record.get('raw')=={'maxRows':32768,'maxBytes':8388608,'maxPending':128,'output':'state/ipc/clinical-intake-raw.jsonl','scope':'all private POST metadata, selected target joined after parse; not kernel arrival'} if record.get('selection')==RAW_NAME else 'raw' not in record,'M7_CLINICAL_RAW_RECORD')
    require(config['services']['evaluator'].get('environment',{}).get('NS_M7_CLINICAL_RAW_TIMELINE')==('1' if record.get('selection')==RAW_NAME else None),'M7_CLINICAL_RAW_SELECTION')
    e=config['services']['evaluator'];directory=d/'state/clinical-timeline'
    require(e.get('command')==SELECTED and e.get('environment',{}).get('NS_M7_CLINICAL_TIMELINE')=='1','M7_CLINICAL_TIMELINE_COMMAND')
    require([v for v in e.get('volumes',[]) if v.get('target')==DEST]==[{'type':'bind','source':str(directory),'target':DEST,'read_only':True}],'M7_CLINICAL_TIMELINE_MOUNT')
    require(sha(directory/'preload.cjs')==record.get('preloadSha256')==sha(Path(__file__).with_name('clinical-intake-timeline.cjs')),'M7_CLINICAL_TIMELINE_BYTES')
    if record.get('targets')!='UNPUBLISHED':require(sha(directory/'targets.json')==record.get('targetsSha256'),'M7_CLINICAL_TIMELINE_TARGETS')

def publish(d,m,roster):
    if not m.get('clinicalTimeline'):return
    require(len(roster)>=2 and len({r['id'] for r in roster})==len(roster),'M7_CLINICAL_TIMELINE_ROSTER')
    ids=[roster[0]['id'],roster[-1]['id']]
    target=d/'state/clinical-timeline/targets.json'
    require(not target.exists(),'M7_CLINICAL_TIMELINE_ALREADY_PUBLISHED')
    target.write_text(json.dumps({'ids':ids})+'\n');target.chmod(0o600)
    if m.get('clinicalSender'):publish_sender(d,m,ids)
    m['clinicalTimeline'].update(targets={'hotA':ids[0],'comparisonB':ids[1],'quietScope':'quiet only if independently unchanged writer clock; never assumed'},targetsSha256=sha(target))

MAX_SAFE_INTEGER=9007199254740991
STATUS_FIELDS={'rows','bytes','pending','written','dropped','failed','closed','qualification'}
RAW_BASE={'instance','sequence','phase','at','monoNs','pid','request','headerLsn','idempotency'}
RAW_EXTRAS={
    'raw-entry':{'connection','peerPort','localPort'},
    'raw-request-aborted':set(),
    'raw-request-close':{'complete','aborted'},
    'raw-response-finish':{'status','finished'},
    'raw-response-close':{'status','finished'},
    'raw-parsed-target':set(),
    'raw-inspector-refusal':set(),
}

def integer(value,minimum,maximum):
    return type(value) is int and minimum<=value<=maximum

def capture_complete(status,raw=False):
    """Require the producer's complete schema; absent and falsey are distinct."""
    fields=STATUS_FIELDS|({'instance'} if raw else set())
    if type(status) is not dict or set(status)!=fields:return False
    max_rows,max_bytes=(32768,8388608) if raw else (4096,2097152)
    limits={'rows':max_rows,'bytes':max_bytes,'pending':128 if raw else max_rows,'written':max_rows,'dropped':MAX_SAFE_INTEGER}
    if any(not integer(status[key],0,limit) for key,limit in limits.items()):return False
    if type(status['closed']) is not bool or type(status['qualification']) is not str or status['qualification']!='COMPLETE':return False
    if status['pending']!=0 or status['dropped']!=0 or status['failed'] is not None or status['written']!=status['rows']:return False
    if raw and (type(status['instance']) is not str or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',status['instance'])):return False
    return True

def selected_complete(file,status):
    """Check selected capture counts, including its optional explicit seal."""
    try:
        if not capture_complete(status):return False
        data=file.read_bytes()
        if len(data)>2097152:return False
        lines=data.splitlines(keepends=True);rows=[json.loads(line) for line in lines]
        if rows and type(rows[-1]) is dict and rows[-1].get('phase')=='trace-seal':
            seal=rows.pop();last=lines.pop()
            if set(seal)!={'phase','at','pid','rows','bytes','pending','written','dropped','failed'}:return False
            if not integer(seal['at'],1,MAX_SAFE_INTEGER) or not integer(seal['pid'],1,2147483647):return False
            if any(type(seal[key]) is not type(status[key]) or seal[key]!=status[key] for key in ('rows','bytes','pending','written','dropped','failed')):return False
            if not status['closed']:return False
        if len(rows)!=status['rows'] or sum(map(len,lines))!=status['bytes']:return False
        return all(type(row) is dict and integer(row.get('sequence'),1,4096) and row['sequence']==index for index,row in enumerate(rows,1))
    except (OSError,ValueError,TypeError):return False

def raw_complete(file,status):
    """Finite metadata integrity; incomplete responses can be valid observations."""
    try:
        if not capture_complete(status,raw=True):return False
        data=file.read_bytes()
        if len(data)>8388608 or len(data)!=status['bytes']:return False
        rows=[json.loads(line) for line in data.splitlines()]
        if len(rows)!=status['rows']:return False
        entries={};terminal=set();pid=None
        for sequence,row in enumerate(rows,1):
            if type(row) is not dict or row.get('phase') not in RAW_EXTRAS:return False
            phase=row['phase']
            if set(row)!=RAW_BASE|RAW_EXTRAS[phase] or row['instance']!=status['instance']:return False
            if not integer(row['sequence'],1,32768) or row['sequence']!=sequence:return False
            if not integer(row['request'],1,32768) or not integer(row['pid'],1,2147483647) or not integer(row['at'],1,MAX_SAFE_INTEGER):return False
            if type(row['monoNs']) is not str or not re.fullmatch(r'[0-9]{1,24}',row['monoNs']):return False
            if pid is None:pid=row['pid']
            if row['pid']!=pid:return False
            for value in (row['headerLsn'],row['idempotency']):
                if type(value) is not str or (value not in ('ABSENT','INVALID') and not re.fullmatch(r'[0-9A-F]{1,8}/[0-9A-F]{1,8}',value)):return False
            key=row['request']
            if phase=='raw-entry':
                if key in entries:return False
                if row['connection'] is not None and not integer(row['connection'],1,32768):return False
                if any(row[field] is not None and not integer(row[field],1,65535) for field in ('peerPort','localPort')):return False
                entries[key]={'headers':(row['headerLsn'],row['idempotency']),'phases':set()}
            elif key not in entries:return False
            state=entries[key]
            if (row['headerLsn'],row['idempotency'])!=state['headers'] or phase in state['phases']:return False
            state['phases'].add(phase)
            if phase=='raw-request-close' and any(type(row[field]) is not bool for field in ('complete','aborted')):return False
            if phase in ('raw-response-finish','raw-response-close'):
                if not integer(row['status'],100,999) or type(row['finished']) is not bool:return False
                if phase=='raw-response-finish' and not row['finished']:return False
            if phase in ('raw-request-aborted','raw-response-finish','raw-response-close'):terminal.add(key)
        return set(entries)==terminal
    except (OSError,ValueError,TypeError):return False

def retain(d,m):
    """After owned services stop, preserve bounded trace before private-state wipe.

    Missing/failed telemetry never prevents resource cleanup or becomes green.
    """
    if not m.get('clinicalTimeline'):return
    out=d/'clinical-timeline';out.mkdir(mode=0o700,exist_ok=True)
    manifest={'status':'UNMEASURED','files':{},'refusals':[]}
    files=[('clinical-intake-timeline.jsonl',2097152),('clinical-intake-timeline-status.json',4096)]
    sender_present=bool(m.get('clinicalSender')) or (d/'state/clinical-sender-output').is_dir()
    if sender_present:retain_sender(d,m,out,manifest)
    if m['clinicalTimeline'].get('selection')==RAW_NAME:files.extend([('clinical-intake-raw.jsonl',8388608),('clinical-intake-raw-status.json',4096)])
    for name,bound in files:
        try:
            source=d/'state/ipc'/name
            require(source.is_file() and not source.is_symlink() and source.stat().st_size<=bound,'M7_CLINICAL_TIMELINE_MISSING_OR_BOUND')
            destination=out/name
            with destination.open('xb') as stream:stream.write(source.read_bytes())
            destination.chmod(0o600);manifest['files'][name]={'sha256':sha(destination),'bytes':destination.stat().st_size}
        except Exception as error:manifest['refusals'].append({'file':name,'type':type(error).__name__,'code':'M7_CLINICAL_TIMELINE_RETAIN_REFUSED'})
    if not manifest['refusals']:
        try:
            value=json.loads((out/'clinical-intake-timeline-status.json').read_text())
            raw_ok=True
            if m['clinicalTimeline'].get('selection')==RAW_NAME:
                raw=json.loads((out/'clinical-intake-raw-status.json').read_text());raw_ok=raw_complete(out/'clinical-intake-raw.jsonl',raw)
            selected_ok=selected_complete(out/'clinical-intake-timeline.jsonl',value)
            if sender_present:manifest['captureParts']={'selected':'COMPLETE' if selected_ok else 'UNMEASURED','raw':'COMPLETE' if raw_ok else 'UNMEASURED','sender':'UNMEASURED_REQUIRES_STRUCTURAL_QUALIFICATION'}
            elif raw_ok and selected_ok:manifest['status']='COMPLETE'
        except Exception:pass
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def probe_environment(m):
    if not m.get('clinicalTimeline'):return {}
    targets=m['clinicalTimeline'].get('targets');require(isinstance(targets,dict),'M7_CLINICAL_TIMELINE_UNPUBLISHED')
    return {'M7_CLINICAL_TIMELINE_IDS':json.dumps([targets['hotA'],targets['comparisonB']])}

# One explicit reviewed local sender experiment; no arbitrary command/plugin.
SENDER_BINARY='/usr/local/bin/pgstream'
SENDER_TARGET='/run/ns-intake-timeline'
SENDER_OUTPUT='/run/ns-ipc'
SENDER_COMMAND=[SENDER_BINARY,'run','-c','/run/ns-stream/pgstream.yaml','--log-level','info']
SENDER_ENV='NS_M7_CLINICAL_SENDER_TIMELINE'

def sender_metadata():
    return json.loads(Path(__file__).with_name('clinical-sender-source.json').read_text())

def owned(path,directory=False,private=False,input_file=False):
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path and not path.is_symlink(),'M7_CLINICAL_SENDER_PATH')
    try:info=path.stat()
    except OSError as error:raise RuntimeError('M7_CLINICAL_SENDER_PATH_UNMEASURED') from error
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) and info.st_uid==os.geteuid(),'M7_CLINICAL_SENDER_OWNER')
    require((input_file or not info.st_mode&0o022) and (not private or stat.S_IMODE(info.st_mode)==0o700),'M7_CLINICAL_SENDER_PERMISSIONS')
    return info

def sender_mounts(d):
    return [
        {'type':'bind','source':str(d/'state/clinical-sender-binary/pgstream'),'target':SENDER_BINARY,'read_only':True},
        {'type':'bind','source':str(d/'state/clinical-sender-targets'),'target':SENDER_TARGET,'read_only':True},
        {'type':'bind','source':str(d/'state/clinical-sender-output'),'target':SENDER_OUTPUT},
    ]

def sender_role(config,m,selected=False):
    require(m.get('runPurpose')=='discovery' and m.get('profile')=='pgstream-sample' and m.get('pgstreamTopology')=='external-service-v1' and config.get(resources.PROFILE_KEY)==resources.EVALUATOR250_MEMORY512_NAME,'M7_CLINICAL_SENDER_SCOPE')
    service=config.get('services',{}).get('pgstream')
    require(service is not None and service.get('command')==SENDER_COMMAND and not service.get('entrypoint'),'M7_CLINICAL_SENDER_ROLE')
    volumes=service.get('volumes',[]);wire=[v for v in volumes if v.get('target')=='/run/ns-stream']
    require(len(wire)==1 and wire[0].get('read_only') is True and Path(wire[0]['source']).name=='pgstream','M7_CLINICAL_SENDER_WIRE')
    require(len(volumes)==(4 if selected else 1),'M7_CLINICAL_SENDER_EXTRA_MOUNT')
    for role,spec in config['services'].items():
        if role!='pgstream':
            require(SENDER_ENV not in spec.get('environment',{}) and not any(v.get('target')==SENDER_BINARY or Path(v.get('source','')).name in ('clinical-sender-targets','clinical-sender-output') or Path(v.get('source','')).parent.name=='clinical-sender-binary' for v in spec.get('volumes',[])),'M7_CLINICAL_SENDER_WRONG_ROLE')
    return service,wire

def install_sender(config,d,m,binary,receipt):
    d=Path(d).resolve();service,wire=sender_role(config,m)
    require(wire[0]['source']==str(d/'state/pgstream'),'M7_CLINICAL_SENDER_WIRE')
    require(m['clinicalTimeline']['selection']==RAW_NAME and SENDER_ENV not in service.get('environment',{}),'M7_CLINICAL_SENDER_SELECTION')
    metadata=sender_metadata();build=metadata['reviewedBuild'];binary=Path(binary);receipt=Path(receipt)
    owned(binary,input_file=True);owned(receipt,input_file=True)
    require(receipt.stat().st_size<=4194304 and sha(receipt)==build['receiptSha256'],'M7_CLINICAL_SENDER_RECEIPT')
    proof=json.loads(receipt.read_text())
    require(proof.get('kind')=='clinical-sender-cli-build-v1' and proof.get('status')=='BUILDS_PASS_SOURCE_ONLY' and proof.get('sourceArchiveSha256')==metadata['archiveSha256'] and proof.get('patchSha256')==metadata['patchSha256'] and proof.get('toolchainSha256')==build['toolchainSha256'] and proof.get('buildEnvironment',{}).get('CGO_ENABLED')=='0' and proof.get('binaries',{}).get('instrumented',{}).get('sha256')==build['instrumentedSha256'],'M7_CLINICAL_SENDER_RECEIPT')
    require(binary.stat().st_size==build['instrumentedBytes'] and sha(binary)==build['instrumentedSha256'],'M7_CLINICAL_SENDER_BINARY')
    owned(d,directory=True);owned(d/'state',directory=True)
    paths=[d/'state'/name for name in ('clinical-sender-binary','clinical-sender-targets','clinical-sender-output')]
    require(all(not path.exists() and not path.is_symlink() for path in paths),'M7_CLINICAL_SENDER_PREEXISTING_OUTPUT')
    for path in paths:path.mkdir(mode=0o700)
    staged=paths[0]/'pgstream'
    with binary.open('rb') as source,staged.open('xb') as target:
        shutil.copyfileobj(source,target,1024*1024);target.flush();os.fsync(target.fileno());os.fchmod(target.fileno(),0o555)
    require(sha(staged)==build['instrumentedSha256'],'M7_CLINICAL_SENDER_BINARY')
    staged_receipt=paths[0]/'build-receipt.json'
    with staged_receipt.open('xb') as stream:stream.write(receipt.read_bytes());stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),0o444)
    require(sha(staged_receipt)==build['receiptSha256'],'M7_CLINICAL_SENDER_RECEIPT')
    service['volumes']=wire+sender_mounts(d);service.setdefault('environment',{})[SENDER_ENV]='1'
    m['clinicalSender']={'selection':'reviewed-external-sender-v1','binarySha256':build['instrumentedSha256'],'binaryBytes':build['instrumentedBytes'],'receiptSha256':build['receiptSha256'],'patchSha256':metadata['patchSha256'],'archiveSha256':metadata['archiveSha256'],'ownerUid':os.geteuid(),'targets':'UNPUBLISHED','maxRows':4096,'maxBytes':2097152,'CLIversion':'development','imageBinarySha256':build['shippingImageBinarySha256'],'nativeQualification':'UNMEASURED','scope':'explicit runtime single-file diagnostic override; image/initializer f9 qualification unchanged; no product acceptance'}

def verify_sender(config,d,m):
    record=m.get('clinicalSender');d=Path(d).resolve()
    if not record:
        for spec in config.get('services',{}).values():
            require(SENDER_ENV not in spec.get('environment',{}) and not any(v.get('target')==SENDER_BINARY for v in spec.get('volumes',[])),'M7_CLINICAL_SENDER_RECORD_REQUIRED')
        return
    require(m.get('clinicalTimeline',{}).get('selection')==RAW_NAME,'M7_CLINICAL_SENDER_SELECTION')
    service,wire=sender_role(config,m,selected=True);metadata=sender_metadata();build=metadata['reviewedBuild']
    fields={'selection','binarySha256','binaryBytes','receiptSha256','patchSha256','archiveSha256','ownerUid','targets','maxRows','maxBytes','CLIversion','imageBinarySha256','nativeQualification','scope'}
    if record.get('targets')!='UNPUBLISHED':fields|={'targetsSha256','layoutSha256','receiverConfigSha256'}
    require(type(record) is dict and set(record)==fields,'M7_CLINICAL_SENDER_RECORD')
    require(record.get('selection')=='reviewed-external-sender-v1' and record.get('binarySha256')==build['instrumentedSha256'] and record.get('receiptSha256')==build['receiptSha256'] and record.get('patchSha256')==metadata['patchSha256'] and record.get('archiveSha256')==metadata['archiveSha256'],'M7_CLINICAL_SENDER_RECORD')
    require(service.get('environment',{}).get(SENDER_ENV)=='1' and service['volumes']==wire+sender_mounts(d),'M7_CLINICAL_SENDER_MOUNTS')
    require(type(record.get('ownerUid')) is int and record['ownerUid']==os.geteuid(),'M7_CLINICAL_SENDER_OWNER')
    require(record.get('binaryBytes')==build['instrumentedBytes'] and record.get('maxRows')==4096 and record.get('maxBytes')==2097152 and record.get('CLIversion')==build['CLIversion'] and record.get('imageBinarySha256')==build['shippingImageBinarySha256'] and record.get('nativeQualification')=='UNMEASURED','M7_CLINICAL_SENDER_RECORD')
    require(wire[0]['source']==str(d/'state/pgstream'),'M7_CLINICAL_SENDER_WIRE')
    for name in ('clinical-sender-binary','clinical-sender-targets','clinical-sender-output'):owned(d/'state'/name,directory=True,private=True)
    staged=d/'state/clinical-sender-binary/pgstream';info=owned(staged)
    require(stat.S_IMODE(info.st_mode)==0o555 and info.st_size==build['instrumentedBytes'] and sha(staged)==build['instrumentedSha256'],'M7_CLINICAL_SENDER_BINARY')
    require({p.name for p in (d/'state/clinical-sender-binary').iterdir()}=={'pgstream','build-receipt.json'},'M7_CLINICAL_SENDER_EXTRA_FILE')
    staged_receipt=d/'state/clinical-sender-binary/build-receipt.json';owned(staged_receipt)
    require(stat.S_IMODE(staged_receipt.stat().st_mode)==0o444 and sha(staged_receipt)==build['receiptSha256'],'M7_CLINICAL_SENDER_RECEIPT')
    target_dir=d/'state/clinical-sender-targets'
    require({p.name for p in target_dir.iterdir()}==(set() if record['targets']=='UNPUBLISHED' else {'targets.json'}),'M7_CLINICAL_SENDER_EXTRA_FILE')
    output=d/'state/clinical-sender-output'
    require(all(path.name in ('clinical-sender-timeline.jsonl','clinical-sender-status.json') and path.is_file() and not path.is_symlink() for path in output.iterdir()),'M7_CLINICAL_SENDER_UNSAFE_OUTPUT')
    if record['targets']!='UNPUBLISHED':
        target=d/'state/clinical-sender-targets/targets.json';owned(target)
        require(sha(target)==record.get('targetsSha256'),'M7_CLINICAL_SENDER_TARGETS')
        value=json.loads(target.read_text());require(set(value)=={'ids','clockSchema'} and value==record['targets'] and value['clockSchema']=='nsdemo_clock' and value['ids']==[m['clinicalTimeline']['targets']['hotA'],m['clinicalTimeline']['targets']['comparisonB']],'M7_CLINICAL_SENDER_SCHEMA')
        require(sha(d/'state/bootstrap/layout.json')==record.get('layoutSha256') and sha(d/'state/evaluator/config.json')==record.get('receiverConfigSha256'),'M7_CLINICAL_SENDER_SCHEMA')

def publish_sender(d,m,ids):
    record=m['clinicalSender'];d=Path(d).resolve()
    require(record['targets']=='UNPUBLISHED' and len(ids)==2 and len(set(ids))==2 and all(isinstance(value,str) and re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',value) for value in ids),'M7_CLINICAL_SENDER_TARGETS')
    require(not any((d/'state/clinical-sender-targets').iterdir()),'M7_CLINICAL_SENDER_PREEXISTING_FILE')
    layout=d/'state/bootstrap/layout.json';receiver=d/'state/evaluator/config.json'
    clock=json.loads(layout.read_text()).get('namespaces',{}).get('clock');actual=json.loads(receiver.read_text()).get('postgres',{}).get('namespaces',{}).get('clock')
    # The existing pgstream-sample oracle requires nsdemo_<kind> at bootstrap.
    require(clock==actual=='nsdemo_clock','M7_CLINICAL_SENDER_SCHEMA')
    value={'ids':ids,'clockSchema':clock};target=d/'state/clinical-sender-targets/targets.json'
    with target.open('x') as stream:json.dump(value,stream);stream.write('\n');stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),0o600)
    record.update(targets=value,targetsSha256=sha(target),layoutSha256=sha(layout),receiverConfigSha256=sha(receiver))

def before_sender_effect(d,args,config,m):
    values=[str(x) for x in args];i=0
    while i<len(values) and values[i]=='--profile':i+=2
    action=values[i] if i<len(values) else None;roles={x for x in values[i+1:] if x in config['services']}
    if action not in ('up','create','start','restart','run'):return
    verify_sender(config,d,m)
    if not m.get('clinicalSender'):return
    if action in ('up','create','start','restart','run') and (not roles or bool(roles&{'pgstream','evaluator'})):
        require(m['clinicalSender']['targets']!='UNPUBLISHED','M7_CLINICAL_SENDER_TARGETS')
    if action in ('up','create','start','restart','run') and (not roles or 'pgstream' in roles):
        require(action!='run','M7_CLINICAL_SENDER_START_ACTION')
        require(m['clinicalSender']['targets']!='UNPUBLISHED','M7_CLINICAL_SENDER_TARGETS')
        require(not any((Path(d)/'state/clinical-sender-output').iterdir()),'M7_CLINICAL_SENDER_PREEXISTING_OUTPUT')

def process_evidence(pid):
    root=Path('/proc')/str(pid)
    def birth():
        value=(root/'stat').read_text();fields=value[value.rfind(')')+2:].split();return fields[19]
    before=birth();link=os.readlink(root/'exe')
    uids=[int(value) for value in next(line for line in (root/'status').read_text().splitlines() if line.startswith('Uid:')).split()[1:]]
    require(len(uids)==4 and len(set(uids))==1,'M7_CLINICAL_SENDER_RUNTIME_UID');uid=uids[0]
    digest=sha(root/'exe');after=birth()
    require(before==after,'M7_CLINICAL_SENDER_PROCESS_REPLACED')
    return {'pid':pid,'birth':before,'uid':uid,'executable':link,'executableSha256':digest}

def sender_runtime(d,m,rows,snapshot):
    if not m.get('clinicalSender'):return None
    selected=[row for row in rows if row.get('Config',{}).get('Labels',{}).get('com.docker.compose.service')=='pgstream']
    require(len(selected)==1,'M7_CLINICAL_SENDER_RUNTIME_ROLE');row=selected[0]
    require(row.get('Image')==m['imageId'] and row.get('Config',{}).get('Cmd')==SENDER_COMMAND and row.get('State',{}).get('Running') is True,'M7_CLINICAL_SENDER_RUNTIME_ROLE')
    require(snapshot.get('id')==row.get('Id'),'M7_CLINICAL_SENDER_RUNTIME_CONTAINER')
    require(len(row.get('Mounts',[]))==4 and SENDER_ENV+'=1' in row.get('Config',{}).get('Env',[]),'M7_CLINICAL_SENDER_RUNTIME_MOUNTS')
    candidates=[(int(pid),value) for pid,value in snapshot.get('hostProcesses',{}).items() if value.get('component')=='pgstream' and not value.get('unavailable')]
    require(len(candidates)==1,'M7_CLINICAL_SENDER_RUNTIME_PRIMARY');pid,known=candidates[0]
    require(pid!=row['State']['Pid'],'M7_CLINICAL_SENDER_PID1_SUBSTITUTE')
    evidence=process_evidence(pid);record=m['clinicalSender']
    require(evidence['birth']==str(known.get('startTicks')) and evidence['uid']==record['ownerUid'] and evidence['executable']==SENDER_BINARY and evidence['executableSha256']==record['binarySha256'],'M7_CLINICAL_SENDER_RUNTIME_EXECUTABLE')
    for mount in sender_mounts(Path(d).resolve()):
        actual=[entry for entry in row.get('Mounts',[]) if entry.get('Destination')==mount['target']]
        require(len(actual)==1 and actual[0].get('Type')=='bind' and actual[0].get('Source')==mount['source'] and actual[0].get('RW') is (not mount.get('read_only',False)),'M7_CLINICAL_SENDER_RUNTIME_MOUNTS')
    return {'observedAt':time.time(),'containerId':row['Id'],'imageId':row['Image'],'imageBinarySha256':record['imageBinarySha256'],'actualPrimary':evidence,'scope':'actual primary /proc exe bytes and birth; image identity alone never qualifies override; point only, not full interval'}

def retain_sender(d,m,out,manifest):
    # Resource cleanup still proceeds if diagnostics refuse or files are absent.
    for name,bound in [('clinical-sender-timeline.jsonl',2097152),('clinical-sender-status.json',4096)]:
        try:
            source=Path(d)/'state/clinical-sender-output'/name;owned(source)
            require(source.stat().st_size<=bound,'M7_CLINICAL_SENDER_RETAIN_BOUND')
            target=out/name
            with target.open('xb') as stream:stream.write(source.read_bytes())
            target.chmod(0o600);manifest['files'][name]={'sha256':sha(target),'bytes':target.stat().st_size}
        except Exception as error:manifest['refusals'].append({'file':name,'type':type(error).__name__,'code':'M7_CLINICAL_SENDER_RETAIN_REFUSED'})
    manifest['senderQualification']='UNMEASURED: captured sender rows require explicit structural/target/connection and lifetime qualification; never clinical acceptance'

def sender_cleanup_observation(config,d,m):
    """Diagnostic refusal is evidence, never a prerequisite for owned teardown."""
    if not m.get('clinicalSender') and not any(SENDER_ENV in spec.get('environment',{}) or any(v.get('target')==SENDER_BINARY for v in spec.get('volumes',[])) for spec in config.get('services',{}).values()):return None
    try:
        verify_sender(config,d,m);return {'status':'CHECKED_POINT_ONLY','scope':'sender files before owned teardown; not clinical acceptance'}
    except Exception as error:return {'status':'UNMEASURED','type':type(error).__name__,'code':str(error) if re.fullmatch(r'M7_[A-Z_]+',str(error)) else 'M7_CLINICAL_SENDER_CLEANUP_OBSERVATION_REFUSED','scope':'continue exact-owned teardown and retain available partial diagnostics'}
