import json
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
import host_io as h

STATS = '259 0 nvme0n1 ' + ' '.join(str(i) for i in range(1, 18)) + '\n'
PSI = 'some avg10=1.25 avg60=2.50 avg300=0.00 total=123\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=7\n'
SHELL = Path(__file__).resolve().parents[1] / 'compose-baseline/probes/sample.sh'


class HostIO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proc, self.sys = self.root / 'proc', self.root / 'sys'
        (self.proc / 'pressure').mkdir(parents=True)
        (self.proc / 'diskstats').write_text(STATS)
        (self.proc / 'stat').write_text('cpu  1 2 3 4 5 6 7 8 9 10\ncpu0 1 2 3 4\n')
        (self.proc / 'pressure/io').write_text(PSI)
        self.node = self.sys / 'devices/pci/nvme/nvme0n1'
        (self.node / 'slaves').mkdir(parents=True)
        (self.node / 'queue').mkdir()
        (self.node / 'queue/logical_block_size').write_text('4096\n')
        (self.node / 'dev').write_text('259:0\n')
        (self.node / 'device').symlink_to(self.node.parent)
        (self.sys / 'dev/block').mkdir(parents=True)
        (self.sys / 'dev/block/259:0').symlink_to(self.node)

    def sampler(self):
        return h.Sampler(self.proc, self.sys)

    def green(self):
        sample = self.sampler().snapshot()
        self.assertEqual(sample['disks']['status'], 'MEASURED')
        self.assertEqual(sample['disks']['devices']['259:0']['counters']['read_ms'], 4)
        self.assertEqual(sample['cpu']['ticks']['iowait'], 5)
        self.assertEqual(sample['ioPressure']['some']['total'], 123)
        self.assertLessEqual(sample['start']['monotonicNs'], sample['end']['monotonicNs'])
        return sample

    def test_counter_control_missing_restore(self):
        self.green()
        sampler = self.sampler()
        (self.proc / 'diskstats').write_text('259 0 nvme0n1 1 2\n')
        self.assertEqual(sampler.snapshot()['disks']['status'], 'NO-INSTRUMENT')
        with self.assertRaises(AssertionError): self.green()
        (self.proc / 'diskstats').write_text(STATS)
        self.green()

    def test_identity_control_missing_restore(self):
        self.green()
        p = self.node / 'dev'
        p.write_text('259:9')
        self.assertEqual(self.sampler().identity['status'], 'NO-INSTRUMENT')
        with self.assertRaises(AssertionError): self.green()
        p.write_text('259:0')
        self.green()

    def test_disappeared_identity_not_zero(self):
        sampler = self.sampler()
        (self.sys / 'dev/block/259:0').unlink()
        row = sampler.snapshot()['disks']['devices']['259:0']
        self.assertEqual(row['status'], 'NO-INSTRUMENT')
        self.assertNotIn('counters', row)

    def test_missing_cpu_pressure_restore(self):
        for path, key, text in [(self.proc / 'stat', 'cpu', 'cpu 1 2 3 4 5\n'),
                                (self.proc / 'pressure/io', 'ioPressure', PSI)]:
            path.unlink()
            self.assertEqual(self.sampler().snapshot()[key]['status'], 'NO-INSTRUMENT')
            path.write_text(text)
            self.assertEqual(self.sampler().snapshot()[key]['status'], 'MEASURED')

    def test_cpu_requires_iowait(self):
        with self.assertRaises(ValueError): h.cpu('cpu 1 2 3 4\n')

    def test_malformed_huge_pressure_is_uninstrumented_not_worker_crash(self):
        path=self.proc/'pressure/io';path.write_text(PSI.replace('total=123','total='+'9'*1000))
        self.assertEqual(self.sampler().snapshot()['ioPressure']['status'],'NO-INSTRUMENT')
        path.write_text(PSI);self.green()

    def test_disk_optional_fields_missing_never_zero(self):
        row = h.diskstats('8 0 sda ' + ' '.join(['1'] * 11))['8:0']
        self.assertEqual(row['flushStatus'], 'NO-INSTRUMENT')
        self.assertNotIn('flush_ms', row['counters'])
        self.assertEqual(row['discardStatus'], 'NO-INSTRUMENT')
        with self.assertRaises(ValueError): h.diskstats('8 0 sda ' + ' '.join(['-1'] * 11))

    def test_pressure_rejects_malformed(self):
        for text in ['', PSI.replace('1.25', 'nan'), PSI.replace('total=123', 'total=-1'), PSI.splitlines()[0]]:
            with self.subTest(text=text), self.assertRaises(ValueError): h.pressure(text)

    def test_partition_stacked_virtual_not_physical(self):
        partition = self.node / 'partition'
        partition.write_text('1')
        self.assertEqual(self.sampler().identity['status'], 'NO-INSTRUMENT')
        partition.unlink()
        (self.node / 'slaves/dm-0').touch()
        self.assertEqual(self.sampler().identity['status'], 'NO-INSTRUMENT')
        (self.node / 'slaves/dm-0').unlink()
        virtual = self.sys / 'devices/virtual/block/nvme0n1'
        virtual.parent.mkdir(parents=True)
        self.node.rename(virtual)
        (self.sys / 'dev/block/259:0').unlink()
        (self.sys / 'dev/block/259:0').symlink_to(virtual)
        self.assertEqual(self.sampler().identity['status'], 'NO-INSTRUMENT')

    def test_metadata_has_units_sources_no_serial(self):
        (self.node / 'serial').write_text('FORBIDDEN-SYNTHETIC-SERIAL')
        meta = self.sampler().metadata()
        self.assertEqual(meta['physicalDevices']['devices']['259:0']['sysfsPath'], '/sys/devices/pci/nvme/nvme0n1')
        self.assertEqual(meta['units']['diskSectors'], '512 bytes per sector')
        self.assertNotIn('FORBIDDEN', json.dumps(meta))
        self.assertEqual(len(meta['sources']), 3)

    def test_shell_cwd_normalizes_before_compose(self):
        case = self.root / 'caller with spaces'
        (case / 'compose').mkdir(parents=True)
        (case / 'out').mkdir()
        for name in ['env', 'one.yml', 'two.yml']:
            (case / 'compose' / name).touch()
        bin_dir = case / 'bin'
        bin_dir.mkdir()
        # All external activity is stubbed: no Docker or host-counter reads.
        docker = bin_dir / 'docker'
        docker.write_text('#!/bin/bash\nprintf "%s\\n" "$PWD" "$@" > "$RECEIPT"\nkill -TERM "$PPID"\n')
        docker.chmod(0o755)
        python = bin_dir / 'python3'
        python.write_text('#!/bin/bash\nexit 0\n')
        python.chmod(0o755)
        receipt = case / 'receipt'
        env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'], RECEIPT=str(receipt))
        args = ['bash', str(SHELL), 'synthetic', 'compose/env', 'compose/one.yml', 'compose/two.yml', 'out']
        result = subprocess.run(args, cwd=case, env=env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = receipt.read_text().splitlines()
        self.assertEqual(lines[0], str(case / 'compose'))
        self.assertIn(str(case / 'compose/env'), lines)
        self.assertIn(str(case / 'compose/one.yml'), lines)
        self.assertEqual(json.loads((case / 'out/host-io-metadata.json').read_text())['status'], 'NO-INSTRUMENT')
        (case / 'compose/env').unlink()
        result = subprocess.run(args, cwd=case, env=env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 66)
        self.assertIn(b'normalization failed', result.stderr)


if __name__ == '__main__':
    unittest.main()
