"""Execute the shared input query in a disposable, socket-free PostgreSQL backend.

Set C1_PG_BINDIR to a PostgreSQL bin directory containing initdb and postgres.
The schema and run markers below belong exclusively to this test.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import kube_adapter as k
import accepted_inputs

PG_BIN = os.environ.get('C1_PG_BINDIR')
TENANT = '00000000-0000-4000-8000-000000000001'
FOREIGN = '00000000-0000-4000-8000-000000000002'
RUN = 'c1-single-user'
CONSUMER = 'evaluator-synthetic'


def literal(value):
    return "'" + value.replace("'", "''") + "'"


@unittest.skipUnless(PG_BIN, 'C1_PG_BINDIR with postgres and initdb required')
class AcceptedInputSql(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.database = Path(tmp.name)/'db'
        self.bin = Path(PG_BIN)
        subprocess.run([self.bin/'initdb', '-D', self.database, '--no-sync', '--no-locale',
                        '--encoding=UTF8', '--auth=trust'], check=True, capture_output=True)
        self.run_sql("""
CREATE SCHEMA nsdemo_entries;
CREATE SCHEMA nsdemo_devicestatus;
CREATE SCHEMA nsdemo_treatments;
CREATE SCHEMA checkpoint;
CREATE SCHEMA lifecycle;
CREATE TABLE nsdemo_entries.entries (tenant_id uuid, doc jsonb);
CREATE TABLE nsdemo_devicestatus.devicestatus (tenant_id uuid, doc jsonb);
CREATE TABLE nsdemo_treatments.treatments (tenant_id uuid, doc jsonb);
CREATE TABLE lifecycle.tenant_lifecycle_windows (tenant_id uuid, generation bigint, phase text);
CREATE TABLE checkpoint.tenant_consumer_checkpoint (
  tenant_id uuid, consumer text, checkpoint bigint, projection jsonb, work_version int,
  contract_digest text, work_enabled boolean, work_observed bigint[], work_completed bigint[],
  output_restore_generation bigint, output_identity text, output_digest text, output_revision bigint);
""")
        identity = self.copy("""SELECT json_build_object('system_id',(pg_control_system()).system_identifier::text,
            'timeline',(pg_control_checkpoint()).timeline_id,'database',current_database(),'slot','synthetic_slot')""")[0]
        self.identity = identity
        self.digest = '1'*64
        self.native = dict(kind='compact-native-v1', generation='2'*32, slot='synthetic_slot',
                           inputConsumer=CONSUMER, lifecycle='lifecycle',
                           receipt={'contractDigest': self.digest, 'selection': {'binding': {'source': identity}}})
        config = dict(kind='evaluator-work-v2', entries='nsdemo_entries', checkpoint='checkpoint',
                      consumer=CONSUMER+'-completed', native=self.native,
                      binding={'nativeConfigurationSha256': k.hashed(self.native)})
        self.query = accepted_inputs.query(config, RUN).rstrip().removesuffix(';')

    def run_sql(self, text):
        run = subprocess.run([self.bin/'postgres', '--single', '-j', '-D', self.database, 'postgres'],
                             input=text.strip()+'\n\n', capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotRegex(run.stderr, r'(ERROR|FATAL|PANIC):')
        return run.stdout

    def copy(self, query):
        raw = self.run_sql(f'COPY ({query}) TO STDOUT;')
        return [json.loads(line) for line in raw.replace('backend> ', '').splitlines() if line.startswith('{')]

    def test_accepted_rows_absent_late_prior_activity_and_durable_output(self):
        self.assertEqual(self.copy(self.query), [])
        rows = [('entries', {'date': 100, 'device': RUN}),
                ('devicestatus', {'created_at': '2026-01-01T00:00:00Z', 'device': RUN}),
                ('treatments', {'date': 102, 'enteredBy': RUN}),
                ('entries', {'date': 103, 'device': RUN+'-probe'})]
        acks = {(TENANT, domain, doc.get('device', doc.get('enteredBy')),
                 str(doc.get('date', doc.get('created_at')))): 1 for domain, doc in rows}
        events = [dict(event='create', domain=d, sequence=i+1, value={'doc': v}) for i, (d, v) in enumerate(rows)]
        stream = {'source_identity': self.identity, 'generation': self.native['generation']+':1',
                  'snapshot_position':'0/1', 'accepted_position':'0/2'}
        intake = [{'kind':'clinical-stream-v2','floor':4,'stream':stream},
                  {'kind':'storage-events-v1','head':4,'base':0,'last':'0/2','events':events}]
        checkpoint = 'checkpoint.tenant_consumer_checkpoint'
        self.run_sql(f"INSERT INTO lifecycle.tenant_lifecycle_windows VALUES ('{TENANT}',1,'active');\n" +
                     '\n'.join(f"INSERT INTO nsdemo_{d}.{d} VALUES ('{TENANT}',{literal(json.dumps(v))});" for d,v in rows)
                     + f"\nINSERT INTO {checkpoint}(tenant_id,consumer,checkpoint,projection) VALUES "
                       f"('{TENANT}','{CONSUMER}',4,{literal(json.dumps(intake))});")
        def assess(current, end=124):
            coverage = accepted_inputs.Coverage(RUN, [TENANT, FOREIGN], 0, source=self.identity)
            coverage.capture(current, 1, 2)
            coverage.capture(current, end, end+1)
            return coverage.assess(acks, end)
        missing = self.copy(self.query)
        self.assertEqual(len(missing), 1)
        self.assertTrue(missing[0]['sourceOK'])
        self.assertTrue(missing[0]['outputAbsent'])
        self.assertEqual(assess(missing)['classifications'], {'LATE':4})
        self.assertEqual(assess(missing, end=10)['classifications'], {'MISSING_AT_DRAIN':4})
        # A previous output covers only the earlier floor. The last event at the
        # new floor gives a definite negative even when older events coalesced.
        def projected(floor, tenant=TENANT):
            return literal(json.dumps([{'kind':'evaluator-work-v2', 'output':{'tenant':tenant,
                'inputCheckpoint':floor, 'result':{'checkpoint':floor,'properties':{}}, 'frame':{}}}]))
        self.run_sql(f"""INSERT INTO {checkpoint} VALUES
('{TENANT}','{CONSUMER}-completed',1,{projected(1)},2,'{self.digest}',true,
 ARRAY[NULL,NULL,NULL,NULL,NULL,4]::bigint[],ARRAY[NULL,NULL,NULL,NULL,NULL,1]::bigint[],
 1,repeat('a',64),repeat('b',64),1);""")
        prior = self.copy(self.query)
        self.assertTrue(prior[0]['outputOK'])
        self.assertEqual(assess(prior)['verdict'], 'FAIL')
        self.run_sql(f"""UPDATE {checkpoint} SET checkpoint=4,work_completed[6]=4,output_revision=2,
 projection={projected(4)} WHERE consumer='{CONSUMER}-completed';""")
        ready = self.copy(self.query)
        self.assertTrue(ready[0]['stateOK'])
        self.assertEqual(assess(ready)['classifications'], {'ON_TIME':4})
        # typed-checkpoint.complete can retain an identical older body while
        # atomically advancing its completed work and checkpoint.
        self.run_sql(f"""UPDATE {checkpoint} SET projection={projected(1)}
 WHERE consumer='{CONSUMER}-completed';""")
        self.assertEqual(assess(self.copy(self.query))['classifications'], {'ON_TIME':4})
        self.run_sql(f"""UPDATE {checkpoint} SET output_digest='invalid'
 WHERE consumer='{CONSUMER}-completed';""")
        with self.assertRaisesRegex(accepted_inputs.EvidenceError, 'M7_INPUT_INVALID_OUTPUT'):
            assess(self.copy(self.query))
        self.run_sql(f"""UPDATE {checkpoint} SET output_digest=repeat('b',64),projection={projected(4, FOREIGN)}
 WHERE consumer='{CONSUMER}-completed';""")
        with self.assertRaisesRegex(accepted_inputs.EvidenceError, 'M7_INPUT_FOREIGN_OUTPUT'):
            assess(self.copy(self.query))
