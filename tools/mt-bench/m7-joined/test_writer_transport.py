"""Writer transport uses the public discovery configuration and the actual service roster."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import adapter as a
import contract
import run_configuration as rc
import runner
import stream_topology as transport
from test_static_topology import config as cdc_config, manifest as cdc_manifest


def writer(value):
    return {**value, 'inputTransport':'writer-driven'}


class WriterTransport(unittest.TestCase):
    def test_plan_receipt_and_both_transport_projections(self):
        with patch.object(a, 'instrument', return_value={'sha256':'d'*64}):
            cfg = cdc_config()
            cfg['prepare']['input-transport'] = 'writer-driven'
            plan = runner.tier_plan(cfg)['effective']
            resolved = rc.resolve(cfg)
            self.assertEqual(plan['inputTransport'], 'writer-driven')
            self.assertNotIn('pgstreamTopology', plan)
            self.assertEqual(plan, rc.from_manifest({**plan, 'instrument':{'sha256':plan['instrument']}}))
            receipt = {**resolved['diagnosticReceiptTemplate'], 'status':'AUTHORIZED_DIAGNOSTIC'}
            m = {**plan, 'instrument':{'sha256':plan['instrument']}, 'runConfiguration':plan}
            contract.receipt_scope(m,receipt,'deploy')
            m.pop('inputTransport')
            with self.assertRaises(RuntimeError):
                contract.receipt_scope(m,receipt,'deploy')
            # The retired stream options are no longer accepted.
            for field,value in [('pgstream-topology','colocated-v1'), ('pgstream-topology','external-service-v1'),
                                ('commissioning-slot-wal-mib',256), ('pgstream-notifier-ack-timeout-ms',2000),
                                ('input-transport','pgstream')]:
                with self.subTest(field=field,value=value),self.assertRaises((RuntimeError, SystemExit)):
                    rc.resolve({**cfg, 'prepare':{**cfg['prepare'],field:value}})
            for retired in ({'pgstreamTopology':'external-service-v1'}, {'pgstreamNotifierAckTimeoutMs':2000},
                            {'commissioningSlotWalMiB':256}, {'inputTransport':'pgstream'}):
                with self.subTest(retired=retired),self.assertRaisesRegex(RuntimeError,'WRITER_CDC_OPTION_CONFLICT|M7_INPUT_TRANSPORT'):
                    transport.selection({**plan, **retired})

    def test_writer_process_expectation_and_snapshot_identity(self):
        m = writer(cdc_manifest())
        m['servingInstances'] = {name:{'role':role} for name,role in
                                  [('api','api'),('api-2','api'),('realtime','realtime'),('realtime-2','realtime'),
                                   ('evaluator','evaluator'),('evaluator-2','evaluator')]}
        expected = transport.expected_processes(m)
        self.assertEqual(expected, {name:('node',) for name in m['servingInstances']})
        snapshots = {name:{'hostProcesses':{'1':{'component':'node'}}} for name in expected}
        transport.readable_processes(snapshots,m)
        snapshots['evaluator']['hostProcesses']['2'] = {'component':'pgstream'}
        with self.assertRaisesRegex(RuntimeError,'UNEXPECTED_PGSTREAM'):
            transport.readable_processes(snapshots,m)
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory)/'deployment.env'
            env.write_text('NS_API_REPLICAS=2\nNS_REALTIME_WORKERS=2\nNS_EVALUATOR_WORKERS=2\nNS_PGSTREAM=1\n')
            with self.assertRaisesRegex(RuntimeError,'INPUT_TRANSPORT_CHANGED'):
                transport.require_snapshot(directory,m)
            env.write_text('NS_API_REPLICAS=2\nNS_REALTIME_WORKERS=2\nNS_EVALUATOR_WORKERS=2\n')
            transport.require_snapshot(directory,m)
            env.write_text(env.read_text()+'NS_INPUT_TRANSPORT=writer-driven\n')
            transport.require_snapshot(directory,m)
            with self.assertRaisesRegex(RuntimeError,'TOPOLOGY_CHANGED'):
                transport.require_snapshot(directory,{**m,'replicas':1})
            with self.assertRaisesRegex(RuntimeError,'INPUT_TRANSPORT'):
                transport.require_snapshot(directory,{k:v for k,v in m.items() if k!='inputTransport'})
