"""cli.py — nsprobe's commands.

    python3 -m nsprobe layout    --src RAW --dest CORPUS --key KEYFILE
    python3 -m nsprobe run       --root CORPUS --out OUT [--contributor NAME]
    python3 -m nsprobe census    --root CORPUS --out OUT
    python3 -m nsprobe warehouse --config warehouse.yaml --out OUT
    python3 -m nsprobe check     OUT
    python3 -m nsprobe compare   OUT [--baseline reports/nsprobe/baseline]

Run from the repository root with ``PYTHONPATH=tools``.
"""

import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from . import FORMAT, family, layout, privacy, probes, sources

REPO = Path(__file__).resolve().parents[2]
_CONTRIBUTOR = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class Ctx:
    __slots__ = ("api", "site", "collection", "family", "signal")


class Run:
    def __init__(self):
        self.site_family = {}
        self.collection_docs = Counter()


def tool_identity():
    """The alignment-repo commit the probes ran at, so results are comparable."""
    def git(*a):
        try:
            return subprocess.run(("git", "-C", str(REPO)) + a, capture_output=True,
                                  text=True, check=True).stdout.strip()
        except Exception:
            return ""
    return {"commit": git("rev-parse", "--short=12", "HEAD") or "unknown",
            "dirty": bool(git("status", "--porcelain", "--", "tools/nsprobe",
                              "tools/nsschema", "specs"))}


def envelope(probe_id, questions, contributor, run_meta, result):
    return {
        "format": FORMAT,
        "probe": probe_id,
        "questions": list(questions),
        "contributor": contributor,
        "generated": date.today().isoformat(),
        "tool": tool_identity(),
        "run": run_meta,
        "privacy": {"min_sites": privacy.MIN_SITES},
        "result": result,
    }


def _write_checked(out_dir: Path, name: str, obj):
    bad = privacy.check_output(obj)
    if bad:
        for path, rule in bad[:20]:
            print(f"  REFUSED {name}: {rule} at {path}", file=sys.stderr)
        raise SystemExit(f"{name}: {len(bad)} privacy violation(s); nothing written")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / name).write_text(json.dumps(obj, indent=1, sort_keys=False) + "\n")


def cmd_run(args):
    root = Path(args.root)
    if not _CONTRIBUTOR.match(args.contributor):
        raise SystemExit("--contributor must be a short lower-case label, e.g. 'holder-a'")
    srcs = sources.discover(root)
    if not srcs:
        raise SystemExit(f"{root}: no <api>/<S###>/<collection>.json files")
    want = set(args.probe or [])
    active = [P() for P in probes.ALL if not want or P.id in want]

    # Probes that compare APIs see every file; the rest see one API per
    # (site, collection) — v1 when both exist — so a site exported twice is
    # not counted twice.
    primary = {}
    for s in srcs:
        primary.setdefault((s.site, s.collection), s.api)
    cross_api = {"duplicates", "v3_envelope"}

    run = Run()
    ds_fam = defaultdict(Counter)
    ctx = Ctx()
    for n, src in enumerate(srcs, 1):
        is_primary = primary[(src.site, src.collection)] == src.api
        listeners = [p for p in active if src.collection in p.collections
                     and (is_primary or p.id in cross_api)]
        if not listeners:
            continue
        ctx.api, ctx.site, ctx.collection = src.api, src.site, src.collection
        docs = 0
        for doc in sources.iter_documents(src.path):
            ctx.family, ctx.signal = family.classify(doc, src.collection)
            if is_primary:
                run.collection_docs[src.collection] += 1
                if src.collection == "devicestatus":
                    ds_fam[src.site][ctx.family] += 1
            for p in listeners:
                p.observe(ctx, doc)
            docs += 1
            if args.max_docs and docs >= args.max_docs:
                break
        for p in listeners:
            p.end_source(ctx)
        print(f"  [{n}/{len(srcs)}] {src.api} {src.site} {src.collection}: {docs} docs",
              file=sys.stderr)

    run.site_family = {s: family.site_family(c) for s, c in ds_fam.items()}
    sites = sorted({s.site for s in srcs})
    meta = {
        "sites": len(sites),
        "apis": sorted({s.api for s in srcs}),
        "documents_by_collection": dict(sorted(run.collection_docs.items())),
        "sites_by_collection": {c: len({s.site for s in srcs if s.collection == c})
                                for c in sources.COLLECTIONS},
        "max_docs_per_source": args.max_docs,
    }
    out = Path(args.out) / "nsprobe"
    for p in active:
        _write_checked(out, f"{p.id}.json",
                       envelope(p.id, p.questions, args.contributor, meta, p.result(run)))
        print(f"-> {out / (p.id + '.json')}")
    return 0


def corpus_spec(root: Path, api: str):
    return f"{api}={root.resolve() / api}:flat_site"


def cmd_census(args):
    """Run the nsschema pipeline over the external corpus, one API at a time."""
    from nsschema import census, diff, dosing_inputs, quirks
    root = Path(args.root)
    for api in sources.APIS:
        if not (root / api).is_dir():
            continue
        dest = (Path(args.out) / f"schema-census-{api}").resolve()
        os.environ["NSSCHEMA_CORPUS"] = corpus_spec(root, api)
        os.environ["NSSCHEMA_ROOT"] = str(REPO)
        extra = ["--max-docs", str(args.max_docs)] if args.max_docs else []
        print(f"== {api}: census -> {dest}")
        census.main(["--out", str(dest)] + extra)
        diff.main(["--census", str(dest), "--out", str(dest)])
        quirks.main(["--out", str(dest / "quirks.json")])
        with contextlib.suppress(SystemExit):
            dosing_inputs.main(["--census-dir", str(dest),
                                "--out", str(dest / "dosing-inputs.json")])
    os.environ.pop("NSSCHEMA_CORPUS", None)
    return 0


def cmd_check(args):
    files, problems = privacy.check_dir(Path(args.out))
    for f, why in problems:
        print(f"FAIL {f}: {why}")
    print(f"{len(files)} file(s) checked, {len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_compare(args):
    from . import compare
    return compare.main(Path(args.out), Path(args.baseline))


def cmd_warehouse(args):
    from . import warehouse
    return warehouse.main(args)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nsprobe", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("layout", help="pseudonymise raw per-site exports")
    p.add_argument("--src", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--key", required=True, help="site-name key file (keep private)")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=layout.main)

    p = sub.add_parser("run", help="run the raw-document probes")
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--contributor", default="external")
    p.add_argument("--probe", action="append", help="run only this probe id")
    p.add_argument("--max-docs", type=int, default=None, help="per-source cap (smoke)")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("census", help="run the nsschema census/reconcile/quirks")
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-docs", type=int, default=None)
    p.set_defaults(fn=cmd_census)

    p = sub.add_parser("warehouse", help="run probes over a flattened SQL warehouse")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--contributor", default="external")
    p.set_defaults(fn=cmd_warehouse)

    p = sub.add_parser("check", help="privacy-check a result directory")
    p.add_argument("out")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("compare", help="compare results with this repo's baseline")
    p.add_argument("out")
    p.add_argument("--baseline", default=str(REPO / "reports/nsprobe/baseline"))
    p.set_defaults(fn=cmd_compare)

    args = ap.parse_args(argv)
    return args.fn(args)
