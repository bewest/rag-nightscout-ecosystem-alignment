"""Outcome evaluator gate: synthetic fixtures and in-memory break-it controls.

Every classifier branch has a control. Each control first runs green on the
real module, then on an in-memory ablation of exactly that branch (the source
file is never modified) where it must go red with the named symptom, then
green again on the real module.
"""
import copy
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

import evaluator_progress as p
import outcome_gate as g
from test_evaluator_progress import A, B

R = '33333333-3333-4333-8333-333333333333'
IDS = [A, B]


def row(tenant, *, failed=0, reasons=None, unresolved=None, resolution=None, ready=True, code=None,
        alert=None, admitted=True, omit=()):
    progress = {'generation':1, 'completedAcquisitions':3, 'completedTimeCycles':0,
                'failedCompletions':failed, 'lastCompletedAgeMs':5}
    if reasons is not None:
        progress['failureReasons'] = reasons
    progress['unresolvedFailure'] = unresolved
    progress['maxFailureResolutionMs'] = resolution
    for key in omit:
        progress.pop(key)
    return {'tenant':tenant, 'admitted':admitted, 'ready':ready, 'code':code, 'evaluation':{'alert':alert},
            'cycles':3, 'progress':progress, 'jobs':dict.fromkeys(p.JOB_FLAGS, False), 'dueAt':None, 'dueReason':None}


def page(rows, *, typed=True, runtime=R):
    view = {'kind':'evaluator', 'runtimeId':runtime, 'configured':{'ordinal':0, 'mode':'single'},
            'gate':{'eligible':True, 'reason':None}, 'tenants':rows}
    if typed:
        view['failureReasonContract'] = g.TYPED_CONTRACT
    return (json.dumps({'selected':[r['tenant'] for r in rows], 'selfOrdinal':0, 'selfMode':'single',
                        'view':view}) + '\n').encode()


def point(*rows, typed=True, runtime=R):
    return g.from_pages({'evaluator':page(list(rows), typed=typed, runtime=runtime)})


HEALTHY = lambda: row(B)
FIXTURES = {
    # name: (rows builder, typed, final, expected verdict, expected code or class)
    'transient-completed': (lambda: [row(A, failed=2, reasons={'verification-pending':1, 'startup-warming':1},
                                          resolution=4000), HEALTHY()], True, True, 'PASS', 'TRANSIENT_COMPLETED'),
    'transient-past-deadline': (lambda: [row(A, failed=1, reasons={'verification-pending':1},
                                              unresolved={'reason':'verification-pending', 'ageMs':130000}), HEALTHY()],
                                True, True, 'FAIL', 'M7_OUTCOME_TRANSIENT_DEADLINE'),
    'transient-resolved-late': (lambda: [row(A, failed=1, reasons={'startup-warming':1}, resolution=150000), HEALTHY()],
                                True, True, 'FAIL', 'M7_OUTCOME_TRANSIENT_DEADLINE'),
    'untyped-old-payload': (lambda: [row(A, failed=3), HEALTHY()], False, True, 'FAIL', 'M7_OUTCOME_UNTYPED_FAILURE'),
    'untyped-declared-unknown': (lambda: [row(A, failed=1, reasons={'unknown':1}, resolution=10), HEALTHY()],
                                 True, True, 'FAIL', 'M7_OUTCOME_UNTYPED_FAILURE'),
    'hard-reason': (lambda: [row(A, failed=1, reasons={'worker-unavailable':1}, resolution=10), HEALTHY()],
                    True, True, 'FAIL', 'M7_OUTCOME_HARD_FAILURE'),
    'missing-reason-field': (lambda: [row(A, failed=1), HEALTHY()], True, True, 'UNMEASURED', 'M7_OUTCOME_REASON_MISSING'),
    'missing-resolution-field': (lambda: [row(A, failed=1, reasons={'verification-pending':1},
                                               omit=('maxFailureResolutionMs',)), HEALTHY()],
                                 True, True, 'UNMEASURED', 'M7_OUTCOME_RESOLUTION_MISSING'),
    'malformed-resolution': (lambda: [row(A, failed=1, reasons={'verification-pending':1}, resolution=-5), HEALTHY()],
                             True, True, 'UNMEASURED', 'M7_OUTCOME_RESOLUTION_MISSING'),
    'foreign-scope': (lambda: [row(A, failed=1, reasons={'scope-mismatch':1}, resolution=10), HEALTHY()],
                      True, True, 'FAIL', 'M7_OUTCOME_HARD_FAILURE'),
    'foreign-ready': (lambda: [row(A), HEALTHY(), row(R, admitted=False, ready=True)], True, True, 'FAIL',
                      'M7_OUTCOME_FOREIGN_READY'),
    'clinical-alert': (lambda: [row(A, alert='SYNTHETIC_ALERT'), HEALTHY()], True, True, 'FAIL', 'M7_OUTCOME_CLINICAL_ALERT'),
    'transient-pending-final': (lambda: [row(A, failed=1, reasons={'startup-warming':1},
                                              unresolved={'reason':'startup-warming', 'ageMs':3000}), HEALTHY()],
                                True, True, 'UNMEASURED', 'M7_OUTCOME_TRANSIENT_UNRESOLVED'),
}
# The foreign row's tenant is outside the roster; classify on the roster only.
FOREIGN_IDS = [A, B]


def classify(module, name):
    build, typed, final, _, _ = FIXTURES[name]
    rows = build()
    if name == 'foreign-ready':
        rows[2]['tenant'] = A  # same id on a second service row is not used; keep roster
        built = module.from_pages({'evaluator':page(rows[:2], typed=typed),
                                   'evaluator-2':page([row(A, admitted=False, ready=True),
                                                       row(B, admitted=False)], typed=typed,
                                                      runtime='44444444-4444-4444-8444-444444444444')})
    else:
        built = module.from_pages({'evaluator':page(rows, typed=typed)})
    return module.classify_point(built, IDS, final=final)


def matches(result, name):
    _, _, _, verdict, marker = FIXTURES[name]
    return result['verdict'] == verdict and (marker in result['codes'] or marker in result['classes'])


class Fixtures(unittest.TestCase):
    def test_every_fixture_matches_its_expected_class(self):
        for name in FIXTURES:
            with self.subTest(name):
                result = classify(g, name)
                self.assertTrue(matches(result, name), (name, result['verdict'], result['codes'], result['classes']))

    def test_transient_completed_is_counted_by_reason(self):
        result = classify(g, 'transient-completed')
        self.assertEqual(result['failedCompletionsByReason'], {'verification-pending':1, 'startup-warming':1})
        self.assertEqual(result['classes']['TRANSIENT_COMPLETED'], 1)

    def test_midpoint_transient_continues_and_hard_stops(self):
        pending = g.classify_point(point(row(A, failed=1, reasons={'startup-warming':1},
                                            unresolved={'reason':'startup-warming', 'ageMs':3000}),
                                         row(B, ready=False, code='EVALUATOR_STARTING')), IDS, final=False)
        self.assertEqual(g.midpoint_decision(pending)['action'], 'continue')
        hard = g.classify_point(point(row(A, failed=1), HEALTHY(), typed=False), IDS, final=False)
        self.assertEqual(g.midpoint_decision(hard)['action'], 'stop')
        self.assertEqual(g.midpoint_decision(None)['action'], 'continue')

    def test_legacy_fixed_tenant_targets_cannot_establish_input_coverage(self):
        self.assertEqual(g.catchup({'byTenant': {A:{'status':'COMPLETED'}}}, IDS)['verdict'], 'UNMEASURED')

    def judged(self, **overrides):
        values = dict(ids=IDS, points={'before':point(row(A), HEALTHY()), 'midpoint':None,
                                       'after':point(row(A), HEALTHY())},
                      storage_findings={'verdict':'GREEN', 'uncertain':0, 'failureCount':0,
                          'rows':[{'tenant':A, 'accepted':1,'probeAccepted':0},{'tenant':B,'accepted':0,'probeAccepted':0}]},
                      completed_output={'verdict':'PASS', 'witnesses':[{'clinicalTiming':{'verdict':'PASS'}}],
                             'clinicalTiming':{'contract':'clinical-deadline-from-acceptance-v1','witnesses':1}},
                      catchup_value={'kind':'accepted-input-drain-v1','verdict':'PASS','deadlineMs':120000,
                                     'acceptedInputs':1, 'inputs':[{'tenant': A, 'status':'ON_TIME'}]})
        values.update(overrides)
        return g.judge(**values)

    def test_judge_pass_needs_every_component_and_missing_is_unmeasured(self):
        self.assertEqual(self.judged()['verdict'], 'PASS')
        for key in ('storage_findings', 'completed_output', 'catchup_value'):
            with self.subTest(key):
                self.assertEqual(self.judged(**{key:None})['verdict'], 'UNMEASURED')
        self.assertEqual(self.judged(points={'before':point(row(A), HEALTHY()), 'after':None})['verdict'], 'UNMEASURED')
        self.assertEqual(self.judged(storage_findings={'verdict':'RED', 'failureCount':1})['verdict'], 'FAIL')

    def test_judge_untyped_failure_fails_and_transient_completed_passes(self):
        old = point(row(A, failed=3), HEALTHY(), typed=False)
        self.assertEqual(self.judged(points={'before':old, 'after':old})['verdict'], 'FAIL')
        typed = point(row(A, failed=1, reasons={'verification-pending':1}, resolution=900), HEALTHY())
        result = self.judged(points={'before':typed, 'after':typed})
        self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['components']['failedCompletions']['failedCompletionsByReason'], {'verification-pending':1})

    def test_runtime_reset_and_foreign_work_fail(self):
        moved = point(row(A), HEALTHY(), runtime='44444444-4444-4444-8444-444444444444')
        self.assertEqual(self.judged(points={'before':point(row(A), HEALTHY()), 'after':moved})['verdict'], 'FAIL')

    def test_decoded_round_is_read_as_untyped(self):
        decoded = {'instances':{'evaluator':{'runtimeId':R}},
                   'allRows':{'evaluator':{A:{'admitted':True, 'ready':True, 'code':None, 'alert':None,
                                              'failedCompletions':3, 'completedAcquisitions':2}}}}
        result = g.classify_point(g.from_decoded(decoded), [A], final=True)
        self.assertEqual(result['classes'], {'UNTYPED':1})

    def test_http_latency_reads_every_shard(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for index, (count, avg, p95) in enumerate(((10, 10.0, 20.0), (30, 20.0, 40.0), (60, 30.0, 35.0))):
                metric = {'count':count, 'avg':avg, 'med':avg, 'p(90)':p95, 'p(95)':p95, 'p(99)':p95 + 1, 'max':p95 + 2}
                (folder / ('k6-summary-%d.json' % index)).write_text(json.dumps({'metrics':{
                    'http_req_duration':metric, 'http_req_duration{shape:w_sgv}':metric}}))
            (folder / 'k6-summary.json').write_text(json.dumps({'metrics':{}}))
            value = g.http_latency(folder)
            pooled = value['pooled']['all']
            self.assertEqual(value['shardCount'], 3)
            self.assertEqual(pooled['count'], 100)
            self.assertAlmostEqual(pooled['mean'], (100 + 600 + 1800) / 100)
            self.assertEqual(pooled['p(95)ShardRange'], [20.0, 40.0])
            self.assertEqual(pooled['pooledQuantiles'], 'UNMEASURED; no raw samples')

    def test_instrument_identity_is_file_bytes_not_configuration(self):
        import hashlib
        identity = g.instrument()
        self.assertEqual(identity['sha256'], hashlib.sha256(b'\0'.join(path.read_bytes() for path in (Path(g.__file__),
            Path(g.accepted_inputs.__file__),Path(g.__file__).with_name('accepted-inputs.sql')))).hexdigest())
        a = self.judged()['instrument']
        b = self.judged(config={'deadlineMs':60000})
        self.assertEqual(a, b['instrument'])
        self.assertEqual(b['configuration']['deadlineMs'], 60000)


class StrictReaders(unittest.TestCase):
    def rounds(self, failed):
        def one(count):
            owners = {t:{'service':'evaluator', 'runtimeId':R, 'generation':1, 'completedAcquisitions':1 + count,
                         'completedTimeCycles':0, 'failedCompletions':failed if t == A else 0, 'legacyCycles':1,
                         'lastCompletedAgeMs':1, 'admitted':True, 'ready':True, 'code':None, 'alert':None,
                         'dueAt':None, 'dueReason':None, 'jobState':None} for t in IDS}
            return {'instances':{'evaluator':{'runtimeId':R, 'ordinal':0}}, 'owners':owners,
                    'allRows':{'evaluator':copy.deepcopy(owners)}, 'queries':1, 'bytes':1, 'wallSeconds':0}
        return [one(0), one(1), one(2)]

    def test_outcome_policy_counts_failed_completions_and_refuses_unknown_policy(self):
        value = p.assess(self.rounds(1), IDS, 'load', failure_policy=p.OUTCOME_FAILURE_POLICY)
        self.assertEqual(value['lifetimeFailedCompletions'], 1)
        self.assertEqual(value['failurePolicy'], p.OUTCOME_FAILURE_POLICY)
        with self.assertRaisesRegex(p.Refused, 'FAILURE_POLICY'):
            p.assess(self.rounds(0), IDS, 'load', failure_policy='anything-else')

    def test_compose_raw_is_written_before_decode(self):
        import adapter
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            fetch = adapter.retain_raw(out, 'load', lambda service, *args: b'not json\n')
            with self.assertRaises(p.Refused):
                p.round_view(['evaluator'], IDS, fetch)
            raw = out / 'evaluator-progress-raw' / 'load-00-evaluator.private.jsonl'
            self.assertEqual(raw.read_bytes(), b'not json\n')
            self.assertEqual(raw.stat().st_mode & 0o777, 0o600)


class ObserverMidpoint(unittest.TestCase):
    """The shared Observer midpoint: signal continues, hard stops."""
    def observe(self, midpoint_page, judge=None):
        calls = []
        healthy = page([row(A), HEALTHY()])
        def fetch(service, *args):
            calls.append(service)
            return midpoint_page if len(calls) == 2 else healthy
        stopped, signals = [], []
        judge = judge or (lambda raw: g.midpoint_decision(g.classify_point(g.from_pages(raw), IDS, final=False)))
        observer = p.Observer(['evaluator'], IDS, fetch, 0, 'load', lambda value: None, midpoint_judge=judge,
                              signal_write=signals.append, on_hard_midpoint=lambda: stopped.append(True))
        observer.observe()
        observer.midpoint()
        return observer, stopped, signals

    def test_readiness_refusal_is_a_signal(self):
        observer, stopped, signals = self.observe(page([row(A, ready=False, code='EVALUATOR_STARTING'), HEALTHY()]))
        self.assertIsNone(observer.failure)
        self.assertEqual(stopped, [])
        self.assertEqual(signals[0]['action'], 'continue')
        self.assertEqual(signals[0]['strictRefusal']['code'], 'M7_EVALUATOR_PROGRESS_ERROR')

    def test_hard_reason_stops_even_when_strict_decode_passes(self):
        observer, stopped, signals = self.observe(page([row(A, failed=1), HEALTHY()], typed=False))
        self.assertEqual(str(observer.failure), 'M7_OUTCOME_MIDPOINT_HARD')
        self.assertEqual(stopped, [True])
        self.assertEqual(signals[0]['action'], 'stop')


# ------------------------------------------------------------ break-it controls

def ablated(needle, replacement):
    source = Path(g.__file__).read_text()
    if source.count(needle) != 1:
        raise AssertionError('control needle not unique: ' + needle)
    module = types.ModuleType('outcome_gate_ablated')
    module.__file__ = g.__file__
    exec(compile(source.replace(needle, replacement), 'outcome_gate_ablation', 'exec'), module.__dict__)
    return module


def fixture_check(name):
    return lambda module: matches(classify(module, name), name)


def midpoint_check(hard):
    def check(module):
        rows = (row(A, failed=1), HEALTHY()) if hard else (row(A, ready=False, code='EVALUATOR_STARTING'), HEALTHY())
        decision = module.midpoint_decision(module.classify_point(point(*rows, typed=not hard), IDS, final=False))
        return decision['action'] == ('stop' if hard else 'continue')
    return check


def missing_storage_check(module):
    return module.storage(None)['verdict'] == 'UNMEASURED'


def compose_drain_check(module):
    """A failure first visible in the end-of-drain catch-up inspection fails the run."""
    with tempfile.TemporaryDirectory() as temporary:
        load = Path(temporary) / 'load'
        load.mkdir()
        raw = load / 'evaluator-progress-raw'
        raw.mkdir()
        (raw/'load-00-evaluator.private.jsonl').write_bytes(page([row(A), HEALTHY()]))
        (raw/'drain-00-evaluator.private.jsonl').write_bytes(page([row(A, failed=1), HEALTHY()], typed=False))
        points = module.compose_points(load)
        return (points['endPoint'].startswith('end of drain') and
                module.classify_point(points['after'], IDS, final=True)['verdict'] == 'FAIL')


CONTROLS = {
    'untyped': ("        return 'UNTYPED', 'FAIL', 'M7_OUTCOME_UNTYPED_FAILURE', {'untyped': failed}",
                "        return 'TRANSIENT_COMPLETED', 'PASS', None, {}", fixture_check('untyped-old-payload')),
    'untyped-name': ("    if any(k in UNTYPED_NAMES for k in reasons):", "    if False:", fixture_check('untyped-declared-unknown')),
    'hard': ("    if any(k not in TRANSIENT for k in reasons):", "    if False:", fixture_check('hard-reason')),
    'foreign-scope': ("TRANSIENT = frozenset(('verification-pending', 'startup-warming'))",
                      "TRANSIENT = frozenset(('verification-pending', 'startup-warming', 'scope-mismatch'))",
                      fixture_check('foreign-scope')),
    'reason-missing': ("        return 'REASON_MISSING', 'UNMEASURED', 'M7_OUTCOME_REASON_MISSING', {}",
                       "        return 'NONE', 'PASS', None, {}", fixture_check('missing-reason-field')),
    'resolution-invalid': ("    if resolution is not None and not _finite(resolution):", "    if False:",
                           fixture_check('malformed-resolution')),
    'resolved-late': ("    if resolution is not None and resolution > deadline_ms:", "    if False:",
                      fixture_check('transient-resolved-late')),
    'unresolved-late': ("        if unresolved['ageMs'] > deadline_ms:", "        if False:",
                        fixture_check('transient-past-deadline')),
    'pending-final': ("        if final:\n            return 'TRANSIENT_PENDING', 'UNMEASURED'",
                      "        if False:\n            return 'TRANSIENT_PENDING', 'UNMEASURED'", fixture_check('transient-pending-final')),
    'transient-completed': ("    return 'TRANSIENT_COMPLETED', 'PASS', None, reasons",
                            "    return 'HARD', 'FAIL', 'M7_OUTCOME_HARD_FAILURE', reasons", fixture_check('transient-completed')),
    'foreign-ready': ("                    note('FAIL', 'M7_OUTCOME_FOREIGN_READY')", "                    pass",
                      fixture_check('foreign-ready')),
    'clinical-alert': ("                note('FAIL', 'M7_OUTCOME_CLINICAL_ALERT')", "                pass",
                       fixture_check('clinical-alert')),
    'midpoint-stop': ("    hard = classification['verdict'] == 'FAIL'", "    hard = False", midpoint_check(True)),
    'midpoint-continue': ("    hard = classification['verdict'] == 'FAIL'", "    hard = True", midpoint_check(False)),
    'compose-drain-end': ("'after': from_pages(terminal) if terminal else None",
                          "'after': ordered[0]", compose_drain_check),
    'missing-never-pass': ("        return {'verdict': 'UNMEASURED', 'codes': ['M7_OUTCOME_STORAGE_NOT_CAPTURED']}",
                           "        return {'verdict': 'PASS', 'codes': []}", missing_storage_check),
}


class BreakIt(unittest.TestCase):
    def test_each_branch_control_is_green_red_green(self):
        lines = []
        for name, (needle, replacement, check) in CONTROLS.items():
            with self.subTest(name):
                self.assertTrue(check(g), name + ': control not green on the real module')
                self.assertFalse(check(ablated(needle, replacement)), name + ': control stayed green when the branch was removed')
                self.assertTrue(check(g), name + ': control not green after restore')
                lines.append('RED_RESTORED outcome-gate ' + name)
        print('\n'.join(lines))


if __name__ == '__main__':
    unittest.main()
