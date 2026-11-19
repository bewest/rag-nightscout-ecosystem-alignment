"""Run the source-bound receipt contract checks on configured shipping trees."""
import subprocess
import unittest
import json
import os
import tempfile
from unittest import mock
from pathlib import Path
import adapter as a


class NativeReceiptSource(unittest.TestCase):
    def test_actual_node_contracts(self):
        subprocess.run(['node', str(Path(__file__).with_name('native-receipt-source.test.cjs'))],
                       check=True, capture_output=True, timeout=20)

    @unittest.skipUnless(os.environ.get('M7_NATIVE_RECEIPT_CORE'), 'selected shipping source required')
    def test_actual_compose_context_caller_uses_selected_image_api(self):
        core = os.environ['M7_NATIVE_RECEIPT_CORE']
        code = """const d=process.argv[1],root=process.argv[2],f=require(d+'/native-observation-fixture.cjs');
          const e=f.evaluator,b={namespace:e.postgres.namespaces.checkpoint,lifecycleNamespace:e.trustedWorker.activity,consumer:e.consumer,generation:e.pgstream.generation,source:f.row.native.actualSource};
          const n=require(root+'/lib/tenant-lifecycle/native-selection').create(b);
          console.log(JSON.stringify({evaluator:e,realtime:f.realtime,operation:{namespace:b.lifecycleNamespace,nativeSelection:b},checkpoints:[{namespace:b.namespace,consumer:b.consumer+'-completed',digest:n.contractDigest}],binding:f.binding}));"""
        inputs = json.loads(subprocess.check_output(['node', '-e', code, a.HERE, core], timeout=10))
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for role in ('evaluator', 'realtime'):
                (d/'state'/role).mkdir(parents=True)
                a.write(d/'state'/role/'config.json', inputs[role])
                a.write(d/'state'/role/'env.json', {})
            (d/'state/admin').mkdir()
            a.write(d/'state/evaluator/operation.json', inputs['operation'])
            a.write(d/'state/admin/config.json', {'provisioning': {'checkpoints':inputs['checkpoints']}})
            a.write(d/'frozen.compose.json', {'services': {role: {'command':['nightscout','multitenant',role]} for role in ('evaluator','realtime')}})
            calls = []
            def compose(directory, *args, input=None, **kwargs):
                if 'module.exports.capture' in input.decode():
                    calls.append(args)
                    script = input.decode().replace("'/opt/app'", json.dumps(core))
                    return subprocess.check_output(['node', '-'], input=script.encode(), timeout=10).decode()
                return json.dumps({'privateConfig': {'sha256':a.digest(d/'state'/args[4]/'config.json')}})
            binding = inputs['binding']
            manifest = {'pair':binding['pair'], 'imageId':binding['imageId'],
                        'instrument':{'sha256':binding['instrument']}, 'completionContract':binding['kind']}
            with mock.patch.object(a,'compose',side_effect=compose), \
                    mock.patch.object(a.sql_attribution,'identities',return_value={'evaluator':['synthetic_evaluator']}), \
                    mock.patch.object(a,'psql',return_value='synthetic_evaluator\n'):
                result, _ = a.sample_context(d,manifest)
            self.assertEqual(result['native']['receipt']['contractDigest'],inputs['checkpoints'][0]['digest'])
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][4], 'evaluator')
