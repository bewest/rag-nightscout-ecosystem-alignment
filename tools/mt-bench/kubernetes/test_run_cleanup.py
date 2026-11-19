"""simple-run-cleanup fixtures: one owned delete plus one absence check, no actors."""
import unittest

import run_cleanup as rc

NS, RID = 'ns-synth-k8s-20261118', 'k8s-20261118'
BINDING = 'clusterrolebinding.rbac.authorization.k8s.io/' + NS + '-vault-tokenreview'


class Cluster:
    """A recorded API server: Namespace plus labelled cluster-scoped objects."""
    def __init__(self, objects, leaks=(), owner=RID):
        self.objects, self.leaks, self.calls, self.owner = set(objects), set(leaks), [], owner
    def __call__(self, argv):
        self.calls.append(argv)
        if argv[:2] == ['get', 'namespace'] and argv[-1].startswith('jsonpath='):
            return self.owner if 'namespace/' + argv[2] in self.objects else ''
        if argv[:2] == ['delete', 'namespace']:
            self.objects -= {'namespace/' + argv[2]}
        elif argv[0] == 'delete':
            self.objects -= {o for o in self.objects if o.startswith('clusterrolebinding')} - self.leaks
        elif argv[:2] == ['get', 'namespace']:
            return ''.join(o + '\n' for o in self.objects if o == 'namespace/' + argv[2])
        elif argv[0] == 'get':
            return ''.join(o + '\n' for o in self.objects if o.startswith('clusterrolebinding'))
        return ''


class RunCleanup(unittest.TestCase):
    def test_namespace_delete_label_delete_and_one_absence_check(self):
        cluster = Cluster({'namespace/' + NS, BINDING})
        result = rc.cleanup(cluster, NS, RID)
        self.assertTrue(result['absent'])
        verbs = [(c[0], c[1]) for c in cluster.calls]
        self.assertEqual(verbs[1], ('delete', 'namespace'))
        self.assertIn('--wait=true', cluster.calls[1])
        self.assertEqual(cluster.calls[2][:2], ['delete', rc.CLUSTER_SCOPED])
        self.assertIn('nightscout.org/run-id=' + RID, cluster.calls[2])
        self.assertEqual([c[0] for c in cluster.calls], ['get', 'delete', 'delete', 'get', 'get'])

    def test_a_leftover_labelled_object_is_found_and_reported_as_a_failure(self):
        cluster = Cluster({'namespace/' + NS, BINDING}, leaks={BINDING})
        with self.assertRaises(rc.CleanupFailed) as caught:
            rc.cleanup(cluster, NS, RID)
        self.assertEqual(caught.exception.leftovers, [BINDING])

    def test_a_namespace_that_does_not_delete_is_a_failure(self):
        cluster = Cluster({'namespace/' + NS})
        stuck = lambda self, argv: (RID if argv[-1].startswith('jsonpath=') else 'namespace/' + NS + '\n') if argv[:2] == ['get', 'namespace'] else ''
        cluster.__class__ = type('Stuck', (Cluster,), {'__call__': stuck})
        with self.assertRaises(rc.CleanupFailed):
            rc.cleanup(cluster, NS, RID)

    def test_only_a_namespace_carrying_this_run_label_is_ever_deleted(self):
        # Any prefix is allowed; the run-id label is the ownership proof.
        for name in ('kube-system', 'default', 'nightscout-preview'):
            for owner in ('', 'another-run'):
                cluster = Cluster({'namespace/' + name}, owner=owner)
                with self.assertRaisesRegex(RuntimeError, 'UNOWNED_NAME'):
                    rc.cleanup(cluster, name, RID)
                self.assertFalse(any(c[0] == 'delete' for c in cluster.calls))
        cluster = Cluster({'namespace/smoke-' + RID})
        self.assertTrue(rc.cleanup(cluster, 'smoke-' + RID, RID)['absent'])


if __name__ == '__main__':
    unittest.main()
