"""Portable fixture archive offline: digests, cold check, readback comparison, private secrets.

Each refusal has a green twin: the same inputs unchanged pass, so the red result is caused by the
one thing the test breaks (measurement rule 3)."""
import base64
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

import fixture_archive as fa

SECRET_VALUE = b'synthetic-secret-value-0123456789'
ROWS = [{'name': 'ns-postgres-password', 'type': 'Opaque',
         'data': {'postgres-password': base64.b64encode(SECRET_VALUE).decode()}},
        {'name': 'ns-config-api', 'type': 'Opaque', 'data': {'k': base64.b64encode(b'synthetic').decode()}}]
PROVENANCE = {'tenants': 2, 'postgresImage': 'r/pg@sha256:' + '2' * 64, 'coreCommit': 'a' * 40,
              'inputTransport': 'writer-driven', 'history': {'mode': 'synthetic-history-looping-2d-v1'},
              'historyLogicalSha256': 'f' * 64}
ROSTER = {'version': 1, 'tenants': [{'id': 't-%d' % i, 'host': 'h%d.example.test' % i, 'dataToken': 'synthetic'}
                                    for i in range(2)]}


def tree(root, files):
    for name, data in files.items():
        path = Path(root)/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return ['tar', '-C', str(root), '--numeric-owner', '-cf', '-', '.']


class Archive(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.archive = self.work/'archive'

    def tearDown(self):
        subprocess.run(['rm', '-rf', str(self.work)])

    def build(self):
        fa.private_directory(self.archive, create=True)
        sources = {'postgres': {'PG_VERSION': b'16\n', 'base/1/1': b'x' * 4096},
                   'vault': {'core/_keyring': b'sealed'},
                   'provisionState': {'bootstrap/vault-init.json': b'{"keys_base64":["synthetic"]}'},
                   'primerResults': {'tenants.json': json.dumps(ROSTER).encode()}}
        parts = {part: fa.capture_part(tree(self.work/'src'/part, files), self.archive, part)
                 for part, files in sources.items()}
        return fa.write_manifest(self.archive, parts, PROVENANCE, ROWS, {'platform': 'test'},
                                 {'format': 'cold-data-directory', 'pgMajor': '16', 'systemIdentifier': '1'})

    # ---------------------------------------------------------- corrupted archive
    def test_intact_archive_verifies(self):
        self.build()
        self.assertEqual(fa.verify(self.archive)['provenance'], PROVENANCE)

    def test_corrupted_part_is_refused(self):
        self.build()
        path = self.archive/'postgres.tar.zst'
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0xFF
        path.write_bytes(bytes(data))
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_DIGEST_POSTGRES'):
            fa.verify(self.archive)

    def test_corrupted_secrets_file_is_refused(self):
        self.build()
        path = self.archive/fa.SECRETS
        path.write_bytes(path.read_bytes().replace(b'ns-config-api', b'ns-config-apX'))
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_DIGEST_SECRETS'):
            fa.verify(self.archive)

    def test_missing_part_is_refused(self):
        self.build()
        (self.archive/'vault.tar.zst').unlink()
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_FILE_VAULT'):
            fa.verify(self.archive)

    def test_replay_checks_the_raw_stream(self):
        manifest = self.build()
        out = self.work/'out'
        out.mkdir()
        fa.replay_part(self.archive, 'vault', manifest['parts']['vault'], ['tar', '-C', str(out), '-xf', '-'])
        self.assertEqual((out/'core/_keyring').read_bytes(), b'sealed')
        record = dict(manifest['parts']['vault'], rawSha256='0' * 64)
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_RAW_DIGEST_VAULT'):
            fa.replay_part(self.archive, 'vault', record, ['sh', '-c', 'cat >/dev/null'])

    def test_compressed_wire_replay_reports_the_raw_digest(self):
        manifest = self.build()
        out = self.work/'wire'
        out.mkdir()
        fa.replay_part(self.archive, 'postgres', manifest['parts']['postgres'], fa.pod_untar(str(out)), compressed=True)
        self.assertEqual((out/'PG_VERSION').read_bytes(), b'16\n')
        (self.work/'wire2').mkdir()
        record = dict(manifest['parts']['postgres'], rawSha256='0' * 64)
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_RAW_DIGEST_POSTGRES'):
            fa.replay_part(self.archive, 'postgres', record, fa.pod_untar(str(self.work/'wire2')), compressed=True)

    def test_compressed_capture_equals_plain_capture(self):
        plain = self.build()['parts']['vault']
        other = self.work/'other'
        fa.private_directory(other, create=True)
        wire = fa.capture_part(['sh', '-c', 'tar -C "$0" --numeric-owner -cf - . | zstd -q -c', str(self.work/'src/vault')],
                               other, 'vault', compressed=True)
        self.assertEqual((wire['rawSha256'], wire['rawBytes']), (plain['rawSha256'], plain['rawBytes']))

    # ---------------------------------------------------------- readback mismatch
    def test_readback_equal_hash_passes_and_changed_hash_is_refused(self):
        manifest = self.build()
        tenants = fa.roster(self.archive, manifest)
        self.assertEqual(tenants, [{'id': 't-0', 'host': 'h0.example.test'}, {'id': 't-1', 'host': 'h1.example.test'}])
        receipt = {'logicalSha256': 'f' * 64, 'rows': 1, 'collections': {}, 'observedUnixMs': 1}
        import populated_history
        with mock.patch.object(populated_history, 'run', return_value=receipt) as run:
            self.assertEqual(fa.readback(manifest, tenants, lambda q: '')['logicalSha256'], 'f' * 64)
            self.assertTrue(run.call_args.kwargs['verify_only'])
        with mock.patch.object(populated_history, 'run', return_value=dict(receipt, logicalSha256='e' * 64)):
            with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_READBACK_MISMATCH'):
                fa.readback(manifest, tenants, lambda q: '')

    def test_roster_count_must_equal_tenants(self):
        manifest = self.build()
        manifest['provenance'] = dict(PROVENANCE, tenants=3)
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_ROSTER_COUNT'):
            fa.roster(self.archive, manifest)

    # ---------------------------------------------------------- cold PostgreSQL
    def fake_controldata(self, state):
        bin_ = self.work/'bin'
        bin_.mkdir(exist_ok=True)
        script = bin_/'pg_controldata'
        script.write_text('#!/bin/sh\necho "Database system identifier:           7710849217556353062"\n'
                          'echo "Database cluster state:               %s"\n'
                          'echo "Latest checkpoint location:           0/1"\n' % state)
        script.chmod(0o755)
        pgdata = self.work/'pgdata'
        pgdata.mkdir(exist_ok=True)
        (pgdata/'PG_VERSION').write_text('16\n')
        return ['env', 'PATH=%s:%s' % (bin_, os.environ['PATH'])], str(pgdata)

    def test_cold_data_directory_passes(self):
        prefix, pgdata = self.fake_controldata('shut down')
        self.assertEqual(fa.controldata(prefix, pgdata)['systemIdentifier'], '7710849217556353062')

    def test_running_or_crashed_data_directory_is_refused(self):
        prefix, pgdata = self.fake_controldata('in production')
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_POSTGRES_NOT_COLD'):
            fa.controldata(prefix, pgdata)
        prefix, pgdata = self.fake_controldata('shut down')
        Path(pgdata, 'postmaster.pid').write_text('1\n')
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_POSTGRES_NOT_COLD'):
            fa.controldata(prefix, pgdata)

    # ---------------------------------------------------------- secrets stay private
    def test_secret_values_only_in_the_private_secrets_file(self):
        manifest = self.build()
        encoded = base64.b64encode(SECRET_VALUE)
        holders = [p.name for p in self.archive.iterdir() if encoded in p.read_bytes() or SECRET_VALUE in p.read_bytes()]
        self.assertEqual(holders, [fa.SECRETS])
        self.assertNotIn(encoded.decode(), json.dumps(manifest))
        for p in self.archive.iterdir():
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600, p.name)
        self.assertEqual(stat.S_IMODE(self.archive.stat().st_mode), 0o700)

    def test_archive_directory_is_private_even_with_an_open_umask(self):
        old = os.umask(0)
        try:
            fa.private_directory(self.archive, create=True)
            fa.write_private(self.archive, 'x', b'1')
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(self.archive.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.archive/'x').stat().st_mode), 0o600)

    def test_secrets_are_refused_in_a_shared_directory(self):
        shared = self.work/'shared'
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_NOT_PRIVATE'):
            fa.write_manifest(shared, {p: {} for p in fa.PARTS}, PROVENANCE, ROWS, {}, {})
        self.assertEqual(list(shared.iterdir()), [])
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_NOT_PRIVATE'):
            fa.capture_part(['true'], shared, 'postgres')
        self.assertEqual(list(shared.iterdir()), [])
        # Green twin: the same call in a private directory writes the file.
        shared.chmod(0o700)
        fa.write_private(shared, fa.SECRETS, b'[]')
        self.assertTrue((shared/fa.SECRETS).is_file())

    def test_a_symlinked_secrets_target_is_not_followed(self):
        fa.private_directory(self.archive, create=True)
        outside = self.work/'outside'
        os.symlink(outside, self.archive/fa.SECRETS)
        with self.assertRaises(FileExistsError):
            fa.write_private(self.archive, fa.SECRETS, SECRET_VALUE)
        self.assertFalse(outside.exists())

    def test_only_fixture_secrets_are_archived(self):
        fa.private_directory(self.archive, create=True)
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_SECRETS'):
            fa.write_manifest(self.archive, {p: {} for p in fa.PARTS}, PROVENANCE,
                              ROWS + [{'name': 'registry-pull', 'type': 'Opaque', 'data': {}}], {}, {})
        self.assertFalse((self.archive/fa.SECRETS).exists())

    def test_empty_stream_is_refused_and_leaves_no_file(self):
        fa.private_directory(self.archive, create=True)
        with self.assertRaisesRegex(fa.Refused, 'ARCHIVE_STREAM_VAULT'):
            fa.capture_part(['sh', '-c', 'exit 3'], self.archive, 'vault')
        self.assertFalse((self.archive/'vault.tar.zst').exists())

    # ---------------------------------------------------------- claim sizes
    def test_claim_sizes_keep_the_seed_floor_and_grow_with_data(self):
        gib = 1 << 30
        small = {'parts': {p: {'rawBytes': 10} for p in fa.PARTS}}
        self.assertEqual(fa.claim_sizes(small), {'postgres': '4Gi', 'vault': '1Gi', 'provisionState': '1Gi',
                                                 'primerResults': '1Gi'})
        big = {'parts': {**small['parts'], 'postgres': {'rawBytes': 20 * gib}}}
        self.assertEqual(fa.claim_sizes(big)['postgres'], '31Gi')


if __name__ == '__main__':
    unittest.main()
