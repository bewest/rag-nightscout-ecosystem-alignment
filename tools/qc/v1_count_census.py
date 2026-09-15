"""v1_count_census.py — what clients put in API v1's ``count=`` parameter.

Sizes BF-14. ``?count=0`` returns the whole collection rather than nothing,
because the limit is built from a truthiness test on a string
(``opts.count ? parseInt(opts.count) : undefined``) and MongoDB defines
``.limit(0)`` as no limit. The defect is proven; what was missing is how much
real traffic can reach it.

WHAT THIS CAN AND CANNOT SEE. Same method and same limits as
``v1_operator_census.py``: it reads client SOURCE, not request logs, because
there are no request logs. That distinction matters more here than it did for
operators. An operator is almost always a literal in source even when the field
and value are not; a **count is very often computed**. So the literal
distribution below is close to worthless on its own, and the number that
actually sizes BF-14 is the DYNAMIC one — a count assembled at runtime is a
count whose value nobody has bounded, and zero is inside its range.

Emits no file contents, no identifiers and no values beyond the numeral itself.

Usage:
    python3 tools/qc/v1_count_census.py
"""

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

EXTENSIONS = ['*.js', '*.ts', '*.jsx', '*.tsx', '*.py', '*.swift', '*.java',
              '*.kt', '*.rb', '*.go', '*.cs', '*.sh', '*.md', '*.json']

NOT_CLIENTS = {'experiments', 'work'}
SERVER_DIRS = {'cgm-remote-monitor'}
SELF_COPY = 'rag-nightscout-ecosystem-alignment'

# `count=` inside something that looks like a query string, plus the next few
# characters of context. The context is what distinguishes a literal from a
# concatenation: the value in `'&count=' + n` ends at the quote, so matching only
# the value classifies the most dynamic shape there is as EMPTY. Getting that
# wrong overstates the literal share -- the arm of this census least able to see
# the defect.
COUNT = re.compile(r'''[?&]count=([^&\s"'`,)\]}]*)(.{0,2})''')

LITERAL = re.compile(r'^\d+$')
# A quote, backtick or interpolation marker immediately after `count=` means the
# value is spliced in at runtime.
CONCAT = re.compile(r'''^["'`{$%]''')
# The shapes a computed count takes inline across the languages in the corpus.
DYNAMIC = re.compile(r'[$%{+\\]|<[a-zA-Z]|\bcount\b|\bnum|\bmax|\blimit|\brecord', re.I)


def repos(root, include_server):
    for entry in sorted((root / 'externals').iterdir()):
        if not entry.is_dir() or entry.name.startswith('.'):
            continue
        if entry.name in NOT_CLIENTS or (not include_server and entry.name in SERVER_DIRS):
            continue
        yield entry


def scan(repo):
    cmd = ['grep', '-rn', '--binary-files=without-match', '-E', r'[?&]count=']
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
        # A `?count=` written inside a comment or a Markdown file sends nothing.
        # Without this, prose like `// If "?count=" is present` matches CONCAT on
        # the closing quote and inflates the dynamic share.
        stripped = text.strip()
        is_prose = (path.endswith('.md')
                    or stripped.startswith(('//', '#', '*', '--', ';')))
        for value, after in COUNT.findall(text):
            if is_prose and not LITERAL.match(value):
                kind = 'prose'
                hits.append({'file': path.lstrip('./'), 'line': int(lineno),
                             'value': value, 'kind': kind})
                continue
            if LITERAL.match(value):
                kind = 'literal'
            elif value == '' and CONCAT.match(after):
                kind = 'dynamic'        # `'&count=' + n` -- spliced at runtime
            elif value == '':
                kind = 'prose'          # a bare `?count=` in a comment or doc
            elif DYNAMIC.search(value):
                kind = 'dynamic'
            else:
                kind = 'other'
            hits.append({'file': path.lstrip('./'), 'line': int(lineno),
                         'value': value, 'kind': kind})
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default=Path(__file__).resolve().parents[2], type=Path)
    ap.add_argument('--include-server', action='store_true')
    ap.add_argument('--json', type=Path)
    args = ap.parse_args(argv)

    per_repo = {}
    for repo in repos(args.root, args.include_server):
        hits = scan(repo)
        if hits:
            per_repo[repo.name] = hits

    kinds = Counter(h['kind'] for hs in per_repo.values() for h in hs)
    literals = Counter(int(h['value']) for hs in per_repo.values()
                       for h in hs if h['kind'] == 'literal')
    total = sum(kinds.values())

    print(f'{total} `count=` occurrences across {len(per_repo)} projects\n')

    print('BY KIND')
    for kind, n in kinds.most_common():
        print(f'  {kind:<10} {n:>4}  ({n / total * 100:4.1f}%)')

    print('\nLITERAL VALUES (the only ones whose reachability is certain)')
    zero = literals.get(0, 0)
    for value, n in sorted(literals.items()):
        flag = '   <- REACHES BF-14: unbounded read' if value == 0 else ''
        print(f'  count={value:<8} {n:>4}{flag}')
    if not zero:
        print('\n  No client sends a literal count=0. That does NOT clear BF-14 --')
        print('  it means the literal arm of the census found nothing, which is the')
        print('  arm least able to see the defect.')

    print('\nBY PROJECT (dynamic counts are the exposure)')
    for name in sorted(per_repo, key=lambda n: -sum(
            1 for h in per_repo[n] if h['kind'] == 'dynamic')):
        ks = Counter(h['kind'] for h in per_repo[name])
        print(f'  {name:<34} ' + '  '.join(f'{k}={v}' for k, v in sorted(ks.items())))

    # `prose` is excluded: a `?count=` written in a comment sends nothing.
    dyn = kinds.get('dynamic', 0) + kinds.get('other', 0)
    print(f'\n{dyn}/{total} ({dyn / total * 100:.0f}%) of call sites compute the count at')
    print('request time. None of them is known to bound it away from zero, and a count')
    print('derived from an empty time window, an empty selection or a cleared preference')
    print('is zero by construction. That is the size of BF-14: not "clients send zero",')
    print('but "nothing stops them, and the server answers with the whole collection".')

    if args.json:
        args.json.write_text(json.dumps(
            {'kinds': dict(kinds), 'literals': {str(k): v for k, v in literals.items()},
             'per_repo': {k: Counter(h['kind'] for h in v) for k, v in per_repo.items()}},
            indent=2, default=dict))


if __name__ == '__main__':
    main()
