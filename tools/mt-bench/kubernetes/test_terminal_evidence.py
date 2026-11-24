import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import execute
import kube_adapter as k
from workloads.reduce import reduce_stage


TENANT = '11111111-1111-4111-8111-111111111111'
RUNTIME = '22222222-2222-4222-8222-222222222222'


def page(ready):
    row = {'tenant':TENANT, 'admitted':True, 'ready':ready, 'code':None if ready else 'SYNTHETIC_REFUSAL',
           'evaluation':{'alert':None}, 'dueAt':None, 'dueReason':None, 'cycles':1,
           'progress':{'generation':1,'completedAcquisitions':1,'completedTimeCycles':0,
                       'failedCompletions':0,'lastCompletedAgeMs':1}, 'omitted':{'private':'raw control'}}
    return json.dumps({'selected':[TENANT], 'selfMode':'single', 'selfOrdinal':0,
        'view':{'tenantCount':1,'runtimeId':RUNTIME,'configured':{'ordinal':0,'mode':'single'},
                'kind':'evaluator','gate':{'eligible':True,'reason':None},'tenants':[row]}}).encode()+b'\n'


class TerminalEvidence(unittest.TestCase):
    def trial(self, *, ready=False, storage=None, missing_response=False):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch)
            config = {'roles':{}, 'pins':{'pair':{'core':'source'}},
                      'deadlines':{'workUntil':'2000-01-01T00:00:00Z' if storage=='expired' else '2099-01-01T00:00:00Z'}}
            point = {'namespace':{'uid':'owned-ns'},'pods':{
                     'eval-pod':{'uid':'eval-uid','containers':{'evaluator':{'containerID':'containerd://owned'}}}}}
            payload = page(ready)
            client = Mock()
            client.call.return_value = payload
            if missing_response:
                client.call.side_effect = k.Refused('K8S_OBSERVATION_LOST','UNMEASURED')

            def observe(*args):
                if storage=='identity' and client.call.called:
                    raise k.Refused('K8S_NAMESPACE_UID_CHANGED','FAIL')
                return point

            def read_postgres(*args, timeout=None):
                # The run-marker census reads whole tables: it carries the table read limit.
                self.assertGreater(timeout, 20)
                if not missing_response:
                    self.assertEqual((path/'progress-after.private.jsonl').read_bytes(),payload)
                self.assertIn("='synthetic-run'",args[-1])
                if storage=='denied':
                    raise k.Refused('K8S_OBSERVATION_LOST','UNMEASURED')
                tenant = TENANT if storage!='foreign-count' else RUNTIME
                return f'{tenant}\tentries\t3\n'

            with patch.object(k,'active_baseline',return_value=point),patch.object(k,'observe',side_effect=observe), \
                 patch.object(k,'selected_pod',side_effect=lambda *a:('eval-pod','evaluator') if a[-1]=='evaluator' else ('pg-pod','postgres')), \
                 patch.object(execute,'roster',return_value=[{'id':TENANT}]),patch.object(k,'postgres_read',side_effect=read_postgres) as sql:
                if ready:
                    execute.terminal_progress(path,path,config,{},client,'synthetic-run',True,'owned-ns')
                    self.assertTrue((path/'progress-after.json').is_file())
                    self.assertFalse((path/'storage-readback.json').exists())
                    sql.assert_not_called()
                else:
                    code = ('K8S_OBSERVATION_LOST' if missing_response else 'K8S_WORK_DEADLINE' if storage=='expired'
                            else 'K8S_NAMESPACE_UID_CHANGED' if storage=='identity' else 'M7_EVALUATOR_PROGRESS_ERROR')
                    # Progress is a figure: the refusal is recorded and the run goes on.
                    execute.terminal_progress(path,path,config,{},client,'synthetic-run',True,'owned-ns')
                    failure = k.document(path/'progress-after-failure.json')
                    captured = not missing_response and storage!='expired'
                    self.assertEqual(failure['responseRetained'],captured)
                    self.assertEqual(failure['code'],code)
                    self.assertFalse((path/'progress-after.json').exists())
                    self.assertFalse((path/'storage-readback.json').exists())
                    execute.capture_storage(path,path,config,{},client,'synthetic-run','owned-ns')
                    if captured:
                        diagnostic = failure.get('diagnostic',failure.get('sourceRefusal',{}).get('diagnostic'))
                        self.assertEqual(diagnostic['failedRow']['code'],'SYNTHETIC_REFUSAL')
                        self.assertNotIn('omitted',diagnostic['failedRow'])
                    storage_result = k.document(path/'storage-readback.json')
                    if storage is None:
                        self.assertEqual(storage_result['verdict'],'OBSERVED')
                        self.assertEqual(k.document(path/'stored-counts.json'),{TENANT:{'entries':3}})
                        (path/'runid').write_text('synthetic-run\n')
                        k.write(path/'stored-counts.json',{TENANT:{'entries':4}})
                        # A changed counts file is not re-proved by hash; the reduction still runs.
                        reduced = reduce_stage(path,path/'reduction')
                        self.assertIn('product', reduced)
                    else:
                        self.assertEqual(storage_result['verdict'],'UNMEASURED')
                        self.assertEqual(storage_result['code'],{'expired':'K8S_WORK_DEADLINE', 'denied':'K8S_OBSERVATION_LOST',
                            'identity':'K8S_NAMESPACE_UID_CHANGED','foreign-count':'K8S_STORAGE_ROSTER_CHANGED'}[storage])
                        self.assertFalse((path/'stored-counts.json').exists())
                        if storage in ('expired','identity'):
                            sql.assert_not_called()
            if not missing_response and storage!='expired':
                raw = path/'progress-after.private.jsonl'
                response = k.document(path/'progress-after-response.json')
                self.assertEqual(raw.read_bytes(),payload)
                self.assertEqual(raw.stat().st_mode & 0o777,0o600)
                self.assertEqual((response['sha256'],response['bytes'],response['podUid']), (k.digest(raw),len(payload),'eval-uid'))

    def test_real_decode_failure_retains_raw_and_independent_storage(self):
        self.trial()

    def test_healthy_terminal_decode(self):
        self.trial(ready=True)

    def test_storage_control_cannot_promote_fail_or_query_after_expiry_and_identity_loss(self):
        for reason in ('expired','denied','identity','foreign-count'):
            with self.subTest(reason=reason):
                self.trial(storage=reason)

    def test_unavailable_raw_response_is_explicit(self):
        self.trial(missing_response=True)
