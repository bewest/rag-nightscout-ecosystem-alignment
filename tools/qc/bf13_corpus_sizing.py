"""bf13_corpus_sizing.py -- how much real data holds BF-13's triggering shape.

BF-13 (docs/60-research/tenancy/seam-ordering-and-pagination-2026-09-14.md) is API v3's
skip/limit paging silently losing and duplicating documents when every key in
parseSort's tiebreak chain ties. The finding was reproduced synthetically, and
the document lists "the corpus was not queried for how many deployments hold the
triggering shape" as an open limit. This closes it.

THE SHAPE. parseSort orders by [user field], identifier, created_at, date. Loss
requires a group of documents where ALL of those tie. Restricted to the default
path (no ?sort= parameter, which is the exposed-without-asking case) the key is:

    (identifier, created_at, date)

A document with a unique identifier is a group of one and is safe. So the
measurement is: among documents with NO identifier, how large do the
(created_at, date) groups get? A group spanning a page boundary is what loses
rows, so GROUP SIZE RELATIVE TO PAGE SIZE is the quantity that matters, not the
count of duplicates.

PRIVACY. This reads document structure only -- presence of keys and equality of
timestamps. It never emits a field value, a document, a site URL or any
identifier. Sites are reported as the single letters the corpus already uses.
The `ns_url.env` files beside the data are not opened.

Usage: python3 tools/qc/bf13_corpus_sizing.py [--page 100]
"""

import argparse
import json
from collections import Counter
from pathlib import Path

COLLECTIONS = ('entries', 'treatments', 'devicestatus', 'profile')


def measure(path, page):
    """-> stats for one collection file, or None if unreadable."""
    try:
        docs = json.loads(path.read_text())
    except Exception:
        return None
    if not isinstance(docs, list) or not docs:
        return None

    total = len(docs)
    no_ident = 0
    groups = Counter()
    for d in docs:
        if not isinstance(d, dict):
            continue
        if d.get('identifier'):
            continue                      # unique key present -> group of one
        no_ident += 1
        # None is a distinct, legitimate key here: absent created_at ties with
        # every other absent created_at, which is exactly the failing shape.
        groups[(d.get('created_at'), d.get('date'))] += 1

    sizes = sorted(groups.values(), reverse=True)
    at_risk = sum(n for n in sizes if n > 1)
    spanning = sum(n for n in sizes if n > page)
    # THE QUANTITY THAT ACTUALLY MATTERS. Loss does not need a group bigger than
    # a page -- it needs a group STRADDLING a page boundary, because that is
    # where two separately-executed queries have to agree about an order neither
    # engine promises. For a group of n placed uniformly at random, the chance
    # it straddles is (n-1)/page. Summing over groups gives the expected number
    # of straddles in one full paginated sweep of the collection.
    straddles = sum((n - 1) / page for n in sizes if n > 1)
    return {
        'documents': total,
        'no_identifier': no_ident,
        'no_identifier_pct': no_ident / total,
        'tie_groups_gt1': sum(1 for n in sizes if n > 1),
        'docs_in_tie_groups': at_risk,
        'docs_in_tie_groups_pct': at_risk / total,
        'largest_group': sizes[0] if sizes else 0,
        'docs_in_groups_larger_than_page': spanning,
        'expected_straddles_per_sweep': round(straddles, 2),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', default=Path(__file__).resolve().parents[2], type=Path)
    ap.add_argument('--page', type=int, default=100,
                    help='page size to compare group sizes against (v3 default limit)')
    args = ap.parse_args(argv)

    base = args.root / 'externals/ns-data/patients'
    if not base.is_dir():
        print(f'corpus not found at {base}')
        return 1

    rows = []
    for site in sorted(p for p in base.iterdir() if p.is_dir()):
        for coll in COLLECTIONS:
            f = site / 'raw' / f'{coll}.json'
            if not f.is_file():
                continue
            st = measure(f, args.page)
            if st:
                rows.append((site.name, coll, st))

    hdr = ('site', 'collection', 'docs', 'no-ident', 'no-ident%',
           'tied docs', 'tied%', 'largest grp', f'>page({args.page})')
    print(f"{'site':5s} {'collection':13s} {'docs':>9s} {'no-id%':>7s} "
          f"{'tied':>9s} {'tied%':>7s} {'largest':>8s} {'E[straddle]':>12s}")
    print('-' * 80)
    for site, coll, s in rows:
        print(f"{site:5s} {coll:13s} {s['documents']:9,d} "
              f"{s['no_identifier_pct']:6.1%} {s['docs_in_tie_groups']:9,d} "
              f"{s['docs_in_tie_groups_pct']:6.1%} {s['largest_group']:8,d} "
              f"{s['expected_straddles_per_sweep']:12.2f}")

    print()
    affected = [(s, c, st) for s, c, st in rows if st['docs_in_tie_groups'] > 0]
    sites_affected = {s for s, _c, _st in affected}
    print(f"collections with at least one tie group: {len(affected)} of {len(rows)}")
    print(f"sites with at least one:                 {len(sites_affected)} of "
          f"{len({s for s, _c, _st in rows})}")
    worst = max(rows, key=lambda r: r[2]['largest_group'], default=None)
    if worst:
        print(f"largest single tie group:                {worst[2]['largest_group']:,} "
              f"({worst[0]}/{worst[1]})")
    spanning = [(s, c, st) for s, c, st in rows
                if st['docs_in_groups_larger_than_page'] > 0]
    print(f"collections with a group larger than one page: {len(spanning)}")

    print()
    print(f"EXPECTED STRADDLES per full paginated sweep (page={args.page}):")
    print("  a straddle is where loss or duplication can occur; a group bigger")
    print("  than a page is NOT required.")
    for coll in COLLECTIONS:
        vals = [st['expected_straddles_per_sweep'] for _s, c, st in rows if c == coll]
        if not vals:
            continue
        nonzero = [v for v in vals if v > 0]
        print(f"  {coll:13s} sites {len(nonzero)}/{len(vals)} exposed, "
              f"median {sorted(vals)[len(vals)//2]:.2f}, max {max(vals):.2f}")

    out = args.root / 'reports/v1-query-census/bf13-corpus-sizing.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {'page_size': args.page,
         'rows': [{'site': s, 'collection': c, **st} for s, c, st in rows]},
        indent=1) + '\n')
    print(f'\nwrote {out.relative_to(args.root)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
