#!/usr/bin/env python3
"""Publish and rescore the native capacity run's durable deadline and viewer evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import coverage_verdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'm7-joined'))
import http_accounting
import latency_oracle

# Controller-owned files produced by the SQL bookends and the synthetic frame logger.
# The native exporter separately selects the writer's fields. Never copy a packet wholesale.
BOOKENDS = ('progress-before.json', 'progress-after.json')
COUNTS = 'stored-counts.json'
FRAMES = 'viewer-frames.jsonl'
FILES = (*BOOKENDS, COUNTS, FRAMES)
WRITER_FILES = ('k6.log', 'k6-summary.json')


def read(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'missing or invalid {path.name}')
    return json.loads(path.read_bytes())


def component(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', value):
        raise ValueError('invalid run or pod identity')
    return value


def fingerprint(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'missing or invalid {path.name}')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256')
    return {'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def publish_observer(load, root):
    """Commit the controller's files atomically, independently of the writer's publication."""
    native = read(load / 'native-load.json')
    run = component(native['runId'])
    pod = component(native['podUid'])
    if run != (load / 'runid').read_text().strip():
        raise ValueError('native writer and load run IDs differ')
    before = read(load / 'before.json')
    if (before['namespace']['uid'], before['pins'], before['runId']) != (
            native['namespaceUid'], native['pins'], native['fixtureRunId']):
        raise ValueError('native writer and load identities differ')
    slices = sum(p['workload'] == 'StatefulSet/evaluator' for p in before['pods'].values())
    manifest = {'kind': 'capacity-observations-v1', 'runId': run, 'podUid': pod,
                'namespaceUid': native['namespaceUid'], 'pins': native['pins'],
                'evaluatorSlices': slices or None, 'files': {}, 'missing': [],
                'writerContinuity': native.get('writerContinuity'),
                'terminalWindow': False}
    if (load / 'window.json').exists():
        window = read(load / 'window.json')
        if (window['runId'], window['namespaceUid'], window['pins']) != (run, native['namespaceUid'], native['pins']):
            raise ValueError('window belongs to a different run')
        manifest['terminalWindow'] = (isinstance(window.get('loadStartedAt'), (int, float))
                                      and isinstance(window.get('loadEndedAt'), (int, float))
                                      and window['loadStartedAt'] <= window['loadEndedAt'])
    if (load / 'probe-exit.json').is_file():
        manifest['viewerCaptureFailure'] = read(load / 'probe-exit.json').get('code', 'UNKNOWN')
    stage = load.parent / 'experiment' / 'result.json'
    if stage.is_file():
        manifest['originalStageVerdict'] = read(stage).get('verdict')

    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='.observations-') as scratch:
        staged = Path(scratch) / 'observer'
        staged.mkdir(mode=0o700)
        for name in FILES:
            source = load / name
            if not source.exists():
                manifest['missing'].append(name)
                continue
            if source.is_symlink() or not source.is_file():
                raise ValueError(f'invalid observation {name}')
            if name in BOOKENDS and read(source).get('pins') != native['pins']:
                raise ValueError('SQL bookend has a different source')
            target = staged / name
            shutil.copyfile(source, target)
            target.chmod(0o600)
            manifest['files'][name] = fingerprint(target)
            if name == COUNTS:
                storage = read(load / 'storage-readback.json')
                if (storage.get('verdict'), storage.get('runId'), storage.get('namespaceUid'), storage.get('pins'),
                        storage.get('countsSha256')) != ('OBSERVED', run, native['namespaceUid'], native['pins'],
                                                        manifest['files'][name]['sha256']):
                    raise ValueError('stored counts do not match the run receipt')
        (staged / 'publication.json').write_text(json.dumps(manifest, indent=2) + '\n')
        target = root / 'observer'
        try:
            staged.rename(target)
        except OSError:
            if target.is_symlink() or not target.is_dir() or read(target / 'publication.json') != manifest:
                raise
            verify_files(target, manifest, manifest['files'])
    return manifest


def verify_files(directory, manifest, names):
    for name in names:
        if manifest['files'].get(name) != fingerprint(directory / name):
            raise ValueError(f'published {name} differs from its receipt')


def publish(load, root, node='node'):
    root = root.resolve()
    native = read(load / 'native-load.json')
    run, pod = component(native['runId']), component(native['podUid'])
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    cmd = [node, str(HERE / 'native-artifacts.cjs'), 'publish', str(load.resolve()), run, pod, str(root)]
    export = subprocess.run(cmd, stdout=subprocess.DEVNULL)
    # An incomplete native writer still leaves a committed partial receipt for the scorer.
    if export.returncode not in (0, 78):
        export.check_returncode()
    writer = read(root / run / pod / 'writer' / 'publication.json')
    observer = publish_observer(load, root)
    complete = (writer.get('status') == 'complete' and not observer['missing'] and observer['terminalWindow']
                and not observer.get('viewerCaptureFailure') and observer.get('writerContinuity') != 'UNMEASURED')
    return {'directory': str(root), 'runId': run, 'podUid': pod, 'status': 'complete' if complete else 'partial',
            'missingObservations': observer['missing']}


def rescore(root, writer=None, clock_bound_ms=None, offset_ms=0):
    observer = root / 'observer'
    data = None
    if observer.exists():
        data = read(observer / 'publication.json')
        if data.get('kind') != 'capacity-observations-v1' or set(data['files']) - set(FILES):
            raise ValueError('unknown observation publication')
        run, pod = component(data['runId']), component(data['podUid'])
        writer = writer or root / run / pod / 'writer'
        verify_files(observer, data, data['files'])
    writer = writer or root  # A surviving volume can supply the writer on its own.
    receipt = read(writer / 'publication.json')
    if receipt.get('kind') != 'm7-writer-publication' or set(receipt['files']) - set(WRITER_FILES):
        raise ValueError('unknown writer publication')
    run, pod = component(receipt['runId']), component(receipt['podUid'])
    if data and (run, pod) != (data['runId'], data['podUid']):
        raise ValueError('writer and observer publications do not match')
    verify_files(writer, receipt, receipt['files'])
    unavailable = {'verdict': 'UNMEASURED'}
    result = {'runId': run, 'podUid': pod, 'originalStageVerdict': (data or {}).get('originalStageVerdict'),
              'http': unavailable, 'viewerDelivery': unavailable, 'evaluatorDeadline': unavailable}
    if (data or {}).get('writerContinuity') == 'UNMEASURED' or receipt.get('status') != 'complete' or receipt.get('exitCode') != 0:
        result['reason'] = 'incomplete writer evidence'
        return result
    if set(receipt['files']) != set(WRITER_FILES):
        raise ValueError('complete writer publication is missing evidence')
    result['http'] = http_accounting.assess(read(writer / 'k6-summary.json')['metrics'])
    if not data or not data['terminalWindow']:
        result['reason'] = 'observer or terminal window unavailable'
        return result
    if set((*BOOKENDS, COUNTS)) <= data['files'].keys():
        result['evaluatorDeadline'] = coverage_verdict.from_case(
            observer, data['evaluatorSlices'], clock_bound_ms, summary_path=writer / 'k6-summary.json')
    if data.get('viewerCaptureFailure'):
        result['viewerDelivery'] = {'verdict': 'UNMEASURED', 'reason': data['viewerCaptureFailure']}
    elif FRAMES in data['files']:
        writes, counts = latency_oracle.accepted([writer / 'k6.log'], run)
        summary, _ = latency_oracle.join(writes, latency_oracle.frames(observer / FRAMES, run), offset_ms)
        result['viewerDelivery'] = {'driver': counts, 'domains': summary, 'offsetMs': offset_ms,
                                    'offsetBasis': 'driver minus viewer; zero means same clock or unmeasured'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    collect = commands.add_parser('publish', help='export retained native load evidence into a private directory')
    collect.add_argument('load', type=Path)
    collect.add_argument('directory', type=Path)
    score = commands.add_parser('rescore', help='read published inputs; no live services required')
    score.add_argument('directory', type=Path)
    score.add_argument('--writer', type=Path, help='writer directory recovered from a retained volume')
    score.add_argument('--clock-bound-ms', type=int, help='measured bound across writer, evaluator and database clocks')
    score.add_argument('--viewer-offset-ms', type=int, default=0)
    args = parser.parse_args()
    if args.command == 'publish':
        result = publish(args.load, args.directory)
    else:
        if args.clock_bound_ms is not None and args.clock_bound_ms < 0:
            parser.error('clock bound must be nonnegative')
        result = rescore(args.directory, args.writer, args.clock_bound_ms, args.viewer_offset_ms)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f'Capacity evidence unavailable: {error}')
