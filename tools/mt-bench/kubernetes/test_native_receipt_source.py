"""Offline selected-image receipt plumbing, using real source factories."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import kube_adapter as k

CORE = os.environ.get('M7_NATIVE_RECEIPT_CORE')
CASE = os.environ.get('M7_NATIVE_RECEIPT_CASE')


@unittest.skipUnless(CORE and CASE, 'selected source and retained case required')
class NativeReceiptCaller(unittest.TestCase):
    def test_actual_current_candidate_refuses_missing_receipt_and_accepts_source_api_readback(self):
        case = Path(CASE)
        config = k.document(case/'pre-entry-packet/run.json')
        evaluator, realtime = [case/'runtime'/(role+'-config.private.json') for role in ('evaluator', 'realtime')]
        self.assertEqual(config['pins']['candidate']['platformVerification'], 'startup-v3')
        with self.assertRaisesRegex(k.Refused, 'COMPLETION_RECEIPT_REQUIRED'):
            k.completion_source(config, evaluator, realtime)
        script = """const fs=require('fs'),p=require('path'),root=process.argv[1],e=JSON.parse(fs.readFileSync(process.argv[2])),r=JSON.parse(fs.readFileSync(process.argv[3]));
          const binding={namespace:e.postgres.namespaces.checkpoint,lifecycleNamespace:e.trustedWorker.activity,consumer:e.consumer,generation:e.pgstream.generation,source:{system_id:'1',timeline:1,database:'nightscout_compose_test',slot:e.pgstream.slot}};
          const native=require(p.join(root,'lib/tenant-lifecycle/native-selection')).create(binding);
          const inputs={evaluator:e,realtime:r,operation:{namespace:binding.lifecycleNamespace,nativeSelection:binding},checkpoints:[{namespace:binding.namespace,consumer:binding.consumer+'-completed',digest:native.contractDigest}]};
          console.log(JSON.stringify(require(process.argv[4]).capture(root,inputs)));"""
        value = json.loads(subprocess.check_output(['node', '-e', script, CORE, evaluator, realtime,
                                                    k.M7/'native-receipt-source.cjs'], timeout=10))
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp)/'receipt.json'
            k.write(receipt, value)
            result = k.completion_source(config, evaluator, realtime, native_receipt=receipt)
            self.assertEqual(result['native']['receipt'], value)
            self.assertEqual(result['binding']['nativeConfigurationSha256'], k.hashed(result['native']))
            value['evaluatorConfigSha256'] = '0'*64
            k.write(receipt, value)
            with self.assertRaisesRegex(k.Refused, 'COMPLETION_SOURCE_REFUSED'):
                k.completion_source(config, evaluator, realtime, native_receipt=receipt)


if __name__ == '__main__':
    unittest.main()
