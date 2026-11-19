"""Prepare/config controls; privilege and process seams are injected, never npm itself."""
import unittest
raise unittest.SkipTest('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import json,os,stat,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import patch
import generator as g

class NpmConfig(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=Path(self.tmp.name)
  self.realstat=Path.stat
  def stat_path(path,*args,**kw):
   v=self.realstat(path,*args,**kw)
   if path==self.d/'npm-config' or path.parent==self.d/'npm-config':
    row=list(v);row[4]=0;row[5]=g.GID;return os.stat_result(row)
   return v
  self.stack=patch.multiple(g.os,chown=lambda *args:None);self.stack.start();self.addCleanup(self.stack.stop)
  self.stats=patch.object(Path,'stat',stat_path);self.stats.start();self.addCleanup(self.stats.stop)
 def test_distinct_immutable_empty_configs_ignore_ambient(self):
  with patch.dict(os.environ,{'NPM_CONFIG_USERCONFIG':'/foreign','NPM_CONFIG_GLOBALCONFIG':'/foreign'}):
   env=g.restricted(g.npm_configs(self.d,create=True))
  self.assertNotEqual(env['NPM_CONFIG_USERCONFIG'],env['NPM_CONFIG_GLOBALCONFIG'])
  self.assertEqual(env['HOME'],'/nonexistent');self.assertNotIn('NODE_PATH',env)
  for value in (env['NPM_CONFIG_USERCONFIG'],env['NPM_CONFIG_GLOBALCONFIG']):
   self.assertEqual(Path(value).read_bytes(),b'');self.assertEqual(Path(value).stat().st_mode&0o777,0o440)
  self.assertEqual((self.d/'npm-config').stat().st_mode&0o777,0o750)
 def test_collision_symlink_content_mode_refuse_restored(self):
  original=g.npm_configs(self.d,create=True);user=Path(original['NPM_CONFIG_USERCONFIG']);glob=Path(original['NPM_CONFIG_GLOBALCONFIG'])
  with self.assertRaises(FileExistsError):g.npm_configs(self.d,create=True)
  user.chmod(0o640);user.write_text('registry=https://foreign.invalid');user.chmod(0o440)
  with self.assertRaisesRegex(RuntimeError,'NPM_CONFIG_CHANGED'):g.npm_configs(self.d)
  user.chmod(0o640);user.write_bytes(b'')
  with self.assertRaisesRegex(RuntimeError,'NPM_CONFIG_CHANGED'):g.npm_configs(self.d)
  user.chmod(0o440);glob.unlink();glob.symlink_to(user)
  with self.assertRaisesRegex(RuntimeError,'NPM_CONFIG_DISTINCT'):g.npm_configs(self.d)
  glob.unlink();glob.write_bytes(b'');glob.chmod(0o440);self.assertEqual(g.npm_configs(self.d),original)
 def test_actual_prepare_emits_locked_ci_restricted_child_and_checks_config(self):
  b={'tenants':1,'expiresAt':time.time()+1800};files={n:(b'[]' if n=='tenants.private.json' else b'{}') for n in g.TRAFFIC_FILES};files['tenants.private.json']=b'[{}]'
  for name,value in files.items():(self.d/name).write_bytes(value)
  descriptor={'version':1,'binding':b,'files':{name:g.executable(self.d/name) for name in files},'generator':{'pair':{'core':'synthetic'},'servingImageId':'synthetic'}}
  b.update(pair={'core':'synthetic'},imageId='synthetic');(self.d/'traffic.json').write_text(json.dumps(descriptor))
  captured={}
  def child(argv,cwd,env,output):
   captured.update(argv=argv,cwd=str(cwd),env=env)
   self.assertEqual(g.npm_configs(self.d),{k:env[k] for k in ('NPM_CONFIG_USERCONFIG','NPM_CONFIG_GLOBALCONFIG')})
   return types.SimpleNamespace(wait=lambda **kw:1,poll=lambda:0)
  with patch.object(g.os,'geteuid',return_value=0),patch.object(g.pwd,'getpwuid',return_value=types.SimpleNamespace(pw_name='nsload',pw_gid=g.GID)),patch.object(g.subprocess,'check_output',return_value='nsload'),patch.object(g,'child',side_effect=child):
   with self.assertRaisesRegex(RuntimeError,'EXTERNAL_CLIENT_INSTALL_FAILED'):g.prepare(self.d,b)
  self.assertEqual(captured['argv'],['/usr/local/bin/npm','ci','--include=dev','--omit=optional','--ignore-scripts','--force'])
  self.assertEqual(captured['cwd'],str(self.d/'dependencies'))
  self.assertEqual(set(captured['env']),{'PATH','HOME','LANG','NPM_CONFIG_USERCONFIG','NPM_CONFIG_GLOBALCONFIG','NPM_CONFIG_CACHE'})
  self.assertEqual(captured['env']['NPM_CONFIG_CACHE'],str(self.d/'dependencies/.npm-cache'))

 def test_actual_prepare_rechecks_configs_after_install_before_tools(self):
  b={'tenants':1,'expiresAt':time.time()+1800,'pair':{'core':'synthetic'},'imageId':'synthetic'}
  for name in g.TRAFFIC_FILES:(self.d/name).write_bytes(b'[{}]' if name=='tenants.private.json' else b'{}')
  descriptor={'version':1,'binding':b,'files':{name:g.executable(self.d/name) for name in g.TRAFFIC_FILES},'generator':{'pair':b['pair'],'servingImageId':b['imageId']}}
  (self.d/'traffic.json').write_text(json.dumps(descriptor))
  def child(*args):
   user=self.d/'npm-config/user.rc';user.chmod(0o640);user.write_text('registry=https://foreign.invalid');user.chmod(0o440)
   return types.SimpleNamespace(wait=lambda **kw:0,poll=lambda:0)
  with patch.object(g.os,'geteuid',return_value=0),patch.object(g.pwd,'getpwuid',return_value=types.SimpleNamespace(pw_name='nsload',pw_gid=g.GID)),patch.object(g.subprocess,'check_output',return_value='nsload'),patch.object(g,'child',side_effect=child):
   with self.assertRaisesRegex(RuntimeError,'EXTERNAL_NPM_CONFIG_CHANGED'):g.prepare(self.d,b)

if __name__=='__main__':unittest.main()
