"""Targeted clinical SQL reads: real identity guards, synthetic API/SQL replies."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
import types
import sys
import unittest
from unittest.mock import patch

import kube_adapter as k
import clinical_sql
from test_native_join import fixture


class ClinicalSql(unittest.TestCase):
    def setUp(self):
        self.area=tempfile.TemporaryDirectory();self.addCleanup(self.area.cleanup)
        self.d=Path(self.area.name)
        self.c,self.inventory,self.render,self.client=fixture()
        self.objects=k.validate(self.c,self.inventory,self.render)
        self.baseline=k.observe(self.c,self.objects,self.client)
        self.calls=[];self.sqls=[];self.after=None
        original=self.client.get
        def get(kind,name=None,cleanup=False):
            if kind=='pod':value=copy.deepcopy(next(row for row in self.client.pods if row['metadata']['name']==name))
            elif kind=='ReplicaSet':value=copy.deepcopy(next(row for row in self.client.replicas if row['metadata']['name']==name))
            else:value=original(kind,name,cleanup)
            self.calls.append({'kind':kind,'name':name,'bytes':len(json.dumps(value,separators=(',',':')).encode())})
            return value
        self.client.get=get
        def call(argv,**kwargs):
            self.assertIn('psql',argv);self.assertFalse(kwargs['read'])
            self.sqls.append(kwargs['data'])
            if self.after:self.after()
            return b'exact-clinical-row\n'
        self.client.call=call
        self.patch=patch.object(k,'active_baseline',return_value=self.baseline)
        self.patch.start();self.addCleanup(self.patch.stop)

    def read(self):return clinical_sql.read(self.d,self.c,self.objects,'SELECT synthetic_clinical();',self.client)

    def test_only_owned_postgres_is_read_and_sql_bytes_are_unchanged(self):
        # Omitted and empty optional argv lists select the same image default.
        for obj in (self.client.objects['StatefulSet/postgres']['spec']['template'],
                    next(row for row in self.client.pods if row['metadata']['name']=='postgres-pod')):
            obj['spec']['containers'][0].setdefault('args',[])
        self.assertEqual(self.read(),'exact-clinical-row\n')
        self.assertEqual(self.sqls,[b'BEGIN READ ONLY;\nSELECT synthetic_clinical();\nROLLBACK;\n'])
        self.assertEqual([(r['kind'],r['name']) for r in self.calls],
                         [('namespace',self.c['namespace']),('StatefulSet','postgres'),('pod','postgres-pod')]*2)

    def test_terminating_namespace_pod_and_unready_process_refuse(self):
        ns=self.client.objects['Namespace/'+self.c['namespace']]
        pod=next(row for row in self.client.pods if row['metadata']['name']=='postgres-pod')
        for target in (ns['metadata'],pod['metadata']):
            target['deletionTimestamp']='synthetic-termination'
            with self.assertRaises(k.Refused):self.read()
            del target['deletionTimestamp'];self.assertEqual(self.read(),'exact-clinical-row\n')
        state=pod['status']['containerStatuses'][0]['state']
        pod['status']['containerStatuses'][0]['state']={'terminated':{'exitCode':0}}
        with self.assertRaisesRegex(k.Refused,'ROLE_NOT_READY'):self.read()
        pod['status']['containerStatuses'][0]['state']=state;self.read()

    def test_work_deadline_and_read_only_query_bound_still_refuse(self):
        for query in ('UPDATE synthetic SET x=1;', 'SELECT '+'x'*131072):
            with self.assertRaisesRegex(k.Refused,'SQL_READ_ONLY'):
                clinical_sql.read(self.d,self.c,self.objects,query,self.client)
        self.c['deadlines']['workUntil']='2000-01-01T00:00:00Z'
        with self.assertRaisesRegex(k.Refused,'WORK_DEADLINE'):self.read()
        self.assertFalse(self.sqls)

    def test_selected_transport_clock_cannot_extend_work_or_credit_late_bytes(self):
        now=[time.time()]
        self.after=lambda:now.__setitem__(0,now[0]+61)
        with patch.object(k.time,'time',side_effect=lambda:now[0]):
            with self.assertRaisesRegex(k.Refused,'OBSERVATION_DEADLINE'):self.read()
        self.after=None
        self.assertEqual(self.read(),'exact-clinical-row\n')

    def test_cli_keeps_full_input_validation_and_uses_clinical_bracket(self):
        out=io.StringIO()
        with patch.object(k,'load',return_value=(self.d,self.c,self.objects)) as loaded, \
             patch.object(k,'Client',return_value=self.client), \
             patch.object(k,'sql',side_effect=AssertionError('FULL_CENSUS_IN_CLINICAL_READ')), \
             patch.object(sys,'argv',['adapter.py','clinical-sql',str(self.d)]), \
             patch.object(sys,'stdin',io.StringIO('SELECT synthetic_clinical();')),contextlib.redirect_stdout(out):
            self.assertIsNone(k.main())
        loaded.assert_called_once_with(str(self.d),cleanup=False)
        self.assertEqual(out.getvalue(),'exact-clinical-row\n')

    def test_read_count_byte_and_local_cost_measurement(self):
        results=[]
        for label,reader in [('full-census',lambda:k.sql(self.d,self.c,self.objects,'SELECT synthetic_clinical();',self.client)),
                             ('clinical-postgres',self.read)]:
            self.calls.clear();self.sqls.clear();started=time.perf_counter();cpu=time.process_time()
            self.assertEqual(reader(),'exact-clinical-row\n')
            results.append({'mode':label,'apiGets':len(self.calls),'apiJsonBytes':sum(r['bytes'] for r in self.calls),
                'sqlExecs':len(self.sqls),'sqlRequestBytes':len(self.sqls[0]),'sqlResponseBytes':len(b'exact-clinical-row\n'),
                'wallSeconds':time.perf_counter()-started,'observerProcessCpuSeconds':time.process_time()-cpu,
                'transport':'synthetic API/SQL in process; no network or DB timing'})
        self.assertGreater(results[0]['apiGets'],results[1]['apiGets'])
        self.assertEqual(results[1]['apiGets'],6)
        print('CLINICAL_SQL_OBSERVER_COST '+json.dumps(results,sort_keys=True))


if __name__=='__main__':unittest.main()
