"""Verify the host invocation preserves its original Pod, finite Job cutoff and private DATA projection."""
import json
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
                self.assertEqual(argv[:6], ['exec','waiting','-c','done','--','cat'])
                fetched.append(argv[-1])
                return json.dumps(roster if argv[-1].endswith('tenants.json') else {'safe':True}).encode()
            client = SimpleNamespace(get=lambda *args:job,call=fetch)
            reply = SimpleNamespace(returncode=0,stdout=b'{"state":"synthetic-data-primed","tenants":1}')
            with patch.object(k,'load',return_value=(d,c,objects)), patch.object(k.candidate,'require'), \
                 patch.object(k,'active_baseline',return_value=observation), patch.object(k,'observe',return_value=observation), \
                 patch.object(k,'selected_pod'), patch.object(k,'Client',return_value=client), \
                 patch.object(primer.subprocess,'run',return_value=reply) as actor:
                result = primer.prime(d,d/'attempt',2)
                self.assertEqual(result['verdict'],'OBSERVED')
                self.assertEqual(result['selectedDataPrimerSeconds'],7200)
                argv = actor.call_args.args[0]
                self.assertEqual(argv[6:15],['exec','-i','waiting','-c','done','--','node','-','owned-ns'])
                self.assertEqual(argv[-3:], [str(int((utc.timestamp()+120)*1000)),'1','2'])
                self.assertGreater(len(actor.call_args.kwargs['input']),0)
                self.assertLessEqual(actor.call_args.kwargs['timeout'],120)
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
                reply.stdout = b'{"error":"SOCKET_IPC_UNAVAILABLE","requestClass":"internal-ownership","notReady":true}'
                reply.returncode = 1
                failure=primer.prime(d,d/'failure',2)
                self.assertEqual(failure['sourceResult']['error'],'SOCKET_IPC_UNAVAILABLE')
                self.assertFalse((d/'failure/tenants.json').exists())
                self.assertEqual(fetched.count('/run/ns-primer/tenants.json'),1)
                job['metadata']['uid']='other'
                self.assertEqual(primer.prime(d,d/'changed',2)['code'],'K8S_PRIMER_JOB_INACTIVE')
                self.assertEqual(actor.call_count,2)
