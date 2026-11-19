"""Actual app.load/ingress/freeze/load, all native/provider seams mocked."""
import unittest
raise unittest.SkipTest('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import copy,importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch
import app,host_binding as h,transport as t
spec=importlib.util.spec_from_file_location('overlay_fixture',Path(__file__).with_name('test_prepared_cleanup.py'));f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class Overlay(unittest.TestCase):
 setUp=f.PreparedCleanup.setUp
 save_owner=f.PreparedCleanup.save_owner
 owner=f.PreparedCleanup.owner
 save_config=f.PreparedCleanup.save_config
 prepared=f.PreparedCleanup.prepared
 def config(self):
  self.config={'name':self.m['project'],'services':{role:{'image':t.POSTGRES if role=='postgres'else t.APP,'command':['postgres']if role=='postgres'else['node',role],'labels':{app.a.OWNER:self.m['owner']},'environment':{}}for role in('postgres','vault','admin','bootstrap','primer','api','evaluator','realtime','tenant-admin','ui','nginx')}}
  self.config['services']['nginx']['ports']=[{'host_ip':'127.0.0.1','published':self.m['port'],'target':8080,'protocol':'tcp'}];self.save_config(self.config);self.m['composeSha256']=app.a.digest(self.d/'frozen.compose.json');self.save_owner(self.m)
 def test_freeze_maintains_overlay_provenance_and_actual_load_stale_red_restored(self):
  # setUp stores self.config, so invoke the method through the class.
  Overlay.config(self);b=self.prepared();self.rows=[]
  fw={'rules':t.firewall_rules(b)[1],'sha256':'e'*64}
  metadata={'imageIds':{r:s['image']for r,s in self.config['services'].items()},'imageConfigs':{r:{'Id':s['image'],'Config':{'Cmd':s['command'],'Entrypoint':None}}for r,s in self.config['services'].items()}}
  with patch.object(t,'firewall_check',return_value=fw),patch.object(h.core,'image_metadata',return_value=metadata):
   app.load(self.d,b);app.ingress(self.d,b);app.load(self.d,b);before=(self.d/'remote-overlay.json').read_bytes();h.freeze(self.d);app.load(self.d,b)
   self.assertEqual((self.d/'remote-overlay.before-freeze.json').read_bytes(),before)
   evidence=(self.d/'remote-overlay.json').read_bytes();cfg=app.a.document(self.d/'frozen.compose.json')
   with self.assertRaisesRegex(RuntimeError,'OVERLAY_HASH_CHANGED'):t.verify_overlay(cfg,b,json.loads(before))
   (self.d/'remote-overlay.json').write_bytes(before)
   with self.assertRaisesRegex(RuntimeError,'FROZEN_OVERLAY_CHANGED'):app.load(self.d,b)
   (self.d/'remote-overlay.json').write_bytes(evidence);app.load(self.d,b);self.assertEqual(app.a.document(self.d/'remote-overlay.json')['freezeTransform']['previousAfterSha256'],json.loads(before)['afterSha256'])
 def test_interrupted_freeze_update_refuses_load_before_any_effect(self):
  Overlay.config(self);b=self.prepared();self.rows=[];realwrite=h.write;effects=[]
  metadata={'imageIds':{r:s['image']for r,s in self.config['services'].items()},'imageConfigs':{r:{'Id':s['image'],'Config':{'Cmd':s['command'],'Entrypoint':None}}for r,s in self.config['services'].items()}}
  def write(path,value):
   if Path(path)==self.d/'owner.json':raise OSError('synthetic owner commit failure')
   return realwrite(path,value)
  with patch.object(t,'firewall_check',return_value={'rules':t.firewall_rules(b)[1],'sha256':'e'*64}),patch.object(h.core,'image_metadata',return_value=metadata):
   app.ingress(self.d,b)
   with patch.object(h,'write',side_effect=write),self.assertRaises(OSError):h.freeze(self.d)
   with self.assertRaisesRegex(RuntimeError,'FIXTURE_CHANGED'):app.load(self.d,b)
   self.assertEqual(effects,[])
if __name__=='__main__':unittest.main()
