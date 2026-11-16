"""Opt-in two-target event tap for one explicit local memory discriminator.

No actor, query, listener or timer is launched here. Existing preparation owns
files; the image still supplies product source and admission. This is a declared
preload/argv/mount instrument delta, not an unchanged-instrument benchmark.
"""
import hashlib
import json
from pathlib import Path
from contract import require
import diagnostic_resources as resources

NAME='two-target-intake-timeline-v1'
DEST='/run/ns-intake-timeline'
COMMAND=['node','deploy/multitenant/entrypoint.js','evaluator']
SELECTED=['node','--require',DEST+'/preload.cjs',*COMMAND[1:]]

def sha(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()

def install(config,d,m,selected):
    if selected=='off':return
    require(selected==NAME and m.get('runPurpose')=='discovery' and config.get(resources.PROFILE_KEY)==resources.EVALUATOR250_MEMORY512_NAME,'M7_CLINICAL_TIMELINE_SCOPE')
    e=config['services']['evaluator']
    require(e.get('command')==COMMAND and not e.get('entrypoint') and not e.get('environment',{}).get('NODE_OPTIONS'),'M7_CLINICAL_TIMELINE_COMMAND')
    directory=d/'state/clinical-timeline';directory.mkdir(mode=0o700)
    source=Path(__file__).with_name('clinical-intake-timeline.cjs');target=directory/'preload.cjs';target.write_bytes(source.read_bytes());target.chmod(0o600)
    require(not any(v.get('target')==DEST for v in e.get('volumes',[])),'M7_CLINICAL_TIMELINE_MOUNT')
    e['command']=list(SELECTED);e.setdefault('environment',{})['NS_M7_CLINICAL_TIMELINE']='1'
    e.setdefault('volumes',[]).append({'type':'bind','source':str(directory),'target':DEST,'read_only':True})
    m['clinicalTimeline']={'selection':NAME,'preloadSha256':sha(target),'maxRows':4096,'maxBytes':2097152,'output':'state/ipc/clinical-intake-timeline.jsonl','targets':'UNPUBLISHED','instrumentDelta':'one readonly owned-state preload mount, --require argv, bounded target event observations; product files unchanged','timingScope':'not a pure configuration-only performance comparison'}

def verify(config,d,m):
    record=m.get('clinicalTimeline')
    if not record:
        e=config.get('services',{}).get('evaluator',{})
        require(e.get('environment',{}).get('NS_M7_CLINICAL_TIMELINE') is None and DEST+'/preload.cjs' not in e.get('command',[]) and not any(v.get('target')==DEST for v in e.get('volumes',[])),'M7_CLINICAL_TIMELINE_RECORD_REQUIRED')
        return
    require(record.get('selection')==NAME and config.get(resources.PROFILE_KEY)==resources.EVALUATOR250_MEMORY512_NAME,'M7_CLINICAL_TIMELINE_SCOPE')
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

def retain(d,m):
    """After owned services stop, preserve bounded trace before private-state wipe.

    Missing/failed telemetry never prevents resource cleanup or becomes green.
    """
    if not m.get('clinicalTimeline'):return
    out=d/'clinical-timeline';out.mkdir(mode=0o700,exist_ok=True)
    manifest={'status':'UNMEASURED','files':{},'refusals':[]}
    for name,bound in [('clinical-intake-timeline.jsonl',2097152),('clinical-intake-timeline-status.json',4096)]:
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
            if value.get('qualification')=='COMPLETE' and value.get('written')==value.get('rows') and not value.get('pending') and not value.get('dropped') and not value.get('failed'):manifest['status']='COMPLETE'
        except Exception:pass
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def probe_environment(m):
    if not m.get('clinicalTimeline'):return {}
    targets=m['clinicalTimeline'].get('targets');require(isinstance(targets,dict),'M7_CLINICAL_TIMELINE_UNPUBLISHED')
    return {'M7_CLINICAL_TIMELINE_IDS':json.dumps([targets['hotA'],targets['comparisonB']])}
