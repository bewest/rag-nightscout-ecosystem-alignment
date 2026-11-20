import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import kube_adapter as k
import candidate
from test_adapter import fixture


class CandidateControls(unittest.TestCase):
    def test_ack_readback_binds_the_owned_running_container(self):
        c = {'pins': {'candidate': {}}, 'roles': {'pgstream': {'workload': 'Deployment/pgstream', 'container': 'pgstream'}},
             'producerAckReadback': {'namespaceUid': 'owned', 'podUid': 'pod', 'containerId': 'stream',
                                     'effectiveWireSha256': 'a'*64}}
        observed = {'namespace': {'uid': 'owned'}, 'pods': {'stream-pod': {
            'name': 'stream-pod', 'uid': 'pod', 'workload': 'Deployment/pgstream',
            'containers': {'pgstream': {'ready': True, 'containerID': 'stream'}}}}}
        self.assertEqual(candidate.verify_ack_owner(k, c, observed), ('stream-pod', 'pgstream'))
        with tempfile.TemporaryDirectory() as tmp, patch.object(k, 'observe', return_value=observed), \
                patch.object(k, 'active_baseline', return_value=observed):
            with self.assertRaisesRegex(k.Refused, 'PGSTREAM_ACK_WIRE_CHANGED'):
                candidate.observe(k, Path(tmp), c, {}, SimpleNamespace(call=lambda *a, **kw: b'wrong'))
        observed['pods']['stream-pod']['containers']['pgstream']['containerID'] = 'replacement'
        with self.assertRaisesRegex(k.Refused, 'PGSTREAM_ACK_OWNER_CHANGED'):
            candidate.verify_ack_owner(k, c, observed)

    def test_source_config_and_actual_image(self):
        c, inv, *_ = fixture()
        p = c['pins']
        current = dict(diagnosticSha256='0'*64, producerBinarySha256='1'*64, nativeCatalogueSha256='2'*64,
                       imageConfigId=p['appImageId'], sourceAcceptance='PENDING')
        inv['candidateContract'] = current
        p.update(candidate=copy.deepcopy(current), postgresImage='example.invalid/postgres@sha256:'+'7'*64,
                 postgresImageId='sha256:'+'8'*64)
        inv['images'] = {'postgres': p['postgresImage']}
        contract = dict(current, coreCommit=p['pair']['core'], deployCommit=p['pair']['deploy'], localImageId=p['appImageId'])
        objects = {'ConfigMap/provision-scripts': {'data': {'source-contract.json': json.dumps(contract)}}}
        candidate.pins(k, c, inv, objects)
        # Identical source/image inputs can run at either qualification state.
        inv['candidateContract']['sourceAcceptance'] = p['candidate']['sourceAcceptance'] = 'PASS'
        candidate.pins(k, c, inv, objects)
        inv['candidateContract']['sourceAcceptance'] = p['candidate']['sourceAcceptance'] = 'PENDING'
        candidate.pins(k, c, inv, objects)
        # Source commits in the contract are provenance; a changed commit runs.
        objects['ConfigMap/provision-scripts']['data']['source-contract.json'] = json.dumps(dict(contract, coreCommit='a'*40))
        candidate.pins(k, c, inv, objects)
        # The image digest is identity: a different delivered image refuses.
        inv['candidateContract']['imageConfigId'] = p['candidate']['imageConfigId'] = 'sha256:'+'9'*64
        with self.assertRaisesRegex(k.Refused, '^K8S_CANDIDATE_SOURCE_IMAGE_CHANGED$'):
            candidate.pins(k, c, inv, objects)
        inv['candidateContract']['imageConfigId'] = p['candidate']['imageConfigId'] = p['appImageId']
        candidate.pins(k, c, inv, objects)
        pod = {'imageReferences': {'api': p['appImage'], 'postgres': p['postgresImage']},
               'containers': {'api': {'imageID': p['appImage']}, 'postgres': {'imageID': p['postgresImageId']}}}
        observation = {'pods': {'fixture': pod}}
        candidate.images(k, c, observation)
        for role, old in [('api', p['appImage']), ('postgres', p['postgresImageId'])]:
            pod['containers'][role]['imageID'] = 'sha256:'+'9'*64
            with self.assertRaisesRegex(k.Refused, '^K8S_CANDIDATE_ACTUAL_IMAGE_CHANGED$'):
                candidate.images(k, c, observation)
            pod['containers'][role]['imageID'] = old
            candidate.images(k, c, observation)

    def test_required_admin_and_native_fixture_proof(self):
        c, *_ = fixture()
        p = c['pins']
        p['candidate'] = {'diagnosticSha256': '1'*64}
        proof = dict(version=1, credentialBoundary='admin-private-api',
                     coreCommit=p['pair']['core'], deployCommit=p['pair']['deploy'], diagnosticSha256='1'*64,
                     fixture={'namespace': c['namespace'], 'runId': c['runId']},
                     nativeSource={'system_id': '123', 'timeline': 1, 'database': 'nightscout_compose_test', 'slot': 'nsdemo_pgstream'},
                     nativeGeneration='test-generation', nativeSelectionSha256='2'*64, selectionSha256='3'*64,
                     roles=[dict(role=role, generation='4'*64, expiresAt='2026-11-19T00:00:00Z') for role in candidate.ROLES])
        candidate.proof(k, c, proof, now=1)
        cases = [
            (None, 'ADMIN_PROOF_REQUIRED'),
            (dict(proof, fixture={'namespace': c['namespace'], 'runId': 'foreign'}), 'FIXTURE_CHANGED'),
            (dict(proof, nativeSource=dict(proof['nativeSource'], slot='wrong_slot')), 'NATIVE_SOURCE_CHANGED'),
            (dict(proof, roles=proof['roles'][1:]), 'VERIFICATION_CHANGED'),
        ]
        for bad, code in cases:
            with self.assertRaisesRegex(k.Refused, '^K8S_CANDIDATE_'+code+'$'):
                candidate.proof(k, c, bad, now=1)
            candidate.proof(k, c, proof, now=1)
