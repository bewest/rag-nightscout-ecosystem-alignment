"""Opt-in two-target event tap for one explicit local memory discriminator.

No actor, query, listener or timer is launched here. Existing preparation owns
files; the image still supplies product source and admission. This is a declared
preload/argv/mount instrument delta, not an unchanged-instrument benchmark.
"""
import hashlib
import json
import re
from pathlib import Path
from contract import require
import diagnostic_resources as resources

NAME='two-target-intake-timeline-v1'
RAW_NAME='two-target-intake-timeline-raw-v2'
DEST='/run/ns-intake-timeline'
COMMAND=['node','deploy/multitenant/entrypoint.js','evaluator']
SELECTED=['node','--require',DEST+'/preload.cjs',*COMMAND[1:]]

def sha(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()

def install(config,d,m,selected):
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
    if selected==RAW_NAME:m['clinicalTimeline']['raw']={'maxRows':32768,'maxBytes':8388608,'maxPending':128,'output':'state/ipc/clinical-intake-raw.jsonl','scope':'all private POST metadata, selected target joined after parse; not kernel arrival'}

def verify(config,d,m):
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
    m['clinicalTimeline'].update(targets={'hotA':ids[0],'comparisonB':ids[1],'quietScope':'quiet only if independently unchanged writer clock; never assumed'},targetsSha256=sha(target))

def raw_complete(file,status):
    """Finite metadata integrity, not sender delivery or clinical completion."""
    data=file.read_bytes()
    if len(data)>8388608 or status.get('qualification')!='COMPLETE' or status.get('pending') or status.get('dropped') or status.get('failed'):return False
    rows=[json.loads(line) for line in data.splitlines()]
    if len(rows)>32768 or status.get('rows')!=len(rows) or status.get('written')!=len(rows) or status.get('bytes')!=len(data):return False
    allowed={'instance','sequence','phase','at','monoNs','pid','request','headerLsn','idempotency','connection','peerPort','localPort','complete','aborted','status','finished'}
    phases={'raw-entry','raw-request-aborted','raw-request-close','raw-response-finish','raw-response-close','raw-parsed-target','raw-inspector-refusal'}
    entries=set();terminal=set();instance=status.get('instance');pid=None
    if not isinstance(instance,str) or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',instance):return False
    for sequence,row in enumerate(rows,1):
        if row.get('instance')!=instance:return False
        if pid is None:pid=row.get('pid')
        if row.get('pid')!=pid:return False
        if set(row)-allowed or row.get('sequence')!=sequence or row.get('phase') not in phases:return False
        if any(type(row.get(key)) is not int or row[key]<1 for key in ('request','pid','at')) or not re.fullmatch(r'[0-9]{1,24}',row.get('monoNs','')):return False
        if any(value not in ('ABSENT','INVALID') and not re.fullmatch(r'[0-9A-F]{1,8}/[0-9A-F]{1,8}',value) for value in (row.get('headerLsn',''),row.get('idempotency',''))):return False
        key=row['request']
        if row['phase']=='raw-entry':
            if key in entries:return False
            entries.add(key)
        elif key not in entries:return False
        if row['phase'] in ('raw-request-aborted','raw-response-finish','raw-response-close'):terminal.add(key)
    return entries==terminal

def retain(d,m):
    """After owned services stop, preserve bounded trace before private-state wipe.

    Missing/failed telemetry never prevents resource cleanup or becomes green.
    """
    if not m.get('clinicalTimeline'):return
    out=d/'clinical-timeline';out.mkdir(mode=0o700,exist_ok=True)
    manifest={'status':'UNMEASURED','files':{},'refusals':[]}
    files=[('clinical-intake-timeline.jsonl',2097152),('clinical-intake-timeline-status.json',4096)]
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
            if raw_ok and value.get('qualification')=='COMPLETE' and value.get('written')==value.get('rows') and not value.get('pending') and not value.get('dropped') and not value.get('failed'):manifest['status']='COMPLETE'
        except Exception:pass
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def probe_environment(m):
    if not m.get('clinicalTimeline'):return {}
    targets=m['clinicalTimeline'].get('targets');require(isinstance(targets,dict),'M7_CLINICAL_TIMELINE_UNPUBLISHED')
    return {'M7_CLINICAL_TIMELINE_IDS':json.dumps([targets['hotA'],targets['comparisonB']])}
