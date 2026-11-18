#!/usr/bin/env python3
"""Bounded normal-path instrument proof. Synthetic actors; no application claim.

Run in a finite native scope with the explicit cached tools/dependencies below.
No cluster, Docker daemon, source acceptance campaign or installation is used.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from test_adapter import fixture, iso, k
import execute as e
import experiment
from workloads import profile as profiles
from workloads import reduce as reduction


def status():
    s = dict(units='mg/dl', enable=[], thresholds=dict(bgHigh=260, bgTargetTop=180, bgTargetBottom=80, bgLow=55))
    s.update(dict.fromkeys(('timeFormat','dayStart','dayEnd','alarmTimeagoWarnMins','alarmTimeagoUrgentMins','focusHours','heartbeat'), 1))
    s.update(dict.fromkeys(('nightMode','showSeconds','editMode','alarmUrgentHigh','alarmHigh','alarmLow','alarmUrgentLow','alarmTimeagoWarn','alarmTimeagoUrgent','alarmPumpBatteryLow','showClockDelta','showClockLastTime','authenticationPromptOnLoad'), False))
    s.update({key: [] for key in ('alarmUrgentHighMins','alarmHighMins','alarmLowMins','alarmUrgentLowMins','alarmUrgentMins','alarmWarnMins')})
    return dict(status='ok', settings=s, extendedSettings=dict(devicestatus=dict(advanced=False, days=1)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('output', 'k6', 'node', 'dependencies', 'core'):
        parser.add_argument('--'+key, required=True, type=Path)
    parser.add_argument('--driver-shards', type=int, default=0,
                        help='Use the shared configured driver natively; zero retains legacy control')
    parser.add_argument('--driver-observer', choices=('summary-v1','scheduling-v1'), default='scheduling-v1')
    a = parser.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False, mode=0o700)
    c, inv, render, replies = fixture()
    n = 10
    tenants = [{'id': f'00000000-0000-4000-8000-{i:012d}', 'host': f'synthetic-{i}.test', 'token': f'synthetic-{i}'} for i in range(n)]
    core = subprocess.check_output(['git','-C',str(a.core),'rev-parse','HEAD'], text=True).strip()
    c['pins']['pair']['core'] = inv['sourceCommit'] = core
    c.update(tenants=n, tenantsFile=str(out/'tenants.json'), kubectl=str(out/'kubectl'), readonlyGuard=str(out/'ro'))
    c['deadlines'] = dict(workUntil=iso(time.time()+1200), cleanupUntil=iso(time.time()+1800))
    c['observer']['hostId'] = c['driver']['hostId'] = 'synthetic-loopback-native'
    c['driver'].update(node=str(a.node.resolve()),nodeSha256=k.digest(a.node),k6=str(a.k6.resolve()),k6Sha256=k.digest(a.k6),
                       dependencies=str(a.dependencies.resolve()),coreRepository=str(a.core.resolve()),
                       packageSha256=k.digest(a.dependencies/'package.json'),lockSha256=k.digest(a.dependencies/'package-lock.json'),
                       nodeModules=k.dependency_reuse.tree(a.dependencies/'node_modules'))
    # Required larger-roster bootstrap declaration; it is synthetic and never applied.
    job = copy.deepcopy(render[1]); job.update(kind='Job');job['metadata']['name']='provision'
    job['spec'].pop('replicas');job['spec']['template']['spec']['containers']=[]
    boot = copy.deepcopy(render[1]['spec']['template']['spec']['containers'][0]);boot.update(name='bootstrap',env=[dict(name='NS_DEMO_TENANTS',value=str(n))])
    job['spec']['template']['spec']['initContainers']=[boot];render.append(job)
    actual = copy.deepcopy(job); actual['metadata'].update(uid='synthetic-provision',resourceVersion='12')
    replies.objects['Job/provision'] = actual
    # The single-fixture grant accounts every scheduled Job, including its init.
    pod = copy.deepcopy(replies.pods[0])
    pod['metadata'].update(name='provision-test', uid='synthetic-provision-pod', ownerReferences=[
        dict(kind='Job', name='provision', uid=actual['metadata']['uid'], controller=True)])
    pod['spec'] = dict(job['spec']['template']['spec'], nodeName='synthetic-node')
    boot_status = dict(pod['status']['containerStatuses'][0], name='bootstrap')
    pod['status'].update(containerStatuses=[], initContainerStatuses=[boot_status])
    replies.pods.append(pod)
    for name, value in [('inventory',inv),('render',render),('tenants',tenants)]: k.write(out/(name+'.json'),value)
    c['pins'].update(renderSha256=k.digest(out/'render.json'),inventorySha256=k.digest(out/'inventory.json'),instrument=k.instrument()['sha256'])
    binding = dict(kind='evaluator-work-v2',pair=c['pins']['pair'],imageId=c['pins']['appImageId'],instrument=c['pins']['instrument'])
    c['completion'] = dict(clock='synthetic_clock',checkpoint='synthetic_checkpoint',entries='synthetic_entries',consumer='evaluator-sample-completed',kind='evaluator-work-v2',binding=binding)
    supplied_status=status();k.write(out/'status.json',supplied_status)
    projection=subprocess.check_output([str(a.node),'-e',"process.stdout.write(require(process.argv[1]).projection(require(process.argv[2])))",str(k.M7/'fingerprint.cjs'),str(out/'status.json')])
    c['settingsFingerprint']=hashlib.sha256(projection).hexdigest()
    k.write(out/'actor-input.json',dict(tenants=tenants,completion=c['completion'],status=supplied_status))
    shutil.copyfile(HERE/'synthetic-kubectl.py',out/'kubectl');(out/'kubectl').chmod(0o700)
    (out/'ro').write_text('#!/bin/sh\nexec "$@"\n');(out/'ro').chmod(0o700)
    log=(out/'actor.log').open('xb')
    actor=subprocess.Popen([str(a.node),str(HERE/'synthetic-actor.cjs'),str(out),str(a.dependencies)],stdout=log,stderr=log,start_new_session=True)
    try:
        until=time.time()+10
        while not (out/'actor-ready.json').exists():
            assert actor.poll() is None and time.time()<until, 'SYNTHETIC_ACTOR_START_FAILED'
            time.sleep(.05)
        port=k.document(out/'actor-ready.json')['port'];c['baseUrl']=f'http://127.0.0.1:{port}'
        k.write(out/'transport.json',dict(objects=replies.objects,pods=replies.pods,base=c['baseUrl']))
        p=profiles.read(HERE/'small.json')
        p.update(name='realistic-synthetic-join',referencePins=dict(core=core,deploy=c['pins']['pair']['deploy'],bindingCommit=c['pins']['bindingCommit']))
        p['population'].update(provisionedTenants=n,ordinaryRosterTenants=n)
        p['workload']=dict(loadSeconds=40,workloadMix='realistic-v1',workloadScale=8,logicalPollingClients=1,probeEveryMs=1000,setupSeconds=60,drainSeconds=150)
        if a.driver_shards:
            import driver_vu_diagnostic as driver
            p['workload'].update(driverShards=a.driver_shards,
                driverPlan=dict(version=1,observer=a.driver_observer,maxAggregateVUs=28*a.driver_shards,
                    scenarios={name:dict(preAllocatedVUs=2,maxVUs=4,gracefulStopSeconds=2,
                        **(dict(startTimeSeconds=1,durationSeconds=39) if name=='r_status' else {}))
                        for name in driver.SHAPES}))
        k.write(out/'profile.json',p)
        c=profiles.bind(p,c)
        c.update(experimentSha256=k.digest(out/'profile.json'),rosterSha256=k.digest(out/'tenants.json'))
        k.write(out/'bound.json',c)
        d=out/'packet';k.prepare(out/'bound.json',out/'inventory.json',out/'render.json',d)
        d,c,objects=k.load(d);client=k.Client(c)
        k.write(d/'observation.initial.json',k.observe(c,objects,client))
        # These are declared synthetic authority/policy observations, not live
        # admission or security qualification. Original assess still joins them.
        ns=k.active_baseline(d)['namespace']['uid']
        k.write(d/'access.json',dict(verdict='PASS',crossTenantChecks=2,pins=c['pins'],context=c['context'],namespaceUid=ns,scope='synthetic transport fixture only'))
        k.write(d/'policy.json',dict(pins=c['pins'],context=c['context'],namespaceUid=ns,observations=[dict(outcome=v) for v in ('connected','timeout','connected')],scope='synthetic transport fixture only'))
        # The allocation is synthetic and bound to this loopback fixture. The runner
        # reads it and the actual generated workload over its ordinary entry point.
        pre = out/'preflight.json'
        k.write(pre, dict(offline='PASS', commissioning='PREFLIGHT_ONLY',
                    experiment=dict(runId=c['runId'], namespace=c['namespace'], experimentSha256=c['experimentSha256'],
                                    renderSha256=c['pins']['renderSha256'])))
        grant = out/'allocation.json'
        k.write(grant, dict(version=1,status='RELEASED',existingCapacityOnly=True,context=c['context'],
                  **c['deadlines'], experimentSha256=c['experimentSha256'], preflight=dict(path=str(pre),sha256=k.digest(pre)),
                  fixtures=[dict(runId=c['runId'], namespace=c['namespace'], namespaceUid=ns, runSha256=k.digest(d/'run.json'))],
                  nodeCeilings={'synthetic-node':dict(millicpus=2500,memoryBytes=2*1024**3,ephemeralBytes=1024**3)},
                  actorCeilings={c['driver']['hostId']:dict(millicpus=1200,memoryBytes=1342177280)}))
        value=experiment.run(d,grant,k.digest(grant))['load']
        e.assess(d,c,objects,client)
        from matrix import joined_point
        baseline=k.active_baseline(d)
        joined=joined_point(d,c,baseline,k.observe(c,objects,client,baseline))
        assert joined['activity']['workloadMix']=='realistic-v1' and 'offeredRps' not in joined['activity']
        k.write(out/'existing-point-join.json',joined)
        rows=value['storedWrites']['rows']
        assert len(rows)==n and all(row['accepted']>0 and row['accepted']==row['stored'] for row in rows), 'ALL_WRITER_STORED_COVERAGE'
        original=reduction.reduce_stage(d/'load',out/'original-reduction')
        assert all(original[key]['verdict']=='PASS' for key in ('stored','offeredWork','selectedClinicalCoverage','delivered'))
        controls=[]
        def control(name, mutate, code, reducer=False):
            dest=out/name/'load';shutil.copytree(d/'load',dest)
            mutate(dest)
            if reducer:
                # Original retained-evidence reducer, on a copied stage/config.
                k.write(dest.parent/'run.json',c)
                result=reduction.reduce_stage(dest,dest.parent/'reduction')
                assert result['stored']['code']==code,result
            else:
                try:e.assess_stage(d,dest,c,objects,client)
                except Exception as error:assert str(error)==code,(str(error),code)
                else:raise AssertionError('CONTROL_DID_NOT_FAIL:'+name)
            restored=e.assess_stage(d,d/'load',c,objects,client)
            assert restored['verdict']=='OBSERVED'
            controls.append(dict(control=name,code=code,restored='OBSERVED'))
        def alter(dest,file,fn):
            value=k.document(dest/file);fn(value);k.write(dest/file,value)
        control('wrong-viewer-binding',lambda d:alter(d,'probe.json',lambda v:v['viewerBindings'][0].update(tenant=tenants[-1]['id'])),'M7_VIEWER_BINDINGS')
        control('dropped-work',lambda d:alter(d,'k6-summary.json',lambda v:v['metrics']['dropped_iterations'].update(count=1)),
                'M7_DRIVER_SHARD_RECONCILIATION' if a.driver_shards else 'K8S_OFFERED_WORK_INCOMPLETE')
        control('unobserved-clinical',lambda d:alter(d,'probe.json',lambda v:v['completedOutput']['witnesses'].pop()),'K8S_CLINICAL_WITNESS_COVERAGE')
        control('unobserved-frame',lambda d:alter(d,'probe.json',lambda v:v['completedOutput']['witnesses'][0].update(clientObservations=[])),'M7_COMPLETION_CLIENT')
        control('unviewed-stored-loss',lambda d:alter(d,'stored-counts.json',lambda v:v[tenants[-1]['id']].update(entries=v[tenants[-1]['id']]['entries']-1)),'M7_DISCOVERY_WRONG_DATA',True)
        bad=copy.deepcopy(c);bad['workload']['offeredRps']=18
        try:e.execute(out/'unused',bad,objects,client,load=True)
        except k.Refused as error:assert str(error)=='K8S_REALISTIC_MIX_CONFIGURATION'
        else:raise AssertionError('AGGREGATE_OVERRIDE_ACCEPTED')
        controls.append(dict(control='aggregate-override',code='K8S_REALISTIC_MIX_CONFIGURATION',restored=e.assess_stage(d,d/'load',c,objects,client)['verdict']))
        if a.driver_shards:
            m=__import__('workload_runtime').driver_manifest(c)
            altered=copy.deepcopy(m);altered['cadence']['workloadScale']=4
            try:driver.retain(d,altered)
            except RuntimeError as error:assert str(error)=='M7_DRIVER_MANIFEST_PLAN_MISMATCH'
            else:raise AssertionError('ALTERED_PLAN_ACCEPTED')
            controls.append(dict(control='altered-plan',code='M7_DRIVER_MANIFEST_PLAN_MISMATCH',
                                 restored=driver.retain(d,m)['offeredWorkVerdict']))
            if a.driver_shards>1:
                copied=out/'missing-shard';shutil.copytree(d/'load',copied/'load')
                (copied/'load/k6-shard-0.rc').unlink()
                try:driver.retain(copied,m)
                except RuntimeError as error:assert str(error)=='M7_DRIVER_SHARD_MISSING'
                else:raise AssertionError('MISSING_SHARD_ACCEPTED')
                partial=driver.partial_configured(copied,m)
                # Independent valid raw shard rows survive; missing exit custody
                # still prevents the complete accounting path from passing.
                k.write(out/'missing-shard-observations.json',partial)
                assert len(partial['shards'])==a.driver_shards and partial['offeredWorkVerdict']=='UNMEASURED'
                controls.append(dict(control='missing-shard',code='M7_DRIVER_SHARD_MISSING',
                                     restored=driver.retain(d,m)['offeredWorkVerdict']))
        with urlopen(c['baseUrl']+'/synthetic/calls') as response:k.write(out/'http-calls.json',json.load(response))
        result=dict(basis='reproduced instrument wiring only; synthetic product/Kubernetes/SQL endpoints',sourceInstrument=k.instrument(),profile=p,
                    normalEntryPoint='profile.bind -> adapter.prepare/load -> execute(load) -> assess',driver=k.document(d/'load/driver.json'),
                    storedWriterTenants=len(rows),unviewedWriterTenants=n-1,frames=value['frames'],clinical=value['clinical'],controls=controls,
                    applicationCorrectness='UNMEASURED',liveKubernetes='NOT_RUN',capacityAcceptance='NOT_GRANTED')
        k.write(out/'result.json',result)
        print(json.dumps({key:result[key] for key in ('storedWriterTenants','unviewedWriterTenants','controls','liveKubernetes','capacityAcceptance')}))
    finally:
        actor.terminate()
        try:actor.wait(timeout=5)
        except subprocess.TimeoutExpired:actor.kill();actor.wait(timeout=3)
        log.close()
        k.write(out/'cleanup.json',dict(actorExitCode=actor.returncode,ownedPid=actor.pid,scope='owned synthetic actor only'))


if __name__=='__main__':main()
