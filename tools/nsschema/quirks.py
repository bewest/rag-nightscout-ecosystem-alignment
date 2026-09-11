"""quirks.py — measure the quirks registry against the corpus.

``specs/quirks/*.yaml`` states how real documents deviate from the schema.
This replays every entry's detector over the same corpus the census reads
and reports what fraction of documents, and how many sites, actually
exhibit it — so a registry entry is a falsifiable claim rather than lore.

Two modes:

``measure``
    Write ``reports/schema-census/quirks.json`` with, per quirk, the
    document count and share, the per-site breakdown, and the snapshots it
    appears in.
``check``
    Compare each measurement against the entry's ``expect`` block and exit
    non-zero when a claim no longer holds — a quirk that has disappeared
    from the data, or one whose prevalence has collapsed. Intended for CI,
    so the registry rots loudly rather than quietly.

Detectors are declarative (see ``specs/quirks/README.md``). Keeping them
data rather than code is what lets the registry be reviewed by someone who
does not read Python, and stops a "quirk" from quietly becoming arbitrary
logic.
"""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from . import corpus

TESTS = (
    "exists", "absent", "is-null", "is-fractional", "is-string", "is-number",
    "is-object", "equals", "in", "not-in", "matches",
)


def resolve(doc, path):
    """Yield every value at a census-style dotted path.

    ``store.{}.units`` yields one value per map entry; ``a[].b`` one per
    array element. A path that does not exist yields nothing, which is how
    ``exists`` and ``absent`` are distinguished.
    """
    nodes = [doc]
    for segment in path.split("."):
        arrays = 0
        while segment.endswith("[]"):
            segment = segment[:-2]
            arrays += 1
        nxt = []
        for node in nodes:
            if segment == "{}":
                if isinstance(node, dict):
                    nxt.extend(node.values())
                continue
            if isinstance(node, dict) and segment in node:
                nxt.append(node[segment])
        for _ in range(arrays):
            expanded = []
            for node in nxt:
                if isinstance(node, list):
                    expanded.extend(node)
            nxt = expanded
        nodes = nxt
        if not nodes:
            return []
    return nodes


def evaluate(detect, doc):
    """True if the detector fires anywhere in this document."""
    test = detect["test"]
    values = resolve(doc, detect["path"])

    if test == "absent":
        return not values
    if not values:
        return False
    if test == "exists":
        return True

    for value in values:
        if test == "is-null" and value is None:
            return True
        if test == "is-string" and isinstance(value, str):
            return True
        if test == "is-object" and isinstance(value, dict):
            return True
        if test == "is-number" and isinstance(value, (int, float)) \
                and not isinstance(value, bool):
            return True
        if test == "is-fractional":
            if isinstance(value, float) and math.isfinite(value) \
                    and not value.is_integer():
                return True
        if test == "equals" and value == detect.get("value"):
            return True
        if test == "in" and value in detect.get("values", []):
            return True
        if test == "not-in" and value is not None \
                and value not in detect.get("values", []):
            return True
        if test == "matches" and isinstance(value, str) \
                and re.search(detect["pattern"], value):
            return True
    return False


def load_registry(directory: Path):
    entries = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for quirk in data.get("quirks", []):
            quirk["collection"] = data["collection"]
            quirk["source_file"] = str(path)
            detect = quirk.get("detect") or {}
            if detect.get("test") not in TESTS:
                raise ValueError(
                    f"{quirk['id']}: unknown test {detect.get('test')!r}; "
                    f"expected one of {', '.join(TESTS)}")
            entries.append(quirk)
    return entries


def measure(registry, sources):
    by_collection = defaultdict(list)
    for quirk in registry:
        by_collection[quirk["collection"]].append(quirk)

    hits = {q["id"]: Counter() for q in registry}
    snapshots = {q["id"]: set() for q in registry}
    totals = Counter()
    site_totals = defaultdict(Counter)

    for src in sources:
        quirks = by_collection.get(src.collection)
        if not quirks:
            continue
        for doc in corpus.iter_documents(src.path):
            totals[src.collection] += 1
            site_totals[src.collection][src.site] += 1
            for quirk in quirks:
                if evaluate(quirk["detect"], doc):
                    hits[quirk["id"]][src.site] += 1
                    snapshots[quirk["id"]].add(src.snapshot)

    results = []
    for quirk in registry:
        collection = quirk["collection"]
        total = totals[collection]
        counted = sum(hits[quirk["id"]].values())
        per_site = {
            site: round(n / site_totals[collection][site], 6)
            for site, n in sorted(hits[quirk["id"]].items())
            if site_totals[collection][site]
        }
        results.append({
            "id": quirk["id"],
            "title": quirk["title"],
            "collection": collection,
            "kind": quirk["kind"],
            "status": quirk["status"],
            "path": quirk["path"],
            "documents": counted,
            "collection_documents": total,
            "share": round(counted / total, 6) if total else 0.0,
            "sites": len(per_site),
            "site_share": per_site,
            "snapshots": sorted(snapshots[quirk["id"]]),
            "expect": quirk.get("expect", {}),
        })
    return results


def check(results):
    """Return a list of failures against each quirk's expect block."""
    failures = []
    for row in results:
        expect = row["expect"] or {}
        if row["status"] == "historical":
            continue
        if row["documents"] == 0:
            failures.append((row["id"], "no longer observed in the corpus"))
            continue
        min_share = expect.get("min_share")
        if min_share is not None and row["share"] < min_share:
            failures.append((row["id"],
                             f"share {row['share']:.1%} below claimed minimum "
                             f"{min_share:.1%}"))
        min_sites = expect.get("min_sites")
        if min_sites is not None and row["sites"] < min_sites:
            failures.append((row["id"],
                             f"seen on {row['sites']} sites, below claimed "
                             f"minimum {min_sites}"))
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--registry", default="specs/quirks", type=Path)
    ap.add_argument("--out", default="reports/schema-census/quirks.json", type=Path)
    ap.add_argument("--check", action="store_true",
                    help="fail if a registry claim no longer holds")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    registry = load_registry(root / args.registry)
    sources = corpus.discover(root)
    results = measure(registry, sources)

    for row in sorted(results, key=lambda r: (r["collection"], r["id"])):
        print(f"  {row['id']:24s} {row['share']:7.2%} of {row['collection']:12s} "
              f"on {row['sites']:2d} sites  {row['title'][:48]}")

    report = {
        "generated_by": "tools/nsschema/quirks.py",
        "registry": str(args.registry),
        "quirks": len(results),
        "results": results,
    }
    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=1) + "\n")
    print(f"-> {args.out}")

    if args.check:
        failures = check(results)
        for quirk_id, reason in failures:
            print(f"FAIL {quirk_id}: {reason}", file=sys.stderr)
        if failures:
            print(f"\n{len(failures)} registry claim(s) no longer hold.",
                  file=sys.stderr)
            return 1
        print("every registry claim still holds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
