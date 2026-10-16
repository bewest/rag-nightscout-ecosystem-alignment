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

D20 (execution plan §2.6.3, SPEC-REG-QUIRKS): an entry may name the
``(vendor, product, versions)`` it affects; the measurement adds, for those
entries, the recent writes, the versions seen (same document or
co-occurrence) and which lifecycle statuses the measurement supports, and
``check`` fails a ``historical`` or ``retired`` claim it does not support.

Detectors are declarative (see ``specs/quirks/README.md``). Keeping them
data rather than code is what lets the registry be reviewed by someone who
does not read Python, and stops a "quirk" from quietly becoming arbitrary
logic.
"""

import argparse
import bisect
import datetime
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


# ── D20: versions, lifecycle and the registry schema ──────────────────
#
# Execution plan §2.6.3 (D20, maintainer 2026-10-16), queue item
# SPEC-REG-QUIRKS. Rule 1: an entry may name the `(vendor, product,
# versions)` it affects, for stored documents and for declarations alike.
# Rule 4: `proposed` -> `active` -> `historical` -> `retired`, each move
# measured here and never asserted.

SCHEMA = "specs/quirks/quirk.schema.json"
STATUSES = ("proposed", "active", "historical", "retired")

# Rule 4's "recent", declared and measured: a write is recent when the
# document's own time is within RECENT_DAYS of the newest snapshot in the
# corpus (the collection pass date, not the wall clock, so a re-run over the
# same corpus gives the same answer). 365 days: the longest common build
# lifetime among the iOS controllers (a paid Apple developer profile) and a
# full year of seasonal use. A choice for the maintainer to confirm
# (hub-sync design §3.7).
RECENT_DAYS = 365

COMPARATORS = ("<=", ">=", "<", ">", "=")


def version_key(version):
    """The order of a vendor's own version strings: dot-separated parts,
    numeric parts as numbers and before text (the hub-sync design §3.6 order
    for "newest"). A shorter version sorts before a longer one it prefixes."""
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p)
                 for p in str(version).split("."))


def parse_range(expr):
    """A range: `*`, or whitespace-separated comparators that must all hold,
    each one of `=`, `>=`, `>`, `<=`, `<` followed by a version string."""
    expr = (expr or "").strip()
    if not expr:
        raise ValueError("an empty version range")
    if expr == "*":
        return []
    out = []
    for term in expr.split():
        op = next((c for c in COMPARATORS if term.startswith(c)), None)
        if op is None or len(term) == len(op):
            raise ValueError(f"version range term {term!r}: expected a comparator and a version")
        out.append((op, term[len(op):]))
    return out


def in_range(version, expr):
    """Whether `version` (the vendor's own string) is inside `expr`."""
    key = version_key(version)
    for op, bound in parse_range(expr):
        b = version_key(bound)
        if not {"=": key == b, ">=": key >= b, ">": key > b,
                "<=": key <= b, "<": key < b}[op]:
            return False
    return True


def affected(entry, vendor, product, version):
    """Rule 1. True when an `affects` item names (vendor, product) with a
    measured range holding `version`; None when the item's versions are
    unmeasured or `version` is unknown (the entry cannot say); False
    otherwise, including an entry with no `affects` (project-level
    attribution only)."""
    found = False
    for item in entry.get("affects") or []:
        if (item["vendor"], item["product"]) != (vendor, product):
            continue
        rng = (item.get("versions") or {}).get("range")
        if rng is None or version is None:
            found = None
            continue
        if in_range(version, rng):
            return True
    return found


def load_registry(directory: Path, schema=None):
    """Every entry, validated: the detector test is known, and the entry
    matches `specs/quirks/quirk.schema.json` (D20's `affects`, lifecycle,
    `mapping` and declaration entries are members of it; the 17 entries
    that predate D20 validate unchanged)."""
    import jsonschema
    if schema is None:
        path = corpus.repo_root() / SCHEMA
        schema = json.loads(path.read_text()) if path.is_file() else None
    validator = jsonschema.Draft202012Validator(schema) if schema else None
    entries = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for quirk in data.get("quirks") or []:
            detect = quirk.get("detect") or {}
            if quirk.get("applies_to", "documents") == "documents" and \
                    detect.get("test") not in TESTS:
                raise ValueError(
                    f"{quirk['id']}: unknown test {detect.get('test')!r}; "
                    f"expected one of {', '.join(TESTS)}")
            if validator is not None:
                errors = sorted(validator.iter_errors(quirk), key=lambda e: list(e.path))
                if errors:
                    where = ".".join(str(p) for p in errors[0].absolute_path)
                    raise ValueError(f"{quirk['id']}: {where or 'entry'}: {errors[0].message}")
            for item in quirk.get("affects") or []:
                rng = (item.get("versions") or {}).get("range")
                if rng is not None:
                    parse_range(rng)
            quirk["collection"] = data["collection"]
            quirk["source_file"] = str(path)
            entries.append(quirk)
    return entries


def doc_time(doc):
    """A document's own time in epoch seconds: `date` or `mills` (epoch
    milliseconds), else `created_at`, `dateString` or `timestamp` (ISO 8601).
    None when it carries none of them."""
    for key in ("date", "mills"):
        value = doc.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value / 1000
        if isinstance(value, str) and value.isdigit():
            return int(value) / 1000
    for key in ("created_at", "dateString", "timestamp"):
        value = doc.get(key)
        if isinstance(value, str):
            try:
                return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
    return None


def as_of(sources):
    """The newest snapshot date, as epoch seconds at midnight UTC, or None
    when no snapshot id is a date."""
    dates = []
    for src in sources:
        try:
            dates.append(datetime.datetime.strptime(src.snapshot, "%Y-%m-%d")
                         .replace(tzinfo=datetime.timezone.utc).timestamp())
        except ValueError:
            continue
    return max(dates) if dates else None


def _version_sources(registry):
    """(quirk id, product key, versionSource) for every affects item that
    says where a version is read."""
    out = []
    for quirk in registry:
        for item in quirk.get("affects") or []:
            source = item.get("versionSource")
            if source:
                out.append((quirk["id"], f"{item['vendor']}/{item['product']}", source))
    return out


def _nearest(timeline, t, window):
    i = bisect.bisect_left(timeline, (t, ""))
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(timeline) and abs(timeline[j][0] - t) <= window:
            if best is None or abs(timeline[j][0] - t) < abs(best[0] - t):
                best = timeline[j]
    return best[1] if best else None


def measure(registry, sources, recent_days=RECENT_DAYS):
    """Per entry: documents, share and sites (as before), and for D20 the
    recent and untimed counts, the newest date a document shows it, and per
    affected product the versions seen — read from the same document, or by
    co-occurrence with the nearest version-bearing document of another
    collection on the same site within a window (co-occurrence, not
    attribution). Declaration entries are not measured over the corpus."""
    by_collection = defaultdict(list)
    for quirk in registry:
        if quirk.get("applies_to", "documents") == "documents":
            by_collection[quirk["collection"]].append(quirk)

    hits = {q["id"]: Counter() for q in registry}
    snapshots = {q["id"]: set() for q in registry}
    recent = Counter()
    untimed = Counter()
    newest = {}
    versions = defaultdict(lambda: defaultdict(Counter))
    totals = Counter()
    site_totals = defaultdict(Counter)

    reference = as_of(sources)
    cutoff = reference - recent_days * 86400 if reference is not None else None
    wanted = _version_sources(registry)
    cross = defaultdict(list)  # (collection, path) -> [(quirk id, product key, window)]
    for qid, key, source in wanted:
        cross[(source["collection"], source["path"])].append((qid, key, source))
    timelines = defaultdict(list)  # (snapshot, site, collection, path) -> [(t, version)]

    # Version-bearing collections first, so a co-occurrence lookup has its timeline.
    order = {c for c, _p in cross}
    for src in sorted(sources, key=lambda s: (s.collection not in order, s.collection)):
        quirks = by_collection.get(src.collection)
        paths = [p for c, p in cross if c == src.collection]
        if not quirks and not paths:
            continue
        for doc in corpus.iter_documents(src.path):
            t = doc_time(doc)
            for path in paths:
                for value in resolve(doc, path)[:1]:
                    if t is not None and value is not None:
                        timelines[(src.snapshot, src.site, src.collection, path)].append(
                            (t, str(value)))
            if not quirks:
                continue
            totals[src.collection] += 1
            site_totals[src.collection][src.site] += 1
            for quirk in quirks:
                if not evaluate(quirk["detect"], doc):
                    continue
                qid = quirk["id"]
                hits[qid][src.site] += 1
                snapshots[qid].add(src.snapshot)
                if t is None:
                    untimed[qid] += 1
                else:
                    day = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date().isoformat()
                    newest[qid] = max(newest.get(qid, day), day)
                    if cutoff is not None and t >= cutoff:
                        recent[qid] += 1
                for item in quirk.get("affects") or []:
                    source = item.get("versionSource")
                    if not source:
                        continue
                    key = f"{item['vendor']}/{item['product']}"
                    if source["collection"] == src.collection:
                        found = resolve(doc, source["path"])
                        version = str(found[0]) if found and found[0] is not None else None
                    else:
                        tl = timelines.get((src.snapshot, src.site, source["collection"],
                                            source["path"]), [])
                        version = _nearest(tl, t, source.get("window_minutes", 60) * 60) \
                            if t is not None else None
                    versions[qid][key][version or "unattributed"] += 1
        for k in [k for k in timelines if k[0] == src.snapshot and k[1] == src.site]:
            timelines[k].sort()

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
        row = {
            "id": quirk["id"],
            "title": quirk["title"],
            "collection": collection,
            "kind": quirk["kind"],
            "status": quirk["status"],
            "path": quirk.get("path"),
            "documents": counted,
            "collection_documents": total,
            "share": round(counted / total, 6) if total else 0.0,
            "sites": len(per_site),
            "site_share": per_site,
            "snapshots": sorted(snapshots[quirk["id"]]),
            "expect": quirk.get("expect", {}),
        }
        if quirk.get("affects") or quirk.get("applies_to") == "declarations":
            row["applies_to"] = quirk.get("applies_to", "documents")
            row["recent_documents"] = recent[quirk["id"]]
            row["untimed_documents"] = untimed[quirk["id"]]
            row["newest"] = newest.get(quirk["id"])
            row["versions"] = {
                key: {"by": "same-document" if next(
                          s for q, k, s in wanted if q == quirk["id"] and k == key)["collection"]
                      == collection else "co-occurrence",
                      "counts": dict(sorted(counts.items(), key=lambda kv: version_key(kv[0])))}
                for key, counts in sorted(versions[quirk["id"]].items())}
        results.append(row)
    return results


def live_instances(entry, instances):
    """Rule 4's live-instance half: how many live instances in a hub's
    listing (`[{vendor, product, version, live}]`) run an affected version;
    an item whose versions are unmeasured counts every version of its
    product. None when no listing was given or the entry names no
    `affects` (an entry without it cannot say which instances it affects)."""
    if instances is None or not entry.get("affects"):
        return None
    count = 0
    for inst in instances:
        if not inst.get("live"):
            continue
        hit = affected(entry, inst["vendor"], inst["product"], inst.get("version"))
        if hit or (hit is None and any((i["vendor"], i["product"]) ==
                                       (inst["vendor"], inst["product"])
                                       for i in entry["affects"])):
            count += 1
    return count


def lifecycle(row, entry, instances=None):
    """Rule 4: which statuses the measurement supports, and why not the
    others. `proposed` is always supported; `active` needs documents in the
    corpus; `historical` needs no recent write, a measured zero of live
    affected instances, and a detector whose evidence the hub's own mapping
    does not erase (a hub that rewrites the document leaves nothing in the
    stored form to count, so only its rule 3 records measure recent writes);
    `retired` needs historical's conditions and no stored document left
    that depends on the mapping. Declaration entries are measured by a
    hub's rule 3 records, which this corpus predates."""
    why = {}
    if entry.get("applies_to") == "declarations":
        reason = "declarations are measured by a hub's recorded mappings, not the corpus"
        return {"supported": ["proposed"], "live_instances": None,
                "why_not": {s: reason for s in STATUSES[1:]}}
    live = live_instances(entry, instances)
    if row["documents"] == 0:
        why["active"] = "no document in the corpus shows it"
    erased = bool((entry.get("mapping") or {}).get("erasesEvidence"))
    if erased:
        why["historical"] = ("the hub's mapping rewrites the stored form, so recent writes "
                             "are measured only by its recorded mappings (rule 3)")
    elif row.get("recent_documents", row["documents"]) > 0:
        why["historical"] = f"{row.get('recent_documents', row['documents'])} recent document(s)"
    elif live is None:
        why["historical"] = "live affected instances are unmeasured"
    elif live > 0:
        why["historical"] = f"{live} live affected instance(s)"
    if "historical" in why:
        why["retired"] = why["historical"]
    elif row["documents"] > 0 or erased:
        why["retired"] = f"{row['documents']} stored document(s) still depend on it"
    supported = [s for s in STATUSES if s not in why]
    return {"supported": supported, "live_instances": live, "why_not": why}


def check(results):
    """Return a list of failures: an `active` claim that no longer holds its
    `expect` block, or a `historical` or `retired` claim the measurement
    does not support (rule 4: each move is measured, never asserted). A
    `proposed` entry is not yet measured and never fails. *(Changed
    2026-10-16, D20: a `historical` entry was skipped; a `proposed` one was
    checked like an active one.)*"""
    failures = []
    for row in results:
        expect = row.get("expect") or {}
        status = row["status"]
        if status == "proposed":
            continue
        if status in ("historical", "retired"):
            life = row.get("lifecycle")
            if life is None:
                failures.append((row["id"], f"{status} is asserted, not measured"))
            elif status not in life["supported"]:
                failures.append((row["id"], f"{status} not supported by measurement: "
                                            f"{life['why_not'][status]}"))
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
    ap.add_argument("--recent-days", type=int, default=RECENT_DAYS,
                    help="rule 4's recent window, in days before the newest snapshot")
    ap.add_argument("--instances", type=Path,
                    help="a hub's de-identified instance listing, "
                         "[{vendor, product, version, live}], for rule 4")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    registry = load_registry(root / args.registry)
    sources = corpus.discover(root)
    instances = json.loads(args.instances.read_text()) if args.instances else None
    results = measure(registry, sources, args.recent_days)
    by_id = {q["id"]: q for q in registry}
    for row in results:
        if "applies_to" in row or row["status"] in ("historical", "retired"):
            row["lifecycle"] = lifecycle(row, by_id[row["id"]], instances)

    for row in sorted(results, key=lambda r: (r["collection"], r["id"])):
        print(f"  {row['id']:24s} {row['share']:7.2%} of {row['collection']:12s} "
              f"on {row['sites']:2d} sites  {row['title'][:48]}")
        if "lifecycle" in row:
            print(f"  {'':24s} recent {row.get('recent_documents')}, newest {row.get('newest')}, "
                  f"supports {', '.join(row['lifecycle']['supported'])}")

    reference = as_of(sources)
    report = {
        "generated_by": "tools/nsschema/quirks.py",
        "registry": str(args.registry),
        "quirks": len(results),
        "results": results,
    }
    if any("lifecycle" in r for r in results):
        report["lifecycle"] = {
            "recent_days": args.recent_days,
            "as_of": datetime.datetime.fromtimestamp(reference, datetime.timezone.utc)
            .date().isoformat() if reference is not None else None,
            "instances": "given" if instances is not None else "unmeasured",
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
