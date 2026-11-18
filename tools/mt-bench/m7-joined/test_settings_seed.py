"""Safe seed classifications and authored predicate-removal controls."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
HERE = Path(__file__).parent
ROW = {'id':'11111111-1111-4111-8111-111111111111','hosts':['synthetic.invalid'],'issueRootSecret':True}
SCRIPT = "const f=require(process.argv[1]);try{console.log(JSON.stringify(f.validateSeed(process.argv[2],Number(process.argv[3]))));}catch(e){console.log(JSON.stringify({code:e.message,classification:e.seedCode}));process.exitCode=1;}"

class SettingsSeed(unittest.TestCase):
    def check_seed(self,path,count=1,module=None):
        p=subprocess.run(['node','-e',SCRIPT,str((module or HERE/'fingerprint.cjs').resolve()),str(path),str(count)],text=True,capture_output=True,timeout=10)
        self.assertEqual(p.stderr,'')
        return p.returncode,json.loads(p.stdout)

    def test_field_classification_and_restoration_never_export_values(self):
        seed={'version':1,'seed':[ROW]}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'seed.json'
            def good():
                path.write_text(json.dumps(seed))
                self.assertEqual(self.check_seed(path),(0,{'schema':1,'tenants':1,'status':'STRUCTURE_VERIFIED'}))
            good()
            cases=[('JSON','{'),('SHAPE','null'),('SHAPE',json.dumps({'version':2,'seed':[ROW]})),('SHAPE',json.dumps({'version':1,'seed':{}})),('COUNT',json.dumps({'version':1,'seed':[]}))]
            for field,value,code in [('extra','private-value','ROW_KEYS'),('id','private-id','ID_FORMAT'),('hosts',['private-host','second'],'HOSTS'),('hosts','private-host','HOSTS'),('hosts',[7],'HOSTS'),('hosts',['x'*254],'HOSTS'),('issueRootSecret',False,'ROOT_SECRET')]:
                bad=copy.deepcopy(seed);bad['seed'][0][field]=value;cases.append((code,json.dumps(bad)))
            for code,raw in cases:
                with self.subTest(code=code):
                    path.write_text(raw)
                    self.assertEqual(self.check_seed(path),(1,{'code':'M7_SETTINGS_SEED_INVALID','classification':'M7_SETTINGS_SEED_'+code}))
                    good()
            path.write_text(json.dumps({'version':1,'seed':[ROW,ROW]}))
            self.assertEqual(self.check_seed(path,2)[1]['classification'],'M7_SETTINGS_SEED_ID_DUPLICATE');good()
            for count in (0,10001,1.5):self.assertEqual(self.check_seed(path,count)[1]['classification'],'M7_SETTINGS_SEED_COUNT')
            link=Path(tmp)/'link.json';link.symlink_to(path)
            for target,code in [(link,'FILE_TYPE'),(Path(tmp),'FILE_TYPE'),(Path(tmp)/'absent','FILE_READ')]:
                self.assertEqual(self.check_seed(target)[1]['classification'],'M7_SETTINGS_SEED_'+code)
            path.write_text('x'*4194305);self.assertEqual(self.check_seed(path)[1]['classification'],'M7_SETTINGS_SEED_FILE_SIZE');good()

    def test_removed_count_id_host_guards_make_criterion_red_then_restore(self):
        original=(HERE/'fingerprint.cjs').read_text()
        controls=[
            (" || seed.seed.length !== count",{'version':1,'seed':[]},1,'COUNT'),
            ("    if (ids.has(row.id)) fail('ID_DUPLICATE');",{'version':1,'seed':[ROW,ROW]},2,'ID_DUPLICATE'),
            ("    if (!Array.isArray(row.hosts) || row.hosts.length !== 1 || typeof row.hosts[0] !== 'string' || row.hosts[0].length > 253) fail('HOSTS');",{'version':1,'seed':[{**ROW,'hosts':[]}]},1,'HOSTS')]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'seed.json';broken=Path(tmp)/'fingerprint.cjs'
            for anchor,seed,count,code in controls:
                self.assertEqual(original.count(anchor),1);broken.write_text(original.replace(anchor,''));path.write_text(json.dumps(seed))
                def criterion(module):self.assertEqual(self.check_seed(path,count,module),(1,{'code':'M7_SETTINGS_SEED_INVALID','classification':'M7_SETTINGS_SEED_'+code}),'SEED_PREDICATE_MUST_REFUSE')
                criterion(HERE/'fingerprint.cjs')
                with self.assertRaisesRegex(AssertionError,'SEED_PREDICATE_MUST_REFUSE'):criterion(broken)
                criterion(HERE/'fingerprint.cjs')
if __name__=='__main__':unittest.main()
