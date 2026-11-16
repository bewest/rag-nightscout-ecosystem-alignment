"""Quota-derived worker counts preserve per-worker connections and identity gates."""
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import adapter as a
import diagnostic_resources as r

TEXT="worker_processes 1;\nworker_rlimit_nofile 65536;\nevents { worker_connections 16384; }\n"
class EdgeWorkers(unittest.TestCase):
 def budget(self):return r.edge_worker_budget(r.QUALIFICATION_NAME)
 def test_existing_profiles_derive_one_worker_default_untouched(self):
  self.assertIsNone(r.edge_worker_budget(None))
  for profile in r.PROFILES:
   value=r.edge_worker_budget(profile);self.assertEqual(value['workerProcesses'],1);self.assertEqual(value['workerConnections'],16384);self.assertEqual(value['nginxMillicpus'],125)
 def test_generated_and_native_readback_reject_auto_missing_tamper(self):
  self.assertEqual(a.verify_edge_workers(TEXT,self.budget())['workerProcesses'],1)
  for text in [TEXT.replace('worker_processes 1;','worker_processes auto;'),TEXT.replace('worker_processes 1;',''),TEXT.replace('16384','8192'),TEXT+'worker_processes 1;']:
   with self.assertRaisesRegex(RuntimeError,'EDGE_WORKER_CONFIGURATION'):a.verify_edge_workers(text,self.budget())
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
    self.assertEqual(calls[0]['NS_EDGE_WORKER_PROCESSES'],'1');budget=a.document(d/'owner.json')['edgeWorkerBudget'];self.assertEqual(budget['workerProcesses'],1);self.assertEqual(budget['configurationSha256'],a.digest(d/'state/edge/nginx.conf'))
   finally:r.configure()
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
