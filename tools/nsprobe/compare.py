"""compare.py — set a data holder's results beside this repository's own.

Reads ``<out>/schema-census-v1`` (and ``-v3``) and ``<out>/nsprobe``, and the
same files for this repo: ``reports/schema-census`` and the nsprobe baseline.
Prints a Markdown summary of where the two corpora disagree about a claim
this repository makes. It changes nothing; turning a disagreement into a
spec, quirk or heuristic change is a reviewed commit.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OURS_CENSUS = REPO / "reports/schema-census"


def _load(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def quirks_table(theirs, ours):
    rows = ["| quirk | ours: share / sites | theirs: share / sites | claim (min share / sites) | holds on theirs |",
            "|---|---|---|---|---|"]
    ours_by = {r["id"]: r for r in (ours or {}).get("results", [])}
    for r in (theirs or {}).get("results", []):
        o = ours_by.get(r["id"], {})
        exp = r.get("expect") or {}
        ok = ((exp.get("min_share") is None or r["share"] >= exp["min_share"]) and
              (exp.get("min_sites") is None or r["sites"] >= exp["min_sites"]))
        rows.append(f"| {r['id']} | {o.get('share', 0):.1%} / {o.get('sites', 0)} | "
                    f"{r['share']:.1%} / {r['sites']} | {exp.get('min_share', '-')} / "
                    f"{exp.get('min_sites', '-')} | {'yes' if ok else '**no**'} |")
    return rows


def reconcile_section(their_dir: Path):
    out = []
    for coll in ("entries", "treatments", "devicestatus", "profile"):
        t = _load(their_dir / f"{coll}.reconcile.json")
        o = _load(OURS_CENSUS / f"{coll}.reconcile.json")
        if not t or not o:
            continue
        our_unobs = {u["path"] for u in o.get("unobserved", [])}
        their_unobs = {u["path"] for u in t.get("unobserved", [])}
        now_seen = sorted(our_unobs - their_unobs)
        our_undecl = {u["path"] for u in o.get("undeclared", [])}
        new_undecl = [u for u in t.get("undeclared", [])
                      if u["path"] not in our_undecl and u.get("site_count", 0) >= 3]
        enum_o = {e["path"]: e for e in o.get("enum_unverifiable", [])}
        enum_t = {e["path"]: e for e in t.get("enum_unverifiable", [])}
        out.append(f"### {coll}: theirs {t.get('documents', 0):,} docs on "
                   f"{len(t.get('sites', []))} sites; ours {o.get('documents', 0):,} on "
                   f"{len(o.get('sites', []))}")
        out.append(f"- declared paths we never observed, observed by them: "
                   f"{', '.join(now_seen) or 'none'}")
        out.append(f"- undeclared paths they see on 3+ sites that we do not list: "
                   f"{', '.join(u['path'] for u in new_undecl[:30]) or 'none'}")
        for path in sorted(set(enum_o) | set(enum_t)):
            eo, et = enum_o.get(path, {}), enum_t.get(path, {})
            out.append(f"- enum `{path}`: values published ours {eo.get('values_published', '-')}, "
                       f"theirs {et.get('values_published', '-')}")
        v3 = t.get("v3_metadata_absent")
        if v3 is not None:
            out.append(f"- v3 metadata paths still absent on theirs: "
                       f"{', '.join(v['path'] for v in v3) or 'none'}")
    return out


def probe_section(their_probe: Path, base: Path):
    out = []
    for f in sorted(their_probe.glob("*.json")):
        t = _load(f)
        o = _load(base / f.name)
        if not t:
            continue
        run = t.get("run", {})
        out.append(f"### {t['probe']} ({', '.join(t['questions'])})")
        out.append(f"- theirs: {run.get('sites')} sites, {run.get('documents_by_collection')}")
        if o:
            out.append(f"- ours: {o['run'].get('sites')} sites, {o['run'].get('documents_by_collection')}")
        if t["probe"] == "smb_marking":
            for fam, rows in t["result"]["explicit_marker_vs_automatic_lt5U_rule"].items():
                cells = ", ".join(f"{k}: {v['documents']}" for k, v in rows.items())
                out.append(f"  - {fam}: {cells}")
        if t["probe"] == "families":
            out.append(f"  - site dominant family: theirs {t['result']['site_dominant_family']}"
                       + (f"; ours {o['result']['site_dominant_family']}" if o else ""))
    return out


def main(out: Path, baseline: Path):
    lines = ["# nsprobe comparison", ""]
    for api in ("v1", "v3"):
        d = out / f"schema-census-{api}"
        if not d.is_dir():
            continue
        lines += [f"## Quirks registry ({api})", ""]
        lines += quirks_table(_load(d / "quirks.json"), _load(OURS_CENSUS / "quirks.json"))
        lines += ["", f"## Reconcile against specs/openapi ({api})", ""]
        lines += reconcile_section(d)
        lines.append("")
    if (out / "nsprobe").is_dir():
        lines += ["## Probes", ""]
        lines += probe_section(out / "nsprobe", baseline)
    print("\n".join(lines))
    return 0
