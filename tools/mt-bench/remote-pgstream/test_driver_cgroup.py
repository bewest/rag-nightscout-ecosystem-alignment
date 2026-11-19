"""Actual supervisor readback seam, authored fake kernel/actor controls; no actor."""
import unittest
raise unittest.SkipTest('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import generator as g
import test_driver_actor as actors

class Cgroup(unittest.TestCase):
 check=actors.Actor.check
 create=actors.Actor.create
 docker_run=actors.Actor.docker_run
 seams=actors.Actor.seams
 def setUp(self):
  actors.Actor.setUp(self)
  self.b['diagnosticResourceAllocation']={'version':1,'services':{r:{'millicpus':125,'memoryBytes':134217728} for r in ('nginx','evaluator','pgstream')},'driver':{'millicpus':4000,'memoryBytes':8589934592},'ceiling':{'millicpus':16000,'memoryBytes':34359738368},'edge':{'workerProcesses':1,'workerConnections':16384}}
  self.argv=g.traffic_commands(self.d,self.b,{'trafficRunId':'m7-synthetic','settingsFingerprint':'e'*64},self.name,123)[1]
  with self.seams():g.plan_k6(self.argv,self.d,self.b,self.name);self.create()
  self.rows[self.cid]['State']={'Pid':123,'Running':True,'StartedAt':'2026-11-18T01:00:00Z'}
  self.rows[self.cid]['HostConfig'].update(NanoCpus=4000000000,Memory=8589934592,MemorySwap=8589934592)
  self.group='/sys/fs/cgroup/system.slice/docker-'+self.cid+'.scope'
  self.files={'/proc/123/stat':'123 (k6) '+' '.join(['S']+['0']*18+['456']),'/proc/123/cgroup':'0::/system.slice/docker-'+self.cid+'.scope\n'}
  self.files.update({self.group+'/'+k:v for k,v in {'cpu.stat':'usage_usec 12345\nnr_periods 10\nnr_throttled 2\nthrottled_usec 700\n','cpu.max':'400000 100000\n','memory.current':'100\n','memory.peak':'200\n','memory.max':'8589934592\n','memory.events':'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n'}.items()})
  self.original_read=Path.read_text
 def kernel(self,path,*args,**kwargs):
  key=str(path)
  if key.startswith(('/proc/123/','/sys/fs/cgroup/')):
   if key not in self.files:raise FileNotFoundError(key)
   return self.files[key]
  return self.original_read(path,*args,**kwargs)
 def observation(self,expected=None):
  with self.seams(),patch.object(Path,'read_text',autospec=True,side_effect=self.kernel):
   return g.driver_cgroup_observation(self.d,self.b,self.name,expected)
 def test_cumulative_kernel_counters_and_exact_bound_identity(self):
  row=self.observation();self.assertEqual(row['status'],'MEASURED')
  self.assertLessEqual(row['readStartedMonotonicNs'],row['cpuStatMonotonicNs']);self.assertLessEqual(row['cpuStatMonotonicNs'],row['readEndedMonotonicNs'])
  self.assertEqual(row['cpuStat']['nr_throttled'],2);self.assertEqual(row['cpuStat']['throttled_usec'],700)
  self.assertEqual(row['memoryPeakBytes'],200);self.assertEqual(row['cpuMax'],'400000 100000')
  self.assertEqual(row['identity']['birthTicks'],'456');self.assertEqual(row['identity']['id'],self.cid)
  self.assertEqual(self.observation(row['identity'])['status'],'MEASURED')
 def test_unknown_missing_and_bad_identity_refuse_then_restore(self):
  green=self.observation();original=copy.deepcopy(self.rows[self.cid]);files=self.files.copy()
  for mutate,code in ((lambda:self.rows[self.cid]['Config']['Labels'].update({'org.nightscout.external.owner':'f'*32}),'EXTERNAL_K6_OWNER_NAME'),(lambda:self.rows[self.cid].update(Image='sha256:'+'1'*64),'EXTERNAL_K6_IMAGE_COMMAND'),(lambda:self.files.pop(self.group+'/memory.peak'),'EXTERNAL_K6_CGROUP_UNAVAILABLE'),(lambda:self.files.update({self.group+'/cpu.stat':'usage_usec 1\n'}),'EXTERNAL_K6_CGROUP_CPU_COUNTERS'),(lambda:self.files.update({self.group+'/cpu.max':'max 100000'}),'EXTERNAL_K6_CGROUP_LIMITS'),(lambda:self.files.update({'/proc/123/cgroup':'1:cpu:/unified-unavailable'}),'EXTERNAL_K6_CGROUP_V2_UNAVAILABLE')):
   self.rows[self.cid]=copy.deepcopy(original);self.files=files.copy();mutate()
   row=self.observation();self.assertEqual(row,{'status':'UNMEASURED','reason':code});self.assertNotIn('cpuStat',row)
  self.rows[self.cid]=original;self.files=files;self.assertEqual(self.observation(green['identity'])['status'],'MEASURED')
 def test_changed_expected_birth_and_changed_midread_birth_refuse_restore(self):
  identity=self.observation()['identity'];identity['birthTicks']='1'
  self.assertEqual(self.observation(identity)['reason'],'EXTERNAL_K6_CGROUP_IDENTITY_CHANGED')
  kernel=self.kernel;reads=0
  def changed(path,*args,**kwargs):
   nonlocal reads
   value=kernel(path,*args,**kwargs)
   if str(path)=='/proc/123/stat':
    reads+=1
    if reads>1:value=value.rsplit(' ',1)[0]+' 999'
   return value
  with self.seams(),patch.object(Path,'read_text',autospec=True,side_effect=changed):
   row=g.driver_cgroup_observation(self.d,self.b,self.name)
  self.assertEqual(row['reason'],'EXTERNAL_K6_CGROUP_BIRTH_CHANGED')
  self.assertEqual(self.observation()['status'],'MEASURED')

if __name__=='__main__':unittest.main()
