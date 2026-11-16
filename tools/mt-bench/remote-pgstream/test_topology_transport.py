"""Explicit topology binding through the actual caller, worker and helper parser."""
import ast,copy,hashlib,importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app,cell,protocol,transport
import test_discovery_reporting as reporting

ROOT=Path(__file__).resolve().parents[3]
class TopologyTransport(unittest.TestCase):
 def selected(self):
  b=reporting.DiscoveryReporting().selected(2)
  b.update(pair={'core':os.environ.get('PGCAL_TOPOLOGY_CORE_COMMIT','a'*40),'deploy':os.environ.get('PGCAL_TOPOLOGY_DEPLOY_COMMIT','b'*40)},imageId=os.environ.get('PGCAL_TOPOLOGY_IMAGE','sha256:'+'c'*64),pgstreamTopology='external-service-v1',diagnosticResourceProfile='local-diagnostic-external-pgstream-4cpu-8g-v1')
  # Fixtures describe the actual committed helper. Production still requires
  # an explicit selector and rejects an omitted transitive dependency.
  names=['tools/mt-bench/m7-joined/stream_topology.py','tools/mt-bench/m7-joined/diagnostic_resources.py']
  tree=ast.parse((ROOT/names[1]).read_text())
  uses_batch=any(isinstance(n,ast.ImportFrom) and n.module=='experiment_batch' for n in ast.walk(tree))
  if uses_batch:names.append('tools/mt-bench/m7-joined/experiment_batch.py')
  files={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
  b['helperDependencies']={'version':1,'profile':'external-service-batch-v1' if uses_batch else 'external-service-v1','files':files}
  return b
 def test_binding_requires_both_selectors_and_exact_dependency_profile(self):
  b=self.selected();protocol.binding(b);protocol.topology_dependencies(b,ROOT)
  for mutate in (lambda b:b.pop('pgstreamTopology'),lambda b:b.pop('diagnosticResourceProfile'),lambda b:b.pop('helperDependencies'),lambda b:b['helperDependencies']['files'].pop('tools/mt-bench/m7-joined/stream_topology.py')):
   broken=copy.deepcopy(b);mutate(broken)
   with self.assertRaises(RuntimeError):protocol.binding(broken)
  broken=copy.deepcopy(b);broken['helperDependencies']['files']['tools/mt-bench/m7-joined/stream_topology.py']='0'*64
  with self.assertRaisesRegex(RuntimeError,'DEPENDENCY_BYTES'):protocol.topology_dependencies(broken,ROOT)
 def test_wrong_transitive_dependency_profile_refuses(self):
  b=self.selected();deps=b['helperDependencies']
  if deps['profile']=='external-service-batch-v1':
   deps['profile']='external-service-v1';deps['files'].pop('tools/mt-bench/m7-joined/experiment_batch.py')
  else:
   deps['profile']='external-service-batch-v1';deps['files']['tools/mt-bench/m7-joined/experiment_batch.py']='0'*64
  with self.assertRaisesRegex(RuntimeError,'DEPENDENCY_'):protocol.topology_dependencies(b,ROOT)

 def test_runtime_cell_cannot_silently_omit_selected_topology(self):
  b=self.selected();m=dict(pair=b['pair'],imageId=b['imageId'],postgresImageId=transport.POSTGRES,tenants=b['tenants'],replicas=1,profile='pgstream-sample',runPurpose='discovery',measurementMode='accepted',completionContract='evaluator-work-v2',cadence=b['workload']['cadence'],primerConcurrency=b['workload']['primerConcurrency'],pgstreamTopology=b['pgstreamTopology'],diagnosticResources={'profile':b['diagnosticResourceProfile']})
  transport.cell_contract(m,b)
  for field in ('pgstreamTopology','diagnosticResources'):
   broken=copy.deepcopy(m);del broken[field]
   with self.assertRaisesRegex(RuntimeError,'TOPOLOGY_CELL_CHANGED'):transport.cell_contract(broken,b)
 @unittest.skipUnless(os.environ.get('REMOTE_PGSTREAM_CONTROLLER_ROOT'),'paired future controller required')
 def test_actual_caller_worker_cell_parser_and_admission_controls(self):
  controller=Path(os.environ['REMOTE_PGSTREAM_CONTROLLER_ROOT']).resolve()
  loader=importlib.util.spec_from_file_location('topology_controller_worker',controller/'tools/perf-cloud/pgstream-worker.py');worker=importlib.util.module_from_spec(loader);loader.loader.exec_module(worker)
  b=self.selected();receipt={'status':'AUTHORIZED_DIAGNOSTIC','remoteProfile':b['profile'],'remoteTransport':b['transport'],'remoteExtensionSha256':b['sourceSha256'],'completionContract':'evaluator-work-v2','remoteWorkload':b['workload'],'remoteReportMode':'discovery','remotePgstreamTopology':b['pgstreamTopology'],'remoteDiagnosticResourceProfile':b['diagnosticResourceProfile'],'remoteHelperDependencies':b['helperDependencies']}
  hosts={role:{**h,'privateIPv4':b['appAddress'] if role=='sut' else b['generatorAddress']} for role,h in b['workload']['resourcePlan']['hosts'].items()}
  spec={'profile':b['profile'],'reportMode':'discovery','runId':b['runId'],'cloudId':b['cloudId'],'nonce':b['nonce'],'tenants':b['tenants'],'pins':{**b['pair'],'app':b['imageId'],'postgres':transport.POSTGRES},'cadence':b['workload']['cadence'],'primerConcurrency':b['workload']['primerConcurrency'],'resourcePlan':b['workload']['resourcePlan'],'hosts':hosts,'port':b['port'],'expiresAt':b['expiresAt'],'k6Image':b['k6Image'],'extensionSha256':b['sourceSha256'],'transport':b['transport'],'completionContract':'evaluator-work-v2','diagnostics':'off','receipt':receipt,**{k:b[k] for k in ('pgstreamTopology','diagnosticResourceProfile','helperDependencies')}}
  script="import {runtimeBinding} from "+json.dumps((controller/'tools/perf-cloud/pgstream-caller.mjs').as_uri())+";let s='';for await(const c of process.stdin)s+=c;console.log(JSON.stringify(runtimeBinding(JSON.parse(s))));"
  actual=json.loads(subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(spec),capture_output=True,text=True,check=True).stdout);self.assertEqual(actual,b);protocol.binding(actual)
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);(d/'input').mkdir();(d/'input/binding.json').write_text(json.dumps(actual));(d/'input/receipt.json').write_text(json.dumps(receipt))
   with patch.object(worker,'ROOT',d):args=list(map(str,worker.prepare_arguments(spec)))[2:]
   def run(argv):
    with patch.object(sys,'argv',['cell.py',*argv]),patch.object(app.a,'prepare') as prepare,patch.object(app,'record_prepared_binding'):
     cell.main();return prepare.call_args.args[0]
   parsed=run(args);self.assertEqual(parsed.pgstream_topology,b['pgstreamTopology']);self.assertEqual(parsed.diagnostic_resource_profile,b['diagnosticResourceProfile']);self.assertEqual(parsed.core_commit,b['pair']['core']);self.assertEqual(parsed.image,b['imageId'])
   for flag in ('--pgstream-topology','--diagnostic-resource-profile'):
    i=args.index(flag);missing=args[:i]+args[i+2:]
    with self.assertRaisesRegex(RuntimeError,'PREPARE_PROFILE_REQUIRED'):run(missing)
   changed=list(args);changed[changed.index('--core-commit')+1]='f'*40
   with self.assertRaisesRegex(RuntimeError,'PREPARE_PROFILE_REQUIRED'):run(changed)
   bad=copy.deepcopy(receipt);del bad['remoteHelperDependencies'];(d/'input/receipt.json').write_text(json.dumps(bad))
   with self.assertRaisesRegex(RuntimeError,'AUTHORIZATION_REQUIRED'):run(args)
   (d/'input/receipt.json').write_text(json.dumps(receipt));self.assertEqual(run(args).image,b['imageId'])
if __name__=='__main__':unittest.main()
