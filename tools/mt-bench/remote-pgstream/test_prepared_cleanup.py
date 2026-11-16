"""Offline remote binding lifecycle; adapter host/image calls are explicit seams."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app
import protocol
import transport as t
fixtures_spec=importlib.util.spec_from_file_location('remote_contract_fixtures',Path(__file__).with_name('test_contract.py'))
fixtures=importlib.util.module_from_spec(fixtures_spec);fixtures_spec.loader.exec_module(fixtures)
selected,nics=fixtures.selected,fixtures.nics

class PreparedCleanup(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.d=Path(tmp.name)
        self.b=selected();self.b['sourceSha256']=protocol.source_identity(app.HERE)['sha256']
        self.m=dict(directory=str(self.d),owner='a'*32,project='nsm7-aaaaaaaaaaaa-n1000-a1',instrument={'sha256':'f'*64},
                    prepared=True,port=18081,pair=self.b['pair'],imageId=t.APP,postgresImageId=t.POSTGRES,
                    profile='pgstream-sample',runPurpose='discovery',tenants=1000,replicas=1,cadence=t.CADENCE,
                    freeze=str(self.d/'receipt.json'))
        self.receipt=dict(kind='joined-diagnostic',status='AUTHORIZED_DIAGNOSTIC',functionalAcceptanceAtAuthorization='PENDING',
                          pair=self.b['pair'],imageId=t.APP,instrument='f'*64,limits={'tenants':1000,'apiReplicas':1,'trafficSeconds':310},
                          remoteProfile=self.b['profile'],remoteTransport=self.b['transport'],remoteExtensionSha256=self.b['sourceSha256'])
        self.config={'name':self.m['project'],'services':{'nginx':{'ports':[{'host_ip':'127.0.0.1','published':18081,'target':8080,'protocol':'tcp'}]}}}
        (self.d/'env').write_text('NS_DEMO_PROJECT='+self.m['project']+'\n');self.save_config(self.config);self.m.update(environmentSha256=app.a.digest(self.d/'env'),composeSha256=app.a.digest(self.d/'frozen.compose.json'));self.save_owner(self.m);(self.d/'receipt.json').write_text(json.dumps(self.receipt))
        self.rows=[{'Config':{'Labels':{app.a.OWNER:'a'*32}}}]
        for target,name,value in [(protocol.time,'time',lambda:1000),(app.a,'instrument',lambda:{'sha256':'f'*64}),
                                  (app.a,'image',lambda m:t.APP),(app.a,'resources',lambda *a,**k:self.rows),
                                  (app.a,'command',lambda *a,**k:''),(t,'local_nics',nics)]:
            p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)
        p=patch.object(app.a,'verify');self.verify=p.start();self.addCleanup(p.stop)
        import host_binding
        p=patch.object(host_binding,'cleanup',return_value='DOWN');self.down=p.start();self.addCleanup(p.stop)
    def save_owner(self,value):
        (self.d/'owner.json').write_text(json.dumps(value))
    def owner(self):return json.loads((self.d/'owner.json').read_text())
    def save_config(self,value):(self.d/'frozen.compose.json').write_text(json.dumps(value))
    def prepared(self):return app.record_prepared_binding(self.d,self.b)[2]
    def test_actual_port_record_pre_ingress_and_post_ingress_match(self):
        b=self.prepared();self.assertEqual(self.b['port'],18080);self.assertEqual(b['port'],18081)
        self.assertEqual(self.owner()['preparedExternalBinding'],b);self.assertIsNone(self.owner().get('externalBinding'))
        with self.assertRaisesRegex(RuntimeError,'EXTERNAL_PREPARED_BINDING_CHANGED'):app.ingress(self.d,self.b)
        self.rows=[]
        with patch.object(t,'firewall_check',return_value={'rules':t.firewall_rules(b)[1],'sha256':'e'*64}):
            app.ingress(self.d,b);self.assertEqual(app.load(self.d,b)[2],b)
        self.assertEqual(self.owner()['externalBinding'],b)
        self.assertEqual(self.owner()['preparedExternalBinding'],b)
    def test_expired_prepared_unbound_cleanup_uses_all_existing_guards(self):
        b=self.prepared()
        with patch.object(protocol.time,'time',return_value=20000):self.assertEqual(app.cleanup(self.d,b),'DOWN')
        self.verify.assert_called_once();self.down.assert_called_once();self.assertIsNone(self.owner().get('externalBinding'))
    def test_changed_or_missing_early_binding_refused_restored_passes(self):
        b=self.prepared()
        for field,value in [('nonce','c'*32),('cloudId','remote-test-'+'c'*12),('runId','other-run'),('port',18082),('sourceSha256','b'*64),('imageId','sha256:'+'a'*64)]:
            bad={**b,field:value};self.down.reset_mock()
            with self.subTest(field=field),self.assertRaises(RuntimeError):app.cleanup(self.d,bad)
            self.down.assert_not_called()
        bad={**b,'runId':'other-run','cloudId':'other-run-'+'c'*12}
        with self.assertRaisesRegex(RuntimeError,'EXTERNAL_PREPARED_BINDING_CHANGED'):app.cleanup(self.d,bad)
        bad=copy.deepcopy(b);bad['pair']['core']='d'*40
        with self.assertRaises(RuntimeError):app.cleanup(self.d,bad)
        m=self.owner();del m['preparedExternalBinding'];self.save_owner(m)
        with self.assertRaisesRegex(RuntimeError,'EXTERNAL_PREPARED_BINDING_CHANGED'):app.cleanup(self.d,b)
        m['preparedExternalBinding']=b;self.save_owner(m);self.assertEqual(app.cleanup(self.d,b),'DOWN')
    def test_foreign_owner_receipt_host_image_config_and_nic_refused(self):
        b=self.prepared();self.rows=[{'Config':{'Labels':{app.a.OWNER:'b'*32}}}]
        with self.assertRaises(RuntimeError):app.cleanup(self.d,b)
        self.down.assert_not_called();self.rows=[{'Config':{'Labels':{app.a.OWNER:'a'*32}}}]
        m=self.owner();m['project']='foreign-project';self.save_owner(m)
        with self.assertRaisesRegex(RuntimeError,'EXTERNAL_PREPARED_PROJECT_CHANGED'):app.cleanup(self.d,b)
        m['project']=self.m['project'];self.save_owner(m)
        bad={**self.receipt,'remoteExtensionSha256':'b'*64};(self.d/'receipt.json').write_text(json.dumps(bad))
        with self.assertRaisesRegex(RuntimeError,'REMOTE_EXTENSION_AUTHORIZATION_REQUIRED'):app.cleanup(self.d,b)
        (self.d/'receipt.json').write_text(json.dumps(self.receipt))
        with patch.object(app.a,'verify',side_effect=RuntimeError('M7_HOST_IDENTITY_CHANGED')),self.assertRaisesRegex(RuntimeError,'M7_HOST_IDENTITY_CHANGED'):app.cleanup(self.d,b)
        with patch.object(app.a,'image',return_value='sha256:'+'b'*64),self.assertRaisesRegex(RuntimeError,'EXTERNAL_APP_IDENTITY'):app.cleanup(self.d,b)
        bad=copy.deepcopy(self.config);bad['services']['nginx']['ports'][0]['host_ip']='0.0.0.0';self.save_config(bad)
        with self.assertRaisesRegex(RuntimeError,'M7_BINDING_FIXTURE_CHANGED'):app.cleanup(self.d,b)
        self.save_config(self.config)
        with patch.object(t,'local_nics',return_value=[]),self.assertRaisesRegex(RuntimeError,'REMOTE_ADDRESS_NOT_ON_APPROVED_SUT_NIC'):app.cleanup(self.d,b)
        self.down.assert_not_called();self.assertEqual(app.cleanup(self.d,b),'DOWN')
    def test_bound_mismatch_still_refused_and_expired_exact_bound_cleans(self):
        b=self.prepared();m=self.owner();m['externalBinding']={**b,'nonce':'c'*32};self.save_owner(m)
        with self.assertRaisesRegex(RuntimeError,'EXTERNAL_BINDING_CHANGED'):app.cleanup(self.d,b)
        self.down.assert_not_called();m['externalBinding']=b;self.save_owner(m)
        with patch.object(protocol.time,'time',return_value=20000):self.assertEqual(app.cleanup(self.d,b),'DOWN')

if __name__=='__main__':unittest.main()
