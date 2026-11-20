import unittest

import kube_adapter as k
import candidate


class CandidateControls(unittest.TestCase):
    def test_ack_readback_binds_the_owned_running_container(self):
        c = {'pins': {'candidate': {}}, 'roles': {'pgstream': {'workload': 'Deployment/pgstream', 'container': 'pgstream'}},
             'producerAckReadback': {'namespaceUid': 'owned', 'podUid': 'pod', 'containerId': 'stream',
                                     'effectiveWireSha256': 'a'*64}}
        observed = {'namespace': {'uid': 'owned'}, 'pods': {'stream-pod': {
            'name': 'stream-pod', 'uid': 'pod', 'workload': 'Deployment/pgstream',
            'containers': {'pgstream': {'ready': True, 'containerID': 'stream'}}}}}
        self.assertEqual(candidate.verify_ack_owner(k, c, observed), ('stream-pod', 'pgstream'))
        observed['pods']['stream-pod']['containers']['pgstream']['containerID'] = 'replacement'
        with self.assertRaisesRegex(k.Refused, 'PGSTREAM_ACK_OWNER_CHANGED'):
            candidate.verify_ack_owner(k, c, observed)
