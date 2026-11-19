import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import lifecycle_config as l
import frozen as f

class Lifecycle(unittest.TestCase):
    def test_bound_inputs_refuse_allocation_preflight_and_stages_then_restore(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp);case=p/'any-tiny-case';case.mkdir();(case/'stages').mkdir()
            for d in ('binding','tools','snapshot','core'):(p/d).mkdir()
            def put(path,v):path.write_text(json.dumps(v));return path
            for n in ('k6','ro','observer','tools/kubectl'):(p/n).write_text('synthetic')
            files={n:put(case/(n+'.json'),{}) for n in ('environment','intent','inventory','render','preflight')}
            e=dict(runId=case.name,namespace='ns-synth-any',tenantCount=500,sourceCommit='1'*40,
                   workDeadlineSeconds=7200,cleanupDeadlineSeconds=7800,provisionDeadlineSeconds=3600)
            put(files['environment'],e)
            intent={'profile':{'population':{'provisionedTenants':500},'phases':{'cohortReadySeconds':900,
                                'startupWindows':{'kubernetes':{'workloadReadySeconds':600,'dataPrimerSeconds':7200}}},
                              'proposedEnvelope':{'nativeLimits':{'millicpus':8000,'memoryBytes':8*1024**3}}}}
            put(files['intent'],intent)
            put(files['preflight'],{'commissioning':'PREFLIGHT_ONLY','experiment':{'renderSha256':l.sha(files['render'])}})
            for stage in l.STAGES:put(case/'stages'/(stage+'.json'),{'items':[]})
            put(p/'binding/binding.json',{'files':{}})
            template=put(p/'template.json',{a:{'hostId':'same','resources':{'millicpus':1000,'memoryBytes':1024**3}} for a in ('driver','observer')})
            delivery=put(p/'delivery.json',{});absence=put(p/'absence.json',{'verifiedAt':'synthetic'})
            cfg=dict(version=1,caseDirectory=str(case),instrumentDirectory=str(Path(l.__file__).resolve().parents[3]),
                     bindingDirectory=str(p/'binding'),toolsDirectory=str(p/'tools'),snapshotDirectory=str(p/'snapshot'),
                     coreRepository=str(p/'core'),k6=str(p/'k6'),readonlyGuard=str(p/'ro'),observerScript=str(p/'observer'),
                     nativeLimits={'millicpus':4000,'memoryBytes':4*1024**3},primerConcurrency=8,
                     runTemplate=l.ref(template),delivery=l.ref(delivery),cacheAbsence=l.ref(absence))
            path=put(p/'control.json',cfg)
            def external(argv,**kw):return '1'*40 if argv[0]=='git' else json.dumps({'sha256':'2'*64}).encode()
            with patch.object(l.subprocess,'check_output',side_effect=external), patch('experiment.workload'):
                frozen=l.fixture_config(path,capture=True);put(path,frozen);self.assertEqual(l.fixture_config(path),frozen)
                windows=frozen['startupWindowPreflight']
                self.assertEqual(windows['authoredFields'],['cohortReadySeconds','dataPrimerSeconds','workloadReadySeconds'])
                self.assertEqual(windows['selectedSeconds']['dataPrimerSeconds'],7200)
                self.assertEqual(windows['selectedSeconds']['execSeconds'],35)
                def refusal(code,mutate,restore):
                    mutate()
                    with self.assertRaisesRegex(ValueError,code):l.fixture_config(path)
                    restore();self.assertEqual(l.fixture_config(path),frozen)
                    print('RED_RESTORED',code)
                changed=copy.deepcopy(intent);changed['profile']['phases']['cohortReadySeconds']=899
                refusal('STARTUP_PREFLIGHT_CHANGED',lambda:put(files['intent'],changed),lambda:put(files['intent'],intent))
                refusal('RESOURCE_ACCOUNTING_MISMATCH',lambda:put(files['environment'],{**e,'resourceAccounting':'requests-v1'}),lambda:put(files['environment'],e))
                wrong=copy.deepcopy(frozen);wrong['startupWindowPreflight']['selectedSeconds']['dataPrimerSeconds']=7199
                refusal('STARTUP_PREFLIGHT_CHANGED',lambda:put(path,wrong),lambda:put(path,frozen))
                stage=case/'stages/stores.json'
                refusal('STAGE_NAMESPACE',lambda:put(stage,{'items':[dict(kind='ConfigMap',metadata={'namespace':'foreign'})]}),lambda:put(stage,{'items':[]}))
                options={'concurrency':64,'maxTenants':20000}
                intent['profile']['phases']['primerOptions']=options
                put(files['intent'],intent)
                contract=dict(primerOptions=options,primerOptionProtocol='positive-safe-integer-v1')
                asset=p/'binding/bindings/kubernetes/assets/source-contract.json'
                asset.parent.mkdir(parents=True)
                bound_manifest=p/'binding/binding.json'
                def materialize(value):
                    put(asset,value)
                    put(bound_manifest,{'files':{'assets/source-contract.json':l.sha(asset)},'sourceContractSha256':l.sha(asset)})
                    put(case/'stages/foundation.json',{'items':[dict(kind='ConfigMap',metadata={'name':'provision-scripts','namespace':e['namespace']},
                                                                    data={'source-contract.json':asset.read_text()})]})
                materialize(contract)
                cfg.pop('primerConcurrency')
                put(path,cfg)
                selected=l.fixture_config(path,capture=True)
                self.assertEqual(selected['primerOptionsPreflight']['selection'],options)
                put(path,{**selected,'primerConcurrency':33})
                with self.assertRaisesRegex(ValueError,'PRIMER_OPTIONS_CHANGED'):l.fixture_config(path)
                put(path,selected)
                materialize({'primerOptions':options})
                with self.assertRaisesRegex(ValueError,'PRIMER_OPTION_SOURCE_UNSUPPORTED'):l.fixture_config(path)
                materialize(contract)
                self.assertEqual(l.fixture_config(path),selected)
                intent['profile']['population']['maxTenants']=10001
                e['populationCeiling']=10001
                put(files['intent'],intent);put(files['environment'],e)
                contract.update(populationCeiling=10001,populationCeilingProtocol='population-ceiling-v1')
                materialize(contract)
                bound=l.fixture_config(path,capture=True);put(path,bound)
                self.assertEqual(bound['populationCeilingPreflight']['selection'],10001)
                self.assertEqual(l.fixture_config(path),bound)
                materialize({**contract,'populationCeiling':500})
                with self.assertRaisesRegex(ValueError,'POPULATION_BINDING_CHANGED'):l.fixture_config(path)
                materialize(contract)
                self.assertEqual(l.fixture_config(path),bound)


class BootstrapReadback(unittest.TestCase):
    def test_declared_overlay_remains_mandatory_and_undeclared_overlay_refuses(self):
        native = {'sourceAcceptance': 'PENDING'}
        overlay = {**native, 'imageSourceAcceptance': 'PASS',
                   'runtimeBootstrapHelper': {'sha256': f.digest(b'synthetic bootstrap')}}
        row = {'kind': 'ConfigMap', 'name': f.HELPER_MAP, 'uid': 'owned'}
        actual = {'immutable': True, 'data': {'bootstrap.js': 'synthetic bootstrap'},
                  'metadata': {'uid': 'owned', 'resourceVersion': '1', 'namespace': 'scope',
                               'labels': {'nightscout.org/run-id': 'run'}}}
        self.assertEqual(f.bootstrap_readback(native, None, [], 'scope', 'run'),
                         {'mode': 'embedded-image', 'effectiveInstanceAcceptance': 'PENDING'})
        with self.assertRaisesRegex(f.Refused, 'BOOTSTRAP_HELPER_UNDECLARED'):
            f.bootstrap_readback(native, actual, [row], 'scope', 'run')
        with self.assertRaisesRegex(f.Refused, 'BOOTSTRAP_HELPER_MISSING'):
            f.bootstrap_readback(overlay, None, [], 'scope', 'run')
        with self.assertRaisesRegex(f.Refused, 'BOOTSTRAP_HELPER_OWNERSHIP'):
            f.bootstrap_readback(overlay, actual, [{**row, 'uid': 'foreign'}], 'scope', 'run')
        with self.assertRaisesRegex(f.Refused, 'BOOTSTRAP_HELPER_CHANGED'):
            f.bootstrap_readback(overlay, {**actual, 'data': {'bootstrap.js': 'wrong'}},
                                 [row], 'scope', 'run')
        result = f.bootstrap_readback(overlay, actual, [row], 'scope', 'run')
        self.assertEqual(result['mode'], 'diagnostic-overlay')
        self.assertEqual(result['effectiveInstanceAcceptance'], 'PENDING')
        self.assertEqual(result['imageSourceAcceptance'], 'PASS')


if __name__=='__main__':unittest.main()
