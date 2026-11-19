"""Read one roster-bound JSONL response with a renewable inactivity window.

Only a complete row or inspection page covering previously unseen selected
tenants renews the clock. Raw bytes may be retained before any JSON decoding.
The caller owns the outer work/drain cutoff and the strict typed decoder.
"""
import json
import os
import selectors
import subprocess
import tempfile
import time

from evaluator_progress import Refused, need


class Rows:
    def __init__(self, ids, seconds, max_line, *, pages=False, sink=None):
        self.pending = set(ids)
        self.seconds = seconds
        self.max_line = max_line
        self.pages = pages
        self.sink = sink
        self.last = time.monotonic()
        self.max_gap = 0
        self.largest = 0
        self.total = 0
        self.buffer = bytearray()

    def check(self):
        gap = time.monotonic() - self.last
        self.max_gap = max(self.max_gap, gap)
        need(gap < self.seconds, 'M7_OPPORTUNITY_DEADLINE')
        return self.seconds - gap

    def line(self):
        self.check()
        need(len(self.buffer) <= self.max_line, 'M7_OPPORTUNITY_BYTE_BOUND')
        self.largest = max(self.largest, len(self.buffer))
        row = json.loads(self.buffer)
        if self.pages:
            ids = row['selected']
            need(isinstance(ids, list) and 0 < len(ids) <= 128
                 and len(ids) == len(set(ids)), 'M7_EVALUATOR_PROGRESS_SELECTOR')
        else:
            ids = [row[0] if isinstance(row, list) else row['tenant']]
        need(self.pending.issuperset(ids), 'M7_OPPORTUNITY_COVERAGE')
        self.pending.difference_update(ids)
        self.buffer.clear()
        self.check()
        self.last = time.monotonic()

    def feed(self, data):
        if self.sink:
            self.sink(data)
        self.total += len(data)
        self.check()
        parts = data.split(b'\n')
        for part in parts[:-1]:
            self.buffer.extend(part)
            self.line()
        self.buffer.extend(parts[-1])
        need(len(self.buffer) <= self.max_line, 'M7_OPPORTUNITY_BYTE_BOUND')

    def finish(self, raw):
        # In-process transports can deliver the whole response at once.
        if not self.total:
            self.feed(raw)
        self.check()
        if self.buffer:
            self.line()
        need(not self.pending, 'M7_OPPORTUNITY_COVERAGE')

    def run(self, argv, *, input, stdout, stderr, timeout, **options):
        """subprocess.run interface for a selected SQL/inspection command."""
        until = time.monotonic() + timeout
        output = bytearray()
        with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as errors:
            source.write(input)
            source.seek(0)
            with subprocess.Popen(argv, stdin=source, stdout=subprocess.PIPE, stderr=errors,
                                  **options) as child, selectors.DefaultSelector() as poll:
                try:
                    poll.register(child.stdout, selectors.EVENT_READ)
                    while True:
                        remaining = min(self.check(), until - time.monotonic())
                        if remaining <= 0 or not poll.select(remaining):
                            raise Refused('M7_OPPORTUNITY_DEADLINE')
                        data = os.read(child.stdout.fileno(), 65536)
                        if not data:
                            break
                        if stdout == subprocess.PIPE:
                            output.extend(data)
                        else:
                            stdout.write(data)
                        self.feed(data)
                    try:
                        child.wait(timeout=max(0, min(self.check(), until - time.monotonic())))
                    except subprocess.TimeoutExpired:
                        raise Refused('M7_OPPORTUNITY_DEADLINE') from None
                    self.check()
                    need(time.monotonic() <= until, 'M7_OPPORTUNITY_DEADLINE')
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait()
                    errors.seek(0)
                    diagnostic = errors.read()
                    if stderr != subprocess.PIPE:
                        stderr.write(diagnostic)
        return subprocess.CompletedProcess(argv, child.returncode, bytes(output), diagnostic)
