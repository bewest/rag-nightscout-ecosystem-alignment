#!/usr/bin/env python3
"""Project the one authored field before the initial pgstream Secret is created."""
import hashlib
import json
from pathlib import Path
import sys

from producer_wire import ACK_BUDGET, load_wire, valid_timeout


def project(contract_path, source, target):
    contract = contract_path.read_bytes()
    budget = json.loads(contract).get(ACK_BUDGET)
    if not valid_timeout(budget):
        raise RuntimeError('K8S_PGSTREAM_ACK_BUDGET_INVALID')
    if source.resolve() != source or not source.is_file() or source.parent != target.parent:
        raise RuntimeError('K8S_PGSTREAM_ACK_WIRE_PATH')
    raw = source.read_bytes()
    config, notifier = load_wire(raw)
    prior = notifier['client_timeout']
    notifier['client_timeout'] = budget
    effective = (json.dumps(config, indent=2) + '\n').encode()
    with open(target, 'xb', opener=private_open) as output:
        output.write(effective)
    return {'sourceTimeoutMs': prior, 'effectiveTimeoutMs': budget,
            'sourceWireSha256': hashlib.sha256(raw).hexdigest(),
            'effectiveWireSha256': hashlib.sha256(effective).hexdigest(),
            'sourceContractSha256': hashlib.sha256(contract).hexdigest()}


def private_open(path, flags):
    import os
    return os.open(path, flags, 0o600)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 4:
            raise RuntimeError('K8S_PGSTREAM_ACK_PUBLISH_ARGUMENTS')
        print(json.dumps(project(*(Path(value) for value in sys.argv[1:]))))
    except (OSError, TypeError, ValueError, RuntimeError) as error:
        code = str(error)
        print(code if code.startswith(('K8S_PGSTREAM_ACK_', 'M7_PGSTREAM_ACK_'))
              else 'K8S_PGSTREAM_ACK_PUBLISH_FAILED', file=sys.stderr)
        sys.exit(1)
