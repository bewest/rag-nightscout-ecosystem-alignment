"""Experimental candidate admission; no provider or runtime action is performed."""
import unittest
raise unittest.SkipTest('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cell,protocol,transport as t
from test_parameters import extended,prep_args

class PerformanceSource(unittest.TestCase):
    def selected(self):
        b=extended(1000,180,310,1)
        b.update(pair={'core':t.PERFORMANCE_CORE,'deploy':t.PERFORMANCE_DEPLOY},imageId=t.PERFORMANCE_APP)
        return b

    def manifest(self,b):
        return dict(pair=b['pair'],imageId=b['imageId'],postgresImageId=t.POSTGRES,
                    profile='pgstream-sample',runPurpose='discovery',tenants=1000,replicas=1,
                    cadence=b['workload']['cadence'],primerConcurrency=1,completionContract='evaluator-work-v2')

    def test_exact_source_workload_and_manifest(self):
        b=self.selected();protocol.binding(b);m=self.manifest(b);t.cell_contract(m,b)
        for edit in (lambda v:v['pair'].update(core=t.MINIMUM_CORE),lambda v:v['pair'].update(deploy=t.PRIMER_DEPLOY),lambda v:v.update(imageId=t.MINIMUM_APP)):
            bad=copy.deepcopy(b);edit(bad)
            with self.assertRaisesRegex(RuntimeError,'QUALIFIED_SOURCE'):protocol.binding(bad)
        for edit in (lambda v:v.update(tenants=3000),lambda v:v['workload']['cadence'].update(offeredRps=240),lambda v:v['workload']['cadence'].update(loadSeconds=600),lambda v:v['workload'].update(primerConcurrency=2),lambda v:v.pop('workload')):
            bad=copy.deepcopy(b);edit(bad)
            with self.assertRaises(RuntimeError):protocol.binding(bad)
        for value in ('evaluator-work-v1',None):
            with self.assertRaisesRegex(RuntimeError,'COMPLETION_V2_REQUIRED'):t.cell_contract({**m,'completionContract':value},b)
        for key,value in (('imageId',t.MINIMUM_APP),('tenants',3000),('cadence',t.CADENCE),('primerConcurrency',2)):
            with self.assertRaises(RuntimeError):t.cell_contract({**m,key:value},b)
        t.cell_contract(m,b)

    def test_actual_prepare_v2_and_receipt_before_effects(self):
        b=self.selected()
        with tempfile.TemporaryDirectory() as tmp:
            args=prep_args(b,tmp)
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare') as prepare,patch.object(cell.app,'record_prepared_binding'):
                cell.main();parsed=prepare.call_args.args[0]
                self.assertEqual((parsed.core_commit,parsed.deploy_commit,parsed.image),(t.PERFORMANCE_CORE,t.PERFORMANCE_DEPLOY,t.PERFORMANCE_APP))
                self.assertEqual((parsed.tenants,parsed.offered_rps,parsed.load_seconds,parsed.primer_concurrency),(1000,180,310,1))
            old=args[args.index('--completion-contract')+1];args[args.index('--completion-contract')+1]='evaluator-work-v1'
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare') as prepare:
                with self.assertRaisesRegex(RuntimeError,'COMPLETION_V2_REQUIRED'):cell.main()
                prepare.assert_not_called()
            args[args.index('--completion-contract')+1]=old
            file=Path(tmp)/'receipt.json';receipt=json.loads(file.read_text());receipt['remoteWorkload']['cadence']['offeredRps']=240;file.write_text(json.dumps(receipt))
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare') as prepare:
                with self.assertRaisesRegex(RuntimeError,'AUTHORIZATION_REQUIRED'):cell.main()
                prepare.assert_not_called()

if __name__=='__main__':unittest.main()
