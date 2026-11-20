"""Verify the host invocation preserves its original Pod, finite Job cutoff and private DATA projection."""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import primer


class PrimeEntry(unittest.TestCase):
    def test_fresh_cli_keeps_kubernetes_roster_separate_from_m7_adapter(self):
        here = Path(__file__).resolve().parent
        code = """
import sys
from pathlib import Path
site = Path(sys.argv[1])
sys.path[:0] = [str(site.parent/'m7-joined'), str(site)]
import adapter as m7
import primer
import experiment
assert Path(m7.__file__).parent.name == 'm7-joined'
assert Path(primer.k.__file__).parent == site
assert primer.k is experiment.k is experiment.execute.k
try:
    primer.require_roster(Path('/synthetic/packet'), {'primerOutput': None}, {})
except primer.k.Refused as error:
    assert str(error) == 'K8S_PRIMER_RECEIPT_REQUIRED'
else:
    raise AssertionError('Missing primer receipt did not fail')
"""
        subprocess.run([sys.executable, '-B', '-c', code, str(here)], check=True, capture_output=True)
        for entrypoint in ('primer.py', 'experiment.py', 'adapter.py'):
            subprocess.run([sys.executable, '-B', str(here/entrypoint), '--help'], check=True, capture_output=True)

    def test_disk_client_state_readback_preserves_bounded_legacy_volume(self):
        def job(volume):
            return {'spec':{'template':{'spec':{'volumes':[{'name':'client-state','emptyDir':volume}]}}}}
        for value in ({'sizeLimit':'16Mi'}, {}, {'medium':'', 'sizeLimit':'16Mi'}):
            got=primer.client_state_volume(job(value),job(value),'/run/ns-client')
            self.assertEqual((got['medium'],got['sizeLimit']),('disk',value.get('sizeLimit')))
        for changed in ({'medium':'Memory'},{'sizeLimit':'1Mi'}):
            with self.assertRaisesRegex(primer.k.Refused,'PRIMER_STORAGE_READBACK_CHANGED'):
                primer.client_state_volume(job({}),job(changed),'/run/ns-client')

    def test_owned_exec_and_private_export(self):
        k = primer.k
        utc = datetime.now(timezone.utc)
        stamp = lambda date: date.isoformat().replace('+00:00','Z')
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            c = dict(context='test', namespace='owned-ns', runId='owned-run', roles={'api':{}},
                     kubectl='/usr/bin/kubectl', tenants=1, pins={'candidate':{}},
                     deadlines={'workUntil':stamp(utc+timedelta(hours=1))}, dataPrimerSeconds=7200)
            objects = {'ConfigMap/provision-scripts':{'data':{'source-contract.json':'{}'}}}
            pod = dict(name='waiting',uid='p',workload='Job/primer',containers={'done':dict(ready=True,containerID='c')})
            observation = dict(namespace={'uid':'ns'},pods={'waiting':pod},
                               objects={'Job/primer':{'uid':'j'},'Service/admin':{'uid':'sa'}})
            policy = dict(verdict='PASS',pins=c['pins'],namespaceUid='ns',adminServiceUid='sa',
                          observations=[dict(outcome=x,podUid='p',containerId='c') for x in ('connected','timeout','connected')])
            k.write(d/'run.json', c)
            k.write(d/'policy.json',policy)
            k.write(d/'candidate-verification.json',{'proof':{'safe':True}})
            roster = dict(version=1,tenants=[dict(id='10000000-0000-4000-8000-000000000001',
                                                   host='a.test',dataToken='synthetic-data',managementToken='synthetic-management')])
            job = dict(metadata={'uid':'j'},status=dict(active=1,startTime=stamp(utc)),spec=dict(activeDeadlineSeconds=120))
            fetched = []
            def fetch(argv,read):
                self.assertFalse(read)
                if argv[-2:] == ['touch','/run/ns-primer/.exported']:
                    receipts = [p for p in d.glob('*/result.json') if k.document(p)['verdict'] == 'OBSERVED']
                    self.assertTrue(any((p.parent/'tenants.json').is_file() for p in receipts))
                    return b''
                self.assertEqual(argv[:6], ['exec','waiting','-c','done','--','cat'])
                fetched.append(argv[-1])
                return json.dumps(roster if argv[-1].endswith('tenants.json') else {'safe':True}).encode()
            client = SimpleNamespace(get=lambda *args:job,call=fetch)
            reply = SimpleNamespace(returncode=0,stdout=b'{"state":"synthetic-tenants-usable","tenants":1}')
            with patch.object(k,'load',return_value=(d,c,objects)), patch.object(k.candidate,'require'), \
                 patch.object(k,'active_baseline',return_value=observation), patch.object(k,'observe',return_value=observation), \
                 patch.object(k,'selected_pod'), patch.object(k,'Client',return_value=client), \
                 patch.object(primer,'run_actor',side_effect=lambda *args: (json.loads(reply.stdout),reply.returncode)) as actor:
                result = primer.prime(d,d/'attempt',2)
                self.assertEqual(result['verdict'],'OBSERVED')
                self.assertEqual(result['selectedDataPrimerSeconds'],7200)
                argv = actor.call_args.args[0]
                self.assertEqual(argv[6:17],['exec','-i','waiting','-c','done','--','env','NS_PRIMER_STALL_SECONDS=7200','node','-','owned-ns'])
                self.assertEqual(argv[-3:], [str(int((utc.timestamp()+120)*1000)),'1','2'])
                self.assertAlmostEqual(actor.call_args.args[1],utc.timestamp()+120)
                self.assertEqual(result['exportAcknowledgement'],'sent')
                rows = k.document(d/'attempt/tenants.json')
                self.assertEqual(rows,[{'host':'a.test','id':roster['tenants'][0]['id'],'token':'synthetic-data'}])
                self.assertEqual((d/'attempt/tenants.json').stat().st_mode & 0o777,0o600)
                (d/'attempt').rename(d/'primer')
                bound = dict(c,primerOutput=str(d/'primer'),tenantsFile=str(d/'primer/tenants.json'))
                primer.require_roster(d,bound,observation)
                k.write(d/'primer/tenants.json', [])
                with self.assertRaisesRegex(k.Refused,'PRIMER_ROSTER_CHANGED'):
                    primer.require_roster(d,bound,observation)
                k.write(d/'primer/tenants.json', rows)
                primer.require_roster(d,bound,observation)
                for value in (0,1.5,True,2**53):
                    with self.assertRaisesRegex(k.Refused,'PRIMER_CONCURRENCY_INVALID'):
                        primer.prime(d,d/'invalid',value)
                    with self.assertRaisesRegex(k.Refused,'PRIMER_MAX_TENANTS_INVALID'):
                        primer.prime(d,d/'invalid',max_tenants=value)
                with self.assertRaisesRegex(k.Refused,'PRIMER_OPTIONS_UNBOUND'):
                    primer.prime(d,d/'invalid',33)
                self.assertFalse((d/'invalid').exists())
                for workers in (1,32,33,64):
                    c['primerOptions']={'concurrency':workers,'maxTenants':20000}
                    selected=primer.prime(d,d/('selected-'+str(workers)))
                    self.assertEqual(selected['primerOptions'],c['primerOptions'])
                    self.assertEqual(actor.call_args.args[0][-4:],
                                     [str(int((utc.timestamp()+120)*1000)),'1',str(workers),'20000'])
                with self.assertRaisesRegex(k.Refused,'PRIMER_OPTIONS_CHANGED'):
                    primer.prime(d,d/'invalid',63,20000)
                self.assertEqual(actor.call_count,5)
                self.assertFalse((d/'invalid').exists())
                c.pop('primerOptions')
                fetched.clear()
                reply.stdout = b'{"error":"SOCKET_IPC_UNAVAILABLE","requestClass":"internal-ownership","notReady":true}'
                reply.returncode = 1
                failure=primer.prime(d,d/'failure',2)
                self.assertEqual(failure['sourceResult']['error'],'SOCKET_IPC_UNAVAILABLE')
                self.assertFalse((d/'failure/tenants.json').exists())
                self.assertEqual(fetched.count('/run/ns-primer/tenants.json'),0)
                job['metadata']['uid']='other'
                self.assertEqual(primer.prime(d,d/'changed',2)['code'],'K8S_PRIMER_JOB_INACTIVE')
                self.assertEqual(actor.call_count,6)

                reply.returncode = 0
                reply.stdout = b'{"state":"synthetic-tenants-usable","tenants":1}'
                job['metadata']['uid'] = 'j'
                self.assertEqual(primer.prime(d,d/'failure',2)['verdict'], 'OBSERVED')
                with self.assertRaisesRegex(k.Refused,'PRIMER_OUTPUT_CHANGED'):
                    primer.prime(d,d/'failure',2)

    def test_transport_budget_renews_on_durable_counts_only(self):
        def run(events, stall, work):
            lines = ['import time']
            for delay, frame in events:
                lines += [f'time.sleep({delay!r})', f'print({json.dumps(frame)!r}, flush=True)']
            return asyncio.run(primer.run_actor([sys.executable, '-c', '\n'.join(lines)],
                                                 time.time()+work, stall, 4, result))
        done = {'state':'synthetic-tenants-usable', 'tenants':4}
        advances = [(0, {'checkpoint':0})] + [(.16, {'checkpoint':i}) for i in range(1,5)]
        result = {}
        self.assertEqual(run(advances + [(0, done)], .4, 5), (done, 0))
        self.assertEqual(result['completedTenants'], 4)
        with self.assertRaisesRegex(primer.k.Refused, 'PRIMER_STALLED'):
            run(advances[:2] + [(.12, {'checkpoint':1})]*5, .4, 5)
        self.assertEqual(result['completedTenants'], 1)
        with self.assertRaisesRegex(primer.k.Refused, 'PRIMER_DEADLINE'):
            run(advances, 3, .4)
