import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import adapter
import population_ceiling as p
from test_run_configuration import config, packet


class PopulationCeiling(unittest.TestCase):
    def test_chunk_scope_is_exposed_without_rewriting_the_independent_default(self):
        partial=p.commissioning(10001)
        self.assertEqual(partial['effective']['maxTenants'],10000)
        self.assertEqual((partial['coverage'],partial['freshSeedBeyondChunk']),('PARTIAL_CHUNK_BUDGET',1))
        complete=p.commissioning(10001,{'maxTenants':10001})
        self.assertEqual((complete['coverage'],complete['freshSeedBeyondChunk']),('FULL_CHUNK_BUDGET',0))
        self.assertEqual(complete['actualDataResult'],'UNMEASURED')

    def test_selection_and_receipt_are_optional_exact_and_bound(self):
        self.assertIsNone(p.from_profile({'population':{'provisionedTenants':2}},adapter.primer_need))
        for value in (2,10001,p.workload_inputs.MAX_ARRAY_LENGTH):
            self.assertEqual(p.selection(value,2,adapter.primer_need),value)
        for value in (0,-1,True,1.5,2**32,'10001'):
            with self.assertRaisesRegex(RuntimeError,'POPULATION_CEILING_INVALID'):
                p.selection(value,2,adapter.primer_need)
        with self.assertRaisesRegex(RuntimeError,'POPULATION_CEILING_INVALID'):
            p.from_profile({'population':{'provisionedTenants':2,'maxTenants':None}},adapter.primer_need)
        with self.assertRaisesRegex(RuntimeError,'POPULATION_SEED_OVER_CEILING'):
            p.selection(2,3,adapter.primer_need)
        with self.assertRaisesRegex(RuntimeError,'POPULATION_SEED_UUID_UNREPRESENTABLE'):
            p.selection(2**32-1,p.MAX_SYNTHETIC_TENANTS+1,adapter.primer_need)
        selected=config();selected['prepare']['population-ceiling']=10001
        with patch.object(adapter,'instrument',return_value={'sha256':'d'*64}):
            manifest,receipt=packet(selected)
        self.assertEqual(manifest[p.FIELD],10001)
        from contract import discovery_authorization
        discovery_authorization(manifest,receipt)
        with self.assertRaisesRegex(RuntimeError,'DIAGNOSTIC_CONFIGURATION_MISMATCH'):
            discovery_authorization({**manifest,p.FIELD:10002},receipt)
        discovery_authorization(manifest,receipt)

    def test_explicit_lower_and_higher_refuse_old_source_before_image_or_other_effects(self):
        for value in (5,10001):
            args=SimpleNamespace(profile='pgstream-sample',run_purpose='discovery',tenants=2,
                primer_concurrency=1,population_ceiling=value,deploy_repo='/synthetic/deploy',deploy_commit='f'*40)
            with patch.object(adapter,'command',return_value=b'old source without capability') as command,patch.object(adapter,'image') as image:
                with self.assertRaisesRegex(RuntimeError,'POPULATION_SOURCE_UNSUPPORTED'):
                    adapter.prepare_image_inputs(args)
                image.assert_not_called()
                self.assertTrue(all(call.args[0][:3]==['git','-C',args.deploy_repo] for call in command.call_args_list))

    def test_image_constructor_checks_effective_values_and_all_source_hashes(self):
        files={name:(p.DECLARATION if name=='population-ceiling.js' else name.encode()) for name in p.SOURCE_FILES}
        hashes=p.source_hashes(files,adapter.primer_need)
        good={'protocol':p.PROTOCOL,p.FIELD:5,'seedCount':2,'sourceFilesSha256':hashes,'overSeedRefused':True,'protocolRefused':True,
              'effective':{role:5 for role in ('api','evaluator','realtime','primer')}}
        for wrong in ({**good,p.FIELD:10000},{**good,'effective':{**good['effective'],'realtime':10000}},
                      {**good,'sourceFilesSha256':{**hashes,'config.js':'0'*64}}):
            with patch.object(p.primer_options,'probe_constructor',return_value=wrong):
                with self.assertRaisesRegex(RuntimeError,'POPULATION_IMAGE_SOURCE_CHANGED'):
                    p.probe_image(None,'sha256:'+'a'*64,files,5,adapter.primer_need)
        with patch.object(p.primer_options,'probe_constructor',return_value=good):
            self.assertEqual(p.probe_image(None,'sha256:'+'a'*64,files,5,adapter.primer_need),good)

    def test_population_constructor_precedes_the_fixture_resource_driver(self):
        args=SimpleNamespace(profile='pgstream-sample',run_purpose='discovery',tenants=2,population_ceiling=10001,
            primer_concurrency=1,deploy_repo='/synthetic/deploy',deploy_commit='f'*40,generator_dependencies='/synthetic/deps')
        class DriverArmed(Exception):pass
        with patch.object(adapter,'selected_resources_profile',return_value='selected'),patch.object(adapter,'commit'), \
             patch.object(adapter,'prepare_image_inputs',return_value={'populationSource':{p.FIELD:10001}}) as preflight, \
             patch.object(adapter.diagnostic_resources,'configure',side_effect=DriverArmed):
            with self.assertRaises(DriverArmed):adapter.prepare(args)
        preflight.assert_called_once_with(args)

    def test_compose_projection_and_private_effective_readback_fail_then_restore(self):
        compose={'services':{role:{'command':['node',role]} for role in ('api','evaluator','realtime','bootstrap')}}
        unchanged=copy.deepcopy(compose);p.project_compose(compose,None,adapter.primer_need)
        self.assertEqual(compose,unchanged)
        p.project_compose(compose,5,adapter.primer_need)
        p.project_compose(compose,5,adapter.primer_need,verify=True)
        with self.assertRaisesRegex(RuntimeError,'POPULATION_CONFIGURATION_CHANGED'):
            p.project_compose(compose,6,adapter.primer_need,verify=True)
        with tempfile.TemporaryDirectory() as temporary:
            d=Path(temporary);adapter.write(d/'frozen.compose.json',compose)
            docs={'api':{'socketForwarding':{'maxTenants':5}},'evaluator':{'maxTenants':5},'realtime':{'maxTenants':5},
                  'primer':{p.FIELD:5,p.PROTOCOL_FIELD:p.PROTOCOL,'seed':[{},{}]}}
            for role,document in docs.items():adapter.write(d/'state'/role/'config.json',document)
            manifest={p.FIELD:5,'tenants':2}
            expected=p.local_readback(d,manifest,adapter.primer_need)
            self.assertEqual(expected['effective'],{role:5 for role in docs})
            for role in docs:
                path=d/'state'/role/'config.json';original=adapter.document(path)
                wrong=copy.deepcopy(original)
                if role=='api':wrong['socketForwarding']['maxTenants']=10000
                elif role=='primer':wrong[p.FIELD]=10000
                else:wrong['maxTenants']=10000
                adapter.write(path,wrong)
                with self.assertRaisesRegex(RuntimeError,'POPULATION_(ROLE|PRIMER)_CHANGED'):
                    p.local_readback(d,manifest,adapter.primer_need)
                adapter.write(path,original)
            self.assertEqual(p.local_readback(d,manifest,adapter.primer_need),expected)


if __name__=='__main__':unittest.main()
