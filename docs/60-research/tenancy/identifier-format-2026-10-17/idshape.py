"""ID-FORMAT-SHAPES: shapes of client identity fields in the ns-data corpus (12 sites).

Classifies the values of `identifier`, `syncIdentifier`, `uuid`, `id`,
`NSCLIENT_ID` and `_id` on entries and treatments by SHAPE only (regex class,
length bucket, UUID version nibble). Output is aggregate counts per collection,
client class, field and shape, plus a per-site count of documents carrying a
non-UUID, non-ObjectId value in a client identity field. No value, record
content, name or host is printed.

Client classes and site list are imported from the sibling study
../identifier-duplicates-2026-10-17/iddup.py so both notes use one taxonomy.

Usage: python3 -I idshape.py            # measure
       python3 -I idshape.py --control  # plant one document per shape in site a; print deltas
"""
import collections, importlib.util, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'iddup', os.path.join(HERE, '..', 'identifier-duplicates-2026-10-17', 'iddup.py'))
iddup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(iddup)

COLS = ['entries', 'treatments']
FIELDS = ['identifier', 'syncIdentifier', 'uuid', 'id', 'NSCLIENT_ID', '_id']

# Ordered: first match wins.
SHAPES = [
    ('uuid-lower', re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
    ('uuid-upper', re.compile(r'^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$')),
    ('uuid-mixed-case', re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')),
    ('hex24 (ObjectId form)', re.compile(r'^[0-9a-fA-F]{24}$')),
    ('alnum24 non-hex', re.compile(r'^[0-9A-Za-z]{24}$')),
    ('digits', re.compile(r'^\d+$')),
    ('decimal digits', re.compile(r'^\d+\.\d+$')),
    ('G7 form: <decimal> <token> <digits>', re.compile(r'^\d+(\.\d+)? \S+ \d+$')),
    ('G6 form: <6 alnum> <digits>', re.compile(r'^[0-9A-Z]{6} \d+$')),
    ('Minimed form: Y-M-D H-M-S', re.compile(r'^\d{4}-\d{1,2}-\d{1,2} \d{1,2}-\d{1,2}-\d{1,2}$')),
    ('other space-separated', re.compile(r'^\S+( \S+)+$')),
    ('hex other length', re.compile(r'^[0-9a-fA-F]+$')),
    ('contains colon', re.compile(r':')),
    ('contains slash or percent', re.compile(r'[/%]')),
]


def length_bucket(n):
    for b in (8, 16, 24, 36, 64, 128, 256, 1024):
        if n <= b: return f'<= {b}'
    return '> 1024'


def token_class(t):
    if re.fullmatch(r'\d+', t): return f'N{len(t)}'
    if re.fullmatch(r'\d+\.\d+', t): return 'F'
    if re.fullmatch(r'[0-9a-f]+', t): return f'h{len(t)}'
    if re.fullmatch(r'[0-9A-F]+', t): return f'H{len(t)}'
    if re.fullmatch(r'[0-9A-Za-z]+', t): return f'A{len(t)}'
    punct = ''.join(sorted(set(re.sub(r'[0-9A-Za-z]', '', t))))
    return f'X{len(t)}{{{punct}}}'


def signature(v):
    """Token classes of a space-separated value: N<len> digits, F decimal, h/H<len> lower/upper
    hex, A<len> other alphanumeric, X<len>{punctuation set} other. A shape, never the value."""
    return ' '.join(token_class(t) for t in v.split(' '))


def shape(v):
    if v is None: return 'null'
    if isinstance(v, bool): return 'bool'
    if isinstance(v, (int, float)): return 'JSON number'
    if isinstance(v, dict): return 'object' + (' ($oid)' if '$oid' in v else '')
    if not isinstance(v, str): return type(v).__name__
    if v == '': return 'empty string'
    if v.strip() == '': return 'whitespace only'
    if v in ('invalid', 'undefined', 'null', 'NaN'): return 'sentinel word'
    for name, rx in SHAPES:
        if rx.search(v):
            if name.startswith('uuid'):
                return f'{name} v{v[14]}'
            if name == 'hex other length':
                return f'{name} (exactly {len(v)})'
            if name == 'other space-separated':
                return f'{name} [{signature(v)}]'
            if name in ('contains colon', 'contains slash or percent'):
                return f'{name} ({length_bucket(len(v))})'
            return name
    return f'other string ({length_bucket(len(v))})'


def is_plain(s):
    """A UUID or ObjectId shape: what today's v1 by-id routes understand."""
    return s.startswith('uuid-lower') or s.startswith('uuid-upper') or s.startswith('uuid-mixed') \
        or s.startswith('hex24') or s == 'object ($oid)' or s == 'null'


def run(load):
    R = collections.defaultdict(collections.Counter)
    for site, path in iddup.SITES:
        for col in COLS:
            docs = load(path, col)
            if docs is None: continue
            R['docs'][(site, col)] += len(docs)
            for x in docs:
                c = iddup.CLS[col](x)
                odd = False
                for f in FIELDS:
                    if f not in x: continue
                    s = shape(x[f])
                    R['shape'][(col, c, f, s)] += 1
                    R['field_sites'][(col, c, f, s, site)] += 1
                    if f != '_id' and not is_plain(s):
                        odd = True
                if odd:
                    R['nonuuid_docs'][(site, col)] += 1
    return R


def report(R):
    out = []
    out.append('## documents per site and collection')
    for (site, col), n in sorted(R['docs'].items()):
        out.append(f'{site}\t{col}\t{n}')
    out.append('\n## shape counts: collection, client class, field, shape, documents, sites')
    for (col, c, f, s), n in sorted(R['shape'].items()):
        sites = sorted({k[4] for k in R['field_sites'] if k[:4] == (col, c, f, s)})
        out.append(f'{col}\t{c}\t{f}\t{s}\t{n}\t{"".join(sites)}')
    out.append('\n## documents with a non-UUID, non-ObjectId value in identifier/syncIdentifier/uuid/id/NSCLIENT_ID')
    for (site, col), n in sorted(R['nonuuid_docs'].items()):
        out.append(f'{site}\t{col}\t{n}')
    return out


PLANTED = [
    ('treatments', {'eventType': 'Note', 'created_at': '2026-01-01T00:00:00Z', 'enteredBy': 'loop://planted',
                    'syncIdentifier': '493012.25 PLANTSN 3600'}),
    ('treatments', {'eventType': 'Note', 'created_at': '2026-01-01T00:00:01Z', 'enteredBy': 'loop://planted',
                    'syncIdentifier': 'invalid'}),
    ('entries', {'type': 'sgv', 'sysTime': '2026-01-01T00:00:00Z', 'device': 'Dexcom G7 planted',
                 'identifier': 'g7:PLANTSN:3600'}),
    ('entries', {'type': 'sgv', 'sysTime': '2026-01-01T00:00:00Z', 'device': 'xDrip-planted',
                 '_id': 'Ab3dEf7hIj1lMn5pQr9tUv2x'}),
    ('entries', {'type': 'sgv', 'sysTime': '2026-01-01T00:05:00Z', 'device': 'Dexcom G6 planted',
                 'identifier': 'ABC123 7200'}),
    ('treatments', {'eventType': 'Note', 'created_at': '2026-01-01T00:00:02Z', 'enteredBy': 'Trio',
                    'id': '0B7E2EF2-7A4B-4C9D-8E2F-1A2B3C4D5E6F'}),
]


def main():
    if '--control' in sys.argv:
        clean = report(run(iddup.load_file))

        def planted_load(path, col):
            d = iddup.load_file(path, col)
            if d is not None and path == iddup.SITES[0][1]:
                d = list(d) + [dict(doc) for c, doc in PLANTED if c == col]
            return d
        planted = report(run(planted_load))
        a, b = collections.Counter(clean), collections.Counter(planted)
        print('## control: lines only in the planted run (+) or only in the clean run (-)')
        for line in sorted(set(planted) - set(clean)): print('+ ' + line)
        for line in sorted(set(clean) - set(planted)): print('- ' + line)
        return
    print('\n'.join(report(run(iddup.load_file))))


if __name__ == '__main__':
    main()
