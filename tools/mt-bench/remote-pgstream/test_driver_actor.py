"""Existing DRIVER supervisor custody controls; every Docker/signal seam mocked."""
import copy,datetime,json,subprocess,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import generator as g

class Actor(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=Path(self.tmp.name);(self.d/'load').mkdir();self.b={'tenants':1000,'nonce':'b'*32,'sourceSha256':'c'*64,'appAddress':'10.8.0.2','port':18080,'k6Image':'grafana/k6@sha256:'+'d'*64};self.name='nsexternal-'+self.b['nonce'][:12]+'-k6';self.argv=g.traffic_commands(self.d,self.b,{'trafficRunId':'m7-synthetic','settingsFingerprint':'e'*64},self.name,123)[1];self.rows={};self.effects=[];self.cid='a'*64;self.metadata={'Id':'sha256:'+'f'*64,'Config':{'Entrypoint':['k6']}}
 def check(self,argv,**kw):
  if argv[:3]==['docker','image','inspect']:return json.dumps([self.metadata])
  if argv[:3]==['docker','ps','-aq']:
   selector=argv[-1]
   if selector.startswith('id='):return selector[3:]if selector[3:]in self.rows else''
   return '\n'.join(k for k,v in self.rows.items()if selector=='name=^'+v.get('Name','/'+self.name)+'$')
  if argv[:2]==['docker','inspect']:return json.dumps([self.rows[argv[2]]])
  raise AssertionError(argv)
 def create(self,cidfile=True):
  intent,cid,record=g.actor_files(self.d,self.name);v=json.loads(intent.read_text());self.rows[self.cid]={'Id':self.cid,'Name':'/'+self.name,'Created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'Image':v['imageId'],'Config':{'Image':v['image'],'Cmd':v['command'],'Entrypoint':v['entrypoint'],'Labels':{'org.nightscout.external.owner':v['nonce']},'User':'1001:1001','Env':[k+'='+x for k,x in v['environment'].items()]},'HostConfig':{'PidMode':'','IpcMode':'private','AutoRemove':True,'ReadonlyRootfs':True,'Privileged':False,'NetworkMode':'host','CapDrop':['ALL'],'SecurityOpt':['no-new-privileges']},'Mounts':[{'Type':'bind','Source':a,'Destination':b,'RW':c}for a,b,c in v['mounts']]}
  if cidfile:cid.write_text(self.cid)
 def docker_run(self,argv,**kw):
  self.assertEqual(argv,['docker','rm','--force',self.cid]);self.effects.append(('rm',argv[-1]));self.rows.pop(self.cid,None);return types.SimpleNamespace(returncode=0)
 def seams(self):return patch.multiple(g.subprocess,check_output=self.check,run=self.docker_run)
 def test_interrupt_missing_cid_and_failed_record_still_exact_cleanup(self):
  for mode in('missing-cid','bad-cid','stdout-failure','interrupt','record-failure','stop-failure'):
   with self.subTest(mode=mode):
    # Each point uses a new exclusive source-owned creation intent.
    self.rows={};self.effects=[]
    for p in(self.d/'control/actors').glob('*')if(self.d/'control/actors').exists()else[]:p.unlink()
    def popen(argv,**kw):
     self.assertTrue(kw['start_new_session']);self.create(mode not in('missing-cid','stdout-failure'))
     if mode=='bad-cid':g.actor_files(self.d,self.name)[1].write_text('capture-failed')
     if mode=='stdout-failure':raise OSError('synthetic failed stdout/CID capture after creation')
     def wait(**kw):
      if mode=='interrupt':raise RuntimeError('SYNTHETIC_CONTROLLER_LOST')
      return 0
     return types.SimpleNamespace(wait=wait,poll=lambda:0)
    realwrite=g.write
    def write(p,v):
     if mode=='record-failure'and str(p).endswith('.captured.json'):raise OSError('synthetic record failure')
     return realwrite(p,v)
    def stop(process):
     self.effects.append(('stop-cli',None))
     if mode=='stop-failure':raise OSError('synthetic CLI stop failure')
    with self.seams(),patch.object(g.subprocess,'Popen',side_effect=popen),patch.object(g,'stop',side_effect=stop),patch.object(g,'write',side_effect=write):
     if mode in('bad-cid','stdout-failure','interrupt','record-failure','stop-failure'):
      with self.assertRaises((OSError,RuntimeError)):g.run_k6(self.argv,self.d,self.b,self.name,None,1)
     else:self.assertEqual(g.run_k6(self.argv,self.d,self.b,self.name,None,1).returncode,0)
    self.assertEqual(self.effects,[('stop-cli',None),('rm',self.cid)]);self.assertFalse(self.rows)
 def test_valid_wrong_absent_or_foreign_cid_recovers_owned_name_and_preserves_refusal(self):
  for foreign in(False,True):
   with self.subTest(foreign=foreign):
    self.rows={};self.effects=[]
    for p in(self.d/'control/actors').glob('*')if(self.d/'control/actors').exists()else[]:p.unlink()
    with self.seams():g.plan_k6(self.argv,self.d,self.b,self.name);self.create(False)
    wrong='f'*64;g.actor_files(self.d,self.name)[1].write_text(wrong)
    if foreign:
     row=copy.deepcopy(self.rows[self.cid]);row.update(Id=wrong,Name='/foreign',Image='sha256:'+'1'*64);self.rows[wrong]=row
    with self.seams(),self.assertRaisesRegex(RuntimeError,'CUSTODY_REFUSED'):g.cleanup_k6(self.d,self.b,self.name)
    self.assertNotIn(self.cid,self.rows);self.assertEqual(self.effects,[('rm',self.cid)])
    self.assertEqual(wrong in self.rows,foreign)
    report=json.loads(g.actor_files(self.d,self.name)[2].read_text());self.assertIn('CAPTURED_CID_DIFFERS_FROM_PLANNED_NAME',report['refusals'])
    with self.seams(),self.assertRaisesRegex(RuntimeError,'CLEANUP_REFUSED'):g.cleanup_actors(self.d,self.b)
    self.assertEqual(self.effects,[('rm',self.cid)])
  self.rows={};self.effects=[]
  for p in(self.d/'control/actors').glob('*'):p.unlink()
  with self.seams():g.plan_k6(self.argv,self.d,self.b,self.name);self.create();self.assertEqual(g.cleanup_k6(self.d,self.b,self.name)['id'],self.cid)
  self.assertFalse(self.rows)
 def test_forged_owner_wrong_image_command_mount_security_created_refuse_restored(self):
  with self.seams():g.plan_k6(self.argv,self.d,self.b,self.name);self.create(False);original=copy.deepcopy(self.rows[self.cid])
  for mutate in(lambda r:r.update(Image='sha256:'+'1'*64),lambda r:r['Config'].update(Cmd=['wrong']),lambda r:r['Config']['Labels'].update({'org.nightscout.external.owner':'f'*32}),lambda r:r['Mounts'][0].update(Source='/foreign'),lambda r:r['HostConfig'].update(Privileged=True),lambda r:r.update(Created='2020-01-01T00:00:00Z')):
   self.rows[self.cid]=copy.deepcopy(original);mutate(self.rows[self.cid]);self.effects=[]
   with self.seams(),self.assertRaisesRegex(RuntimeError,'EXTERNAL_K6_'):g.cleanup_k6(self.d,self.b,self.name)
   self.assertFalse(self.effects);self.assertTrue(self.rows)
  self.rows[self.cid]=original
  with self.seams():result=g.cleanup_k6(self.d,self.b,self.name)
  self.assertEqual(result['id'],self.cid);self.assertFalse(self.rows)
 def test_name_collision_and_short_inventory_refuse_before_create(self):
  self.rows[self.cid]={'Id':self.cid}
  with self.seams(),patch.object(g.subprocess,'Popen')as launch:
   with self.assertRaises(RuntimeError):g.plan_k6(self.argv,self.d,self.b,self.name)
   launch.assert_not_called();self.assertFalse(g.actor_files(self.d,self.name)[0].exists())
  def short(argv,**kw):return self.cid[:12]if argv[:3]==['docker','ps','-aq']else self.check(argv,**kw)
  with patch.object(g.subprocess,'check_output',side_effect=short),self.assertRaisesRegex(RuntimeError,'FULL_CID'):g.plan_k6(self.argv,self.d,self.b,self.name)
  self.rows={}
  with self.seams():g.plan_k6(self.argv,self.d,self.b,self.name)
  self.assertTrue(g.actor_files(self.d,self.name)[0].exists())
if __name__=='__main__':unittest.main()
