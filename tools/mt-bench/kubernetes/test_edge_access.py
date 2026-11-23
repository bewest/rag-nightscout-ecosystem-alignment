import unittest

import edge_access


class EdgeAccess(unittest.TestCase):
    def test_in_cluster_controller_uses_the_edge_service(self):
        # A controller Pod reaches the case's edge Service directly; one kubectl port-forward does not carry
        # thousands of viewer sockets (lanel-c2-02: 13,000 requested, 8,167 connected, M7_VIEWER_SETUP_STALLED).
        self.assertEqual(edge_access.base_url('in-cluster', 'nominal-x-a1', 8080),
                         'http://edge.nominal-x-a1.svc.cluster.local:8080')

    def test_workstation_attached_runs_keep_the_port_forward(self):
        self.assertIsNone(edge_access.base_url('do-sfo2-do-helloworld', 'nominal-x-a1', 8080))
        self.assertIsNone(edge_access.base_url('kind-lanel', 'nominal-x-a1', 8080))

    def test_refuses_a_malformed_namespace_or_port(self):
        for ns, port in (('Bad_NS', 8080), ('ok', 0), ('ok', '8080')):
            with self.assertRaises(ValueError):
                edge_access.base_url('in-cluster', ns, port)

    def test_attach_uses_the_helper_before_forwarding(self):
        from pathlib import Path
        text = (Path(edge_access.__file__).with_name('attach.py')).read_text()
        self.assertIn('edge_access.base_url(', text)
        self.assertLess(text.index('edge_access.base_url('), text.index("'port-forward'"))


if __name__ == '__main__':
    unittest.main()
