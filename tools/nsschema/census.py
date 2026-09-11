"""census.py — walk the raw corpus and record what each field actually is.

Produces, per collection, one record per observed JSON path:

* how many documents carry it, on how many sites, in which snapshots
* every JSON type observed at that path, with counts (union types are the
  point of the exercise, not an error)
* numeric range and integer/float split, string length distribution,
  array length distribution
* the distinct value set, when and only when :mod:`redact` permits it

Map-like objects (a ``profile``'s ``store`` is keyed by user-chosen profile
names) are collapsed to a single ``{}`` path segment so that user data does
not become schema structure. Map detection runs as a bounded first pass;
``--map-path`` adds one manually.

Usage::

    python3 -m nsschema.census --out reports/schema-census
    python3 -m nsschema.census --collection treatments --max-docs 5000
"""

import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import corpus, redact

# A first-pass object path is map-like when it has many distinct child keys
# but few children per occurrence — the shape of a dictionary keyed by user
# data, as opposed to a wide record like ``openaps.suggested``.
MAP_MIN_DISTINCT_KEYS = 25
MAP_KEY_TO_WIDTH_RATIO = 3.0
MAP_SAMPLE_DOCS = 3000

# Paths known to be user-keyed regardless of what the sample shows.
MAP_PATHS_ALWAYS = frozenset({"store"})

MAX_PATHS = 20000

# Numeric min/max over a handful of observations is not a distribution, it is
# one person's data point — and for a timestamp field it is the exact moment
# something happened on one identifiable site. Below this many observations,
# only the count is reported.
MIN_NUMERIC_SAMPLES = 20


class FieldStat:
    """Accumulated evidence for one JSON path within one collection."""

    __slots__ = (
        "count", "sites", "snapshots", "types",
        "num_count", "num_min", "num_max", "num_sum",
        "int_count", "float_count", "nonfinite",
        "str_count", "len_min", "len_max", "len_sum",
        "values", "values_overflow", "values_reason",
        "arr_count", "arr_min", "arr_max", "arr_sum",
        "true_count", "false_count", "null_count",
        "obj_keys", "docs_present", "site_docs",
    )

    def __init__(self):
        self.count = 0
        self.sites = set()
        self.snapshots = set()
        self.types = Counter()
        self.num_count = 0
        self.num_min = math.inf
        self.num_max = -math.inf
        self.num_sum = 0.0
        self.int_count = 0
        self.float_count = 0
        self.nonfinite = 0
        self.str_count = 0
        self.len_min = math.inf
        self.len_max = 0
        self.len_sum = 0
        self.values = {}
        self.values_overflow = False
        self.values_reason = None
        self.arr_count = 0
        self.arr_min = math.inf
        self.arr_max = 0
        self.arr_sum = 0
        self.true_count = 0
        self.false_count = 0
        self.null_count = 0
        self.obj_keys = Counter()
        self.docs_present = 0
        self.site_docs = Counter()

    def observe(self, path, value, site, snapshot):  # noqa: C901
        self.count += 1
        self.sites.add(site)
        self.snapshots.add(snapshot)

        if value is None:
            self.types["null"] += 1
            self.null_count += 1
        elif value is True or value is False:
            self.types["boolean"] += 1
            if value:
                self.true_count += 1
            else:
                self.false_count += 1
        elif isinstance(value, int):
            self.types["integer"] += 1
            self._observe_number(float(value))
            self.int_count += 1
        elif isinstance(value, float):
            self.types["number"] += 1
            if math.isfinite(value):
                self._observe_number(value)
                if value.is_integer():
                    self.int_count += 1
                else:
                    self.float_count += 1
            else:
                self.nonfinite += 1
        elif isinstance(value, str):
            self.types["string"] += 1
            self.str_count += 1
            n = len(value)
            self.len_min = min(self.len_min, n)
            self.len_max = max(self.len_max, n)
            self.len_sum += n
            self._observe_value(path, value, site)
        elif isinstance(value, list):
            self.types["array"] += 1
            self.arr_count += 1
            n = len(value)
            self.arr_min = min(self.arr_min, n)
            self.arr_max = max(self.arr_max, n)
            self.arr_sum += n
        elif isinstance(value, dict):
            self.types["object"] += 1
            for k in value:
                self.obj_keys[k] += 1

    def _observe_number(self, v):
        self.num_count += 1
        self.num_min = min(self.num_min, v)
        self.num_max = max(self.num_max, v)
        self.num_sum += v

    def _observe_value(self, path, value, site):
        if self.values_overflow:
            return
        if not redact.recordable(path, value):
            self._withhold(
                "identifying field name" if redact.is_denied(path)
                else "personal-shaped or over-long values")
            return
        self.values.setdefault(redact.scrub(value), set()).add(site)
        if len(self.values) > redact.MAX_DISTINCT:
            self._withhold("high cardinality")

    def _withhold(self, reason):
        self.values_overflow = True
        self.values = {}
        self.values_reason = reason

    def _corroborated_values(self):
        """Values written by at least MIN_VALUE_SITES independent sites.

        A vocabulary term is shared; a person's own text is not. Dropping
        single-site values is what keeps dashboard labels holding people's
        names, and a site's Apple Developer Team ID, out of the output.
        """
        return sorted(v for v, sites in self.values.items()
                      if len(sites) >= redact.MIN_VALUE_SITES)

    def note_document(self, site):
        """Called once per document that contained this path anywhere."""
        self.docs_present += 1
        self.site_docs[site] += 1

    def to_dict(self, path, total_docs, site_totals):
        # Fraction of sites on which the field is near-universal, which
        # separates "every client writes it" from "one client writes it
        # always and the rest never do".
        saturated = sum(
            1 for s, n in self.site_docs.items()
            if site_totals.get(s) and n / site_totals[s] >= 0.95
        )
        out = {
            "path": path,
            "count": self.count,
            "docs_present": self.docs_present,
            "doc_frequency": round(self.docs_present / total_docs, 6) if total_docs else 0.0,
            "values_per_doc": round(self.count / self.docs_present, 3) if self.docs_present else 0.0,
            "sites": sorted(self.sites),
            "site_count": len(self.sites),
            "sites_saturated": saturated,
            "site_frequency": {
                s: round(n / site_totals[s], 6)
                for s, n in sorted(self.site_docs.items()) if site_totals.get(s)
            },
            "snapshots": sorted(self.snapshots),
            "types": dict(sorted(self.types.items())),
        }
        if self.num_count and self.num_count < MIN_NUMERIC_SAMPLES:
            out["numeric"] = {
                "count": self.num_count,
                "range_note": (
                    f"withheld: fewer than {MIN_NUMERIC_SAMPLES} observations, "
                    "so an extreme would be one site's individual data point"
                ),
                "integral_values": self.int_count,
                "fractional_values": self.float_count,
            }
        elif self.num_count:
            out["numeric"] = {
                "count": self.num_count,
                "min": self.num_min,
                "max": self.num_max,
                "mean": round(self.num_sum / self.num_count, 6),
                "integral_values": self.int_count,
                "fractional_values": self.float_count,
                "nonfinite": self.nonfinite,
            }
        if self.str_count:
            out["string"] = {
                "count": self.str_count,
                "len_min": self.len_min,
                "len_max": self.len_max,
                "len_mean": round(self.len_sum / self.str_count, 2),
            }
            if self.values_overflow:
                out["string"]["distinct_values"] = None
                out["string"]["value_note"] = f"withheld: {self.values_reason}"
            else:
                corroborated = self._corroborated_values()
                out["string"]["distinct_values"] = corroborated or None
                # Counts are not identifying and keep the cost of the
                # corroboration rule visible: a declared enum can be
                # incomplete in ways this census deliberately cannot show,
                # because the missing values were each written by too few
                # sites to publish.
                out["string"]["distinct_value_count"] = len(self.values)
                dropped = len(self.values) - len(corroborated)
                if dropped:
                    out["string"]["values_withheld"] = dropped
                    out["string"]["value_note"] = (
                        f"{dropped} value(s) withheld: seen on fewer than "
                        f"{redact.MIN_VALUE_SITES} sites"
                    )
        if self.arr_count:
            out["array"] = {
                "count": self.arr_count,
                "len_min": self.arr_min,
                "len_max": self.arr_max,
                "len_mean": round(self.arr_sum / self.arr_count, 2),
            }
        if self.true_count or self.false_count:
            out["boolean"] = {"true": self.true_count, "false": self.false_count}
        if self.null_count:
            out["null_count"] = self.null_count
        return out


def _walk(doc, prefix, map_paths, emit):
    """Emit (path, value) for every node, collapsing map-like object keys."""
    for key, value in doc.items():
        path = f"{prefix}.{key}" if prefix else key
        emit(path, value)
        if isinstance(value, dict):
            if path in map_paths:
                for mv in value.values():
                    mpath = f"{path}.{{}}"
                    emit(mpath, mv)
                    if isinstance(mv, dict):
                        _walk(mv, mpath, map_paths, emit)
                    elif isinstance(mv, list):
                        _walk_list(mv, mpath, map_paths, emit)
            else:
                _walk(value, path, map_paths, emit)
        elif isinstance(value, list):
            _walk_list(value, path, map_paths, emit)


def _walk_list(items, path, map_paths, emit):
    epath = f"{path}[]"
    for item in items:
        emit(epath, item)
        if isinstance(item, dict):
            _walk(item, epath, map_paths, emit)
        elif isinstance(item, list):
            _walk_list(item, epath, map_paths, emit)


def detect_map_paths(sources, sample_docs=MAP_SAMPLE_DOCS, extra=()):
    """Bounded first pass: find object paths keyed by user data."""
    distinct_keys = defaultdict(set)
    occurrences = Counter()
    width_sum = Counter()

    def scan(doc, prefix):
        for key, value in doc.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                distinct_keys[path].update(value.keys())
                occurrences[path] += 1
                width_sum[path] += len(value)
                scan(value, path)
            elif isinstance(value, list):
                scan_list(value, path)

    def scan_list(items, path):
        epath = f"{path}[]"
        for item in items:
            if isinstance(item, dict):
                scan(item, epath)
            elif isinstance(item, list):
                scan_list(item, epath)

    for src in sources:
        for i, doc in enumerate(corpus.iter_documents(src.path)):
            if i >= sample_docs:
                break
            scan(doc, "")

    maps = set(extra)
    detected = {}
    for path, keys in distinct_keys.items():
        n_keys = len(keys)
        mean_width = width_sum[path] / occurrences[path]
        if n_keys >= MAP_MIN_DISTINCT_KEYS and n_keys > MAP_KEY_TO_WIDTH_RATIO * mean_width:
            maps.add(path)
            detected[path] = {"distinct_keys": n_keys, "mean_width": round(mean_width, 2)}
    for path in MAP_PATHS_ALWAYS:
        maps.add(path)
    return maps, detected


def census_collection(collection, sources, max_docs=None, extra_maps=()):
    """Run the two-pass census for one collection."""
    sources = [s for s in sources if s.collection == collection]
    if not sources:
        return None

    map_paths, detected = detect_map_paths(sources, extra=extra_maps)

    stats = defaultdict(FieldStat)
    per_source = {}
    site_totals = Counter()
    total_docs = 0
    truncated = False
    t0 = time.time()

    for src in sources:
        n = 0
        for doc in corpus.iter_documents(src.path):
            site, snapshot = src.site, src.snapshot

            seen = set()

            def emit(path, value, _site=site, _snap=snapshot, _seen=seen):
                if path not in stats and len(stats) >= MAX_PATHS:
                    return
                stats[path].observe(path, value, _site, _snap)
                _seen.add(path)

            _walk(doc, "", map_paths, emit)
            for path in seen:
                stats[path].note_document(site)
            site_totals[site] += 1
            n += 1
            if max_docs and n >= max_docs:
                truncated = True
                break
        per_source[src.label] = n
        total_docs += n

    fields = [stats[p].to_dict(p, total_docs, site_totals) for p in sorted(stats)]
    return {
        "collection": collection,
        "generated_by": "tools/nsschema/census.py",
        "documents": total_docs,
        "sources": per_source,
        "sites": sorted({s.site for s in sources}),
        "site_documents": dict(sorted(site_totals.items())),
        "snapshots": sorted({s.snapshot for s in sources}),
        "map_paths": sorted(map_paths),
        "map_paths_detected": detected,
        "truncated": truncated,
        "path_cap_reached": len(stats) >= MAX_PATHS,
        "elapsed_seconds": round(time.time() - t0, 1),
        "fields": fields,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="reports/schema-census", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    ap.add_argument("--max-docs", type=int, default=None,
                    help="cap documents per source (smoke runs)")
    ap.add_argument("--map-path", action="append", default=[],
                    help="force a path to be treated as user-keyed")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    sources = corpus.discover(root)
    if not sources:
        print("no corpus found under externals/", file=sys.stderr)
        return 1

    collections = args.collections or list(corpus.COLLECTIONS)
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    for collection in collections:
        result = census_collection(collection, sources, args.max_docs, args.map_path)
        if result is None:
            print(f"{collection}: no sources", file=sys.stderr)
            continue
        dest = out_dir / f"{collection}.census.json"
        dest.write_text(json.dumps(result, indent=1, sort_keys=False) + "\n")
        print(f"{collection}: {result['documents']:,} docs, "
              f"{len(result['fields'])} paths, {result['elapsed_seconds']}s -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
