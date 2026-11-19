"""Controls for attribution and missing driver samples."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import adapter
import driver_memory as memory


class DriverMemory(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.cid = 'b' * 64
        self.image = 'sha256:' + 'c' * 64
        self.birth = '2026-11-18T12:00:00.1Z'
        self.m = {'owner': 'a' * 32, 'project': 'synthetic',
                  'diagnosticResources': {'profile': {
                      'driver': {'millicpus': 1000, 'memoryReservationBytes': 4 * 1024**2}}}}
        self.terminal = {'status':'exited', 'startedAt':self.birth, 'exitCode':137,
                         'oomKilled':True, 'restartCount':0}
        self.created = {'containerId':self.cid, 'imageId':self.image,
                        'hostConfig':{'NanoCpus':1000000000,'MemoryReservation':4*1024**2,
                                      'Memory':0,'MemorySwap':0}}
        (self.root / memory.CID).write_text(self.cid)
        adapter.write(self.root / memory.CREATED, self.created)

    def retain(self, samples):
        (self.root / memory.SAMPLES).write_text(
            't\tcontainerId\tstartedAt\tmemoryPeakBytes\tmemoryMax\tmemorySwapMax\n' + samples)
        with patch.object(memory, 'inspect', return_value={**self.created, 'state':self.terminal}):
            memory.retain(adapter, self.m, self.root, self.image, 'synthetic-run-id')
        return adapter.document(self.root / memory.RESULT)

    def test_early_exit_with_only_foreign_samples(self):
        value = self.retain(f'1.0\t{"f"*64}\t{self.birth}\t10\tmax\tmax\n')
        self.assertEqual(value['settings']['status'], 'VERIFIED')
        self.assertEqual(value['terminal']['exitCode'], 137)
        self.assertTrue(value['terminal']['oomKilled'])
        self.assertEqual(value['memoryPeak']['status'], 'UNMEASURED')
        self.assertNotIn('observedPeakBytes', value['memoryPeak'])

    def test_peak_belongs_to_bound_id_and_birth(self):
        old = '2026-11-18T12:00:00.0Z'
        value = self.retain(f'1.0\t{self.cid}\t{old}\t100\tmax\tmax\n'
                            f'2.0\t{self.cid}\t{self.birth}\t17\tmax\tmax\n'
                            f'3.0\t{self.cid}\t{self.birth}\t22\tmax\tmax\n')
        self.assertEqual(value['runId'], 'synthetic-run-id')
        self.assertEqual(value['containerId'], self.cid)
        self.assertEqual(value['memoryPeak']['observedPeakBytes'], 22)
        self.assertEqual(value['memoryPeak']['sampleCount'], 2)

    def test_finite_memory_max_is_effective_settings_failure(self):
        value = self.retain(f'1.0\t{self.cid}\t{self.birth}\t10\t20\tmax\n')
        self.assertEqual(value['settings']['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
