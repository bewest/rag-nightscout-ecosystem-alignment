"""Case supervisor: the decision, the one-delete-one-absence-check run, the RBAC narrowing, and (when a local kind cluster
named by CASE_SUPERVISOR_KIND_CONTEXT is present) the real Job. Synthetic names only."""
import json
import os
import subprocess
import unittest

import case_supervisor as cs
import run_cleanup

NS, RID = 'case-a', 'run-1'


class Decide(unittest.TestCase):
    def test_reasons(self):
        self.assertIsNone(cs.decide(100, 200, {}, 600))
        self.assertEqual(cs.decide(200, 200, {}, 600), 'deadline')
        self.assertEqual(cs.decide(100, 200, {cs.RELEASED: 'true'}, 600), 'released')
        self.assertEqual(cs.decide(100, 200, {}, 600, present=False), 'namespace-absent')
        self.assertEqual(cs.decide(1000, 5000, {cs.HEARTBEAT: '100'}, 600), 'heartbeat-stale')
        self.assertIsNone(cs.decide(1000, 5000, {cs.HEARTBEAT: '900'}, 600), 'a fresh heartbeat waits')
        self.assertIsNone(cs.decide(1000, 5000, {}, 600), 'no heartbeat yet is not stale')


class Fake:
    """kubectl stand-in: one namespace carrying LABEL; delete removes it; records every call."""

    def __init__(self, label=RID, present=True, notes=None, undeletable=False):
        self.calls, self.label, self.present, self.notes, self.undeletable = [], label, present, notes or {}, undeletable

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[:2] == ['get', 'namespace'] and '-o' in argv and argv[-1] == 'json':
            return json.dumps({'metadata': {'annotations': self.notes}}) if self.present else ''
        if argv[:2] == ['get', 'namespace']:
            if argv[-1].startswith('jsonpath'):
                return self.label if self.present else ''
            return 'namespace/' + NS if self.present else ''
        if argv[:3] == ['delete', 'namespace', NS]:
            self.present = self.present and self.undeletable
            return ''
        return ''


class Supervise(unittest.TestCase):
    def run_it(self, fake, **kw):
        clock = iter(range(1000, 1100))
        return cs.supervise(NS, RID, 1002, 'sup', call=fake, clock=lambda: next(clock), sleep=lambda s: None, poll=1, **kw)

    def test_deadline_deletes_once_checks_once_and_records(self):
        fake = Fake()
        doc = self.run_it(fake)
        self.assertEqual((doc['verdict'], doc['reason']), ('CLEANED', 'deadline'))
        deletes = [c for c in fake.calls if c[0] == 'delete' and c[1] == 'namespace']
        self.assertEqual(len(deletes), 1)
        self.assertEqual(fake.calls[-1][:5], ['-n', 'sup', 'create', 'configmap', 'case-cleanup-' + RID])
        self.assertIn('"verdict": "CLEANED"', fake.calls[-1][-1])

    def test_a_namespace_without_this_runs_label_is_never_deleted(self):
        fake = Fake(label='someone-else')
        doc = self.run_it(fake)
        self.assertEqual(doc['verdict'], 'FAIL')
        self.assertEqual(doc['code'], 'K8S_CLEANUP_UNOWNED_NAME')
        self.assertFalse([c for c in fake.calls if c[:2] == ['delete', 'namespace']])

    def test_a_leftover_is_a_failure_never_a_pass(self):
        doc = self.run_it(Fake(undeletable=True))
        self.assertEqual((doc['verdict'], doc['code']), ('FAIL', 'K8S_CLEANUP_LEFTOVER'))

    def test_cluster_scoped_objects_are_deleted_by_name_never_by_selector(self):
        fake = Fake()
        self.run_it(fake, cluster_scoped_names=['clusterrolebinding/crb-x'])
        self.assertIn(['delete', 'clusterrolebinding', 'crb-x', '--ignore-not-found=true'], fake.calls)
        self.assertFalse([c for c in fake.calls if c[0] == 'delete' and '-l' in c])

    def test_a_delete_that_times_out_is_judged_by_the_absence_check(self):
        class Slow(Fake):
            def __call__(self, argv):
                if argv[:3] == ['delete', 'namespace', NS]:
                    self.calls.append(argv)
                    self.present = False          # gone by the time the check runs
                    raise subprocess.CalledProcessError(1, argv)
                return super().__call__(argv)
        self.assertEqual(self.run_it(Slow())['verdict'], 'CLEANED')
        stuck = Fake(undeletable=True)
        stuck.__class__ = type('Stuck', (Fake,), {'__call__': lambda self, argv: (_ for _ in ()).throw(subprocess.CalledProcessError(1, argv)) if argv[:2] == ['delete', 'namespace'] else Fake.__call__(self, argv)})
        self.assertEqual(self.run_it(stuck)['code'], 'K8S_CLEANUP_LEFTOVER')

    def test_an_already_absent_namespace_is_confirmed_absent(self):
        doc = self.run_it(Fake(present=False))
        self.assertEqual((doc['verdict'], doc['reason']), ('CLEANED', 'namespace-absent'))


class Render(unittest.TestCase):
    def test_rbac_is_narrowed_to_the_one_namespace(self):
        items = cs.render(NS, RID, 'img:1', 2000000000, 'sup', cluster_scoped_names=['clusterrolebinding/crb-x'])['items']
        role = next(i for i in items if i['kind'] == 'ClusterRole')
        ns_rule = next(r for r in role['rules'] if r['resources'] == ['namespaces'])
        self.assertEqual((ns_rule['resourceNames'], ns_rule['verbs']), ([NS], ['get', 'delete']))
        deletes = [r for r in role['rules'] if 'delete' in r['verbs']]
        self.assertTrue(all(r.get('resourceNames') for r in deletes), 'no unnamed delete')
        self.assertEqual(next(r for r in deletes if r['resources'] == ['clusterrolebindings'])['resourceNames'], ['crb-x'])
        job = next(i for i in items if i['kind'] == 'Job')
        self.assertIn(RID, ' '.join(job['spec']['template']['spec']['containers'][0]['command']))
        self.assertNotIn(run_cleanup.LABEL, job['metadata']['labels'], 'the absence check lists by the run label and must not find the supervisor')
        self.assertTrue(all(run_cleanup.LABEL not in i['metadata'].get('labels', {}) for i in items))


KIND = os.environ.get('CASE_SUPERVISOR_KIND_CONTEXT')


@unittest.skipUnless(KIND and KIND.startswith('kind-'), 'set CASE_SUPERVISOR_KIND_CONTEXT=kind-<name> (a local kind cluster with the supervisor image loaded as CASE_SUPERVISOR_IMAGE)')
class Kind(unittest.TestCase):
    def k(self, *argv, check=True, stdin=None):
        return subprocess.run(['kubectl', '--context', KIND, *argv], capture_output=True, text=True, input=stdin, check=check, timeout=120)

    def launch(self, run, label, delay):
        import time
        ns = 'case-' + run
        self.k('create', 'namespace', ns)
        if label:
            self.k('label', 'namespace', ns, run_cleanup.LABEL + '=' + label)
        self.k('-n', ns, 'create', 'configmap', 'payload', '--from-literal=a=b')
        manifest = cs.render(ns, run, os.environ['CASE_SUPERVISOR_IMAGE'], time.time() + delay, 'case-supervisors', grace=600)
        # The workstation's only act is this apply; after it nothing else touches the case.
        self.k('apply', '-f', '-', stdin=json.dumps(manifest))
        return ns

    def wait_job(self, run, seconds=150):
        import time
        end = time.time() + seconds
        while time.time() < end:
            st = json.loads(self.k('-n', 'case-supervisors', 'get', 'job', 'case-supervisor-' + run, '-o', 'json').stdout)['status']
            if st.get('succeeded') or st.get('failed'):
                return st
            time.sleep(2)
        self.fail('supervisor job did not finish')

    @classmethod
    def setUpClass(cls):
        subprocess.run(['kubectl', '--context', KIND, 'create', 'namespace', 'case-supervisors'], capture_output=True)

    def test_owned_namespace_is_removed_at_the_deadline_without_the_controller(self):
        ns = self.launch('kind-own', 'kind-own', 10)
        self.assertTrue(self.wait_job('kind-own').get('succeeded'))
        self.assertEqual(self.k('get', 'namespace', ns, '--ignore-not-found', '-o', 'name').stdout.strip(), '')
        doc = json.loads(json.loads(self.k('-n', 'case-supervisors', 'get', 'configmap', 'case-cleanup-kind-own', '-o', 'json').stdout)['data']['result'])
        self.assertEqual((doc['verdict'], doc['absent']), ('CLEANED', True))
        self.assertIn(doc['reason'], ('deadline', 'namespace-absent'), 'a retry after a slow delete sees it absent')

    def test_a_namespace_that_is_not_this_runs_is_left_alone_and_the_refusal_is_recorded(self):
        import time
        ns = self.launch('kind-foreign', 'other-run', 5)
        end = time.time() + 120
        while time.time() < end:
            r = self.k('-n', 'case-supervisors', 'get', 'configmap', 'case-cleanup-kind-foreign', '-o', 'json', check=False)
            if r.returncode == 0:
                break
            time.sleep(2)
        doc = json.loads(json.loads(r.stdout)['data']['result'])
        self.assertEqual((doc['verdict'], doc['code']), ('FAIL', 'K8S_CLEANUP_UNOWNED_NAME'))
        self.assertEqual(self.k('get', 'namespace', ns, '-o', 'name').stdout.strip(), 'namespace/' + ns)
        self.k('delete', 'namespace', ns, '--wait=false')


if __name__ == '__main__':
    unittest.main()
