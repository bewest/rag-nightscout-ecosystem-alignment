"""Minimum source admission at the actual binding, parser and manifest boundaries."""
import copy,sys,tempfile,unittest
from unittest.mock import patch
import cell,protocol,transport as t
from test_parameters import extended,prep_args

class MinimumSource(unittest.TestCase):
    def selected(self):
        b=extended(1000,180,310,2)
        b.update(pair={'core':t.MINIMUM_CORE,'deploy':t.PRIMER_DEPLOY},imageId=t.MINIMUM_APP)
        return b
    def test_exact_pair_and_manifest_v2(self):
        b=self.selected();protocol.binding(b)
        m=dict(pair=b['pair'],imageId=b['imageId'],postgresImageId=t.POSTGRES,profile='pgstream-sample',runPurpose='discovery',tenants=1000,replicas=1,cadence=b['workload']['cadence'],primerConcurrency=2,completionContract='evaluator-work-v2')
        t.cell_contract(m,b)
        for edit in (lambda v:v['pair'].update(core=t.REPAIRED_CORE),lambda v:v['pair'].update(deploy=t.DEPLOY),lambda v:v.update(imageId=t.REPAIRED_APP)):
            bad=copy.deepcopy(b);edit(bad)
            with self.assertRaisesRegex(RuntimeError,'QUALIFIED_SOURCE'):protocol.binding(bad)
        for value in ('evaluator-work-v1',None):
            with self.assertRaisesRegex(RuntimeError,'COMPLETION_V2_REQUIRED'):t.cell_contract({**m,'completionContract':value},b)
    def test_actual_prepare_v1_refuses_before_effects_and_v2_restores(self):
        b=self.selected()
        with tempfile.TemporaryDirectory() as tmp:
            args=prep_args(b,tmp)
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare') as prepare,patch.object(cell.app,'record_prepared_binding'):
                cell.main();self.assertEqual(prepare.call_args.args[0].core_commit,t.MINIMUM_CORE)
            args[args.index('--completion-contract')+1]='evaluator-work-v1'
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare') as prepare:
                with self.assertRaisesRegex(RuntimeError,'COMPLETION_V2_REQUIRED'):cell.main()
                prepare.assert_not_called()

if __name__=='__main__':unittest.main()
