"""Actual canonical prefix/config checks; only Compose config expansion may execute."""
import copy,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import host_binding as h
from protocol import write

class HostBinding(unittest.TestCase):
 def fixture(self,folder):
  d=Path(folder);(d/'env').write_text('NS_DEMO_PROJECT=remote-canonical-test\n')
  cfg={'name':'remote-canonical-test','services':{'api':{'image':'synthetic-image:immutable','command':['node','api']}}}
  write(d/'input.json',cfg)
  argv=['docker','compose','-p',cfg['name'],'--env-file',str(d/'env'),'-f',str(d/'input.json'),'--profile','ops','config','--format','json']
  expanded=json.loads(subprocess.check_output(argv,timeout=10,stderr=subprocess.PIPE))
  write(d/'frozen.compose.json',expanded);m={'directory':str(d),'project':cfg['name'],'owner':'a'*32,'environmentSha256':h.core.digest(d/'env'),'composeSha256':h.core.digest(d/'frozen.compose.json')};write(d/'owner.json',m);return d,m
 def test_actual_compose_config_and_wrong_project_env_hash_before_effect(self):
  with tempfile.TemporaryDirectory()as folder:
   d,m=self.fixture(folder);effects=[]
   def runner(argv):
    self.assertIn('config',argv);return subprocess.check_output(argv,timeout=10,stderr=subprocess.PIPE)
   argv=h.core.fixture_argv(d,['up','-d','api']);h.core.fixture_mutation_preflight(d,argv,runner)
   write(d/'owner.json',{**m,'project':'foreign-project'})
   with self.assertRaisesRegex(RuntimeError,'PROJECT_MISMATCH'):h.preflight(d)
   with patch.object(h.a,'command')as commands,patch.object(h.a,'image')as images:
    with self.assertRaisesRegex(RuntimeError,'PROJECT_MISMATCH'):h.producer.deploy(d,{**m,'project':'foreign-project'})
    commands.assert_not_called();images.assert_not_called()
   write(d/'owner.json',m);h.preflight(d)
   (d/'env').write_text('NS_DEMO_PROJECT=foreign-project\n')
   with self.assertRaisesRegex(RuntimeError,'FIXTURE_CHANGED'):h.preflight(d)
   (d/'env').write_text('NS_DEMO_PROJECT=remote-canonical-test\n');h.preflight(d)
   cfg=json.loads((d/'frozen.compose.json').read_text());cfg['services']['api']['command']=['node','changed'];write(d/'frozen.compose.json',cfg)
   with self.assertRaisesRegex(RuntimeError,'FIXTURE_CHANGED'):h.preflight(d)
   self.assertEqual(effects,[])
 def test_unjournaled_existing_resource_refuses_and_case_home_not_forged(self):
  with tempfile.TemporaryDirectory()as folder:
   d,m=self.fixture(folder)
   with patch.object(h.a,'resources',return_value=[{'Id':'f'*64}]):
    with self.assertRaisesRegex(RuntimeError,'UNJOURNALED_RESOURCE'):h.cleanup(d)
   with patch.object(h.a,'resources',return_value=[]):self.assertEqual(h.cleanup(d)['status'],'PREPARED_NO_RUNTIME_RESOURCES')
   write(d/'owner.json',{**m,'orchestrationHome':str(d/'forged')})
   with self.assertRaisesRegex(RuntimeError,'CANONICAL_BINDING_HOME'):h.existing(d)
if __name__=='__main__':unittest.main()
