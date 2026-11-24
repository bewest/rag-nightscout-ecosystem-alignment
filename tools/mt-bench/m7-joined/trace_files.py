"""Read k6 scheduling CSV with independent finite gzip, decoded and row budgets."""
from contextlib import contextmanager
import csv
import gzip

from workload_inputs import MAX_SAFE_INTEGER

MAX_TRACE_BYTES = 512 * 1024**2
MAX_TRACE_ROWS = 5_000_000
LEGACY_DECODED_RATIO = 16
MAX_RECORD_BYTES = 65_536


class TraceBound(RuntimeError):
    def __init__(self):
        super().__init__('M7_DRIVER_TRACE_BOUND')


def decoded_trace_bytes(cfg):
    return cfg.get('maxDecodedTraceBytes', cfg['maxTraceBytes'] * LEGACY_DECODED_RATIO)


def validate(cfg, minimum_compressed):
    def fits(value, minimum, maximum):
        return type(value) is int and minimum <= value <= maximum

    if not (fits(cfg['maxTraceBytes'], minimum_compressed, MAX_SAFE_INTEGER // LEGACY_DECODED_RATIO)
            and fits(decoded_trace_bytes(cfg), 1, MAX_SAFE_INTEGER)
            and fits(cfg['maxTraceRows'], 1, MAX_SAFE_INTEGER)):
        raise TraceBound()


@contextmanager
def reader(path, cfg):
    if not path.is_file() or not 0 < path.stat().st_size <= cfg['maxTraceBytes']:
        raise TraceBound()
    maximum = decoded_trace_bytes(cfg)
    decoded = record_bytes = 0
    with gzip.open(path, 'rb') as source:
        def lines():
            nonlocal decoded, record_bytes
            while line := source.readline(MAX_RECORD_BYTES + 1):
                decoded += len(line)
                record_bytes += len(line)
                if record_bytes > MAX_RECORD_BYTES or decoded > maximum:
                    raise TraceBound()
                yield line.decode('utf-8')

        csv_reader = csv.DictReader(lines())

        def rows():
            nonlocal record_bytes
            for index in range(cfg['maxTraceRows'] + 1):
                record_bytes = 0
                row = next(csv_reader, None)
                if row is None:
                    return
                if index == cfg['maxTraceRows']:
                    raise TraceBound()
                yield row

        yield csv_reader.fieldnames, rows()
