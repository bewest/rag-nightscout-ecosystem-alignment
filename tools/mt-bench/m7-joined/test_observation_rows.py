import json
import unittest
from unittest.mock import patch

from evaluator_progress import Refused
from observation_rows import Rows


class RosterStream(unittest.TestCase):
    def test_only_new_rows_renew_the_clock(self):
        now = 0
        with patch('observation_rows.time.monotonic', side_effect=lambda:now):
            ids = ['a','b','c']
            raw = b''
            reader = Rows(ids, 2, 32)
            for tenant in ids:
                now += 1.5
                line = json.dumps({'tenant':tenant}).encode()+b'\n'
                raw += line
                reader.feed(line[:5])
                reader.feed(line[5:])
            reader.finish(raw)
            self.assertEqual(reader.total, len(raw))
            self.assertGreater(reader.total, reader.max_line)
            self.assertGreater(now, reader.seconds)
            self.assertEqual(reader.max_gap, 1.5)

            for invalid, code in [(b'{"tenant":"a"}\n', 'COVERAGE'),
                                  (b'{"tenant":"z"}\n', 'COVERAGE'),
                                  (b' '*33, 'BYTE_BOUND')]:
                reader = Rows(ids, 2, 32)
                reader.feed(b'{"tenant":"a"}\n')
                with self.assertRaisesRegex(Refused, code):
                    reader.feed(invalid)

            reader = Rows(ids, 2, 32)
            now += 1.5
            reader.feed(b'{"tenant":')
            now += 1
            with self.assertRaisesRegex(Refused, 'DEADLINE'):
                reader.feed(b'"a"}\n')
