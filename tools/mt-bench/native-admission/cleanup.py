"""Independent exact-owned emergency stop; never retires connection credits."""
import argparse,json,time,os
from pathlib import Path
import commissioning as C

def cleanup(spec,output):
    C.need(spec['kind']=='m7-commission-exact-owned-cleanup-v1','CLEANUP_KIND');plan=spec['plan']
    C.need(plan['source']=={'coreCommit':C.CORE,'deployCommit':C.DEPLOY}and plan['imageId']==C.IMAGE and plan['project']=='ns-admission-'+plan['nonce'],'CLEANUP_SOURCE_PROJECT')
    C.need(Path(plan['base']).is_absolute(),'CLEANUP_BASE')
    if not spec['allocationAttempted']:return {'cleanup':'NO_ALLOCATION_NO_EFFECTS','creditRetirement':'NOT_GRANTED','nativeAcceptance':'UNMEASURED'}
    h=C.Host(plan,output);h.environment={k:os.environ[k]for k in ['PATH','HOME','USER','LANG']if k in os.environ};h.cleanup=True;h.skip_controller_cleanup=True;h.deadline=time.monotonic()+180;h.allocation_attempted=spec['allocationAttempted'];h.images=spec['images'];h.owned={cid:tuple(value)for cid,value in spec['known'].items()}
    C.need(h.images.get('postgres')==C.PG_IMAGE,'CLEANUP_PG_IMAGE');C.need(h.command(['docker','context','show']).strip()=='default','CLEANUP_DOCKER_CONTEXT');h.cleanup_owned()
    return {'cleanup':'STOPPED_CURRENT_CONFIRMED_OWNED','creditRetirement':'NOT_GRANTED','nativeAcceptance':'UNMEASURED'}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('spec',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    try:print(json.dumps(cleanup(C.read(a.spec),a.output)))
    except Exception as error:print(json.dumps({'cleanup':'UNCONFIRMED','error':str(error),'nativeAcceptance':'UNMEASURED'}));raise SystemExit(1)
