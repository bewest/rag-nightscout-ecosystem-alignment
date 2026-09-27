#!/usr/bin/env python3
"""Defect arrival by day and origin, from the backfix register's history.

For each BF-n id, the first commit under docs/ whose diff mentions it
(`git log --reverse -G'BF-0*n([^0-9]|$)' -- docs`, commit date) is its filing
date. Origins are the classes used in
docs/60-research/programme/paving-the-cowpaths-2026-09-27.md; the id lists
below are that record's, so a new id defaults to 'latent' until classified.

Usage: python3 tools/programme/defect-arrival.py [--json]
"""
import collections
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

REGISTER = 'docs/30-design/remedial/nightscout-backfix-register.md'

ORIGIN = {
    'invalid': {12, 41},
    'seam': set(range(18, 27)) | {82, 83, 84},
    'cuts': {56, 57, 58, 59, 60, 61, 62, 64, 65, 66},
    'connector': {8, 34, 42, 43, 85, 89, 91, 97, 98},
    'review': {109, 110, 111, 112, 113, 115, 116, 117, 130, 131},
    'escaped': {80, 106, 140, 141, 142, 143, 144},
    'github': {107} | set(range(118, 129)),
}
OUT_OF_SCOPE = {'invalid', 'seam', 'cuts'}
CLOSED = ('merged', 'closed', 'decided')


def origin(n):
    for k, ids in ORIGIN.items():
        if n in ids:
            return k
    return 'latent'


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout


def highest_id():
    text = open(REGISTER).read()
    return max(int(m) for m in re.findall(r'^\|\s*\*\*BF-(\d+)\*\*', text, re.M))


def first_seen(n):
    out = git('log', '--reverse', '--format=%cI', f'-G(^|[^0-9A-Za-z])BF-0*{n}([^0-9]|$)', '--', 'docs')
    line = out.split('\n', 1)[0]
    return line[:10] or None


def statuses():
    text = open(REGISTER).read()
    st = {}
    for line in text.split('\n'):
        m = re.match(r'\|\s*\*\*BF-(\d+)\*\*\s*\|(.*)', line)
        if not m or int(m.group(1)) in st:
            continue
        cell = [c.strip() for c in m.group(2).split('|') if c.strip()][-1].replace('*', '')
        d = re.match(r'(partly merged|merged|closed|decided|fixed)\s+(\d{4}-\d\d-\d\d)', cell)
        st[int(m.group(1))] = (d.group(1), d.group(2)) if d else (cell.split()[0].strip(',—'), None)
    return st


def main():
    top = highest_id()
    ids = [n for n in range(1, top + 1)]
    with ThreadPoolExecutor(12) as ex:
        found = dict(zip(ids, ex.map(first_seen, ids)))
    st = statuses()
    rows = []
    for n in ids:
        if not found[n]:
            continue
        s, d = st.get(n, ('reserved', None))
        closed = max(d, found[n]) if (s in CLOSED and d) else None
        rows.append({'id': n, 'found': found[n], 'origin': origin(n), 'status': s, 'closed': closed})
    if '--json' in sys.argv:
        json.dump(rows, sys.stdout, indent=1)
        return
    days = sorted({r['found'] for r in rows} | {r['closed'] for r in rows if r['closed'] and r['closed'] >= min(r['found'] for r in rows)})
    cols = ['latent', 'github', 'connector', 'review', 'escaped', 'seam', 'cuts', 'invalid']
    print('date        ' + ' '.join(f'{c:>9}' for c in cols) + '    total  closed  open(scope)')
    scope = [r for r in rows if r['origin'] not in OUT_OF_SCOPE]
    for day in days:
        c = collections.Counter(r['origin'] for r in rows if r['found'] == day)
        closed = sum(r['closed'] == day for r in scope)
        opn = sum(r['found'] <= day and not (r['closed'] and r['closed'] <= day) for r in scope)
        print(f'{day}  ' + ' '.join(f'{c[k]:>9}' for k in cols) + f'  {sum(c.values()):>7} {closed:>7} {opn:>12}')
    t = collections.Counter(r['origin'] for r in rows)
    print('all         ' + ' '.join(f'{t[k]:>9}' for k in cols) + f'  {len(rows):>7}')


if __name__ == '__main__':
    main()
