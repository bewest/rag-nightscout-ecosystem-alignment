"""Stage the joined clinical probe and its selected platform transport."""
import hashlib
from pathlib import Path
import shutil

HELPERS = ('evaluator_recovery.py','evaluator_progress.py','evaluator-progress.cjs','probe-accounting.cjs',
           'completed-oracle.cjs','accepted-writer-baseline.sql','native-observation.cjs','client-delivery.cjs','durable-lag.cjs','clinical-timing.cjs')


def generate(root, target, *, transport=None):
    root, target = Path(root), Path(target)
    directory = root/'tools/mt-bench/m7-joined'
    program = directory/'joined-probe.cjs'
    selected = Path(transport) if transport else directory/'probe-compose.cjs'
    shutil.copyfile(program, target)
    helpers = {}
    for source, name in [(selected, 'probe-transport.cjs'), *((directory/name, name) for name in HELPERS)]:
        destination = target.with_name(name)
        shutil.copyfile(source, destination)
        helpers[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {'baseline':str(program.relative_to(root)), 'baselineSha256':digest,
            'adaptedSha256':digest, 'recoveryHelpers':helpers}
