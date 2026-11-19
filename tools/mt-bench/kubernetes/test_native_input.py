"""Lossless synthetic DATA roster controls; no cluster actors or credentials."""
import base64
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import uuid

import kube_adapter as k
import native_input as codec
import native_join as join
import native_load as load
from test_native_files import configured
from test_native_join import fixture
from test_native_load import SCRIPT, TENANTS


def roster(count):
    rng = random.Random(71937)
    return [{'id': str(uuid.UUID(int=rng.getrandbits(128), version=4)),
             'host': f'codec-tenant-{index:05d}.synthetic.capacity.test',
             'token': base64.urlsafe_b64encode(rng.getrandbits(160).to_bytes(20, 'big')).decode().rstrip('=')}
            for index in range(count)]


def materialize(secret, target):
    for name, raw in secret['stringData'].items():
        (target / name).write_text(raw)
    for name, raw in secret.get('data', {}).items():
        (target / name).write_bytes(base64.b64decode(raw, validate=True))


def run_unpack(inputs, output, count):
    node = os.environ.get('NS_NATIVE_NODE_IMAGE_BINARY', 'node')
    return subprocess.run([node, k.HERE / 'native-input-unpack.cjs', inputs, output, str(count)],
                          capture_output=True, timeout=10)


class NativeInput(unittest.TestCase):
    def package(self, count=10000):
        c, job, options = configured()
        c['tenants'] = count
        return c, job, options, roster(count)

    def test_raw_compatibility_and_exact_10k_gzip_roundtrip(self):
        c, job, options, rows = self.package()
        with self.assertRaisesRegex(k.Refused, 'INPUT_SECRET_BOUND'):
            load.package(c, job, SCRIPT, rows, **options)
        rendered, secret, receipt = load.package(c, job, SCRIPT, rows, input_codec='gzip-v1', **options)
        raw = json.dumps(rows, separators=(',', ':')).encode()
        self.assertGreater(len(raw), load.MAX_INPUT_BYTES)
        self.assertLessEqual(len(json.dumps(secret).encode()), load.MAX_INPUT_BYTES)
        self.assertEqual(receipt['rosterSha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt['inputTransport']['sha256'], receipt['rosterSha256'])
        self.assertEqual(secret['stringData']['workload.js'].encode(), SCRIPT)
        self.assertEqual(secret['stringData']['k6-vu-driver.js'], (k.M7 / 'k6-vu-driver.js').read_text())
        self.assertEqual(receipt['driverManifest']['cadence']['driverPlan']['observer'], 'scheduling-v1')
        self.assertIn('k6-scheduling.csv.gz', receipt['files'])
        self.assertEqual(receipt['outcomeGate'], 'UNMEASURED')
        self.assertEqual(receipt['capacityAcceptance'], 'NOT_GRANTED')
        with tempfile.TemporaryDirectory() as area:
            root = Path(area); inputs = root / 'inputs'; output = root / 'roster'
            inputs.mkdir(); output.mkdir(); materialize(secret, inputs)
            self.assertEqual(run_unpack(inputs, output, 10000).returncode, 0)
            self.assertEqual((output / 'tenants.json').read_bytes(), raw)
            self.assertEqual(json.loads((output / 'tenants.json').read_bytes()), rows)
            self.assertEqual((output / 'tenants.json').stat().st_mode & 0o777, 0o400)
            self.assertEqual(run_unpack(inputs, output, 10000).returncode, 78, 'no overwrite/replay')
        c, job, options = configured()
        old = load.package(c, job, SCRIPT, TENANTS, **options)
        explicit = load.package(c, job, SCRIPT, TENANTS, input_codec='raw-v1', **options)
        self.assertEqual(old, explicit)
        self.assertEqual(old[1]['stringData']['tenants.json'], json.dumps(TENANTS, separators=(',', ':')))
        self.assertNotIn('data', old[1])
        self.assertNotIn('initContainers', old[0]['spec']['template']['spec'])

    def test_damaged_truncated_hash_count_and_bomb_controls_restore(self):
        c, job, options, rows = self.package()
        _, secret, _ = load.package(c, job, SCRIPT, rows, input_codec='gzip-v1', **options)
        with tempfile.TemporaryDirectory() as area:
            root = Path(area); inputs = root / 'inputs'; output = root / 'roster'
            inputs.mkdir(); output.mkdir(); materialize(secret, inputs)
            packed = (inputs / 'tenants.json.gz').read_bytes()
            meta = json.loads((inputs / 'tenants.digest.json').read_bytes())
            def check(bad_packed, bad_meta, expected=10000, failure_code=None):
                (inputs / 'tenants.json.gz').write_bytes(bad_packed)
                (inputs / 'tenants.digest.json').write_text(json.dumps(bad_meta))
                failed = run_unpack(inputs, output, expected)
                self.assertEqual(failed.returncode, 78)
                if failure_code:
                    self.assertIn(('K8S_NATIVE_INPUT_' + failure_code).encode(), failed.stderr)
                self.assertFalse((output / 'tenants.json').exists())
                # Every authored failure restores the original bytes and passes.
                (inputs / 'tenants.json.gz').write_bytes(packed)
                (inputs / 'tenants.digest.json').write_text(json.dumps(meta))
                restored = run_unpack(inputs, output, 10000)
                self.assertEqual(restored.returncode, 0, restored.stderr.decode())
                self.assertEqual(hashlib.sha256((output / 'tenants.json').read_bytes()).hexdigest(), meta['sha256'])
                (output / 'tenants.json').unlink()
            check(packed[:-9], meta)
            check(bytes([packed[0] ^ 1]) + packed[1:], meta)
            check(packed + b'x' * codec.MAX_GZIP_BYTES, meta)
            check(packed, dict(meta, sha256='0' * 64), failure_code='ROSTER_CHANGED')
            check(packed, dict(meta, gzipSha256='0' * 64))
            check(packed, dict(meta, tenants=9999))
            check(packed, meta, 9999)
            check(packed, dict(meta, bytes=codec.MAX_RAW_BYTES + 1))
            check(packed, dict(meta, gzipBytes=codec.MAX_GZIP_BYTES + 1))
            check(packed, dict(meta, tenants=10001), 10001)
            check(packed, dict(meta, unexpected='x' * 4096))
            # Digest the substituted gzip so the inflate bound itself must fail.
            check(packed, dict(meta, bytes=64), failure_code='DECODE_REFUSED')
            bomb = gzip.compress(b'x' * (codec.MAX_RAW_BYTES + 1), mtime=0)
            check(bomb, dict(meta, bytes=codec.MAX_RAW_BYTES,
                             gzipBytes=len(bomb), gzipSha256=hashlib.sha256(bomb).hexdigest()),
                             failure_code='DECODE_REFUSED')
            corrupt = packed[:-7]
            check(corrupt, dict(meta, gzipBytes=len(corrupt), gzipSha256=hashlib.sha256(corrupt).hexdigest()))
            # A valid digest does not replace the original row-count/ID contract.
            raw = json.dumps(rows[:-1], separators=(',', ':')).encode()
            fewer = gzip.compress(raw, mtime=0)
            check(fewer, dict(meta, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                              gzipBytes=len(fewer), gzipSha256=hashlib.sha256(fewer).hexdigest()))
            duplicate = copy.deepcopy(rows); duplicate[1]['id'] = duplicate[0]['id']
            raw = json.dumps(duplicate, separators=(',', ':')).encode()
            packed_duplicate = gzip.compress(raw, mtime=0)
            check(packed_duplicate, dict(meta, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                gzipBytes=len(packed_duplicate), gzipSha256=hashlib.sha256(packed_duplicate).hexdigest()))

    def test_input_bounds_and_budget_refuse_before_cluster_reads(self):
        c, job, options, rows = self.package()
        class Kube:
            def call(self, *_args, **_kw): raise AssertionError('cluster call before refusal')
            def json(self, *_args, **_kw): raise AssertionError('cluster read before refusal')
        with tempfile.TemporaryDirectory() as area:
            for bad, code in [('unknown', 'INPUT_CODEC')]:
                with self.assertRaisesRegex(k.Refused, code):
                    load.run(Kube(), c, job, SCRIPT, rows, area, input_codec=bad, **options)
            c['tenants'] = 10001
            with self.assertRaisesRegex(k.Refused, 'INPUT_TENANT_BOUND'):
                load.run(Kube(), c, job, SCRIPT, roster(10001), area, input_codec='gzip-v1', **options)
            c['tenants'] = 10000
            changed = copy.deepcopy(rows); changed[0]['token'] = 'x' * codec.MAX_RAW_BYTES
            with self.assertRaisesRegex(k.Refused, 'INPUT_RAW_BOUND'):
                load.run(Kube(), c, job, SCRIPT, changed, area, input_codec='gzip-v1', **options)
            changed[0]['token'] = base64.b64encode(random.Random(29).randbytes(700000)).decode()
            with self.assertRaisesRegex(k.Refused, 'INPUT_GZIP_BOUND'):
                load.run(Kube(), c, job, SCRIPT, changed, area, input_codec='gzip-v1', **options)
            with self.assertRaisesRegex(k.Refused, 'INPUT_SECRET_BOUND'):
                load.run(Kube(), c, job, b'//' + b'x' * load.MAX_INPUT_BYTES, rows, area,
                         input_codec='gzip-v1', **options)
            budget = copy.deepcopy(options['exporter_resources'])
            for key, value in [('memory', '16Mi'), ('ephemeral-storage', '1Mi')]:
                bad = copy.deepcopy(budget); bad['requests'][key] = value
                with self.assertRaisesRegex(k.Refused, 'INPUT_UNPACK_BUDGET'):
                    load.run(Kube(), c, job, SCRIPT, rows, area, input_codec='gzip-v1',
                             **dict(options, exporter_resources=bad))
            load.package(c, job, SCRIPT, rows, input_codec='gzip-v1', **options)

    def test_declared_init_budget_scoped_mounts_and_frozen_template(self):
        c, inventory, render, _ = fixture()
        c[join.FIELD]['inputCodec'] = 'gzip-v1'
        inventory[join.FIELD] = copy.deepcopy(c[join.FIELD])
        declared = join.declarations(c)[0]
        pod = declared['spec']['template']['spec']
        self.assertEqual([row['name'] for row in pod['initContainers']], ['wait-for-jobs', 'unpack-roster'])
        waiter, unpacker = pod['initContainers']
        self.assertEqual(unpacker['resources'], c[join.FIELD]['exporterResources'])
        self.assertEqual(unpacker['image'], c['pins']['appImage'])
        self.assertEqual(unpacker['volumeMounts'], [
            {'name': 'inputs', 'mountPath': '/inputs', 'readOnly': True},
            {'name': 'roster', 'mountPath': '/roster'}])
        self.assertEqual([v['name'] for v in waiter['volumeMounts']], ['kube-api'])
        for actor in pod['containers']:
            self.assertNotIn('kube-api', [v['name'] for v in actor['volumeMounts']])
        main = pod['containers'][0]
        self.assertIn({'name': 'roster', 'mountPath': '/roster', 'readOnly': True}, main['volumeMounts'])
        self.assertFalse(pod['automountServiceAccountToken'])
        resources = k.resource_budget.pod_budget(pod, 'requests-v1', k.need)
        self.assertGreater(resources['memoryBytes'], 0)
        objects = {k.key(obj): obj for obj in render}
        objects[join.JOB] = declared
        join.validate(c, inventory, objects)
        c['tenants'] = 2
        s = c[join.FIELD]
        # Real and planning templates stay byte-identical despite roster bytes.
        import workload
        with tempfile.TemporaryDirectory() as area:
            source = Path(area) / 'workload.js'; workload.generate(k.ROOT, source)
            actual, _, _ = load.package(c, join.base_job(c), source.read_bytes(), TENANTS,
                runid=join.stage_runid(c), seconds=s['deadlineSeconds'], run_start_ms=2, setup_seconds=1,
                exporter_resources=s['exporterResources'], shell_contract=s['shellContract'], input_codec='gzip-v1')
        actual['spec']['suspend'] = True
        self.assertEqual(actual, declared)
        unpacker['resources']['requests']['memory'] = '16Mi'
        with self.assertRaisesRegex(k.Refused, 'DECLARATION_CHANGED'):
            join.validate(c, inventory, objects)

    @unittest.skipUnless(os.environ.get('NS_NATIVE_K6_IMAGE_BINARY'), 'selected cached k6 binary required')
    def test_cached_k6_original_workload_decoder_sees_exact_10k_rows(self):
        import workload
        c, job, options, rows = self.package()
        with tempfile.TemporaryDirectory() as area:
            root = Path(area); inputs = root / 'inputs'; output = root / 'roster'
            inputs.mkdir(); output.mkdir()
            workload.generate(k.ROOT, root / 'workload.js')
            actual, secret, receipt = load.package(c, job, (root / 'workload.js').read_bytes(), rows,
                                                 input_codec='gzip-v1', **options)
            materialize(secret, inputs)
            restored = run_unpack(inputs, output, 10000)
            self.assertEqual(restored.returncode, 0, restored.stderr.decode())
            # Import the unmodified configured driver and generated workload.
            # Its own SharedArray decoder must populate the existing named array.
            # This init/decoder control issues no HTTP traffic and runs no setup.
            script = r'''
import {options as driverOptions} from './k6-vu-driver.js';
import {SharedArray} from 'k6/data';
import crypto from 'k6/crypto';
const text = open(__ENV.TENANTS_FILE), expected = JSON.parse(text);
const rows = new SharedArray('baseline tenants', () => { throw Error('ORIGINAL_DECODER_MISSING'); });
if (rows.length !== 10000 || expected.length !== rows.length ||
    crypto.sha256(text, 'hex') !== __ENV.EXPECTED_ROSTER_SHA256 ||
    Object.keys(driverOptions.scenarios).length !== 7) throw Error('INPUT_DECODER_BINDING');
for (let index = 0; index < rows.length; index++) {
  const a = rows[index], b = expected[index];
  if (a.id !== b.id || a.host !== b.host || a.token !== b.token) throw Error('INPUT_DECODER_SEMANTICS');
}
export const options = {vus: 1, iterations: 1};
export default function () { console.log('NATIVE_INPUT_10000_EXACT_ROWS_PASS'); }
'''
            (inputs / 'decoder-control.js').write_text(script)
            env = dict(os.environ, **{row['name']: row['value']
                       for row in actual['spec']['template']['spec']['containers'][0]['env']})
            env.update(TENANTS_FILE=str(output / 'tenants.json'),
                       EXPECTED_ROSTER_SHA256=receipt['rosterSha256'])
            result = subprocess.run([os.environ['NS_NATIVE_K6_IMAGE_BINARY'], 'run', '--quiet',
                        '--no-usage-report', '--address=', str(inputs / 'decoder-control.js')],
                        env=env, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertIn(b'NATIVE_INPUT_10000_EXACT_ROWS_PASS', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
