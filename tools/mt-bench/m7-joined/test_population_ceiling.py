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
