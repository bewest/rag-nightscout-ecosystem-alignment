"""Explicit DRIVER native limits use the existing exact custody actor seam."""
import copy,json,subprocess,types
from unittest.mock import patch
import unittest
import generator as g
import test_driver_actor as actors

def allocation():
 return {'version':1,'services':{r:{'millicpus':125,'memoryBytes':134217728}for r in ('nginx','evaluator','pgstream')},'driver':{'millicpus':4000,'memoryBytes':8589934592},'ceiling':{'millicpus':16000,'memoryBytes':34359738368},'edge':{'workerProcesses':1,'workerConnections':16384}}

class Resources(actors.Actor):
 def setUp(self):
  super().setUp();self.b['diagnosticResourceAllocation']=allocation();self.argv=g.traffic_commands(self.d,self.b,{'trafficRunId':'m7-synthetic','settingsFingerprint':'e'*64},self.name,123)[1]
 def create(self,cidfile=True):
  super().create(cidfile);self.rows[self.cid]['HostConfig'].update(NanoCpus=4000000000,Memory=8589934592,MemorySwap=8589934592)
 def test_missing_wrong_duplicate_and_alias_limits_refuse_before_process(self):
  def remove(argv):
   i=argv.index('--cpus');del argv[i:i+6]
  def wrong(argv):argv[argv.index('--memory')+1]='1'
  def duplicate(argv):argv[3:3]=['--cpus','4']
  def alias(argv):argv[3:3]=['--memory-swap=-1']
  for change in (remove,wrong,duplicate,alias):
   argv=self.argv.copy();change(argv)
   with self.seams(),patch.object(g.subprocess,'Popen')as launch:
    with self.assertRaisesRegex(RuntimeError,'RESOURCE_FLAGS'):g.run_k6(argv,self.d,self.b,self.name,None,1)
    launch.assert_not_called()
   self.assertFalse(g.actor_files(self.d,self.name)[0].exists())
  with self.seams():g.plan_k6(self.argv,self.d,self.b,self.name)
  intent=json.loads(g.actor_files(self.d,self.name)[0].read_text());self.assertEqual(intent['resourceLimits'],allocation()['driver'])
 def test_native_missing_wrong_and_unlimited_swap_refuse_then_restore(self):
  with self.seams():g.plan_k6(self.argv,self.d,self.b,self.name);self.create()
  intent=json.loads(g.actor_files(self.d,self.name)[0].read_text());original=copy.deepcopy(self.rows[self.cid])
  for key,value in (('NanoCpus',0),('NanoCpus',2000000000),('Memory',0),('MemorySwap',-1)):
   row=copy.deepcopy(original);row['HostConfig'][key]=value
   with self.assertRaisesRegex(RuntimeError,'RESOURCE_LIMITS'):g.qualify_k6(row,intent)
  self.assertEqual(g.qualify_k6(original,intent),self.cid)
  with self.seams():g.cleanup_k6(self.d,self.b,self.name)
  self.assertFalse(self.rows)
 def test_run_retains_primary_native_failure_and_cleans_only_exact_owned_actor(self):
  def launch(*args,**kwargs):
   self.create();self.rows[self.cid]['HostConfig']['NanoCpus']=0
   return types.SimpleNamespace(poll=lambda:None,wait=lambda **kw:0)
  with self.seams(),patch.object(g.subprocess,'Popen',side_effect=launch),patch.object(g,'stop',side_effect=OSError('synthetic CLI stop fault')):
   with self.assertRaisesRegex(RuntimeError,'^EXTERNAL_K6_RESOURCE_LIMITS$')as caught:g.run_k6(self.argv,self.d,self.b,self.name,None,2)
  self.assertEqual(caught.exception.stopFailure,'EXTERNAL_K6_CLI_STOP_REFUSED')
  self.assertEqual(caught.exception.cleanupFailure,'EXTERNAL_K6_CUSTODY_REFUSED_AFTER_OWNED_CLEANUP')
  self.assertEqual(self.effects,[('rm',self.cid)]);self.assertFalse(self.rows)
  native=json.loads(g.actor_files(self.d,self.name)[2].with_suffix('.native.json').read_text());self.assertEqual(native['status'],'FAIL');self.assertEqual(native['native']['NanoCpus'],0)
 def test_no_explicit_allocation_preserves_historical_argv_and_qualification(self):
  b=dict(self.b);b.pop('diagnosticResourceAllocation')
  argv=g.traffic_commands(self.d,b,{'trafficRunId':'m7-synthetic','settingsFingerprint':'e'*64},self.name,123)[1]
  self.assertNotIn('--cpus',argv);self.assertNotIn('--memory',argv);self.assertNotIn('--memory-swap',argv)
  with self.seams():g.plan_k6(argv,self.d,b,self.name);super().create()
  intent=json.loads(g.actor_files(self.d,self.name)[0].read_text());self.assertNotIn('resourceLimits',intent)
  self.rows[self.cid]['HostConfig'].update(NanoCpus=0,Memory=0,MemorySwap=0)
  self.assertEqual(g.qualify_k6(self.rows[self.cid],intent),self.cid)

if __name__=='__main__':unittest.main()
