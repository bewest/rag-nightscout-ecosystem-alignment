"""simple-run-cleanup fixtures: one owned delete plus one absence check, no actors."""
import unittest

import run_cleanup as rc

NS, RID = 'ns-synth-k8s-20261118', 'k8s-20261118'
BINDING = 'clusterrolebinding.rbac.authorization.k8s.io/' + NS + '-vault-tokenreview'


class Cluster:
    """A recorded API server: Namespace plus labelled cluster-scoped objects."""
    def __init__(self, objects, leaks=()):
        self.objects, self.leaks, self.calls = set(objects), set(leaks), []
    def __call__(self, argv):
        self.calls.append(argv)
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
        self.assertEqual(verbs[0], ('delete', 'namespace'))
        self.assertIn('--wait=true', cluster.calls[0])
        self.assertEqual(cluster.calls[1][:2], ['delete', rc.CLUSTER_SCOPED])
        self.assertIn('nightscout.org/run-id=' + RID, cluster.calls[1])
        self.assertEqual([c[0] for c in cluster.calls], ['delete', 'delete', 'get', 'get'])

    def test_a_leftover_labelled_object_is_found_and_reported_as_a_failure(self):
        cluster = Cluster({'namespace/' + NS, BINDING}, leaks={BINDING})
        with self.assertRaises(rc.CleanupFailed) as caught:
            rc.cleanup(cluster, NS, RID)
        self.assertEqual(caught.exception.leftovers, [BINDING])

    def test_a_namespace_that_does_not_delete_is_a_failure(self):
        cluster = Cluster({'namespace/' + NS})
        cluster.__class__ = type('Stuck', (Cluster,), {'__call__': lambda self, argv: ('namespace/' + NS + '\n') if argv[:2] == ['get', 'namespace'] else ''})
        with self.assertRaises(rc.CleanupFailed):
            rc.cleanup(cluster, NS, RID)

    def test_only_a_synthetic_run_namespace_is_ever_deleted(self):
        for name in ('kube-system', 'default', 'nightscout-preview'):
            cluster = Cluster({'namespace/' + name})
            with self.assertRaisesRegex(RuntimeError, 'UNOWNED_NAME'):
                rc.cleanup(cluster, name, RID)
            self.assertEqual(cluster.calls, [])


if __name__ == '__main__':
    unittest.main()
