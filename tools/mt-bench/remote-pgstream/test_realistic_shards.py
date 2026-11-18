"""Real configured cadence/roster/argv and paired worker parser; no provider effects."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import app
import cell
import generator as g
import protocol
import transport
from test_topology_transport import TopologyTransport
from test_driver_actor import Actor

ROOT=Path(__file__).resolve().parents[3]


def selected(tenants=1000,seconds=1800):
    b=TopologyTransport().selected()
    b['tenants']=tenants
    cadence=b['workload']['cadence']
    cadence.pop('offeredRps')
    cadence.update(workloadMix='realistic-v1',driverShards=8,loadSeconds=seconds,
                   warmupSeconds=10,idleSeconds=30,accel=1,hotFactor=1,socketsPerTenant=1,
                   logicalPollingClients=tenants//10,probeEveryMs=30000)
    b['workload']['resourcePlan'].update(tenants=tenants,logicalPollingClients=tenants//10)
    b['workload']['jwtSetupConcurrency']=16
    for name in ('driver_shards.py','contract.py'):
        file='tools/mt-bench/m7-joined/'+name
        b['helperDependencies']['files'][file]=hashlib.sha256((ROOT/file).read_bytes()).hexdigest()
    return b


def controller_spec(b):
    hosts={role:{**host,'privateIPv4':b['appAddress'] if role=='sut' else b['generatorAddress']}
           for role,host in b['workload']['resourcePlan']['hosts'].items()}
    receipt={'status':'AUTHORIZED_DIAGNOSTIC','remoteProfile':b['profile'],'remoteReportMode':'discovery',
             'remoteTransport':b['transport'],'remoteExtensionSha256':b['sourceSha256'],
             'remotePgstreamTopology':b['pgstreamTopology'],'remoteDiagnosticResourceProfile':b['diagnosticResourceProfile'],
             'remoteHelperDependencies':b['helperDependencies'],'remoteWorkload':b['workload'],'completionContract':'evaluator-work-v2'}
    return {'profile':b['profile'],'reportMode':'discovery','runId':b['runId'],'cloudId':b['cloudId'],'nonce':b['nonce'],
            'tenants':b['tenants'],'logicalPollingClients':b['workload']['resourcePlan']['logicalPollingClients'],
            'pins':{**b['pair'],'app':b['imageId'],'postgres':transport.POSTGRES},'cadence':b['workload']['cadence'],
            'primerConcurrency':b['workload']['primerConcurrency'],'jwtSetupConcurrency':b['workload']['jwtSetupConcurrency'],
            'resourcePlan':b['workload']['resourcePlan'],'hosts':hosts,'port':b['port'],'expiresAt':b['expiresAt'],
            'k6Image':b['k6Image'],'extensionSha256':b['sourceSha256'],'transport':b['transport'],
            'completionContract':'evaluator-work-v2','diagnostics':'off','receipt':receipt,
            **{key:b[key] for key in ('pgstreamTopology','diagnosticResourceProfile','helperDependencies')}}


class RealisticShards(unittest.TestCase):
    def test_realistic_binding_and_unknown_mixed_selectors_refuse_restore(self):
        for count in (1000,10000):
            b=selected(count);protocol.binding(b);protocol.topology_dependencies(b,ROOT)
            self.assertEqual(protocol.prepared_cadence(b),b['workload']['cadence'])
            for change in ({'workloadMix':'unknown'},{'offeredRps':180},{'accel':2},{'hotFactor':2},
                           {'driverShards':True},{'driverShards':0},{'driverShards':17},{'unknownSelector':1}):
                bad=copy.deepcopy(b);bad['workload']['cadence'].update(change)
                with self.assertRaises(RuntimeError):protocol.binding(bad)
            bad=copy.deepcopy(b);bad['helperDependencies']['files'].pop('tools/mt-bench/m7-joined/driver_shards.py')
            with self.assertRaisesRegex(RuntimeError,'DEPENDENCIES'):protocol.binding(bad)
            bad=copy.deepcopy(b);bad['helperDependencies']['files']['tools/mt-bench/m7-joined/contract.py']='0'*64
            with self.assertRaisesRegex(RuntimeError,'DEPENDENCY_BYTES'):protocol.topology_dependencies(bad,ROOT)
            protocol.binding(b);protocol.topology_dependencies(b,ROOT)

    def test_actual_rosters_and_canonical_shell_custody(self):
        actor=Actor();actor.setUp();self.addCleanup(actor.tmp.cleanup)
        d=actor.d;b=selected();actor.b=b
        roster=[{'id':str(i),'host':str(i)+'.example.test','token':'synthetic'} for i in range(1000)]
        (d/'tenants.private.json').write_text(json.dumps(roster))
        descriptor={'trafficRunId':'synthetic-shards','settingsFingerprint':'e'*64}
        (d/'traffic.json').write_text(json.dumps(descriptor))
        with patch.object(g.os,'chown'):record=g.prepare_driver_shards(d,b)
        self.assertEqual(len(record['rows']),8)
        reconstructed=[]
        for row in record['rows']:
            reconstructed+=json.loads((d/'k6-shards'/('tenants-%d.private.json'%row['index'])).read_text())
        self.assertEqual(reconstructed,roster)
        probe,argv=g.traffic_commands(d,b,descriptor,actor.name,123)
        self.assertEqual(probe[probe.index('--clients')+1],'100')
        self.assertEqual(argv[-2],'-c');self.assertEqual(argv[-1].count('k6 run --quiet'),8)
        self.assertIn('M7_WORKLOAD_MIX=realistic-v1',argv);self.assertNotIn('TENANTS_FILE=/tenants.private.json',argv)
        self.assertNotIn('OFFERED_RPS=', ' '.join(argv));self.assertIn('tenants-7.private.json',argv[-1])
        subprocess.run(['sh','-n','-c',argv[-1]],check=True)
        actor.argv=argv
        bad=argv.copy();bad[-1]+='\ntrue'
        with actor.seams(),self.assertRaisesRegex(RuntimeError,'SHARD_COMMAND'):g.plan_k6(bad,d,b,actor.name)
        victim=d/'k6-shards/tenants-0.private.json';original=victim.read_bytes();victim.chmod(0o640);victim.write_text('[]')
        with actor.seams(),self.assertRaisesRegex(RuntimeError,'SHARD_ROSTER'):g.plan_k6(argv,d,b,actor.name)
        victim.write_bytes(original);victim.chmod(0o440)
        with actor.seams():g.plan_k6(argv,d,b,actor.name);actor.create()
        intent=json.loads(g.actor_files(d,actor.name)[0].read_text())
        self.assertEqual(intent['entrypoint'],['sh']);self.assertEqual(len(intent['mounts']),4)
        self.assertEqual(g.qualify_k6(actor.rows[actor.cid],intent),actor.cid)
        wrong=copy.deepcopy(actor.rows[actor.cid]);wrong['Config']['Entrypoint']=['k6']
        with self.assertRaisesRegex(RuntimeError,'IMAGE_COMMAND'):g.qualify_k6(wrong,intent)
        with actor.seams():g.cleanup_k6(d,b,actor.name)
        self.assertFalse(actor.rows)

    def test_scale_binding_refuses_mixed_unknown_and_outside_bounds(self):
        for scale in (.25,1,2,8):
            b=selected();b['workload']['cadence']['workloadScale']=scale
            protocol.binding(b)
            for value in (True,None,0,.24,8.01,float('nan'),float('inf')):
                bad=copy.deepcopy(b);bad['workload']['cadence']['workloadScale']=value
                with self.assertRaisesRegex(RuntimeError,'REMOTE_WORKLOAD_SCALE_CONFIGURATION'):protocol.binding(bad)
            bad=copy.deepcopy(b);bad['workload']['cadence'].pop('workloadMix')
            with self.assertRaisesRegex(RuntimeError,'REMOTE_WORKLOAD_SCALE_CONFIGURATION'):protocol.binding(bad)
            protocol.binding(b)

    def test_scaled_canonical_driver_refuses_omitted_environment_mirror(self):
        actor=Actor();actor.setUp();self.addCleanup(actor.tmp.cleanup);d=actor.d;b=selected();actor.b=b
        b['workload']['cadence']['workloadScale']=2
        (d/'tenants.private.json').write_text(json.dumps([{'id':str(i),'token':'synthetic'} for i in range(1000)]))
        descriptor={'trafficRunId':'synthetic-scale','settingsFingerprint':'e'*64};(d/'traffic.json').write_text(json.dumps(descriptor))
        with patch.object(g.os,'chown'):g.prepare_driver_shards(d,b)
        _,argv=g.traffic_commands(d,b,descriptor,actor.name,123)
        self.assertIn('M7_WORKLOAD_SCALE=2',argv)
        i=argv.index('M7_WORKLOAD_SCALE=2');bad=argv[:i-1]+argv[i+1:]
        with actor.seams(),self.assertRaisesRegex(RuntimeError,'EXTERNAL_K6_SHARD_COMMAND'):g.plan_k6(bad,d,b,actor.name)
        self.assertFalse(g.actor_files(d,actor.name)[0].exists())
        with actor.seams():g.plan_k6(argv,d,b,actor.name);actor.create();g.cleanup_k6(d,b,actor.name)
        self.assertFalse(actor.rows)

    @unittest.skipUnless(os.environ.get('REMOTE_PGSTREAM_CONTROLLER_ROOT'),'paired controller checkout required')
    def test_scale_actual_caller_worker_helper_and_receipt_mirrors(self):
        controller=Path(os.environ['REMOTE_PGSTREAM_CONTROLLER_ROOT'])
        module=importlib.util.spec_from_file_location('scale_worker',controller/'tools/perf-cloud/pgstream-worker.py')
        worker=importlib.util.module_from_spec(module);module.loader.exec_module(worker)
        script='import {runtimeBinding} from '+json.dumps((controller/'tools/perf-cloud/pgstream-caller.mjs').as_uri())+';let s="";for await(const c of process.stdin)s+=c;console.log(JSON.stringify(runtimeBinding(JSON.parse(s))));'
        for scale in (.25,1,2,8):
            b=selected();b['workload']['cadence']['workloadScale']=scale;spec=controller_spec(b)
            actual=json.loads(subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(spec),capture_output=True,text=True,check=True).stdout)
            self.assertEqual(actual,b);protocol.binding(actual)
            with tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);(d/'input').mkdir();(d/'input/binding.json').write_text(json.dumps(actual));(d/'input/receipt.json').write_text(json.dumps(spec['receipt']))
                dependencies={'root':'/synthetic/dependencies','receipt':'/synthetic/receipt','sha256':'f'*64}
                with patch.object(worker,'ROOT',d):args=list(map(str,worker.prepare_arguments(spec,dependencies)))[2:]
                with patch.object(sys,'argv',['cell.py',*args]),patch.object(app.a,'prepare') as prepare,patch.object(app,'record_prepared_binding'):
                    cell.main();parsed=prepare.call_args.args[0]
                self.assertEqual(app.a.cadence_options(parsed),b['workload']['cadence'])
                self.assertEqual(parsed.workload_scale,scale)
                i=args.index('--workload-scale');missing=args[:i]+args[i+2:]
                with patch.object(sys,'argv',['cell.py',*missing]),patch.object(app.a,'prepare') as prepare:
                    with self.assertRaisesRegex(RuntimeError,'REMOTE_PREPARE_PROFILE_REQUIRED'):cell.main()
                    prepare.assert_not_called()
                receipt_path=d/'input/receipt.json';original=receipt_path.read_text();bad=json.loads(original);bad['remoteWorkload']['cadence']['workloadScale']=3;receipt_path.write_text(json.dumps(bad))
                with patch.object(sys,'argv',['cell.py',*args]),patch.object(app.a,'prepare') as prepare:
                    with self.assertRaisesRegex(RuntimeError,'REMOTE_EXTENSION_AUTHORIZATION_REQUIRED'):cell.main()
                    prepare.assert_not_called()
                receipt_path.write_text(original)
                with patch.object(sys,'argv',['cell.py',*args]),patch.object(app.a,'prepare') as prepare,patch.object(app,'record_prepared_binding'):
                    cell.main();prepare.assert_called_once()

    @unittest.skipUnless(os.environ.get('REMOTE_PGSTREAM_CONTROLLER_ROOT'),'paired controller checkout required')
    def test_actual_caller_worker_helper_and_result_paths(self):
        controller=Path(os.environ['REMOTE_PGSTREAM_CONTROLLER_ROOT'])
        module=importlib.util.spec_from_file_location('realistic_worker',controller/'tools/perf-cloud/pgstream-worker.py')
        worker=importlib.util.module_from_spec(module);module.loader.exec_module(worker)
        for count in (1000,10000):
            b=selected(count);spec=controller_spec(b)
            script='import {runtimeBinding} from '+json.dumps((controller/'tools/perf-cloud/pgstream-caller.mjs').as_uri())+';let s="";for await(const c of process.stdin)s+=c;console.log(JSON.stringify(runtimeBinding(JSON.parse(s))));'
            actual=json.loads(subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(spec),capture_output=True,text=True,check=True).stdout)
            self.assertEqual(actual,b);protocol.binding(actual)
            with tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);(d/'input').mkdir();(d/'input/binding.json').write_text(json.dumps(actual));(d/'input/receipt.json').write_text(json.dumps(spec['receipt']))
                dependencies={'root':'/synthetic/dependencies','receipt':'/synthetic/receipt','sha256':'f'*64}
                with patch.object(worker,'ROOT',d):args=list(map(str,worker.prepare_arguments(spec,dependencies)))[2:]
                with patch.object(sys,'argv',['cell.py',*args]),patch.object(app.a,'prepare') as prepare,patch.object(app,'record_prepared_binding'):
                    cell.main();parsed=prepare.call_args.args[0]
                self.assertEqual(app.a.cadence_options(parsed),b['workload']['cadence'])
                for flag in ('--workload-mix','--driver-shards'):
                    i=args.index(flag);bad=args[:i]+args[i+2:]
                    with patch.object(sys,'argv',['cell.py',*bad]),patch.object(app.a,'prepare') as prepare:
                        with self.assertRaisesRegex(RuntimeError,'PREPARE_PROFILE_REQUIRED'):cell.main()
                        prepare.assert_not_called()
                with patch.object(worker,'ROOT',d):paths=worker.client_result_paths(spec)
                self.assertIn('k6-shards.json',paths);self.assertIn('k6-shard-rosters.json',paths)
                self.assertEqual(paths['k6-shard-rosters.json'],d/'traffic/control/k6-shard-rosters.json')
                for index in range(8):
                    self.assertIn('k6-summary-%d.json'%index,paths);self.assertIn('k6-shard-%d.rc'%index,paths);self.assertIn('k6-shard-%d.log'%index,paths)


if __name__=='__main__':unittest.main()
