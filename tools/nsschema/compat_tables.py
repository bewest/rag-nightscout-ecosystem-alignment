"""Generate the tables in docs/30-design/platform/spec/compatibility.md (SPEC-COMPAT-APPS).

The overview sits between `<!-- BEGIN GENERATED: compat-overview -->` and its END marker, and
each layer's table between `<!-- BEGIN GENERATED: compat-L<n> -->` and its END marker. They are
written from specs/sync/compat/*.yaml. `--check` fails when a table differs.
"""
import argparse
import os
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(os.environ.get("NSSCHEMA_ROOT", pathlib.Path(__file__).resolve().parents[2]))
DATA = ROOT / "specs" / "sync" / "compat"
PAGE = ROOT / "docs" / "30-design" / "platform" / "spec" / "compatibility.md"
GROUPS = ("ios", "android", "uploaders", "readers")
LAYERS = ("L0", "L1", "L2", "L3", "L4", "L5")
KIND_ORDER = ("controller", "uploader", "follower", "reader", "hub", "tool")


def load():
    entries = []
    for group in GROUPS:
        path = DATA / ("%s.yaml" % group)
        for e in yaml.safe_load(path.read_text()) or []:
            entries.append(dict(e, group=group))
    return sorted(entries, key=lambda e: (KIND_ORDER.index(e["kind"]), e["app"].lower()))


def cell(text):
    return " ".join(str(text).split()).replace("|", "\\|")


def tables(entries):
    out = {}
    rows = ["| app | kind | read at | " + " | ".join(LAYERS) + " |",
            "|---|---|---|" + "---|" * len(LAYERS)]
    for e in entries:
        rows.append("| %s | %s | %s | %s |" % (
            cell(e["app"]), e["kind"], cell(e["ref"]),
            " | ".join(e["layers"][layer]["verdict"] for layer in LAYERS)))
    out["overview"] = "\n".join(rows)
    for layer in LAYERS:
        rows = ["| app | today | with a hub that implements the specifications | verdict | rules |",
                "|---|---|---|---|---|"]
        for e in entries:
            c = e["layers"][layer]
            rows.append("| %s | %s | %s | %s | %s |" % (
                cell(e["app"]), cell(c["today"]), cell(c["newer"]), c["verdict"],
                ", ".join(c.get("rules") or []) or "—"))
        out[layer] = "\n".join(rows)
    return out


def render(page, entries):
    for name, table in tables(entries).items():
        pattern = re.compile(r"(<!-- BEGIN GENERATED: compat-%s -->\n).*?(<!-- END GENERATED: compat-%s -->)"
                             % (name, name), re.S)
        if not pattern.search(page):
            raise SystemExit("%s: no generated block compat-%s" % (PAGE, name))
        page = pattern.sub(lambda m: m.group(1) + table + "\n" + m.group(2), page)
    return page


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    page = PAGE.read_text()
    new = render(page, load())
    if args.check:
        if new != page:
            print("%s: the generated tables are stale; run python3 -m tools.nsschema.compat_tables" % PAGE)
            sys.exit(1)
        return
    PAGE.write_text(new)
    print("wrote %s" % PAGE)


if __name__ == "__main__":
    main()
