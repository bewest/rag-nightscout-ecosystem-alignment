#!/usr/bin/env python3
"""Explicit fake Kubernetes transport for the bounded instrument qualifier."""
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen
root = Path(__file__).resolve().parent
value = json.loads((root / 'transport.json').read_text())
args = sys.argv[1:]
if 'get' in args:
    args = args[args.index('get')+1:]
    kind = args[0]
    result = ({'items': value['pods']} if kind == 'pods' else {'items': []} if kind == 'replicasets'
              else value['objects'][('Namespace' if kind == 'namespace' else kind) + '/' + args[1]])
    print(json.dumps(result))
else:
    assert 'exec' in args
    raw = sys.stdin.buffer.read()
    if 'psql' in args:
        endpoint, data = 'sql', raw
    else:
        ids = re.search(rb'const M7_PROGRESS_IDS=(.*?);', raw)[1]
        endpoint, data = 'progress', ids
    with urlopen(Request(value['base'] + '/synthetic/' + endpoint, data=data), timeout=5) as reply:
        sys.stdout.buffer.write(reply.read())
