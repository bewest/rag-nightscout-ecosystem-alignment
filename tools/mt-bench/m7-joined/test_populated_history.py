"""Exercise fixture equivalence and readback; HISTORY_TEST_PSQL_ARGV enables PostgreSQL."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import subprocess
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit

import populated_history as h


class History(unittest.TestCase):
    def setUp(self):
        self.anchor = int(time.time()*1000)//h.STEP_MS*h.STEP_MS
        self.spec = {'mode': h.MODE, 'anchorUnixMs': self.anchor}
        self.tenants = [{'id': f'00000000-0000-4000-8000-{i:012d}', 'host': f'demo-{i}.test',
                         'token': f'local /{i}'} for i in range(2)]
        self.data = {}

    def save(self, port, tenant, docs, until):
        self.data[tenant['id']] = docs

    def rows(self, query):
        if query.startswith('SELECT DISTINCT'):
            return ''
        return '\n'.join('\t'.join(map(str, (key,len(rows),len(json.dumps(rows)),len(rows),h.digest(rows))))
                         for key, rows in self.data.items())

    def fixture(self, **changes):
        options = dict(spec=self.spec, tenants=self.tenants, base='http://127.0.0.1:8000',
                       sql=self.rows, until=None, window_seconds=300, post_batch=self.save)
        return h.run(**(options | changes))

    def test_same_inputs_reordered_roster_changed_ids_and_repeat(self):
        first = self.fixture()
        self.assertEqual((first['rows'], first['activeRows'], first['seededBatches']), (144, 144, 2))
        restored = self.fixture(tenants=self.tenants[::-1], verify_only=True)
        self.assertEqual((restored['logicalSha256'], restored['seededBatches']), (first['logicalSha256'], 0))
        self.data.clear()
        independent = self.fixture(tenants=[dict(t, id='other-'+str(i)) for i,t in enumerate(self.tenants)])
        self.assertEqual(independent['logicalSha256'], first['logicalSha256'])
        self.assertNotIn('local /', json.dumps(first))

    def test_refuses_corruption_partial_extra_absent_and_expired_then_restores(self):
        self.fixture()
        healthy = copy.deepcopy(self.data)
        key = self.tenants[0]['id']
        for mutate in (lambda: self.data[key][0].update(sgv=999), lambda: self.data[key].pop(),
                       lambda: self.data[key].append(self.data[key][-1]),
                       lambda: self.data.update(other=self.data[key]), lambda: self.data.pop(key)):
            mutate()
            with self.assertRaisesRegex(ValueError, 'M7_HISTORY_'):
                self.fixture(verify_only=True)
            self.data = copy.deepcopy(healthy)
        for clock in (self.anchor/1000-1, (self.anchor+h.LOOKBACK_MS-(h.ROWS-1)*h.STEP_MS)/1000):
            with self.assertRaisesRegex(ValueError, 'OUTSIDE_CLINICAL_WINDOW'):
                self.fixture(now=lambda: clock)
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_CLINICAL_WINDOW'):
            self.fixture(until=time.time()+h.LOOKBACK_MS/1000)
        self.assertEqual(self.fixture(verify_only=True)['seededBatches'], 0)

    def test_paired_snapshot_and_legacy(self):
        h.validate(h.BASELINE)
        h.check_snapshot(h.BASELINE, {})
        h.check_snapshot(self.spec, {'history': self.spec})
        for spec, manifest in ((h.BASELINE, {'history':self.spec}), (self.spec, {}),
                               (self.spec, {'history':dict(self.spec,anchorUnixMs=self.anchor-h.STEP_MS)})):
            with self.assertRaisesRegex(ValueError, 'SNAPSHOT_MISMATCH'):
                h.check_snapshot(spec,manifest)
        with self.assertRaisesRegex(ValueError, 'ANCHOR'):
            h.validate(dict(self.spec, anchorUnixMs=self.anchor+1))

    @unittest.skipUnless(os.environ.get('HISTORY_TEST_PSQL_ARGV'), 'requires disposable PostgreSQL')
    def test_http_seed_real_postgres_readback(self):
        argv = json.loads(os.environ['HISTORY_TEST_PSQL_ARGV'])
        # Isolated synthetic edge; PostgreSQL computes the very same JSONB census as both runners.
        by_host = {t['host']:t for t in self.tenants}
        def read(query):
            staging = json.dumps([dict(tenant_id=tid, doc=doc) for tid,rows in self.data.items() for doc in rows])
            sql = """BEGIN;
CREATE TEMP TABLE history_test (tenant_id uuid NOT NULL, doc jsonb NOT NULL);
INSERT INTO history_test SELECT * FROM jsonb_to_recordset($rows$""" + staging + """$rows$::jsonb)
    AS rows(tenant_id uuid, doc jsonb);
""" + query.replace('nsdemo_entries.entries', 'pg_temp.history_test') + '\nROLLBACK;'
            return subprocess.run(argv, input=sql, capture_output=True, text=True, timeout=15, check=True).stdout
        owner = self
        class Edge(BaseHTTPRequestHandler):
            def do_POST(self):
                tenant = by_host[self.headers['Host']]
                query = urlsplit(self.path)
                if query.path != '/api/v1/entries' or parse_qs(query.query) != {'token':[tenant['token']]}:
                    self.send_error(403)
                    return
                owner.data[tenant['id']] = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(('127.0.0.1',0), Edge) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                args = dict(sql=read, post_batch=h.post, base='http://127.0.0.1:'+str(server.server_port))
                first = self.fixture(**args)
                restored = self.fixture(**args, verify_only=True)
                self.assertEqual(first['logicalSha256'], restored['logicalSha256'])
                self.assertEqual((first['rows'], first['activeRows'], first['seededBatches']), (144, 144, 2))
                self.assertEqual(restored['seededBatches'], 0)
                print('postgresReadback', json.dumps(first, sort_keys=True))
                self.data[self.tenants[0]['id']][1]['isValid'] = False
                with self.assertRaisesRegex(ValueError, 'READBACK_MISMATCH'):
                    self.fixture(**args, verify_only=True)
                self.data[self.tenants[0]['id']][1].pop('isValid')
                self.data[self.tenants[0]['id']][1]['dateString'] = 'changed'
                with self.assertRaisesRegex(ValueError, 'READBACK_MISMATCH'):
                    self.fixture(**args, verify_only=True)
                ordinary = self.data[self.tenants[0]['id']][0]
                ordinary.update(device='synthetic-compose-demo', sysTime=ordinary['dateString'])
                self.data = {self.tenants[0]['id']: [ordinary]}
                with self.assertRaisesRegex(ValueError, 'UPSERT_KEY_IN_USE'):
                    self.fixture(**args)
            finally:
                server.shutdown()
                thread.join()
