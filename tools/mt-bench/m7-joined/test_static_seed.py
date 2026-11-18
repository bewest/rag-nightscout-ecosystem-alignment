"""The ordinary selected bootstrap seed must retain the runner's tenant count."""
import copy
import inspect
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import adapter as a
import static_topology as s

CORE=os.environ.get('M7_PROFILE_TEST_CORE')
COMMIT=os.environ.get('M7_PROFILE_TEST_COMMIT')
HERE=Path(__file__).parent


def manifest():
    return {'pair':{'core':COMMIT or s.E217_CORE,'deploy':os.environ.get('M7_PROFILE_TEST_DEPLOY_COMMIT',s.DEPLOY)},'profile':'pgstream-sample',
            'runPurpose':'discovery','pgstreamTopology':'external-service-v1','completionContract':'evaluator-work-v2',
            'replicas':2,'tenants':4,'staticTopology':{'kind':s.KIND,'workers':2}}


class SeedCount(unittest.TestCase):
    def test_static_early_count_mismatch_refuses_before_role_launch(self):
        from test_role_instances import config as role_config
        value=role_config();value['services']['bootstrap']={'environment':{'NS_DEMO_TENANTS':'2'}}
        # Check seed propagation first, before unrelated edge requirements.
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_SEED_COUNT'):s.verify_config(manifest(),value)
        value['services']['bootstrap']['environment']['NS_DEMO_TENANTS']='4'
        with self.assertRaisesRegex(RuntimeError,'M7_STATIC_EDGE_COMMAND|M7_STATIC_PLATFORM_RESTART'):s.verify_config(manifest(),value)

    @unittest.skipUnless(CORE and COMMIT,'owned selected source fixture required')
    def test_actual_ordinary_seed_count_red_restored(self):
        self.assertIn((COMMIT,manifest()['pair']['deploy']),s.SOURCE_PAIRS)
        self.assertEqual(subprocess.check_output(['git','-C',CORE,'rev-parse','HEAD'],text=True).strip(),COMMIT)
        m=manifest();source=inspect.getsource(a.preparation_environment)
        broken=source.replace("'NS_DEMO_TENANTS': str(m['tenants']),",'')
        self.assertNotEqual(source,broken);scope=dict(vars(a));exec(compile(broken,'seed_count_control','exec'),scope)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def generate(name,environment):
                out=root/name;out.mkdir()
                env=a.runtime_env({'NS_PGSTREAM':'1',**environment})
                emitted=subprocess.run(['node',str(HERE/'bootstrap-seed-fixture.cjs'),CORE,str(out),COMMIT,m['pair']['deploy']],env=env,cwd=CORE,capture_output=True,text=True,check=True,timeout=30)
                path=out/'primer/config.json';value=json.loads(path.read_text())
                return path,value,json.loads(emitted.stdout),env
            for name,environment,good in [('normal',a.preparation_environment(m),True),('omitted',scope['preparation_environment'](m),False),('restored',a.preparation_environment(m),True)]:
                path,value,emitted,env=generate(name,environment)
                self.assertEqual(len(value['seed']),4 if good else 2)
                self.assertEqual(emitted['seedCount'],len(value['seed']))
                self.assertIn('NS_DEMO_TENANTS: "'+str(len(value['seed']))+'"',(path.parent.parent/'source-evaluator-overlay.yaml').read_text())

if __name__=='__main__':unittest.main()
