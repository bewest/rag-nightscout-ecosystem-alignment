"""sort_key_typing.py -- is every sort key really one type in the real corpus?

WHY THIS EXISTS. `lib/api3/storage/pgCollection/sql.js`, in `orderBy`, records a
known difference between the two backends and then bounds it with an empirical
claim:

    KNOWN DIFFERENCE [...] jsonb's cross-TYPE ordering is not BSON's. [...] A
    collection whose sort key holds two different types in different documents
    therefore orders differently on the two backends. Every sort this code path
    issues is on a field that is one type in practice (`date`, `srvModified`,
    `identifier`, `created_at`), so it does not bite today -- but it is not a
    property the adapter can enforce.

"one type in practice" is a statement about data, and it was asserted, not
measured. This measures it against both snapshots of the patient corpus -- 11
real Nightscout exports, 4 collections, 1,968,464 documents. If the claim holds
the comment stands. If it fails at one site, ordering silently diverges between
MongoDB and PostgreSQL for that deployment, and the comment is wrong in a way
that matters.

A mixture is reported PER SITE, because a deployment sorts its own rows and
nobody else's. A field that is one type at every site and a different one
between sites cannot reorder anything today, and saying otherwise would
manufacture a finding; that case gets its own section in the output.

TWO DIVERGENCE MECHANISMS, NOT ONE. The comment names only the second.

  (A) The field HAS a generated column. The emitted DDL builds it with a type
      guard -- `CASE WHEN jsonb_typeof(doc #> '{date}') = 'number' THEN ...` --
      so an off-type value lands in the column as SQL NULL and sorts to whichever
      end NULLS FIRST/LAST puts it. On MongoDB the same document sorts inside its
      own type's block. This is a divergence the comment does not mention.
  (B) The field has NO column (`srvModified`, `isValid`, anything AMBIGUOUS in the
      emitted manifest). `orderBy` falls back to `doc #> '{...}'` and jsonb's own
      cross-type order applies -- which is the case the comment describes.

So the measurement is the same either way: does any one (site, collection, field)
hold more than one JSON type? Which mechanism fires is a property of the manifest,
and this tool reports it alongside.

TWO FIELD SETS, REPORTED SEPARATELY. The comment's four fields are the ones the
code path issues *today*. API v3 also lets the CLIENT pick the sort key with
`?sort=` / `?sort$desc=`, so the reachable set is much larger. Blurring the two
would either excuse the comment or condemn it unfairly, so they are counted and
printed apart.

WHAT THIS METHOD CANNOT SEE -- stated up front because it bounds the verdict.
The corpus is JSON captured from the REST API, not a BSON dump. JSON has six
types; BSON has around twenty, and several collapse on the way out:

  * BSON Date, and a string that merely looks like a date, are both JSON strings
    here. In MongoDB they are DIFFERENT types and sort in different blocks. A
    collection storing `created_at` as Date in some documents and as String in
    others is invisible to this tool and would read as single-typed.
  * BSON Int32, Int64, Double and Decimal128 are all JSON numbers here. Those
    four DO sort together as one numeric block in MongoDB, so collapsing them
    loses nothing for this question.
  * ObjectId serialises as a JSON string. Same blind spot as Date.

Therefore a "single-typed" result from this tool is a NECESSARY, NOT SUFFICIENT
condition for the comment's claim. A "mixed" result is conclusive: two JSON types
in the export were two BSON types in the database.

NON-VACUITY. `--self-test` runs the same detector over a small synthetic corpus
that plants a mixed-type field, and fails loudly if the detector does not flag it.
A detector that reports "no mixed types" because it is broken looks exactly like
one that reports it because the data is clean; only breaking it tells you which.
Run it before believing a clean table.

PRIVACY. This reads document STRUCTURE only: which keys exist and what JSON type
each value has. It never emits a value, a document, a key's contents, a site URL
or any identifier. Sites are the single letters the corpus already uses. The
`ns_url.env` and `manifest.json` files beside the data are not opened -- both
carry the deployment URL.

Usage:
    python3 tools/qc/sort_key_typing.py --self-test
    python3 tools/qc/sort_key_typing.py
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

COLLECTIONS = ('entries', 'treatments', 'devicestatus', 'profile')

# TWO SNAPSHOTS OF THE SAME 11 SITES, three and a half weeks apart, in two
# different layouts. Both are measured: `reports/schema-census/*.census.json`
# already spans both, and a result quoted against half the corpus the census used
# would not be comparable with it. The second is also the only chance this corpus
# gives to see a field CHANGE type over time at one site, which is the shape that
# would break a deployment that used to sort correctly.
#
# (label, directory holding the site folders, how a site+collection resolves)
SNAPSHOTS = (
    ('2026-04-01', 'externals/ns-data/patients',
     lambda base, site, coll: base / site / 'raw' / f'{coll}.json'),
    ('2026-04-26', 'externals/ns-resync-2026-04-26/raw',
     lambda base, site, coll: base / site / f'{coll}.json'),
)

# The four the comment names: what `parseSort`'s chain and the v3 defaults
# actually issue today.
CODE_ISSUED = ('date', 'srvModified', 'identifier', 'created_at')

# Reachable because API v3 takes the sort key from the query string. Not
# exhaustive -- a client can name any field at all -- but these are the ones with
# a plausible reason to be sorted on, plus three chosen as POSITIVE CONTROLS
# DRAWN FROM THE REAL DATA:
#
#   `mills`, `carbs`, `insulin`  -- reports/schema-census/*.census.json already
#       records each of these holding two JSON types across the corpus (string
#       and number for `mills`; null and number for the other two). If this tool
#       cannot see those, it cannot see anything, so they are measured here to
#       prove the detector against real files and not only the synthetic case.
#       Whether the mixing is WITHIN one site -- which is the only thing that can
#       change an ordering, since a deployment sorts its own rows -- is exactly
#       what the per-site breakdown answers and the census's corpus-wide totals
#       do not.
#   `NSCLIENT_ID` -- the emitted manifest flags it AMBIGUOUS on three
#       collections with the words "observed as number, string". Measured to
#       check that. See the report: the flag does not come from the corpus.
CLIENT_CHOOSABLE = ('sysTime', 'srvCreated', 'startDate', '_id', 'sgv',
                    'NSCLIENT_ID', 'mills', 'carbs', 'insulin')

FIELDS = CODE_ISSUED + CLIENT_CHOOSABLE


def json_type(value):
    """The jsonb_typeof name for a decoded JSON value.

    bool before int deliberately: in Python bool IS an int, and calling `true` a
    number would hide exactly the kind of mixing being looked for.
    """
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, (int, float)):
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, dict):
        return 'object'
    return 'unknown'                        # unreachable for json.loads output


def iter_docs(path):
    """Yield documents from a top-level JSON array, one at a time.

    The corpus holds a 235 MB file; `json.loads` on it materialises every
    document at once. `raw_decode` walks the array and lets each document be
    dropped after it is counted, which keeps peak memory at the file text plus
    one document.

    Raises ValueError on anything that is not a top-level array -- the caller
    reports that as a skip rather than guessing.
    """
    text = path.read_text()
    idx = 0
    n = len(text)

    def skip_ws(i):
        while i < n and text[i] in ' \t\r\n':
            i += 1
        return i

    idx = skip_ws(idx)
    if idx >= n or text[idx] != '[':
        raise ValueError(f'top level is not a JSON array (starts {text[idx:idx+1]!r})')
    idx = skip_ws(idx + 1)
    if idx < n and text[idx] == ']':
        return
    decoder = json.JSONDecoder()
    while True:
        obj, idx = decoder.raw_decode(text, idx)
        yield obj
        idx = skip_ws(idx)
        if idx >= n:
            raise ValueError('array is unterminated')
        if text[idx] == ',':
            idx = skip_ws(idx + 1)
            continue
        if text[idx] == ']':
            return
        raise ValueError(f'expected , or ] at offset {idx}')


def measure(path, fields):
    """-> (per-field type counters, total docs, skip counter) for one file.

    A document that is not a JSON object is COUNTED as a skip with its reason,
    never dropped quietly: a skipped document is one this measurement did not
    look at, and the number of those is part of the result.
    """
    types = {f: Counter() for f in fields}
    absent = Counter()
    total = 0
    skips = Counter()
    for doc in iter_docs(path):
        total += 1
        if not isinstance(doc, dict):
            skips[f'document is a JSON {json_type(doc)}, not an object'] += 1
            continue
        for f in fields:
            if f in doc:
                types[f][json_type(doc[f])] += 1
            else:
                absent[f] += 1
    return types, absent, total, skips


def verdict(counter):
    """'absent' | 'single:<type>' | 'MIXED:<type>+<type>...' for one field."""
    present = [t for t, c in counter.items() if c]
    if not present:
        return 'absent'
    if len(present) == 1:
        return f'single:{present[0]}'
    # Alphabetical, not by frequency: the label names a PAIRING, and whether
    # that pairing reorders is a property of the two types, not of which is
    # commoner. Sorting by count would print the same mixture two ways and make
    # a summary count it twice.
    return 'MIXED:' + '+'.join(sorted(present))


# --------------------------------------------------------------------------
# non-vacuity
# --------------------------------------------------------------------------

SELF_TEST_DOCS = [
    # Three documents with a `date` that is a number -- the shape the comment
    # claims the whole corpus has.
    {'date': 1, 'identifier': 'a', 'created_at': 'x'},
    {'date': 2, 'identifier': 'b', 'created_at': 'y'},
    {'date': 3, 'identifier': 'c', 'created_at': 'z'},
    # ONE document that breaks it: `date` is a string, `created_at` is a number.
    # This is precisely the divergence under test -- an ISO string where the rest
    # of the collection holds an epoch, and an epoch where the rest holds an ISO
    # string.
    {'date': '2026-01-01T00:00:00Z', 'identifier': 'd', 'created_at': 1767225600000},
    # And the quieter ones: an explicit JSON null is a TYPE in both jsonb and
    # BSON, distinct from the key being absent, so it must show as mixing.
    {'date': 4, 'identifier': None, 'created_at': 'w'},
    # A document with no `date` at all -- absent, which is NOT a type and must
    # not be counted as one.
    {'identifier': 'e', 'created_at': 'v'},
]


def self_test(tmpdir):
    """Plant a mixed type, run the real detector, insist it is flagged."""
    tmpdir.mkdir(parents=True, exist_ok=True)
    synthetic = tmpdir / 'sort_key_typing_selftest.json'
    synthetic.write_text(json.dumps(SELF_TEST_DOCS))

    types, absent, total, skips = measure(synthetic, ('date', 'identifier', 'created_at'))

    print('NON-VACUITY CHECK -- synthetic corpus, mixed type planted')
    print(f'  documents: {total}   skipped: {sum(skips.values())}')
    for f in ('date', 'identifier', 'created_at'):
        print(f'  {f:12s} absent={absent[f]:d}  '
              f'types={dict(types[f])}  ->  {verdict(types[f])}')

    ok = True
    checks = [
        ('date mixes number and string',
         verdict(types['date']) == 'MIXED:number+string'),
        ('created_at mixes string and number',
         verdict(types['created_at']) == 'MIXED:number+string'),
        ('identifier mixes string and an explicit JSON null',
         verdict(types['identifier']) == 'MIXED:null+string'),
        ('a single-typed field is NOT flagged (no false positive)',
         verdict(Counter({'number': 99})) == 'single:number'),
        ('an absent key is not counted as a type',
         absent['date'] == 1 and sum(types['date'].values()) == 5),
    ]
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed

    synthetic.unlink()
    print(f"NON-VACUITY: {'PASS -- the detector sees a planted mixed type' if ok else 'FAIL -- results below are NOT evidence'}")
    return ok


# --------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', default=Path(__file__).resolve().parents[2], type=Path)
    ap.add_argument('--self-test', action='store_true',
                    help='run the non-vacuity check only and exit')
    args = ap.parse_args(argv)

    scratch = args.root / 'reports/v1-query-census'
    if args.self_test:
        return 0 if self_test(scratch) else 1

    # The non-vacuity check runs on EVERY run, not only when asked. A clean table
    # printed by a broken detector is worse than no table.
    if not self_test(scratch):
        print('\nABORTING: the detector failed its own non-vacuity check.')
        return 1
    print()

    rows = []
    file_skips = []
    doc_skips = Counter()
    all_sites = set()

    for label, rel, resolve in SNAPSHOTS:
        base = args.root / rel
        if not base.is_dir():
            # A whole missing snapshot is reported, never quietly dropped: the
            # denominator of every percentage below depends on it.
            file_skips.append((label, '-', '-', f'snapshot directory not found'))
            continue
        sites = sorted(p.name for p in base.iterdir() if p.is_dir())
        all_sites |= set(sites)
        for site in sites:
            for coll in COLLECTIONS:
                f = resolve(base, site, coll)
                if not f.is_file():
                    # Reported, not passed over. A missing collection is a hole
                    # in the measurement and the reader is entitled to know it.
                    file_skips.append((label, site, coll, 'file not present'))
                    continue
                try:
                    types, absent, total, skips = measure(f, FIELDS)
                except Exception as exc:   # noqa: BLE001 -- reported, not swallowed
                    file_skips.append((label, site, coll,
                                       f'{type(exc).__name__}: {exc}'))
                    continue
                for reason, n in skips.items():
                    doc_skips[f'{label} {site}/{coll}: {reason}'] += n
                rows.append({
                    'snapshot': label, 'site': site, 'collection': coll,
                    'documents': total, 'skipped_documents': sum(skips.values()),
                    'fields': {f: {'absent': absent[f], 'types': dict(types[f]),
                                   'verdict': verdict(types[f])} for f in FIELDS},
                })

    def table(title, fields):
        print(title)
        print(f"{'snap':11s} {'st':3s} {'collection':13s} {'docs':>9s} " +
              ' '.join(f'{f:>21s}' for f in fields))
        print('-' * (40 + 22 * len(fields)))
        for r in rows:
            cells = []
            for f in fields:
                v = r['fields'][f]['verdict']
                n = sum(r['fields'][f]['types'].values())
                cells.append(f'{v}({n})' if v != 'absent' else '-')
            print(f"{r['snapshot']:11s} {r['site']:3s} {r['collection']:13s} "
                  f"{r['documents']:9,d} " +
                  ' '.join(f'{c:>21s}' for c in cells))
        print()

    table('A. THE FOUR FIELDS THE COMMENT NAMES (issued by the code path today)',
          CODE_ISSUED)
    table('B. REACHABLE BY A CLIENT VIA ?sort= / ?sort$desc=', CLIENT_CHOOSABLE)

    mixed = [(r['snapshot'], r['site'], r['collection'], f, r['fields'][f]['types'])
             for r in rows for f in FIELDS
             if r['fields'][f]['verdict'].startswith('MIXED')]

    print('MIXED WITHIN ONE SITE -- the only mixing that can reorder anything,')
    print('because a deployment sorts its own rows and nobody else\'s.')
    if not mixed:
        print('  none')
    for snap, site, coll, f, t in mixed:
        bucket = 'code-issued' if f in CODE_ISSUED else 'client-choosable'
        print(f'  {snap} {site}/{coll:13s} {f:14s} {t}   [{bucket}]')

    # A field can be one type at every site and still be two types across the
    # corpus -- site j's `mills` against everyone else's. That is NOT an ordering
    # divergence for any deployment, and conflating the two would manufacture a
    # finding. Printed separately for exactly that reason.
    print()
    print('SINGLE-TYPED PER SITE BUT DISAGREEING BETWEEN SITES')
    across = defaultdict(lambda: defaultdict(set))
    for r in rows:
        for f in FIELDS:
            v = r['fields'][f]['verdict']
            if v.startswith('single:'):
                across[(r['collection'], f)][v.split(':', 1)[1]].add(r['site'])
    found = False
    for (coll, f), by_type in sorted(across.items()):
        if len(by_type) > 1:
            found = True
            parts = ', '.join(f'{t}: {len(s)} site(s)' for t, s in sorted(by_type.items()))
            print(f'  {coll:13s} {f:14s} {parts}')
    if not found:
        print('  none')

    print()
    print(f'sites: {len(all_sites)}   snapshots: {len({r["snapshot"] for r in rows})}   '
          f'(snapshot,site,collection) triples: {len(rows)}   '
          f'documents: {sum(r["documents"] for r in rows):,}')
    print(f'documents skipped: {sum(doc_skips.values())}')
    for reason, n in doc_skips.items():
        print(f'  {n:,} -- {reason}')
    print(f'files skipped: {len(file_skips)}')
    for label, site, coll, why in file_skips:
        print(f'  {label} {site}/{coll}: {why}')

    out = scratch / 'sort-key-typing.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        'code_issued_fields': list(CODE_ISSUED),
        'client_choosable_fields': list(CLIENT_CHOOSABLE),
        'rows': rows,
        'file_skips': [{'snapshot': sn, 'site': s, 'collection': c, 'reason': w}
                       for sn, s, c, w in file_skips],
        'document_skips': dict(doc_skips),
    }, indent=1) + '\n')
    print(f'\nwrote {out.relative_to(args.root)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
