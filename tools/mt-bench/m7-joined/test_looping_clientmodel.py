"""AID client model in the harness: driver looping-v2 (D1-D5), the backlog scenario (D6) and the history
synthetic-history-looping-2d-v2. The k6 scripts are evaluated in node with only k6 imports mocked.

Each property has a red control: the same check run against a broken driver, script or generator must fail
with an assertion (measurement rule 3)."""
import collections
import copy
import json
import math
import random
import subprocess
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

import adapter
import fixture_catalog
import looping_backlog
import looping_driver as D
import looping_history as L
import looping_history_v2 as V
import populated_history as h
import workload

ANCHOR = 1_763_683_200_000
SPEC1 = L.default_spec(ANCHOR)
SPEC2 = V.default_spec(ANCHOR)
BASE_KEY = dict(tenants=10, image='sha256:' + 'a' * 64, postgres_image='sha256:' + 'b' * 64,
                schema='migrations-tree:' + 'c' * 40, transport='writer-driven')

# Evaluate a k6 script in node; record each POST compactly (route, token, body bytes, documents,
# identity-less documents, eventTypes, whether a document carries `identifier`, uploader-only status).
INSPECT = r"""
const fs = require('fs'), vm = require('vm');
const [script, tenantsFile, envJson, calls, mutations] = process.argv.slice(1);
const env = Object.assign({ACCEL: '1', HOT_FACTOR: '1', DURATION: '1800', RUN_ID: 'run-x', RUN_START: '1763683200000',
  BASE_URL: 'http://api.test', M7_WORKLOAD_MIX: 'realistic-v1',
  SHAPES: 'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'}, JSON.parse(envJson));
const posts = [];
const scenario = {name: '', iterationInTest: 0, startTime: 0};
const vu = {idInTest: 1};
class Counter { add () {} }
const IDS = ['syncIdentifier', 'id', 'uuid', 'NSCLIENT_ID', 'identifier', '_id'];
function record (url, text, params) {
  const body = JSON.parse(text);
  const docs = Array.isArray(body) ? body : [body];
  const u = new URL(url);
  const auth = params && params.headers && params.headers.Authorization;
  posts.push({path: u.pathname, token: u.searchParams.get('token') || (auth ? auth.replace('Bearer jwt', 'tok') : null), bearer: Boolean(auth), bytes: text.length, docs: docs.length,
    idless: docs.filter(d => !IDS.some(k => d[k] !== undefined && d[k] !== null && d[k] !== '')).length,
    types: docs.map(d => d.eventType || d.type || (d.uploader && Object.keys(d).length <= 3 ? 'battery' : 'status')),
    identifier: docs.some(d => 'identifier' in d), stamps: docs.map(d => d.created_at || d.dateString || null),
    device: docs.map(d => d.device || d.enteredBy || null)});
  return {status: 200};
}
const http = {post: (url, body, params) => record(url, body, params), get: () => ({status: 200}), expectedStatuses: () => null,
  request: (m, url, body, params) => record(url, body, params), batch: reqs => reqs.map(r => record(r.url, r.body, r.params))};
const context = {__ENV: env, SharedArray: function (_, fn) { return fn(); }, open: () => fs.readFileSync(tenantsFile, 'utf8'),
  Counter, http, exec: {scenario, vu}, sleep: () => {}, console: {log () {}}, URL};
let source = fs.readFileSync(script, 'utf8').replace(/^import .*;$/gm, '').replace(/^export /gm, '');
for (const [a, b] of JSON.parse(mutations)) { if (!source.includes(a)) throw Error('MUTATION_NOT_FOUND ' + a); source = source.split(a).join(b); }
const names = ['options', 'w_devicestatus', 'w_treatments_v3', 'w_sgv', 'backlog'].filter(n => new RegExp('(function|const) ' + n + '\\b').test(source));
const run = vm.runInNewContext(source + '\n({' + names.join(',') + '});', context);
for (const [name, n] of JSON.parse(calls)) for (let i = 0; i < n; i++) {
  scenario.name = name; scenario.iterationInTest = i; vu.idInTest = i + 1; run[name]();
}
console.log(JSON.stringify({scenarios: run.options.scenarios, posts}));
"""


def roster(n, seed=7):
    rows = [{'id': '%08d-0000-4000-8000-000000000000' % i, 'host': 't%05d.test' % i, 'token': 'tok%05d' % i,
             'jwt': 'jwt%05d' % i} for i in range(n)]
    random.Random(seed).shuffle(rows)  # roster order is not host order
    return rows


def evaluate(tenants, env, calls=(), mutations=(), script=None):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'tenants.json'
        if script is None:
            script = Path(d) / 'workload.js'
            workload.generate(adapter.ROOT, script)
        path.write_text(json.dumps(tenants))
        result = subprocess.run(['node', '--max-old-space-size=4096', '-e', INSPECT, str(script), str(path), json.dumps(env),
                                 json.dumps(list(calls)), json.dumps(list(mutations))], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return json.loads(result.stdout)


def kinds_by_token(rows):
    return {r['token']: (r['loopKind'] or 'cgm') for r in rows}


class DriverV2(unittest.TestCase):
    N = 300

    @classmethod
    def setUpClass(cls):
        cls.rows = D.annotate(SPEC2, roster(cls.N), roster(cls.N))
        cls.counts = D.kind_counts(SPEC2, cls.N)
        cls.env = D.environment(D.SHAPE_V2)

    def run_ds(self, mutations=(), env=None, cycles=D.DS_PERIOD):
        slots = D.wheel_slots(self.counts)
        return evaluate(self.rows, env or self.env, [('w_devicestatus', slots * cycles // D.DS_PERIOD)], mutations)

    # ---------------------------------------------------------------- D1 + D4: devicestatus per controller
    def check_devicestatus(self, out):
        kinds = kinds_by_token(self.rows)
        per = collections.defaultdict(list)
        for p in out['posts']:
            self.assertEqual(p['path'], '/api/v1/devicestatus')
            per[kinds[p['token']]].append(p)
        n = collections.Counter(kinds.values())
        # posts per tenant per cycle, over one whole 20-cycle wheel
        rate = {k: len(v) / n[k] / D.DS_PERIOD for k, v in per.items()}
        self.assertAlmostEqual(rate['loop'], 1.35, places=6, msg='LOOP_1_35_PER_CYCLE')
        self.assertAlmostEqual(rate['trio'], 2.0, places=6, msg='TRIO_2_PER_CYCLE')
        self.assertAlmostEqual(rate['aaps'], 1.0, places=6, msg='AAPS_1_PER_CYCLE')
        self.assertAlmostEqual(rate['cgm'], 1.0, places=6, msg='CGM_ONLY_1_PER_CYCLE')
        mean = {k: sum(p['bytes'] for p in v) / len(v) for k, v in per.items()}
        self.assertTrue(1350 <= mean['loop'] <= 1650, mean)      # model: 1,494 B median (n=1)
        self.assertTrue(3350 <= mean['trio'] <= 3900, mean)      # model: 1,348-3,877 B, median 3,692 B
        self.assertTrue(2500 <= mean['aaps'] <= 3100, mean)      # model: 2.8 KB (E1 generator's, assumed)
        self.assertLess(mean['cgm'], 200)                         # D4: battery only, about 0.1 KB
        self.assertTrue(all(p['types'] == ['battery'] for p in per['cgm']), 'CGM_ONLY_BATTERY_ONLY')
        self.assertTrue(all(p['types'] == ['status'] for k in ('loop', 'trio', 'aaps') for p in per[k]))
        # a Trio tenant's suggested and enacted posts are adjacent slots of the wheel
        trio = [i for i, p in enumerate(out['posts']) if kinds[p['token']] == 'trio']
        self.assertTrue(all(out['posts'][a]['token'] == out['posts'][a + 1]['token'] for a in trio[::2]))
        # every post carries the run marker and a unique time per tenant
        self.assertTrue(all(p['device'] == ['run-x'] for p in out['posts']))
        seen = collections.Counter((p['token'], p['stamps'][0]) for p in out['posts'])
        self.assertEqual(max(seen.values()), 1)
        # phases spread: each tenant's first post lands at its own place in the cycle
        first = {}
        for p in out['posts']:
            first.setdefault(p['token'], p['stamps'][0])
        self.assertEqual(len(set(first.values())), len(first))

    def test_devicestatus_per_controller(self):
        out = self.run_ds()
        self.check_devicestatus(out)
        s = out['scenarios']['w_devicestatus']
        self.assertEqual((s['rate'], s['timeUnit']), (D.wheel_slots(self.counts), '%dms' % (D.DS_PERIOD * 300000)))

    def test_red_devicestatus_per_controller(self):
        rules = json.loads(self.env['M7_LOOPING_V2_RULES'])
        for broken in (dict(rules, loopExtra=[0, 20]),):          # Loop back to 1 per cycle
            with self.assertRaises(AssertionError):
                self.check_devicestatus(self.run_ds(env={**self.env, 'M7_LOOPING_V2_RULES': json.dumps(broken)}))
        # Trio's second post dropped from the wheel
        with self.assertRaises(AssertionError):
            self.check_devicestatus(self.run_ds([("kind === 'trio' ? 2 :", "kind === 'trio' ? 1 :")]))
        # v1 bodies (one Loop-sized status for every controller)
        v1docs = json.loads(D.environment(D.SHAPE)['M7_LOOPING_TEMPLATES'])['documents']
        t = json.loads(self.env['M7_LOOPING_TEMPLATES'])
        t['devicestatus'].update(trio_suggested=v1docs['trio'], trio_enacted=v1docs['trio'], loop=v1docs['loop'])
        with self.assertRaises(AssertionError):
            self.check_devicestatus(self.run_ds(env={**self.env, 'M7_LOOPING_TEMPLATES': json.dumps(t)}))

    def test_red_cgm_only_battery(self):
        # CGM-only tenants given a full oref status, or left out of the devicestatus wheel
        with self.assertRaises(AssertionError):
            self.check_devicestatus(self.run_ds([("const kind = t.loopKind === null ? 'cgm' : t.loopKind;",
                                                  "const kind = t.loopKind === null ? 'aaps' : t.loopKind;")]))
        with self.assertRaises((AssertionError, KeyError)):
            self.check_devicestatus(self.run_ds([("const posts = kind === 'trio'", "if (kind === null) continue;\n    const posts = kind === 'trio'")]))

    # ---------------------------------------------------------------- D2 + D3 + D5: treatments
    def run_tx(self, rounds, mutations=(), env=None):
        loopers = sum(1 for r in self.rows if r['loopKind'])
        return evaluate(self.rows, env or self.env, [('w_treatments_v3', loopers * rounds)], mutations), loopers

    def check_treatment_rate(self, out, loopers):
        s = out['scenarios']['w_treatments_v3']
        self.assertEqual(s['rate'], loopers)
        per_day = 86_400_000 / int(s['timeUnit'].removesuffix('ms'))
        self.assertAlmostEqual(per_day, 216, delta=1, msg='ONE_PER_LOOPING_TENANT_PER_400_S')
        touched = {p['token'] for p in out['posts']}
        kinds = kinds_by_token(self.rows)
        self.assertFalse(any(kinds[t] == 'cgm' for t in touched), 'TREATMENTS_TO_CGM_ONLY')

    def test_treatment_rate(self):
        self.check_treatment_rate(*self.run_tx(2))

    def test_red_treatment_rate(self):
        with self.assertRaises(AssertionError):   # looping-v1's cadence (565 s)
            self.check_treatment_rate(*self.run_tx(2, env={**self.env, 'M7_LOOPING_TREATMENT_CYCLE_MS': '565476'}))

    def check_routes_and_identity(self, out):
        kinds = kinds_by_token(self.rows)
        by = collections.defaultdict(list)
        for p in out['posts']:
            if p['path'] == '/api/v1/profile':
                by['profile'].append(p)
                continue
            by[kinds[p['token']]].append(p)
        for p in by['loop'] + by['trio']:
            self.assertEqual(p['path'], '/api/v1/treatments')
            self.assertFalse(p['identifier'])
            self.assertIn(p['docs'], (1, 2))
        for p in by['aaps']:
            self.assertEqual((p['path'], p['docs'], p['identifier'], p['bearer']), ('/api/v3/treatments', 1, False, True))
            self.assertIn(p['types'][0], ('Temp Basal', 'Correction Bolus'))
        docs = {k: sum(p['docs'] for p in by[k]) for k in ('loop', 'trio')}
        idless = {k: sum(p['idless'] for p in by[k]) / docs[k] for k in docs}
        self.assertAlmostEqual(docs['loop'] / len(by['loop']), 1.1, delta=0.03)
        self.assertAlmostEqual(docs['trio'] / len(by['trio']), 1.2, delta=0.03)
        self.assertTrue(0 < idless['loop'] < 0.01, idless)           # model: < 1 %
        self.assertTrue(0.015 <= idless['trio'] <= 0.025, idless)    # model: about 2 %
        identityless_types = {t for p in by['loop'] + by['trio'] for t in p['types'][:1] if p['idless']}
        self.assertTrue(identityless_types <= {'Site Change', 'Exercise', 'Temporary Target', 'Note'}, identityless_types)

    def test_routes_and_identity_share(self):
        out, _ = self.run_tx(60)
        self.check_routes_and_identity(out)

    def test_red_routes_and_identity_share(self):
        rules = json.loads(self.env['M7_LOOPING_V2_RULES'])
        with self.assertRaises(AssertionError):    # every Trio request identity-less
            self.check_routes_and_identity(self.run_tx(60, env={**self.env, 'M7_LOOPING_V2_RULES': json.dumps(dict(rules, trioIdless=1))})[0])
        with self.assertRaises(AssertionError):    # looping-v1's route: every treatment a v3 document
            self.check_routes_and_identity(self.run_tx(60, [("BASE + '/api/v1/treatments?token=' + t.token, docs, {}, [200], 'POST v1 treatments', 'tx_loop_v1'",
                                                            "BASE + '/api/v3/treatments', docs[0], { Authorization: 'Bearer ' + t.jwt }, [200], 'POST v3 treatments', 'tx_loop_v1'")])[0])

    def test_loop_profile_posts(self):
        out, loopers = self.run_tx(D.PROFILE_EVERY_ROUNDS)
        kinds = kinds_by_token(self.rows)
        profiles = [p for p in out['posts'] if p['path'] == '/api/v1/profile']
        loop_tokens = {r['token'] for r in self.rows if r['loopKind'] == 'loop'}
        # one per Loop tenant per 648 rounds (3 days at 400 s), none for others, about 2.2 KB
        self.assertEqual(collections.Counter(p['token'] for p in profiles), collections.Counter({t: 1 for t in loop_tokens}))
        self.assertTrue(all(1800 <= p['bytes'] <= 2600 for p in profiles))
        self.assertEqual(len(out['posts']), loopers * D.PROFILE_EVERY_ROUNDS)   # instead of, not in addition to
        self.assertFalse(any(kinds[p['token']] != 'loop' for p in profiles))

    def test_offered_rate_per_1000(self):
        rate = D.offered(SPEC2, 1000)
        # model: SGV 3.33 + devicestatus 4.53 + treatments 2.0 + reads 6.67 = about 16.5 req/s at 20 % CGM-only
        self.assertAlmostEqual(rate['total'], 16.5, delta=0.1)
        self.assertAlmostEqual(rate['scenarios']['w_treatments_v3'], 2.0, places=6)
        self.assertAlmostEqual(sum(rate['requestShapes'].values()),
                               rate['scenarios']['w_devicestatus'] + rate['scenarios']['w_treatments_v3'], places=3)
        # the generated k6 scenarios offer exactly what the driver accounting projects
        rows = D.annotate(SPEC2, roster(1000), roster(1000))
        s = evaluate(rows, self.env)['scenarios']
        measured = {k: 1000 * v['rate'] / int(v['timeUnit'].removesuffix('ms')) for k, v in s.items()}
        for k, v in measured.items():
            self.assertAlmostEqual(v, rate['scenarios'][k], places=3, msg=k)

    def test_v2_runs_on_the_v1_fixture_with_the_same_roles(self):
        n = 200
        self.assertEqual(L.roles(SPEC1, n), V.roles(SPEC2, n))
        self.assertEqual(D.annotate(SPEC1, roster(n), roster(n)), D.annotate(SPEC2, roster(n), roster(n)))
        self.assertEqual(D.write_offers(SPEC1, n, 1, 1, 300000, D.SHAPE_V2), D.write_offers(SPEC2, n, 1, 1, 300000, D.SHAPE_V2))

    def test_configured_plan_matches_the_generated_scenarios(self):
        import driver_accounting
        rows = roster(25)
        spec = dict(SPEC2, cgmOnlyPercent=32)
        annotated = D.annotate(spec, rows, rows)
        plan = dict(version=1, observer='scheduling-v1', writeRateScale=2, scenarios={name: {} for name in driver_accounting.WEIGHTS})
        cadence = dict(workloadMix='realistic-v1', driverShape=D.SHAPE_V2, workloadScale=1.5, loadSeconds=60, hotFactor=1, driverPlan=plan)
        projected, = driver_accounting.expected_plans(dict(tenants=len(rows), history=spec, cadence=cadence))
        measured = evaluate(annotated, {**self.env, 'M7_WORKLOAD_SCALE': '1.5', 'M7_DRIVER_PLAN': json.dumps(plan)})['scenarios']
        for name, row in measured.items():
            self.assertEqual((row['rate'], row['timeUnit']), (projected['scenarios'][name]['rate'], projected['scenarios'][name]['timeUnit']), name)

    def test_env_fits_one_environment_string(self):
        self.assertLess(len(self.env['M7_LOOPING_TEMPLATES']), D.V2_ENV_MAX_BYTES)

    def test_v1_and_default_unchanged(self):
        rows = D.annotate(SPEC1, roster(100), roster(100))
        s = evaluate(rows, D.environment(D.SHAPE))['scenarios']
        looping = sum(1 for r in rows if r['loopKind'])
        self.assertEqual((s['w_devicestatus']['rate'], s['w_devicestatus']['timeUnit']), (looping, '300000ms'))
        s = evaluate(roster(100), {})['scenarios']
        self.assertEqual((s['w_devicestatus']['rate'], s['w_treatments_v3']['timeUnit']), (100, '1800000ms'))


class Backlog(unittest.TestCase):
    def setUp(self):
        self.rows = D.annotate(SPEC2, roster(1000), roster(1000))

    def check_steady_has_no_backlog(self, env):
        self.assertFalse(any(k.startswith('M7_BACKLOG') for k in env), 'BACKLOG_IN_STEADY_ENV')
        source = (Path(adapter.ROOT) / 'tools/mt-bench/capacity/k6/workload.js').read_text()
        self.assertNotIn('backlog', source.lower())
        s = evaluate(self.rows, env)['scenarios']
        self.assertEqual(set(s), {'w_sgv', 'w_devicestatus', 'w_treatments_v3', 'r_sgv', 'r_devicestatus', 'r_treatments', 'r_status'})
        measured = sum(1000 * v['rate'] / int(v['timeUnit'].removesuffix('ms')) for v in s.values())
        self.assertAlmostEqual(measured, D.offered(SPEC2, 1000)['total'], places=3)

    def test_backlog_not_in_steady_load(self):
        self.check_steady_has_no_backlog(D.environment(D.SHAPE_V2))

    def test_red_backlog_in_steady_load(self):
        chosen = looping_backlog.select(SPEC2, self.rows, 1.0)
        leaked = {**D.environment(D.SHAPE_V2), **looping_backlog.environment(chosen)}
        with self.assertRaises(AssertionError):
            self.check_steady_has_no_backlog(leaked)
        # a backlog's extra posts folded into the steady rate (Loop's treatment slot at twice the rate)
        with self.assertRaises(AssertionError):
            self.check_steady_has_no_backlog({**D.environment(D.SHAPE_V2), 'M7_LOOPING_TREATMENT_CYCLE_MS': '200000'})

    def check_backlog_shapes(self, out, chosen):
        kinds = {r['token']: r['loopKind'] for r in self.rows}
        by = collections.defaultdict(list)
        for p in out['posts']:
            by[kinds[p['token']]].append(p)
        per = {k: looping_backlog.expected_requests(k) for k in L.KINDS}
        n = collections.Counter(self.rows[i]['loopKind'] for i in chosen)
        for k in L.KINDS:
            self.assertEqual(len(by[k]), n[k] * per[k]['requests'] if k != 'aaps' else len(by[k]), k)
        aaps = by['aaps']
        if n['aaps']:
            self.assertTrue(380 <= len(aaps) / n['aaps'] <= 420, len(aaps) / n['aaps'])   # about 400 single documents
            self.assertTrue(all(p['docs'] == 1 and p['path'].startswith('/api/v3/') for p in aaps))
        if n['loop']:
            self.assertEqual(len(by['loop']) / n['loop'], 10)
            big = [p['bytes'] for p in by['loop']]
            self.assertTrue(20_000 <= sorted(big)[len(big) // 2] <= 55_000, sorted(big))   # 25-50 KB each
        if n['trio']:
            self.assertEqual(len(by['trio']) / n['trio'], 5)
            self.assertTrue(all(p['docs'] <= 100 for p in by['trio']))
            self.assertEqual(sum(p['path'] == '/api/v1/devicestatus' for p in by['trio']), n['trio'])  # latest only

    def test_backlog_scenario_shapes(self):
        chosen = looping_backlog.select(SPEC2, self.rows, 1.0)
        self.assertEqual(len(chosen), 10)                        # 1 % of 1,000
        self.assertTrue(all(self.rows[i]['loopKind'] for i in chosen))
        self.assertEqual(len(looping_backlog.select(SPEC2, self.rows, 0.5)), 5)
        with self.assertRaisesRegex(ValueError, 'BACKLOG_PERCENT'):
            looping_backlog.select(SPEC2, self.rows, 5)
        env = {**looping_backlog.environment(chosen), 'RUN_START': '1763683200000'}
        script = Path(__file__).resolve().with_name('looping-backlog.js')
        out = evaluate(self.rows, env, [('backlog', len(chosen))], script=script)
        self.assertEqual(out['scenarios']['backlog']['executor'], 'per-vu-iterations')
        self.check_backlog_shapes(out, chosen)
        plan = looping_backlog.plan(SPEC2, self.rows, 1.0)
        self.assertEqual(plan['selected'], chosen)

    def test_red_backlog_scenario_shapes(self):
        chosen = looping_backlog.select(SPEC2, self.rows, 1.0)
        env = {**looping_backlog.environment(chosen), 'RUN_START': '1763683200000'}
        script = Path(__file__).resolve().with_name('looping-backlog.js')
        # Loop's statuses one per POST instead of 25 per POST
        out = evaluate(self.rows, env, [('backlog', len(chosen))], [('chunks(statuses, 25)', 'chunks(statuses, 1)')], script=script)
        with self.assertRaises(AssertionError):
            self.check_backlog_shapes(out, chosen)


class HistoryV2(unittest.TestCase):
    def setUp(self):
        self.anchor = int(time.time() * 1000) // h.STEP_MS * h.STEP_MS - h.STEP_MS
        self.spec = V.default_spec(self.anchor)
        self.tenants = [{'id': f'00000000-0000-4000-8000-{i:012d}', 'host': f'demo-{i:02d}.test', 'token': f'local /{i}'}
                        for i in range(12)]
        self.store, self.calls = {}, []

    def save(self, port, tenant, body, until, path='/api/v1/entries'):
        rows = body if isinstance(body, list) else [body]
        self.calls.append((tenant['id'], path, len(rows), len(json.dumps(body))))
        self.store.setdefault(tenant['id'], {}).setdefault(path, []).extend(copy.deepcopy(rows))

    def sql(self, query):
        if 'FROM pg_class' in query:
            return '\n'.join(f'{t}\tnsdemo_{t}' for t in ('entries', 'devicestatus', 'treatments', 'profile'))
        if query.startswith('SELECT DISTINCT'):
            return ''
        out = []
        for tenant, paths in self.store.items():
            e = paths.get('/api/v1/entries', []); d = paths.get('/api/v1/devicestatus', [])
            t = paths.get('/api/v1/treatments', []); p = paths.get('/api/v1/profile', [])
            if V.DEVICE not in query:
                continue
            if '"nsdemo_entries"."entries"' in query and e:
                out.append([tenant, len(e), len(json.dumps(e)), len(e), h.digest(sorted(e, key=lambda r: r['date']))])
            elif '"nsdemo_devicestatus"' in query and d:
                out.append([tenant, len(d), len(json.dumps(d)), sum(r['uploader']['battery'] for r in d)])
            elif '"nsdemo_treatments"' in query and t:
                out.append([tenant, len(t), len(json.dumps(t)), round(sum(r.get('insulin', 0) for r in t) * 100),
                            sum(r.get('carbs', 0) for r in t)])
            elif '"nsdemo_profile"' in query and p:
                out.append([tenant, len(p), len(json.dumps(p))])
        return '\n'.join('\t'.join(map(str, r)) for r in out)

    def fixture(self, **changes):
        options = dict(spec=self.spec, tenants=self.tenants, base='http://127.0.0.1:8000', sql=self.sql, until=None,
                       window_seconds=300, post_batch=self.save)
        return h.run(**(options | changes))

    def red(self, test, *patches):
        with unittest.mock.patch.multiple(V, **dict(patches)):
            with self.assertRaises(AssertionError):
                test()

    def sample(self, kind_):
        return V._sample(self.spec, 'looping', kind_) if kind_ != 'cgm' else V._sample(self.spec, 'cgm-only', 'cgm')

    # ranks 1-2: per-controller devicestatus rows and bytes, treatments per day and mix
    def check_rows_and_bytes(self):
        want_ds = dict(loop=(390, 1350, 1650), trio=(576, 3350, 3900), aaps=(288, 2500, 3100), cgm=(288, 60, 200))
        for k, (per_day, low, high) in want_ds.items():
            t = self.sample(k)
            ds = V.devicestatus(t)
            self.assertAlmostEqual(len(ds) / 2, per_day, delta=1.5, msg=k)
            mean = sum(len(json.dumps(d, separators=(',', ':'))) for d in ds) / len(ds)
            self.assertTrue(low <= mean <= high, (k, mean))
            self.assertEqual(len(ds), V.rows_per_tenant(self.spec, 'cgm-only' if k == 'cgm' else 'looping', None if k == 'cgm' else k)['devicestatus'])
        trio = V.devicestatus(self.sample('trio'))
        self.assertTrue(all('suggested' in d['openaps'] and 'enacted' in d['openaps'] for d in trio))
        for k, (low, high) in dict(loop=(225, 250), trio=(225, 250), aaps=(205, 225)).items():
            tx = V.treatments(self.sample(k))
            self.assertTrue(low <= len(tx) / 2 <= high, (k, len(tx)))
            mix = collections.Counter(d['eventType'] for d in tx)
            self.assertEqual(mix['Temp Basal'], 2 * V.DAY[k]['tempBasal'])
        cgm = V.treatments(self.sample('cgm'))
        self.assertEqual(len(cgm), 4)

    def test_rows_and_bytes_per_controller(self):
        self.check_rows_and_bytes()

    def test_red_rows_and_bytes(self):
        # v1's devicestatus (one per cycle for every controller) and v1's treatment mix
        self.red(self.check_rows_and_bytes, ('STATUS', dict(loop=lambda t, i, iso, w: L._loop(t, i, iso, w == 'loop'),
                                                            trio=lambda t, i, iso, w: L._oref(t, i, iso, True),
                                                            aaps=V._aaps_status, cgm=V._cgm_status)))
        self.red(self.check_rows_and_bytes, ('DAY', dict(V.DAY, loop=dict(tempBasal=144, bolus=3, carbs=3, override=1))))

    # ranks 3-5: Profile Switch only for AAPS (one, older), one profile per store, CGM-only without profile
    def check_profiles_and_switches(self):
        for k in L.KINDS:
            t = self.sample(k)
            switches = [d for d in V.treatments(t) if d['eventType'] == 'Profile Switch']
            if k == 'aaps':
                self.assertEqual(len(switches), 1)
                age = self.anchor - V._ms(switches[0]['created_at'])
                self.assertTrue(2 * V.DAY_MS < age < 372 * V.DAY_MS, age)
            else:
                self.assertEqual(switches, [])
            docs = V.profiles(t)
            self.assertEqual(len(docs), {'loop': 2, 'trio': 1, 'aaps': 1}[k])
            for d in docs:
                self.assertEqual(list(d['store']), [d['defaultProfile']])
                self.assertTrue(1800 <= len(json.dumps(d, separators=(',', ':'))) <= 2900)
        roles = V.seed_roles(self.spec, 1000)
        cgm = roles.count('cgm-only') + roles.count('cgm-only-no-profile')
        self.assertEqual(cgm, 200)
        self.assertEqual(roles.count('cgm-only-no-profile'), 100)   # the stated share: 50 %
        self.assertEqual(V.profiles(V.Tenant(self.spec, 0, 'cgm-only', profile=False)), [])

    def test_profiles_switches_and_cgm_only_share(self):
        self.check_profiles_and_switches()

    def test_red_profiles_switches(self):
        self.red(self.check_profiles_and_switches, ('PROFILES', dict(loop=3, trio=3, aaps=3, cgm=1)))
        self.red(self.check_profiles_and_switches, ('AAPS_SWITCH_AGE_DAYS', 1))

    # the seed posts the profile FIRST
    def check_profile_first(self):
        self.fixture()
        first = {}
        for tenant, path, *_ in self.calls:
            first.setdefault(tenant, path)
        roles = V.seed_roles(self.spec, len(self.tenants))
        ordered = sorted(self.tenants, key=lambda r: r['host'])
        for i, tenant in enumerate(ordered):
            want = '/api/v1/entries' if roles[i] == 'cgm-only-no-profile' else '/api/v1/profile'
            self.assertEqual(first[tenant['id']], want, roles[i])

    def test_profile_posted_first(self):
        self.check_profile_first()

    def test_red_profile_first(self):
        v1_order = lambda t: (('/api/v1/entries', V.entries(t)), ('/api/v1/devicestatus', V.devicestatus(t)),
                              ('/api/v1/treatments', V.treatments(t)), ('/api/v1/profile', V.profiles(t)))
        self.red(self.check_profile_first, ('seed_requests', v1_order))

    # fixture key and marker distinct from v1; v1 unchanged
    def check_own_key(self):
        a, b = L.default_spec(self.anchor), V.default_spec(self.anchor)
        ka = fixture_catalog.digest(fixture_catalog.key(**BASE_KEY, history=a))
        kb = fixture_catalog.digest(fixture_catalog.key(**BASE_KEY, history=b))
        self.assertNotEqual(ka, kb)
        self.assertEqual(h.default_spec(h.MODE_LOOPING_V2, self.anchor), b)
        self.assertEqual(h.default_spec(h.MODE_LOOPING, self.anchor), a)
        self.assertEqual(len({L.DEVICE, V.DEVICE, h.DEVICE, h.DEVICE_2D, h.DEVICE_4W}), 5)
        t = V.Tenant(b, 0, 'looping')
        self.assertEqual({r['device'] for r in V.entries(t)}, {V.DEVICE})
        self.assertTrue(all(d['device'].endswith(V.DEVICE) for d in V.devicestatus(t)))
        self.assertEqual({r['enteredBy'] for r in V.treatments(t) + V.profiles(t)}, {V.DEVICE})

    def test_fixture_key_distinct_from_v1(self):
        self.check_own_key()

    def test_red_fixture_key(self):
        self.red(self.check_own_key, ('DEVICE', L.DEVICE))
        self.red(self.check_own_key, ('default_spec', lambda anchor, **_: L.default_spec(anchor)))

    def test_validation(self):
        h.validate(self.spec)
        for bad, code in ((dict(self.spec, cgmOnlyWithoutProfilePercent=101), 'LOOPING_OPTIONS'),
                          (dict(self.spec, anchorUnixMs=self.anchor + 1), 'ANCHOR'),
                          ({k: v for k, v in self.spec.items() if k != 'cgmOnlyWithoutProfilePercent'}, 'UNSUPPORTED'),
                          (dict(L.default_spec(self.anchor), mode=V.MODE), 'UNSUPPORTED')):
            with self.assertRaisesRegex(ValueError, code):
                h.validate(bad)

    def check_representable(self):
        bad = []

        def walk(x, path):
            if isinstance(x, float) and (not math.isfinite(x) or (x == 0 and math.copysign(1, x) < 0)):
                bad.append(path)
            elif isinstance(x, dict):
                for k, v in x.items():
                    if not k or any(c in k for c in '.$\0'):
                        bad.append(path + '.' + k)
                    walk(v, path + '.' + k)
            elif isinstance(x, list):
                for v in x:
                    walk(v, path + '[]')
        spec = V.default_spec(1795308000000)
        make = V.tenant_factory(spec, 30)
        for i in range(30):
            t = make(i)
            for name, rows in (('entries', V.entries(t)), ('devicestatus', V.devicestatus(t)),
                               ('treatments', V.treatments(t)), ('profile', V.profiles(t))):
                for d in rows:
                    walk(d, name)
        self.assertEqual(sorted(set(bad)), [])

    def test_documents_representable_by_postgres_storage(self):
        self.check_representable()

    def test_red_representable(self):
        with unittest.mock.patch.multiple(L, _r1=lambda x: round(x, 1), _r2=lambda x: round(x, 2), _r4=lambda x: round(x, 4)), \
             unittest.mock.patch.multiple(V, _r1=lambda x: round(x, 1), _r2=lambda x: round(x, 2), _r4=lambda x: round(x, 4)):
            with self.assertRaises(AssertionError):
                self.check_representable()

    def test_identifiers_unique_and_storage_shaped(self):
        for k in L.KINDS:
            tx = V.treatments(self.sample(k))
            for field in ('syncIdentifier', 'id', 'identifier', '_id'):
                values = [d[field] for d in tx if field in d]
                self.assertEqual(len(values), len(set(values)), (k, field))
            # no two identity-less rows share created_at + eventType (the v1 fallback key)
            keys = [(d['created_at'], d['eventType']) for d in tx
                    if not any(d.get(f) for f in ('syncIdentifier', 'id', 'identifier', '_id'))]
            self.assertEqual(len(keys), len(set(keys)))
        share = {k: V.identity_share(self.sample(k)) for k in L.KINDS}
        self.assertTrue(share['loop'] < 0.01 and share['trio'] < 0.025 and share['aaps'] == 0, share)

    def test_seed_readback_restore_and_mismatch(self):
        receipt = self.fixture()
        roles = V.seed_roles(self.spec, len(self.tenants))
        make = V.tenant_factory(self.spec, len(self.tenants))
        for i, tenant in enumerate(sorted(self.tenants, key=lambda r: r['host'])):
            want = make(i).expected()
            got = self.store[tenant['id']]
            self.assertEqual(len(got.get('/api/v1/devicestatus', [])), want['devicestatus'])
            self.assertEqual(len(got.get('/api/v1/profile', [])), want['profile'])
        self.assertEqual(set(receipt['roles']), set(roles))
        restored = self.fixture(verify_only=True, tenants=self.tenants[::-1])
        self.assertEqual((restored['logicalSha256'], restored['seededBatches']), (receipt['logicalSha256'], 0))
        self.assertLess(max(c[3] for c in self.calls), 1024 * 1024)   # devicestatus parser limit: 1 MB (HTTP 413 seen)
        healthy = copy.deepcopy(self.store)
        key = sorted(self.tenants, key=lambda r: r['host'])[roles.index('looping')]['id']
        for mutate in (lambda: self.store[key]['/api/v1/devicestatus'].pop(),
                       lambda: self.store[key]['/api/v1/treatments'][4].update(carbs=1),
                       lambda: self.store[key].pop('/api/v1/profile')):
            mutate()
            with self.assertRaisesRegex(ValueError, 'M7_HISTORY_'):
                self.fixture(verify_only=True)
            self.store = copy.deepcopy(healthy)

    def test_window_rows(self):
        d = V.describe(self.spec, 10_000)
        w = {k: v['windowRows'] for k, v in d['perTenant'].items()}
        self.assertEqual(w['looping/trio']['devicestatus'], 576)
        self.assertEqual(w['looping/aaps']['devicestatus'], 288)
        self.assertAlmostEqual(w['looping/loop']['devicestatus'], 389, delta=2)
        self.assertEqual(w['looping/loop']['entries'], 576)
        self.assertEqual(w['looping/aaps']['treatments'], V.rows_per_tenant(self.spec, 'looping', 'aaps')['treatments'] - 1)
        self.assertEqual(w['cgm-only-no-profile/cgm']['profile'], 0)


if __name__ == '__main__':
    unittest.main()
