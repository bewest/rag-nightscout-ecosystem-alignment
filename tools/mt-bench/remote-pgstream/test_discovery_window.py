"""Original finite discovery binding at actual stage/session ports; no actors."""
import unittest
raise unittest.SkipTest('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import contextlib,io,tempfile,unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch,Mock
import app,generator,producer,protocol,host_binding
import test_discovery_reporting as fixtures
class Window(unittest.TestCase):
 def selected(self):
  b=fixtures.DiscoveryReporting().selected();b['expiresAt']=10000;return b
 def test_binding_age_and_global_limit_are_not_renewed(self):
  b=self.selected();protocol.binding(b,now=1000)
  self.assertEqual(protocol.work_seconds(b,600,now=1000),8460)
  self.assertEqual(protocol.work_seconds(b,600,now=9450),10)
  self.assertEqual(protocol.work_seconds({**b,'reportMode':'strict'},600,now=1000),600)
  for now in (9460,10000):
   with self.assertRaisesRegex(RuntimeError,'EXTERNAL_DEADLINE'):protocol.work_seconds(b,600,now=now)
  for expiry in (12000,float('inf'),float('nan')):
   with self.assertRaisesRegex(RuntimeError,'EXTERNAL_DEADLINE'):protocol.binding({**b,'expiresAt':expiry},now=1000)
 def test_actual_generator_prime_wait_exceeds_legacy_cap_but_not_original_cutoff(self):
  b=self.selected();clock=[1000];path=Mock();path.exists.side_effect=[False,False,True];path.is_file.return_value=True;path.is_symlink.return_value=False
  process=Mock();process.poll.return_value=None
  def sleep(_):clock[0]+=700
  with patch.object(generator.time,'time',side_effect=lambda:clock[0]),patch.object(generator.time,'monotonic',side_effect=lambda:clock[0]),patch.object(generator.time,'sleep',side_effect=sleep):generator.wait_file(path,process,b)
  clock[0]=9450;path.exists.side_effect=None;path.exists.return_value=False
  with patch.object(generator.time,'time',side_effect=lambda:clock[0]),patch.object(generator.time,'monotonic',side_effect=lambda:clock[0]),patch.object(generator.time,'sleep',side_effect=sleep):
   with self.assertRaisesRegex(RuntimeError,'TRAFFIC_PHASE_TIMEOUT'):generator.wait_file(path,process,b)
 def test_producer_and_app_session_keep_original_and_stricter_cutoffs(self):
  b=self.selected();m={'externalBinding':b};d=Path('/synthetic')
  def observed(*args):return app.a._COMMAND_DEADLINE.get()
  with patch.object(host_binding,'preflight'),patch.object(producer,'_deploy',side_effect=observed),patch.object(protocol.time,'time',return_value=1000):
   self.assertEqual(producer.deploy(d,m),9460)
   with app.a.command_deadline(2000):self.assertEqual(producer.deploy(d,m),2000)
  with patch.object(app,'load',return_value=(d,m,b)),patch.object(app,'_session',side_effect=observed):
   self.assertEqual(app.session(d,b),9460)
   with app.a.command_deadline(2000):self.assertEqual(app.session(d,b),2000)
 def test_actual_app_prime_receive_gets_remainder(self):
  b=self.selected();m={'externalBinding':b};channel=Mock();channel.receive.side_effect=RuntimeError('STOP_BEFORE_LOAD');record=Mock()
  with patch.object(app,'load',return_value=(Path('/synthetic'),m,b)),patch.object(app,'Channel',return_value=channel),patch.object(app.a,'sample_context'),patch('discovery.Record',return_value=record),patch.object(protocol.time,'time',return_value=1000):
   with self.assertRaisesRegex(RuntimeError,'STOP_BEFORE_LOAD'):app.session('/synthetic',b)
  channel.receive.assert_called_once_with('client-primed',8460)
 def test_actual_channel_caps_wait_at_original_cleanup_reserve(self):
  b=self.selected()
  with patch.object(protocol.time,'time',return_value=1000):channel=protocol.Channel(b,'app-0',incoming=io.StringIO(),outgoing=io.StringIO(),clock=lambda:9450)
  with patch.object(protocol.select,'select',return_value=([],[],[])) as select:
   with self.assertRaisesRegex(RuntimeError,'HANDSHAKE_TIMEOUT'):channel.receive('load-start',protocol.work_seconds(b,1800,now=1000))
  self.assertGreater(select.call_args.args[3],9);self.assertLessEqual(select.call_args.args[3],10)
 def test_actual_remote_compose_stage_receives_original_remainder(self):
  b=self.selected()
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   root=Path(tmp);producer.a.write(root/'frozen.compose.json',{'services':{}})
   m={'externalBinding':b,'profile':'pgstream-sample','runPurpose':'discovery','generator':{'ready':True}}
   for name in ('frozen','experiment_host','verify','verify_generator','pin_service_images'):stack.enter_context(patch.object(producer.a,name))
   stack.enter_context(patch.object(producer.a,'image',return_value='synthetic'))
   stack.enter_context(patch.object(producer,'cell_contract'));stack.enter_context(patch.object(host_binding,'preflight'));stack.enter_context(patch.object(host_binding,'freeze'))
   stack.enter_context(patch.object(producer,'deployment_plan',return_value=[('commission','compose',['run'])]))
   stage=stack.enter_context(patch.object(host_binding,'run_stage',side_effect=RuntimeError('STOP_BEFORE_ACTOR')))
   stack.enter_context(patch.object(protocol.time,'time',return_value=1000))
   with self.assertRaisesRegex(RuntimeError,'STOP_BEFORE_ACTOR'):producer.deploy(root,m)
   self.assertEqual(stage.call_args.kwargs['timeout'],8460)

 def test_actual_generator_session_k6_and_probe_waits_use_original_remainder(self):
  b=self.selected();descriptor={'files':{'workload.js':'a'*64}};waits=[]
  class Process:
   pid=12345;returncode=0
   def poll(self):return None
   def wait(self,timeout):waits.append(timeout);return 0
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   root=Path(tmp);out=root/'load';out.mkdir()
   def child(*args):
    (out/'.window').touch();protocol.write(out/'prime.json',{'primed':0});return Process()
   stack.enter_context(patch.object(protocol.time,'time',return_value=1000))
   stack.enter_context(patch.object(generator,'prepare',return_value=descriptor));stack.enter_context(patch.object(generator,'source_identity',return_value={'sha256':b['sourceSha256']}))
   stack.enter_context(patch.object(generator.subprocess,'check_output',return_value=b''))
   stack.enter_context(patch.object(generator,'traffic_commands',return_value=([],[])));stack.enter_context(patch.object(generator,'child',side_effect=child))
   stack.enter_context(patch.object(generator,'sample'));stack.enter_context(patch.object(generator,'Channel',return_value=Mock()))
   run=stack.enter_context(patch.object(generator,'run_k6',return_value=SimpleNamespace(returncode=0)))
   stack.enter_context(patch.object(generator,'stop'));stack.enter_context(patch.object(generator,'cleanup_k6'))
   generator.session(root,b)
   self.assertEqual(run.call_args.args[-1],8460);self.assertEqual(waits,[8460])

if __name__=='__main__':unittest.main()
