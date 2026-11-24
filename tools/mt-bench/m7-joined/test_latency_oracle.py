"""M3 offline latency oracle: synthetic driver lines and viewer frames, no database."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import latency_oracle as o  # noqa: E402

A, B, C = 'tenant-a', 'tenant-b', 'tenant-c'
RUN = 'run-1'


def k6_line(tenant, domain, key, accepted, request=20, run=RUN):
    msg = json.dumps({'event': 'm7-input-accepted', 'run': run, 'tenant': tenant, 'domain': domain, 'key': key,
                      'requestToAcceptanceMs': request, 'acceptedAtMs': accepted})
    return 'time="2026-11-21T00:00:00Z" level=info msg=%s source=console\n' % json.dumps(msg)


def frame(tenant, at, entries=None, devicestatus=None, treatments=None, socket=0, run=RUN):
    keys = {domain: [key] if key is not None else [] for domain, key in
            [('entries', entries), ('devicestatus', devicestatus), ('treatments', treatments)]}
    return json.dumps({'event': 'viewer-frame', 'version': 2, 'run': run, 'tenant': tenant,
                       'socket': socket, 'atMs': at, 'delta': False, 'keys': keys}) + '\n'


class LatencyOracle(unittest.TestCase):
    def run_oracle(self, lines, frames, offset=0):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'k6.log').write_text(''.join(lines))
            (Path(d) / 'frames.jsonl').write_text(''.join(frames))
            out = subprocess.run([sys.executable, '-I', str(HERE / 'latency_oracle.py'), '--k6', d, '--frames', str(Path(d) / 'frames.jsonl'),
                                  '--run', RUN, '--offset-ms', str(offset), '--rows', str(Path(d) / 'rows.jsonl')],
                                 check=True, capture_output=True, text=True).stdout
            rows = [json.loads(x) for x in (Path(d) / 'rows.jsonl').read_text().splitlines()]
        return json.loads(out), rows

    def test_joins_first_frame_reflecting_each_write(self):
        lines = [k6_line(A, 'entries', '1000000', 5000), k6_line(A, 'entries', '1300000', 305000),
                 k6_line(A, 'devicestatus', '1970-01-01T00:16:40.000Z', 5100)]
        frames = [frame(A, 4000, entries=700000),                     # primed, before the write
                  frame(A, 6500, entries=1000000, devicestatus=1000000),  # reflects both first writes
                  frame(A, 7000, entries=1000000, socket=1),
                  frame(A, 309000, entries=1300000)]
        doc, rows = self.run_oracle(lines, frames)
        self.assertEqual(doc['domains']['entries']['matched'], 2)
        self.assertEqual(sorted(r['lagMs'] for r in rows if r['domain'] == 'entries'), [1500, 4000])
        self.assertEqual(doc['domains']['devicestatus']['matched'], 1)
        self.assertEqual(doc['domains']['devicestatus']['p50Ms'], 1400)
        self.assertEqual(doc['domains']['entries']['within1000Ms'], 0)
        self.assertEqual(doc['domains']['entries']['within30000Ms'], 2)

    def test_offset_sign(self):
        # Driver clock runs 300 ms ahead of the viewer: the frame happened 300 ms later in driver time.
        doc, rows = self.run_oracle([k6_line(A, 'entries', '1000000', 5000)], [frame(A, 5500, entries=1000000)], offset=300)
        self.assertEqual(rows[0]['lagMs'], 800, 'OFFSET_SIGN')
        doc, rows = self.run_oracle([k6_line(A, 'entries', '1000000', 5000)], [frame(A, 5500, entries=1000000)], offset=-300)
        self.assertEqual(rows[0]['lagMs'], 200)

    def test_skipped_input_foreign_run_and_old_ledger_cannot_prove_delivery(self):
        lines = [k6_line(A, 'entries', '1000000', 5000)]
        observations = [frame(A, 6000, entries=1000001), frame(A, 6500, entries=1000000, run='other'),
                        frame(A, 140000)]
        doc, rows = self.run_oracle(lines, observations)
        self.assertFalse(rows)
        self.assertEqual(doc['domains']['entries']['unmatched'], 1)
        legacy = json.dumps(dict(event='viewer-frame', tenant=A, atMs=6000, entries=1000000)) + '\n'
        doc, rows = self.run_oracle(lines, [legacy])
        self.assertFalse(rows)
        self.assertEqual(doc['domains']['entries']['legacyUnmeasured'], 1)

    def test_frames_before_the_request_cannot_match(self):
        # A frame carrying a key at least as new, but received before the request began (a clock or key error), is ignored.
        doc, _ = self.run_oracle([k6_line(A, 'entries', '1000000', 5000, request=100)],
                                 [frame(A, 4800, entries=2000000), frame(A, 200000, entries=0)])
        self.assertEqual(doc['domains']['entries']['matched'], 0)
        self.assertEqual(doc['domains']['entries']['unmatched'], 1)

    def test_unviewed_censored_and_unmatched(self):
        lines = [k6_line(B, 'entries', '1000000', 5000),           # no viewer
                 k6_line(A, 'entries', '1000000', 5000),           # never reflected, ledger runs past the deadline
                 k6_line(A, 'entries', '9000000', 190000),         # accepted < 120 s before the ledger ends
                 k6_line(C, 'entries', '1000000', 5000, run='other')]
        doc, _ = self.run_oracle(lines, [frame(A, 1000, entries=10), frame(A, 200000, entries=10)])
        d = doc['domains']['entries']
        self.assertEqual((d['unviewed'], d['unmatched'], d['censored'], d['matched']), (1, 1, 1, 0))
        self.assertEqual(doc['driver']['otherRun'], 1)

    def test_lines_without_acceptance_time_are_counted_not_joined(self):
        line = k6_line(A, 'entries', '1000000', 5000).replace(', \\"acceptedAtMs\\": 5000', '')
        self.assertNotIn('acceptedAtMs', line)
        doc, _ = self.run_oracle([line], [frame(A, 6000, entries=1000000)])
        self.assertEqual(doc['driver']['noAcceptanceTime'], 1)
        self.assertEqual(doc['domains']['entries']['matched'], 0)

    def test_json_log_format(self):
        msg = json.loads(json.loads(k6_line(A, 'entries', '1000000', 5000).split('msg=')[1].split(' source=')[0]))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'k6.log'
            p.write_text(json.dumps({'level': 'info', 'msg': json.dumps(msg)}) + '\n')
            rows, counts = o.accepted([p], RUN)
        self.assertEqual(len(rows), 1)
        self.assertEqual(counts['malformed'], 0)


if __name__ == '__main__':
    unittest.main()
