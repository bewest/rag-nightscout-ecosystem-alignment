"""Independent exact-owned clinical emergency stop; never retires any credit.

Use only the original private root-cleanup-spec and a NEW private output path.
No start, remove, SQL, retry, image load or worker admission is available here.
"""
import argparse,json,os,re,time
from pathlib import Path
import clinical as D,runtime as R
C=D.C

def cleanup(spec,output):
    D.need(spec['kind']=='m7-clinical-exact-owned-cleanup-v1','CLEANUP_KIND');plan=spec['plan']
    D.need(plan['source']=={'coreCommit':C.CORE,'deployCommit':C.DEPLOY}and plan['imageId']==C.IMAGE,'CLEANUP_SOURCE_IMAGE')
    D.need(re.fullmatch('[a-f0-9]{32}',plan['nonce'])and plan['project']=='ns-admission-'+plan['nonce']and Path(plan['base']).is_absolute(),'CLEANUP_PROJECT_BASE')
    D.need(len(plan['slots'])==11 and len(set(plan['slots']))==11 and set(plan['slots'])==set(plan['startOrder']),'CLEANUP_ROSTER')
    D.need(plan['clinicalFiles']=={p.name:C.sha(p)for p in D.HERE.iterdir()if p.is_file()and p.suffix in('.py','.cjs','.md')},'CLEANUP_INSTRUMENT_CHANGED')
    if not spec['allocationAttempted']:return {'cleanup':'NO_ALLOCATION_NO_EFFECTS','creditRetirement':'NOT_GRANTED','nativeAcceptance':'UNMEASURED'}
    h=R.Host(plan,output);h.environment={k:os.environ[k]for k in ('PATH','HOME','USER','LANG')if k in os.environ};h.cleanup=True;h.skip_controller_cleanup=True;h.deadline=time.monotonic()+180;h.p.update(maximumCommands=256,maximumOutputBytes=33554432);h.allocation_attempted=True;h.images=spec['images'];h.owned={cid:tuple(value)for cid,value in spec['known'].items()}
    D.need(h.images.get('postgres')==C.PG_IMAGE and h.images.get('app',C.IMAGE)==C.IMAGE,'CLEANUP_IMAGE');D.need(h.command(['docker','context','show']).strip()=='default','CLEANUP_DOCKER_CONTEXT');h.cleanup_owned()
    return {'cleanup':'STOPPED_CURRENT_CONFIRMED_OWNED','creditRetirement':'NOT_GRANTED','nativeAcceptance':'UNMEASURED'}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('spec',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    try:print(json.dumps(cleanup(C.read(args.spec),args.output)))
    except Exception as error:print(json.dumps({'cleanup':'UNCONFIRMED','error':str(error),'nativeAcceptance':'UNMEASURED'}));raise SystemExit(1)
