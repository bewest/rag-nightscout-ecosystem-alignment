import unittest

import edge_base


class EdgeBase(unittest.TestCase):
    POD = {'NS_CAMPAIGN_ATTACH_SCOPE': 'pod'}

    def test_loopback_always(self):
        self.assertTrue(edge_base.ok('http://127.0.0.1:41234', env={}))
        self.assertTrue(edge_base.ok('http://127.0.0.1:41234', seeding=True, env={}))

    def test_cluster_ip_only_from_the_controller_pod_and_never_for_seeding(self):
        self.assertFalse(edge_base.ok('http://10.245.3.7:8080', env={}))
        self.assertTrue(edge_base.ok('http://10.245.3.7:8080', env=self.POD))
        self.assertFalse(edge_base.ok('http://10.245.3.7:8080', seeding=True, env=self.POD))

    def test_refusals(self):
        for base in ('http://edge.ns.svc:8080', 'http://127.0.0.1:0', 'https://10.0.0.1:8080', 'http://10.0.0.1:8080/x',
                     'http://0.0.0.0:8080', 'http://127.0.0.2:8080', None, 'http://10.0.0.1:99999'):
            self.assertFalse(edge_base.ok(base, env=self.POD), base)

    def test_callers_use_the_predicate(self):
        from pathlib import Path
        here = Path(edge_base.__file__).parent
        for path, count in ((here / 'populated_history.py', 2), (here / 'looping_history.py', 1),
                            (here.parent / 'kubernetes/experiment.py', 1)):
            text = path.read_text()
            self.assertEqual(text.count('edge_base.ok('), count, path.name)
            self.assertNotIn(r"http://127\.0\.0\.1:[0-9]{1,5}', base", text, path.name)


if __name__ == '__main__':
    unittest.main()
