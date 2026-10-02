#!/usr/bin/env python3
"""Measure the series the 15.0.9 colophon charts, into
releases/cgm-remote-monitor-15.0.9/colophon-data.json.

Sources, each re-read on every run:
  - cgm-remote-monitor history (externals/cgm-remote-monitor-official, after
    `git fetch official`): PR merges per day and the headline counts;
  - tools/programme/defect-arrival.py: each register id's filing and closing
    date and its origin;
  - releases/cgm-remote-monitor-15.0.9/colophon.md: the test-run tables and
    the regressions table, which record runs and decisions that git cannot
    re-derive.

Usage: python3 tools/programme/colophon-data.py [--range official/master..official/dev]
Then re-render the page: tools/site/.venv/bin/python tools/site/render_colophon.py
"""
import collections
import os
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CRM = Path(os.environ.get('CRM_REPO', REPO / 'externals/cgm-remote-monitor-official'))
COLOPHON = REPO / 'releases/cgm-remote-monitor-15.0.9/colophon.md'
OUT = REPO / 'releases/cgm-remote-monitor-15.0.9/colophon-data.json'
YEAR = '2026'
SCOPE_ORIGINS = ['latent', 'github', 'connector', 'review', 'escaped']
OUT_OF_SCOPE = {'seam', 'cuts', 'invalid'}

# The kind of check first run on a day, from the 2026-09-27 snapshot §5
# (docs/60-research/programme/paving-the-cowpaths-2026-09-27.md) and, for
# 10-01, the triage commit 2caadf63.
CHECKS = [
    ('2026-09-14', 'code audit'),
    ('2026-09-21', 'security advisory review'),
    ('2026-09-22', 'client census (40 clients)'),
    ('2026-09-23', 'client replay lab'),
    ('2026-09-24', 'review of #8758'),
    ('2026-09-25', 'GitHub issue triage'),
    ('2026-09-26', 'release-candidate runs, soak, journey lab'),
    ('2026-10-01', 'triage of new reports and advisories'),
]


def git(*args, cwd=CRM):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout


def days(first, last):
    d, end = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    while d <= end:
        yield d.isoformat()
        d += dt.timedelta(days=1)


def md_table(text, header_start):
    """Rows of the first markdown table whose header row starts with header_start."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(header_start):
            rows = []
            for row in lines[i + 2:]:
                if not row.startswith('|'):
                    break
                rows.append([c.strip() for c in row.strip().strip('|').split('|')])
            return [c.strip() for c in line.strip().strip('|').split('|')], rows
    sys.exit(f'colophon-data: no table starting {header_start!r} in {COLOPHON.name}')


def short(s):
    return re.sub(r'`', '', s)


def main():
    rng = sys.argv[sys.argv.index('--range') + 1] if '--range' in sys.argv else 'official/master..official/dev'
    base, tip = rng.split('..')
    tip_sha = git('rev-parse', '--short=8', tip).strip()
    base_sha = git('rev-parse', '--short=8', base).strip()

    # PR merges per day
    merges = collections.OrderedDict()
    for line in git('log', '--first-parent', '--reverse', '--format=%ad\t%s', '--date=short', rng).splitlines():
        date, subj = line.split('\t', 1)
        m = re.search(r'#(\d+)', subj)
        merges.setdefault(date, []).append(int(m.group(1)) if m else None)
    first_day, last_day = next(iter(merges)), next(reversed(merges))

    # defects: filing and closing by day
    arrival = json.loads(subprocess.run([sys.executable, str(REPO / 'tools/programme/defect-arrival.py'), '--json'],
                                        cwd=REPO, check=True, capture_output=True, text=True).stdout)
    scope = [r for r in arrival if r['origin'] not in OUT_OF_SCOPE]
    d_first = min(r['found'] for r in arrival)
    d_last = max([r['found'] for r in arrival] + [r['closed'] for r in arrival if r['closed']] + [last_day])
    defects = []
    for day in days(d_first, d_last):
        by = collections.Counter(r['origin'] for r in arrival if r['found'] == day)
        defects.append({
            'date': day,
            'filed': {o: by[o] for o in SCOPE_ORIGINS},
            'filed_out_of_scope': sum(by[o] for o in OUT_OF_SCOPE),
            'filed_cum': sum(r['found'] <= day for r in scope),
            'closed_cum': sum(bool(r['closed']) and r['closed'] <= day for r in scope),
        })

    text = COLOPHON.read_text(encoding='utf-8')

    # test runs: the run-history table (transposed: one column per run) and the after-run-020 table
    head, rows = md_table(text, '| run | bf2 |')
    table = {r[0]: r[1:] for r in rows}
    runs = []
    for i, name in enumerate(head[1:]):
        dd = table['date (09-)'][i].split('/')[-1]
        cells = table.get('cells (blank: not recorded)', [''] * len(head))[i]
        runs.append({'label': f'run {name}', 'date': f'{YEAR}-09-{int(dd):02d}', 'passing': int(table['passing'][i]),
                     'cells': int(cells) if cells else None, 'kind': 'release-candidate run'})
    _, after = md_table(text, '| merge | check |')
    for merge, check, result in after:
        m = re.match(r'(\d+)/\d+/\d+', short(result).split()[0]) if result not in ('—', '') else None
        if not m:
            continue
        pr = re.search(r'#(\d+)', merge).group(1)
        date = next(d for d, prs in merges.items() if int(pr) in prs)
        runs.append({'label': f'#{pr}', 'date': date, 'passing': int(m.group(1)), 'cells': 1 if 'CI' not in check else 9,
                     'kind': 'one merge, its own branch or CI'})
    baseline = re.search(r'15\.0\.8[^|\n]*?\b(1533)/0/3', text) or re.search(r'\b(1533)/0/3', text)

    # regressions
    _, reg = md_table(text, '| id | cause merged |')
    regressions = []
    for rid, cause, filed, fix, family in reg:
        cpr, cdate = re.match(r'#(\d+), (\d\d-\d\d)', cause).groups()
        fpr, fdate = re.match(r'#(\d+), (\d\d-\d\d)', fix).groups()
        regressions.append({'id': rid, 'cause_pr': int(cpr), 'caused': f'{YEAR}-{cdate}', 'filed': f'{YEAR}-{filed}',
                            'fix_pr': int(fpr), 'fixed': f'{YEAR}-{fdate}', 'family': short(family)})

    # the open entries by disposition
    _, opn = md_table(text, '| disposition | entries | count |')
    open_entries = []
    for disp, entries, count in opn:
        if disp.startswith('**'):
            continue
        ids = re.findall(r'BF-\d+', entries)
        if len(ids) != int(count):
            sys.exit(f'colophon-data: {disp!r} lists {len(ids)} ids but says {count}')
        open_entries.append({'disposition': disp, 'count': len(ids), 'ids': ids})
    if sum(o['count'] for o in open_entries) != sum(1 for r in scope if not r['closed']):
        sys.exit('colophon-data: the open-entries table does not cover every open in-scope id')
    listed = {int(i[3:]) for o in open_entries for i in o['ids']}
    actual = {r['id'] for r in scope if not r['closed']}
    if listed != actual:
        sys.exit(f'colophon-data: open table differs from the register: missing {sorted(actual - listed)}, extra {sorted(listed - actual)}')

    it_count = lambda ref: sum(int(l.rsplit(':', 1)[1]) for l in git('grep', '-cE', r'^\s*it\(', ref, '--', 'tests').splitlines())
    data = {
        'measured': dt.date.today().isoformat(),
        'range': {'base': base_sha, 'tip': tip_sha, 'spec': rng},
        'repo_commit': git('rev-parse', '--short=8', 'HEAD', cwd=REPO).strip(),
        'kpis': {
            'pr_merges': int(git('rev-list', '--first-parent', '--count', rng)),
            'commits': int(git('rev-list', '--count', rng)),
            'non_merge_commits': int(git('rev-list', '--no-merges', '--count', rng)),
            'it_calls': {'base': it_count(base), 'tip': it_count(tip)},
            'passing': {'base': int(baseline.group(1)) if baseline else None, 'tip': max(r['passing'] for r in runs)},
            'defect_ids': len(arrival),
            'defect_ids_in_scope': len(scope),
            'regressions_caught': len(regressions),
        },
        'merges_per_day': [{'date': d, 'count': len(merges.get(d, [])), 'prs': [p for p in merges.get(d, []) if p]}
                           for d in days(first_day, last_day)],
        'defects': defects,
        'checks': [{'date': d, 'label': l} for d, l in CHECKS],
        'runs': runs,
        'regressions': regressions,
        'open_entries': open_entries,
    }
    OUT.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
    k = data['kpis']
    print(f"wrote {OUT.relative_to(REPO)}: {rng} = {base_sha}..{tip_sha}; {k['pr_merges']} merges, "
          f"{len(defects)} defect days, {len(runs)} runs, {len(regressions)} regressions")


if __name__ == '__main__':
    main()
