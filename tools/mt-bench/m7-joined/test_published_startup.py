"""Published joined startup/static selection and every serving ordinal."""
import copy, inspect
from pathlib import Path
import tempfile, unittest
from unittest.mock import patch
import adapter as a, contract as c, run_configuration as rc, static_topology as s
from test_static_topology import config

class PublishedStartup(unittest.TestCase):
    def test_published_exact_startup_receipt_retains_pending_truth(self):
        cfg=config();cfg['prepare'].update({'core-commit':s.STARTUP_STATIC_CORE,'deploy-commit':s.STARTUP_STATIC_DEPLOY,
            'tenant-readiness':'serve','primer-concurrency':16,'commissioning-slot-wal-mib':1024})
        with patch.object(a,'instrument',return_value={'sha256':'d'*64}):projection=rc.resolve(cfg,{'status':'PENDING'})
        value=projection['configuration'];proof={**projection['diagnosticReceiptTemplate'],'status':'AUTHORIZED_DIAGNOSTIC'}
        m={**value,'instrument':{'sha256':'d'*64},'runConfiguration':value,'diagnosticResources':{'profile':value['resources']['profile']}}
        self.assertEqual(value['pair'],{'core':s.STARTUP_STATIC_CORE,'deploy':s.STARTUP_STATIC_DEPLOY})
        self.assertEqual((value['tenantReadiness'],value['primerConcurrency'],value['commissioningSlotWalMiB']),('serve',16,1024))
        self.assertEqual(c.receipt_scope(m,proof,'run')['functionalAcceptance'],'PENDING')
        self.assertEqual(c.receipt_scope(m,proof,'deploy')['capacityAcceptance'],'NOT_GRANTED')
        for field,changed in [('tenantReadiness','all'),('primerConcurrency',1),('commissioningSlotWalMiB',256)]:
            bad=copy.deepcopy(m);bad['runConfiguration'][field]=changed
            with self.assertRaisesRegex(RuntimeError,'CONFIGURATION_MISMATCH'):c.receipt_scope(bad,proof,'run')
        bad=copy.deepcopy(proof);bad['sourceAcceptance']={'status':'PASS'}
        with self.assertRaisesRegex(RuntimeError,'M7_DIAGNOSTIC_ACCEPTANCE_STATUS'):c.receipt_scope(m,bad,'run')
        self.assertEqual(c.receipt_scope(m,proof,'run')['functionalAcceptance'],'PENDING')

    def test_startup_readiness_all_ordinals_red_restored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);helper=root/'core/deploy/multitenant/platform-startup.js';helper.parent.mkdir(parents=True);helper.write_text('synthetic capability')
            roles=('api','api-2','evaluator','evaluator-2','realtime','realtime-2')
            def criterion(fn):
                config={'services':{role:{'environment':{}}for role in roles}};m={};fn(config,root,m,'serve')
                self.assertEqual({config['services'][role]['environment'].get('NS_TENANT_READINESS')for role in roles},{'serve'},'ALL_SERVING_ORDINALS_MUST_BIND_READINESS')
                fn(config,root,m,verify=True);return config,m
            config,m=criterion(a.platform_startup_config)
            for role in roles:
                bad=copy.deepcopy(config);bad['services'][role]['environment']['NS_TENANT_READINESS']='all'
                with self.assertRaisesRegex(RuntimeError,'READINESS_CHANGED'):a.platform_startup_config(bad,root,m,verify=True)
            source=inspect.getsource(a.platform_startup_config)
            broken=source.replace("role in role_instances.FAMILIES or any(role.startswith(family+'-') for family in role_instances.FAMILIES)","role in role_instances.FAMILIES")
            self.assertNotEqual(source,broken);scope=dict(vars(a));exec(compile(broken,'startup_ordinal_control','exec'),scope)
            with self.assertRaisesRegex(AssertionError,'ALL_SERVING_ORDINALS_MUST_BIND_READINESS'):criterion(scope['platform_startup_config'])
            criterion(a.platform_startup_config)

if __name__=='__main__':unittest.main()
