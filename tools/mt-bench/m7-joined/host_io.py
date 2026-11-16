"""Host-only raw kernel IO counters; never application/PG latency."""
import json
import math
import os
from pathlib import Path
import signal
import sys
import threading
import time

DISK_FIELDS = ('reads_completed reads_merged sectors_read read_ms writes_completed '
               'writes_merged sectors_written write_ms ios_in_progress io_ms weighted_io_ms '
               'discards_completed discards_merged sectors_discarded discard_ms '
               'flushes_completed flush_ms').split()
CPU_FIELDS = 'user nice system idle iowait irq softirq steal guest guest_nice'.split()


def missing(reason):
    return {'status': 'NO-INSTRUMENT', 'reason': reason}


def diskstats(text):
    result = {}
    for line in text.splitlines():
        p = line.split()
        if len(p) < 3:
            raise ValueError('disk identity missing')
        key = f'{int(p[0])}:{int(p[1])}'
        if key in result:
            raise ValueError('duplicate disk identity')
        if len(p[3:]) not in (11, 15, 17):
            result[key] = missing('unsupported diskstats field count')
            continue
        v = [int(n) for n in p[3:]]
        if any(n < 0 for n in v):
            raise ValueError('negative disk counter')
        result[key] = {'status': 'MEASURED', 'kernelName': p[2], 'counters': dict(zip(DISK_FIELDS, v)),
                       'discardStatus': 'MEASURED' if len(v) >= 15 else 'NO-INSTRUMENT',
                       'flushStatus': 'MEASURED' if len(v) >= 17 else 'NO-INSTRUMENT'}
    return result


def cpu(text):
    row = next((line.split()[1:] for line in text.splitlines() if line.startswith('cpu ')), [])
    if not 5 <= len(row) <= len(CPU_FIELDS):
        raise ValueError('aggregate cpu/iowait missing')
    values = [int(v) for v in row]
    if any(v < 0 for v in values):
        raise ValueError('negative cpu counter')
    return {'status': 'MEASURED', 'ticks': dict(zip(CPU_FIELDS, values))}


def pressure(text):
    result = {}
    for line in text.splitlines():
        row = line.split()
        if not row or row[0] not in ('some', 'full') or row[0] in result:
            raise ValueError('unsupported pressure row')
        fields = dict(p.split('=', 1) for p in row[1:])
        if set(fields) != {'avg10', 'avg60', 'avg300', 'total'}:
            raise ValueError('pressure fields missing')
        value = {k: int(v) if k == 'total' else float(v) for k, v in fields.items()}
        if any(not math.isfinite(v) or v < 0 for v in value.values()):
            raise ValueError('invalid pressure counter')
        if any(value[k] > 100 for k in ('avg10', 'avg60', 'avg300')):
            raise ValueError('invalid pressure percentage')
        result[row[0]] = value
    if set(result) != {'some', 'full'}:
        raise ValueError('pressure some/full missing')
    return {'status': 'MEASURED', **result}


def read_counter(path, parser):
    try:
        return parser(path.read_text())
    except (OSError, ValueError, OverflowError, StopIteration):
        return missing('source missing, unreadable or malformed')


def topology(sys_root, rows):
    """Select host-visible physical leaves, excluding partitions/stacked devices.

    Device nodes in VMs identify guest-visible disks, not backing physical media.
    No serials, UUIDs, environment or other host identifiers are read.
    """
    devices, excluded = {}, {}
    for key, row in rows.items():
        try:
            if row.get('status') != 'MEASURED':
                raise ValueError('counter identity unavailable')
            node = (sys_root / 'dev/block' / key).resolve(strict=True)
            node.relative_to((sys_root / 'devices').resolve(strict=True))
            if (node / 'dev').read_text().strip() != key or node.name != row['kernelName']:
                raise ValueError('sysfs/proc identity mismatch')
            if (node / 'partition').exists():
                excluded[key] = 'partition'
                continue
            if any((node / 'slaves').iterdir()):
                excluded[key] = 'stacked device; physical leaves sampled separately'
                continue
            if 'virtual' in node.relative_to(sys_root.resolve()).parts or not (node / 'device').resolve(strict=True).is_dir():
                raise ValueError('no physical topology')
            block_size = int((node / 'queue/logical_block_size').read_text())
            if block_size <= 0:
                raise ValueError('invalid block size')
            devices[key] = {'kernelName': row['kernelName'], 'majorMinor': key,
                            'sysfsPath': '/sys/' + str(node.relative_to(sys_root.resolve())),
                            'logicalBlockBytes': block_size}
        except (OSError, ValueError):
            excluded[key] = 'NO-INSTRUMENT: physical source identity unavailable'
    return {'status': 'MEASURED' if devices else 'NO-INSTRUMENT', 'devices': devices, 'excluded': excluded}


class Sampler:
    def __init__(self, proc=Path('/proc'), sys_root=Path('/sys')):
        self.proc, self.sys_root = proc, sys_root
        initial = read_counter(proc / 'diskstats', diskstats)
        self.identity = topology(sys_root, initial if 'status' not in initial else {})

    def metadata(self):
        return {'schema': 'host-io-v1', 'scope': 'entire host; no workload/device attribution',
                'sources': ['https://docs.kernel.org/admin-guide/iostats.html',
                            'https://docs.kernel.org/accounting/psi.html',
                            'https://docs.kernel.org/filesystems/proc.html'],
                'paths': ['/proc/stat', '/proc/pressure/io', '/proc/diskstats', '/sys/dev/block'],
                'physicalDevices': self.identity,
                'units': {'cpu': 'cumulative USER_HZ ticks', 'ticksPerSecond': os.sysconf('SC_CLK_TCK'),
                          'pressureAverage': 'percent', 'pressureTotal': 'cumulative microseconds',
                          'diskSectors': '512 bytes per sector', 'diskTimes': 'cumulative milliseconds',
                          'ios_in_progress': 'instantaneous requests', 'diskOtherCounters': 'cumulative counts',
                          'clocks': 'unix wall nanoseconds and monotonic nanoseconds'},
                'limits': ['Disk request-time sums are kernel request lifecycle aggregates, not application or PostgreSQL latency.',
                           'io_ms may undercount concurrent IO; weighted_io_ms is weighted queue time.',
                           'CPU iowait can decrease and does not reliably measure per-CPU waiting.',
                           'Counters can reset on reboot, reattach or overflow; no deltas are inferred.',
                           'Topology captured once; hotplug additions are excluded; changed/disappeared topology becomes NO-INSTRUMENT; same-path device reuse cannot be detected.',
                           'Host-visible device topology does not identify cloud/hypervisor backing media.']}

    def snapshot(self):
        start = {'wallNs': time.time_ns(), 'monotonicNs': time.monotonic_ns()}
        rows = read_counter(self.proc / 'diskstats', diskstats)
        disks = {}
        for key, identity in self.identity['devices'].items():
            row = rows.get(key, missing('disk counters missing'))
            try:
                node = (self.sys_root / 'dev/block' / key).resolve(strict=True)
                actual = '/sys/' + str(node.relative_to(self.sys_root.resolve()))
                if actual != identity['sysfsPath'] or row.get('kernelName') != identity['kernelName']:
                    row = missing('disk identity changed or counters unavailable')
            except (OSError, ValueError):
                row = missing('disk identity unavailable')
            disks[key] = row
        result = {'start': start, 'cpu': read_counter(self.proc / 'stat', cpu),
                  'ioPressure': read_counter(self.proc / 'pressure/io', pressure),
                  'disks': {'status': 'MEASURED' if disks and all(v['status'] == 'MEASURED' for v in disks.values()) else 'NO-INSTRUMENT',
                            'devices': disks}}
        result['end'] = {'wallNs': time.time_ns(), 'monotonicNs': time.monotonic_ns()}
        return result


def main():
    out, interval = Path(sys.argv[1]), float(sys.argv[2])
    if not math.isfinite(interval) or not 1 <= interval <= 60:
        raise ValueError('invalid sampler interval')
    sampler = Sampler()
    (out / 'host-io-metadata.json').write_text(json.dumps(sampler.metadata(), indent=2) + '\n')
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    with (out / 'host-io.jsonl').open('w') as stream:
        while not stop.is_set():
            began = time.monotonic()
            stream.write(json.dumps(sampler.snapshot(), separators=(',', ':')) + '\n')
            stream.flush()
            stop.wait(max(0, interval - (time.monotonic() - began)))


if __name__ == '__main__':
    main()
