import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import node_observation as n


class NodeObservationTest(unittest.TestCase):
    def test_teardown_marker_survives_large_k6_summary(self):
        with TemporaryDirectory() as directory:
            log = Path(directory) / 'k6.log'
            at = 123456
            marker = 'msg=' + json.dumps(json.dumps({'event': 'scenario-phase-end', 'atMs': at}))
            summary = '\nper-tenant summary\n' * 9000
            log.write_text(marker + summary)
            self.assertNotIn('scenario-phase-end', n.log_events(log, tail=True))
            self.assertEqual(n.phase_end(log), at)
            log.write_text(summary)
            self.assertIsNone(n.phase_end(log))
            log.write_text(marker + summary)
            self.assertEqual(n.phase_end(log), at)

    def test_unvalidated_raw_capture_is_bounded_and_retained(self):
        with TemporaryDirectory() as directory:
            raw = Path(directory) / 'source.json'
            captured = Path(directory) / 'capture.json'
            qualified = Path(directory) / 'measured.json'
            raw.write_bytes(b'{"kind":"captured-but-unvalidated"}')
            with patch.object(n, 'MAX_BYTES', 8):
                self.assertIsNone(n.retain_raw(raw, captured))
            self.assertFalse(captured.exists())
            retention = n.retain_raw(raw, captured)
            refusal = n.copy_checked(captured, qualified, {}, {}, 'profile', None, None)
            self.assertEqual(refusal['reason'], 'M7_NODE_OBSERVATION_NO_PHASE')
            self.assertFalse(qualified.exists())
            raw.unlink()
            self.assertEqual(retention['sha256'], n.sha(captured))


if __name__ == '__main__':
    unittest.main()
