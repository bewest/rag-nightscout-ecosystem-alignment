#!/usr/bin/env python3
"""canary.py - scan container logs for credentials and record-shaped text.

    canary.py <state-dir> <container...>

Saves each container's full `docker logs` (stdout and stderr) under
<state>/logs/<container>.log, then counts, per log, occurrences of:

  * every lab secret and access token under <state>/secrets (raw value, and the
    SHA-1 hex of each raw secret - the form Nightscout compares), and each
    token/secret URL-encoded;
  * credential-shaped text: JWTs, 40-hex strings, api-secret headers, Bearer,
    token= query strings, password, accessToken;
  * record-shaped text: lab record ids, sgv/carbs/insulin fields.

It prints counts only, never a matched value. A count of zero is evidence only
if the same scan finds a planted value, so the scan first plants a synthetic
canary line in a scratch file and fails if it cannot find it.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse

state, containers = sys.argv[1], sys.argv[2:]
secdir = os.path.join(state, 'secrets')
logdir = os.path.join(state, 'logs')
os.makedirs(logdir, exist_ok=True)

literals = {}
for f in sorted(os.listdir(secdir)):
    if f.endswith('.env'):
        continue
    raw = open(os.path.join(secdir, f)).read().strip()
    if len(raw) < 8:
        continue
    literals[f'{f}:raw'] = raw
    literals[f'{f}:urlenc'] = urllib.parse.quote(raw, safe='')
    if not f.endswith('.token'):
        literals[f'{f}:sha1'] = hashlib.sha1(raw.encode()).hexdigest()

shapes = {
    'jwt': re.compile(r'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
    'hex40': re.compile(r'\b[0-9a-f]{40}\b'),
    'api-secret': re.compile(r'api[-_]?secret', re.I),
    'bearer': re.compile(r'bearer\s+\S', re.I),
    'token=': re.compile(r'token=', re.I),
    'password': re.compile(r'password', re.I),
    'accessToken': re.compile(r'accesstoken', re.I),
    'record:soakId': re.compile(r'cksoak-(sgv|mbg|ds|carb|bolus|temp|profile)-'),
    'record:sgv-field': re.compile(r'["\']?sgv["\']?\s*:\s*\d'),
    'record:carbs/insulin': re.compile(r'["\']?(carbs|insulin)["\']?\s*:\s*\d'),
}


def scan(text):
    out = {k: text.count(v) for k, v in literals.items()}
    out.update({k: len(r.findall(text)) for k, r in shapes.items()})
    return out


# Self-test: a planted secret and a planted JWT must be found.
if literals:
    k0, v0 = next(iter(literals.items()))
    probe = scan('x ' + v0 + ' eyJabcdefghij.klmnopqrstuv y')
    if probe[k0] < 1 or probe['jwt'] < 1:
        sys.exit('canary self-test failed: the scan cannot see a planted value')

report = {}
for c in containers:
    p = subprocess.run(['docker', 'logs', c], capture_output=True, text=True, errors='replace')
    text = p.stdout + p.stderr
    open(os.path.join(logdir, c + '.log'), 'w').write(text)
    counts = scan(text)
    report[c] = {'lines': text.count('\n'), 'bytes': len(text),
                 'hits': {k: v for k, v in counts.items() if v}}
print(json.dumps({'literals_checked': len(literals), 'shapes': list(shapes), 'containers': report}, indent=1))
