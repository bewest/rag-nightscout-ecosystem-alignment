"""dosing_inputs.py — can a dosing decision be replayed from Nightscout?

An AID controller decides a temp basal or an SMB from a specific set of
inputs. Nightscout stores the *decision* well. Whether it stores enough to
*reproduce* the decision is a different question, and it is the one that
matters for retrospective analysis, for conformance testing against real
history, and for anyone asking "why did it do that".

The input set is evidence-based: the union of ``input.*`` paths across the
385 replay vectors in ``conformance/``, captured from real AAPS and Loop
runs. ``specs/nsschema/dosing-input-sources.yaml`` maps each to the
Nightscout paths that could carry it, classified ``recorded``,
``derivable``, ``partial`` or ``absent``.

This tool checks those claims against the census rather than trusting
them: a source path claimed to carry an input must actually exist in the
corpus, and the per-site coverage says whether it exists *for that
controller family* or only for one.

The last distinction is the interesting one. Recording is not uniform
across the ecosystem: Loop writes its dosing safety limits into
``profile.loopSettings`` while oref0 derivatives write none of theirs
anywhere, so "is this input recoverable" has a different answer depending
on which controller produced the data.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from . import corpus

MAP = "specs/nsschema/dosing-input-sources.yaml"

KIND_ORDER = ("recorded", "derivable", "partial", "absent")


def load_census(root: Path, census_dir: Path):
    censuses = {}
    for path in (census_dir if census_dir.is_absolute() else root / census_dir).glob(
            "*.census.json"):
        data = json.loads(path.read_text())
        censuses[data["collection"]] = {f["path"]: f for f in data["fields"]}
    return censuses


def check(mapping, censuses):
    rows = []
    for entry in mapping["inputs"]:
        collection = entry.get("collection")
        fields = censuses.get(collection, {})
        found, missing = [], []
        best_sites = 0
        best_freq = 0.0
        for source in entry.get("sources") or []:
            field = fields.get(source)
            if field:
                found.append({
                    "path": source,
                    "doc_frequency": field["doc_frequency"],
                    "sites": field["site_count"],
                })
                best_sites = max(best_sites, field["site_count"])
                best_freq = max(best_freq, field["doc_frequency"])
            else:
                missing.append(source)

        claimed = entry["kind"]
        if claimed in ("recorded", "partial") and not found:
            verdict = "claim-unsupported"
        elif claimed == "absent" and found:
            verdict = "claim-contradicted"
        else:
            verdict = "confirmed"

        rows.append({
            "input": entry["input"],
            "algorithm": entry.get("algorithm", "oref0"),
            "kind": claimed,
            "verdict": verdict,
            "collection": collection,
            "sources_found": found,
            "sources_missing": missing,
            "best_site_count": best_sites,
            "best_doc_frequency": round(best_freq, 6),
            "confidence": entry.get("confidence"),
            "note": entry.get("note"),
        })
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--census-dir", default="reports/schema-census", type=Path)
    ap.add_argument("--out", default="reports/schema-census/dosing-inputs.json",
                    type=Path)
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if a mapping claim is unsupported")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    mapping = yaml.safe_load((root / MAP).read_text())
    censuses = load_census(root, args.census_dir)
    rows = check(mapping, censuses)

    by_algorithm = defaultdict(Counter)
    for row in rows:
        by_algorithm[row["algorithm"]][row["kind"]] += 1
    kinds = Counter(r["kind"] for r in rows)
    verdicts = Counter(r["verdict"] for r in rows)
    print(f"{len(rows)} dosing inputs: " +
          "  ".join(f"{k}={kinds[k]}" for k in KIND_ORDER if kinds[k]))
    print("  claim checks: " + "  ".join(f"{k}={v}" for k, v in sorted(verdicts.items())))

    for algorithm, counts in sorted(by_algorithm.items()):
        print(f"    {algorithm:6s} " +
              "  ".join(f"{k}={counts[k]}" for k in KIND_ORDER if counts[k]))

    print("\n  not fully recoverable:")
    for row in sorted(rows, key=lambda r: (r["algorithm"], r["input"])):
        if row["kind"] in ("absent", "partial"):
            where = (row["sources_found"][0]["path"] + f" ({row['sources_found'][0]['sites']} sites)"
                     if row["sources_found"] else "nothing")
            print(f"    {row['algorithm']:6s} {row['kind']:9s} "
                  f"{row['input']:34s} {where}")

    problems = [r for r in rows if r["verdict"] != "confirmed"]
    if problems:
        print("\n  mapping claims the census does not support:")
        for row in problems:
            print(f"    {row['verdict']:20s} {row['input']:34s} "
                  f"missing={row['sources_missing']}")

    report = {
        "generated_by": "tools/nsschema/dosing_inputs.py",
        "mapping": MAP,
        "inputs": len(rows),
        "by_kind": dict(kinds),
        "by_algorithm": {a: dict(c) for a, c in sorted(by_algorithm.items())},
        "by_verdict": dict(verdicts),
        "rows": rows,
    }
    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=1) + "\n")
    print(f"-> {args.out}")

    if args.check and problems:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
