"""v1_operator_census.py — which API v1 query operators clients actually send.

Task T2.4 of the multitenancy execution plan:

    Derive the operators clients actually send from the corpus; support those,
    reject the rest with a documented 400. Ships as a security fix regardless
    of Postgres -- it is the allowlist that does not exist today.

WHY SOURCE CODE AND NOT REQUEST LOGS. There are no request logs. What this
workspace has instead is ~58 checked-out ecosystem projects, and API v1 encodes
its filters in the URL as ``find[field][$op]=value``, which is a literal string
in client source. So the query surface can be read directly out of the clients
that produce it.

That is evidence of a specific kind and its limits belong with the number:
it measures what client SOURCE contains, not what a running deployment
receives. A query built by string concatenation at runtime, or typed by a human
into a browser, is invisible here. It is a **lower bound on the field set and a
strong signal on the operator set**, because the operator is almost always a
literal even when the field and value are not.

The same method is already used in this repository for field attribution
(``reports/schema-census/attribution.json``), with the same caveat.

Usage:
    python3 tools/qc/v1_operator_census.py
    python3 tools/qc/v1_operator_census.py --include-server
"""

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

# Every bracketed segment following `find`, so the nested form is parsed rather
# than mangled. API v1 accepts BOTH shapes and a real client sends the second:
#
#     find[created_at][$gte]=...                  flat
#     find[$and][0][enteredBy][$ne]=...           indexed group  (Trio)
#     find[$or][0][id][$eq]=...                   indexed group  (Trio)
#
# Segments may hold a language's interpolation syntax instead of a literal
# index -- Swift's \(idx), JS ${i}, Python {} -- which is why the index is
# normalised rather than required to be a number.
PATTERN = re.compile(r"""find((?:\[[^\[\]\s"'=&]*\])+)""")
SEGMENT = re.compile(r'\[([^\[\]]*)\]')
LOGICAL = {'$and', '$or', '$nor', '$not'}
INDEXISH = re.compile(r'^(\d+|\\?\(\w+\)|\$\{[^}]*\}|\{[^}]*\}|%[sd]|i|idx|index|n)$')


def parse(segments):
    """[segments] -> (logical_group_or_None, field, operator)."""
    segs = [x for x in segments if x != '']
    if not segs:
        return None
    group = None
    segs = [x.lstrip('\\') for x in segs]
    if segs[0] in LOGICAL:
        group = segs[0]
        segs = segs[1:]
        # the array index, literal or interpolated
        if segs and INDEXISH.match(segs[0]):
            segs = segs[1:]
    if not segs:
        return None
    field = segs[0]
    op = segs[1] if len(segs) > 1 else '$eq'
    # Dart (and shell, and template literals) escape the sigil: find[date][\$lte].
    # Normalise, or the same operator is counted as two.
    return group, field, op.lstrip('\\').lstrip('$')

EXTENSIONS = ('*.js', '*.mjs', '*.cjs', '*.ts', '*.tsx', '*.swift', '*.java',
              '*.kt', '*.py', '*.dart', '*.rb', '*.go', '*.cs', '*.php',
              '*.md', '*.json', '*.yaml', '*.yml', '*.sh')

# Nightscout itself and its own copies: these are the SERVER, so their
# occurrences are the surface being offered, not demand for it.
SERVER_DIRS = {'cgm-remote-monitor', 'cgm-remote-monitor-official', 'work',
               'releases', 'readiness', 'nocturne', 'ns-resync-2026-04-26'}

# NOT ecosystem clients. `experiments` holds autoresearch run artifacts that
# include a full nested copy of THIS repository, so counting it would double-
# count our own documentation as third-party demand.
NOT_CLIENTS = {'experiments', 'logs', 'reports', 'models', 'sweep-data',
               'sweep-uva', 'sweep-uva-250', 'ns-data', 'ns-parquet',
               'ns-parquet-tiny', 'ns-parquet-dynisf-v2',
               'ns-parquet-dynisf-v2-split', 'ns-data-dynisf', 'settings-recommendations'}
SELF_COPY = 'rag-nightscout-ecosystem-alignment'

# Names that are obviously a variable being interpolated rather than a field.
# Kept as a list rather than a heuristic so the judgement is reviewable.
PLACEHOLDER = {'prop', 'field', 'key', 's', 'l', 'k', 'f', 'name', 'x',
               'fieldName', 'property', 'attr', 'col', 'column'}

# The seam's filter AST (lib/storage/filter.js). An operator outside this set
# cannot be expressed, which is precisely what makes the AST an allowlist.
AST_OPS = {'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'nin', 're', 'exists'}


def repos(root, include_server):
    for entry in sorted((root / 'externals').iterdir()):
        if not entry.is_dir() or entry.name.startswith('.'):
            continue
        if entry.name in NOT_CLIENTS:
            continue
        if not include_server and entry.name in SERVER_DIRS:
            continue
        yield entry


def scan(repo):
    """Every find[...] occurrence in one repo, with the file it came from."""
    cmd = ['grep', '-rn', '--binary-files=without-match', '-E', r'find\[']
    for ext in EXTENSIONS:
        cmd += ['--include', ext]
    cmd.append('.')
    try:
        out = subprocess.run(cmd, cwd=repo, capture_output=True, text=True,
                             timeout=300, errors='replace').stdout
    except subprocess.TimeoutExpired:
        return []
    hits = []
    for line in out.splitlines():
        parts = line.split(':', 2)
        if len(parts) < 3:
            continue
        path, lineno, text = parts
        if 'node_modules' in path or '/.git/' in path or SELF_COPY in path:
            continue
        for segments in PATTERN.findall(text):
            parsed = parse(SEGMENT.findall(segments))
            if not parsed:
                continue
            group, field, op = parsed
            hits.append({'file': path.lstrip('./'), 'line': int(lineno),
                         'field': field, 'op': op, 'group': group})
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', default=Path(__file__).resolve().parents[2], type=Path)
    ap.add_argument('--include-server', action='store_true')
    ap.add_argument('--out', default='reports/v1-query-census', type=Path)
    args = ap.parse_args(argv)

    by_op = defaultdict(lambda: {'count': 0, 'repos': set(), 'fields': defaultdict(int)})
    by_group = defaultdict(lambda: {'count': 0, 'repos': set()})
    by_field = defaultdict(lambda: {'count': 0, 'repos': set(), 'ops': defaultdict(int)})
    per_repo = {}
    sites = []

    for repo in repos(args.root, args.include_server):
        hits = scan(repo)
        if not hits:
            continue
        per_repo[repo.name] = len(hits)
        for h in hits:
            op, field = h['op'], h['field']
            by_op[op]['count'] += 1
            by_op[op]['repos'].add(repo.name)
            by_op[op]['fields'][field] += 1
            by_field[field]['count'] += 1
            by_field[field]['repos'].add(repo.name)
            by_field[field]['ops'][op] += 1
            if h['group']:
                by_group[h['group']]['count'] += 1
                by_group[h['group']]['repos'].add(repo.name)
            sites.append({'repo': repo.name, **h})

    def op_rows():
        for op, v in sorted(by_op.items(), key=lambda kv: -kv[1]['count']):
            yield {'operator': op, 'occurrences': v['count'],
                   'projects': sorted(v['repos']),
                   'in_ast': op in AST_OPS,
                   'top_fields': sorted(v['fields'].items(), key=lambda kv: -kv[1])[:5]}

    def field_rows():
        for f, v in sorted(by_field.items(), key=lambda kv: -kv[1]['count']):
            yield {'field': f, 'occurrences': v['count'],
                   'projects': sorted(v['repos']),
                   'placeholder': f in PLACEHOLDER,
                   'operators': dict(sorted(v['ops'].items(), key=lambda kv: -kv[1]))}

    report = {
        'generated_by': 'tools/qc/v1_operator_census.py',
        'method': 'literal find[field][$op] occurrences in ecosystem project source',
        'scope': 'server repos included' if args.include_server else 'client projects only',
        'projects_scanned': len(per_repo),
        'occurrences': len(sites),
        'operators': list(op_rows()),
        'logical_groups': {g: {'occurrences': v['count'], 'projects': sorted(v['repos'])}
                           for g, v in sorted(by_group.items(), key=lambda kv: -kv[1]['count'])},
        'fields': list(field_rows()),
        'per_project': dict(sorted(per_repo.items(), key=lambda kv: -kv[1])),
    }

    out_dir = args.root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'census.json').write_text(json.dumps(report, indent=1) + '\n')
    with (out_dir / 'sites.tsv').open('w') as fh:
        fh.write('repo\tfile\tline\tgroup\tfield\toperator\n')
        for s in sorted(sites, key=lambda s: (s['repo'], s['file'], s['line'])):
            fh.write(f"{s['repo']}\t{s['file']}\t{s['line']}\t{s['group'] or ''}"
                     f"\t{s['field']}\t{s['op']}\n")

    print(f"{len(sites)} occurrences across {len(per_repo)} projects "
          f"({report['scope']})\n")
    print(f"{'operator':10s} {'count':>6s}  {'projects':>8s}  in-AST  top fields")
    print('-' * 78)
    for r in report['operators']:
        fields = ', '.join(f for f, _ in r['top_fields'][:3])
        print(f"{r['operator']:10s} {r['occurrences']:6d}  {len(r['projects']):8d}  "
              f"{'yes' if r['in_ast'] else 'NO ':6s}  {fields[:40]}")

    if report['logical_groups']:
        print('\nlogical grouping (nested form find[$and][0][field][$op]):')
        for g, v in report['logical_groups'].items():
            print(f"  {g:6s} {v['occurrences']:4d}  {', '.join(v['projects'])}")

    outside = [r for r in report['operators'] if not r['in_ast']]
    print(f"\noperators OUTSIDE the seam's AST: {len(outside)}"
          + (f" -> {', '.join(r['operator'] for r in outside)}" if outside else ''))
    print(f"\nwrote {(out_dir / 'census.json').relative_to(args.root)} and sites.tsv")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
