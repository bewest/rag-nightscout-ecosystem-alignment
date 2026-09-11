"""observability.py — score real sites against the observability profile.

`specs/conformance/observability-profile.yaml` states what each kind of
system has to upload for an AID system to be observable. A profile nobody
measures is a wish list, so this replays it over the corpus: for every site,
work out which roles it plays, then check what share of its documents
satisfy each obligation that applies to it.

Two numbers per obligation per site, and they mean different things:

``document share``
    the fraction of that site's documents in the collection that satisfy it.
    Low is not automatically a failure — ``loop.enacted`` is absent on
    cycles where nothing was enacted, and that is correct behaviour.
``satisfied``
    whether the site ever satisfies it at all. A site that never once
    writes ``loop.version`` is not "mostly conformant"; it simply does not
    record which build made its decisions.

Role detection is per site, from the data, and for the controller role it
is deliberately *not* based on the fields the obligations then ask for:
detecting a controller by "it wrote a devicestatus" would make the profile
unfalsifiable, since a system that uploads nothing would be classified as
not-a-controller and therefore conformant. The controller role is detected
from evidence of automated dosing in the treatment record instead.

Roles are never inferred from a device string. That is free text, it is the
field this work has spent the most effort de-identifying, and it is not
reliable: one site's device strings read like a controller while its
treatments show no automated dosing at all.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml

from . import corpus
from .quirks import evaluate

PROFILE = "specs/conformance/observability-profile.yaml"

LEVELS = ("MUST", "SHOULD", "MAY")


def load_profile(root: Path, rel=PROFILE):
    profile = yaml.safe_load((root / rel).read_text())
    known = {r["id"] for r in profile["roles"]}
    for obligation in profile["obligations"]:
        if obligation["role"] not in known:
            raise ValueError(f"{obligation['id']}: unknown role {obligation['role']}")
        if obligation["level"] not in LEVELS:
            raise ValueError(f"{obligation['id']}: unknown level {obligation['level']}")
    return profile


def score(profile, sources):
    roles = profile["roles"]
    obligations = profile["obligations"]

    by_collection = defaultdict(list)
    for role in roles:
        for detector in role.get("detect_any") or [role["detect"]]:
            by_collection[detector["collection"]].append(("role", role, detector))
    for obligation in obligations:
        by_collection[obligation["collection"]].append(
            ("obligation", obligation, obligation))

    site_docs = defaultdict(lambda: defaultdict(int))
    role_hits = defaultdict(lambda: defaultdict(int))
    obl_hits = defaultdict(lambda: defaultdict(int))

    for src in sources:
        checks = by_collection.get(src.collection)
        if not checks:
            continue
        for doc in corpus.iter_documents(src.path):
            site_docs[src.site][src.collection] += 1
            for kind, item, detect in checks:
                if evaluate({k: v for k, v in detect.items()
                             if k in ("path", "test", "value", "values", "pattern")},
                            doc):
                    target = role_hits if kind == "role" else obl_hits
                    target[src.site][item["id"]] += 1

    # A site plays a role if the role's detector ever fires for it.
    site_roles = {
        site: sorted(r["id"] for r in roles if role_hits[site].get(r["id"], 0) > 0)
        for site in site_docs
    }

    results = []
    for site in sorted(site_docs):
        played = set(site_roles[site])
        rows = []
        for obligation in obligations:
            if obligation["role"] not in played:
                continue
            total = site_docs[site].get(obligation["collection"], 0)
            hits = obl_hits[site].get(obligation["id"], 0)
            rows.append({
                "id": obligation["id"],
                "level": obligation["level"],
                "role": obligation["role"],
                "collection": obligation["collection"],
                "path": obligation["path"],
                "title": obligation["title"],
                "documents": hits,
                "collection_documents": total,
                "document_share": round(hits / total, 6) if total else 0.0,
                "satisfied": hits > 0,
            })
        results.append({
            "site": site,
            "roles": sorted(played),
            "documents": dict(site_docs[site]),
            "obligations": rows,
            "unmet": sorted(r["id"] for r in rows if not r["satisfied"]),
            "unmet_must": sorted(r["id"] for r in rows
                                 if not r["satisfied"] and r["level"] == "MUST"),
        })
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", default=PROFILE)
    ap.add_argument("--out", default="reports/schema-census/observability.json",
                    type=Path)
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if any site fails a MUST it is in scope for")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    profile = load_profile(root, args.profile)
    results = score(profile, corpus.discover(root))

    print(f"{len(profile['obligations'])} obligations, "
          f"{len(profile['roles'])} roles, {len(results)} sites\n")
    for site in results:
        met = sum(1 for r in site["obligations"] if r["satisfied"])
        print(f"  site {site['site']}  roles={','.join(site['roles']):58s} "
              f"{met}/{len(site['obligations'])} met")
        for row in site["obligations"]:
            if not row["satisfied"]:
                print(f"      UNMET {row['level']:6s} {row['id']:16s} {row['title']}")

    # An obligation nobody meets is a statement about the ecosystem, not
    # about one site.
    universal_gaps = []
    for obligation in profile["obligations"]:
        scoped = [s for s in results if obligation["role"] in s["roles"]]
        if scoped and all(obligation["id"] in s["unmet"] for s in scoped):
            universal_gaps.append(obligation)
    if universal_gaps:
        print("\n  met by no site in scope:")
        for obligation in universal_gaps:
            print(f"      {obligation['level']:6s} {obligation['id']:16s} "
                  f"{obligation['title']}")

    report = {
        "generated_by": "tools/nsschema/observability.py",
        "profile": args.profile,
        "profile_version": profile.get("version"),
        "sites": results,
        "met_by_no_site_in_scope": [o["id"] for o in universal_gaps],
    }
    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=1) + "\n")
    print(f"-> {args.out}")

    if args.check:
        failing = [s for s in results if s["unmet_must"]]
        for site in failing:
            print(f"FAIL site {site['site']}: unmet MUST {site['unmet_must']}")
        if failing:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
