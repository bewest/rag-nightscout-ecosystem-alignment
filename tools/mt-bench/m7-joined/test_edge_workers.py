"""Quota-derived worker counts preserve per-worker connections and identity gates."""
import copy
import json
import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import adapter as a
import diagnostic_resources as r

TEXT="worker_processes 1;\nworker_rlimit_nofile 65536;\nevents { worker_connections 16384; }\n"

def setUpModule():
 global _unit_directory,_unit_lock_patch
 import diagnostic_resources as experiment_batch
 _unit_directory=tempfile.TemporaryDirectory(prefix='m7-edge-unit-')
 _unit_lock_patch=patch.object(experiment_batch,'global_lock_path',return_value=Path(_unit_directory.name)/'heap.lock')
 _unit_lock_patch.start()

def tearDownModule():
 r.configure();_unit_lock_patch.stop();_unit_directory.cleanup()

class EdgeWorkers(unittest.TestCase):
 def test_explicit_worker_and_connection_values_are_independent_of_reference(self):
  from test_resource_allocation import allocation
  selected=allocation();selected['edge']={'workerProcesses':65,'workerConnections':65536}
  self.assertEqual(r.edge_worker_budget(selected),{**selected['edge'],'nginxMillicpus':125,'source':'explicit-resource-allocation-v1'})
 def budget(self):return r.edge_worker_budget(r.QUALIFICATION_NAME)
 def test_existing_profiles_derive_one_worker_default_untouched(self):
  self.assertIsNone(r.edge_worker_budget(None))
  for profile in r.PROFILES:
   value=r.edge_worker_budget(profile);self.assertEqual(value['workerProcesses'],1);self.assertEqual(value['workerConnections'],16384);self.assertEqual(value['nginxMillicpus'],125)
 def test_generated_and_native_readback_reject_auto_missing_tamper(self):
  self.assertEqual(a.verify_edge_workers(TEXT,self.budget())['workerProcesses'],1)
  for text in [TEXT.replace('worker_processes 1;','worker_processes auto;'),TEXT.replace('worker_processes 1;',''),TEXT.replace('16384','8192'),TEXT+'worker_processes 1;',TEXT.replace('65536','32768'),TEXT+'worker_rlimit_nofile 65536;']:
   with self.assertRaisesRegex(RuntimeError,'EDGE_WORKER_CONFIGURATION'):a.verify_edge_workers(text,self.budget())
 def test_explicit_projection_changes_only_numeric_fields_and_refuses_source_drift(self):
  from test_resource_allocation import expanded_allocation
  budget=r.edge_worker_budget(expanded_allocation())
  projected=a.project_edge_workers(TEXT,budget)
  self.assertEqual(projected,TEXT.replace('worker_processes 1;','worker_processes 65;').replace('worker_connections 16384;','worker_connections 65536;'))
  self.assertEqual(a.verify_edge_workers(projected,budget),{'workerProcesses':65,'workerConnections':65536})
  for broken in (TEXT.replace('16384','8192'),TEXT.replace('65536','32768'),TEXT+'worker_processes 1;',TEXT+'events { worker_connections 16384; }'):
   with self.assertRaisesRegex(RuntimeError,'EDGE_WORKER_CONFIGURATION'):a.project_edge_workers(broken,budget)
   self.assertEqual(a.project_edge_workers(TEXT,budget),projected)
  with self.assertRaisesRegex(RuntimeError,'PROJECTION_SELECTION'):a.project_edge_workers(TEXT,self.budget())
  print('RED_RESTORED mounted edge source drift, duplicate fields and descriptor budget')
 @unittest.skipUnless(os.environ.get('M7_EDGE_DEPLOY_REPOSITORY') and os.environ.get('M7_EDGE_DEPLOY_COMMIT'),'exact deployment repository and commit required')
 def test_actual_source_renderer_and_explicit_projection_preserve_all_other_bytes(self):
  from test_resource_allocation import expanded_allocation
  repo=os.environ['M7_EDGE_DEPLOY_REPOSITORY'];commit=os.environ['M7_EDGE_DEPLOY_COMMIT']
  with tempfile.TemporaryDirectory() as folder:
   d=Path(folder)
   for name in ('edge.js','nginx.compose.conf'):
    raw=subprocess.run(['git','-C',repo,'show',commit+':bindings/compose/multitenant/'+name],capture_output=True,check=True).stdout
    (d/name).write_bytes(raw)
   script="const fs=require('node:fs'),edge=require('./edge');process.stdout.write(edge.render(fs.readFileSync('nginx.compose.conf','utf8'),{source:JSON.parse(process.argv[1])}));"
   def render(source):return subprocess.run(['node','-e',script,json.dumps(source)],cwd=d,capture_output=True,text=True,timeout=10)
   baseline=render({'NS_EDGE_WORKER_PROCESSES':'1','NS_EDGE_WORKER_CONNECTIONS':'16384'})
   self.assertEqual(baseline.returncode,0,baseline.stderr)
   a.verify_edge_workers(baseline.stdout,self.budget())
   selected=r.edge_worker_budget(expanded_allocation());projected=a.project_edge_workers(baseline.stdout,selected)
   self.assertEqual(projected,baseline.stdout.replace('worker_processes 1;','worker_processes 65;').replace('worker_connections 16384;','worker_connections 65536;'))
   # The source remains at its original reference policy. The helper owns
   # this mounted-config projection; it does not relabel source capability.
   rejected=render({'NS_EDGE_WORKER_PROCESSES':'65','NS_EDGE_WORKER_CONNECTIONS':'65536'})
   self.assertNotEqual(rejected.returncode,0);self.assertIn('NS_EDGE_WORKER_PROCESSES',rejected.stderr)
   self.assertEqual(a.project_edge_workers(baseline.stdout,r.edge_worker_budget({**expanded_allocation(),'edge':{'workerProcesses':1,'workerConnections':16384}})),baseline.stdout)
   print('REPRODUCED exact deployment source renders baseline, rejects direct65, preserves every other byte under mounted projection')
 def test_actual_prepare_forwards_and_records_generated_workers(self):
  with tempfile.TemporaryDirectory() as temp:
   d=Path(temp);calls=[]
   args=SimpleNamespace(core_repo='core',deploy_repo='deploy',core_commit='a'*40,deploy_commit='b'*40,image='sha256:'+'c'*64,postgres_image='sha256:'+'d'*64,tenants=4,replicas=1,quiet_load=3,freeze=str(d/'freeze.json'),profile='pgstream-sample',backend_subnet='10.221.0.0/28',edge_subnet='10.221.1.0/28',fixture_project='ns-edge-fixture',diagnostic_resource_profile=r.QUALIFICATION_NAME,pgstream_topology=a.stream_topology.EXTERNAL)
   def git(repo,*argv):
    if argv[:2]==('worktree','add'):(d/'core/deploy/multitenant').mkdir(parents=True)
    return ''
   def command(argv,**options):
    if argv[0]=='tar':
     overlay=d/'core/deploy/multitenant'
     for name in ('compose.yaml','commission-restore.js','publish-primer.js'):(overlay/name).write_text('synthetic')
     return ''
    if argv[0]=='node':
     calls.append(options['env']);(d/'core/deploy/multitenant/.env').write_text('SYNTHETIC=1\n');edge=d/'state/edge';edge.mkdir(parents=True);(edge/'nginx.conf').write_text(TEXT if options['env'].get('NS_EDGE_WORKER_PROCESSES')=='1' else TEXT.replace('worker_processes 1;','worker_processes auto;'));return ''
    if argv[0]=='docker':
     if argv[1] in ('network','volume'):return ''
     names=['postgres','vault','admin','primer','api','realtime','evaluator','tenant-admin','ui','nginx','pgstream']
     return json.dumps({'services':{name:{'command':['postgres']if name=='postgres'else(a.stream_topology.EXTERNAL_COMMAND if name=='pgstream'else['node','entrypoint.js',name]),'image':args.postgres_image if name=='postgres'else args.image}for name in names}})
    return b''
   r.configure(r.QUALIFICATION_NAME)
   try:
    with patch.object(a,'setup_generator'),patch.object(a,'seal_diagnostic_images',side_effect=lambda config,m:config),patch.object(a,'port',return_value=12345),patch.object(a,'git',side_effect=git),patch.object(a,'command',side_effect=command),patch.object(a,'inventory',return_value={}),patch.object(a,'host_identity',return_value='host'),patch.object(a,'resources',return_value=[]):a.prepare_staged(args,d,{'sha256':'e'*64})
    expected=r.edge_worker_budget(r.QUALIFICATION_NAME)
    self.assertEqual(calls[0]['NS_EDGE_WORKER_PROCESSES'],'1');budget=a.document(d/'owner.json')['edgeWorkerBudget'];self.assertEqual(budget['workerProcesses'],expected['workerProcesses']);self.assertEqual(budget['workerConnections'],expected['workerConnections']);self.assertEqual(budget['configurationSha256'],a.digest(d/'state/edge/nginx.conf'));a.verify_edge_workers((d/'state/edge/nginx.conf').read_text(),expected)
   finally:r.configure()
 def test_actual_prepare_records_projected_explicit_fields(self):
  from test_resource_allocation import allocation
  import diagnostic_resources as experiment_batch
  selected=allocation();selected['edge']={'workerProcesses':65,'workerConnections':65536}
  with tempfile.TemporaryDirectory() as folder,patch.object(experiment_batch,'global_lock_path',return_value=Path(folder)/'unit-heap.lock'),patch.object(r,'QUALIFICATION_NAME',selected):
   self.test_actual_prepare_forwards_and_records_generated_workers()
 def test_actual_prepare_projection_omission_is_red_then_restored(self):
  with patch.object(a,'project_edge_workers',side_effect=lambda text,budget:text):
   with self.assertRaisesRegex(RuntimeError,'EDGE_WORKER_CONFIGURATION'):self.test_actual_prepare_records_projected_explicit_fields()
  self.test_actual_prepare_records_projected_explicit_fields()
  print('RED_RESTORED omitted actual prepare projection: generated config differs from authored edge budget')
 def test_runtime_exact_owned_container_and_budget(self):
  m={'edgeWorkerBudget':self.budget(),'diagnosticResources':{'profile':r.QUALIFICATION_NAME}}
  rows=[{'Id':'owned-nginx','Config':{'Labels':{'com.docker.compose.service':'nginx'}}}]
  with patch.object(a,'resources',return_value=rows),patch.object(a,'command',return_value=TEXT) as command:
   result=a.edge_runtime(None,m);self.assertEqual(result['containerId'],'owned-nginx');self.assertEqual(command.call_args.args[0],['docker','exec','owned-nginx','nginx','-T'])
   bad=copy.deepcopy(m);bad['edgeWorkerBudget']['workerProcesses']=16
   with self.assertRaisesRegex(RuntimeError,'BUDGET_CHANGED'):a.edge_runtime(None,bad)
  with patch.object(a,'resources',return_value=[]):
   with self.assertRaisesRegex(RuntimeError,'RUNTIME_ROSTER'):a.edge_runtime(None,m)
  self.assertIsNone(a.edge_runtime(None,{}))
if __name__=='__main__':unittest.main()
