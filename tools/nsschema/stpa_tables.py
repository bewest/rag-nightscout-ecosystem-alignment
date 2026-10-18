"""Generate the entry tables in docs/30-design/platform/spec/control-loops.md (SPEC-STPA-PLATFORM).

Each loop's table sits between `<!-- BEGIN GENERATED: stpa-<loop> -->` and
`<!-- END GENERATED: stpa-<loop> -->` and is written from
specs/sync/stpa/platform-control-loops.yaml. `--check` fails when a table differs.
"""
import argparse
import os
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(os.environ.get("NSSCHEMA_ROOT", pathlib.Path(__file__).resolve().parents[2]))
DATA = ROOT / "specs" / "sync" / "stpa" / "platform-control-loops.yaml"
PAGE = ROOT / "docs" / "30-design" / "platform" / "spec" / "control-loops.md"


def tables(stpa):
    owner = {}
    for name, loop in stpa["loops"].items():
        for aid in list(loop.get("actions", {})) + list(loop.get("feedback", {})):
            owner[aid] = name
    out = {}
    for name in stpa["loops"]:
        rows = ["| id | type | unsafe control action or feedback | hazards | severity | prevented by | status |",
                "|---|---|---|---|---|---|---|"]
        for u in stpa["ucas"]:
            if owner[u["action"]] != name:
                continue
            status = u["status"] + (": " + u["open"] if u.get("open") else "")
            rows.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                u["id"], u["type"], u["text"], ", ".join(u["hazards"]), u["severity"],
                ", ".join(u["constraints"]), status))
        out[name] = "\n".join(rows)
    return out


def render(page, stpa):
    for name, table in tables(stpa).items():
        pattern = re.compile(r"(<!-- BEGIN GENERATED: stpa-%s -->\n).*?(<!-- END GENERATED: stpa-%s -->)"
                             % (name, name), re.S)
        if not pattern.search(page):
            raise SystemExit("%s: no generated block for loop %s" % (PAGE, name))
        page = pattern.sub(lambda m: m.group(1) + table + "\n" + m.group(2), page)
    return page


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    stpa = yaml.safe_load(DATA.read_text())
    page = PAGE.read_text()
    new = render(page, stpa)
    if args.check:
        if new != page:
            print("%s: the generated tables are stale; run python3 -m tools.nsschema.stpa_tables" % PAGE)
            sys.exit(1)
        return
    PAGE.write_text(new)
    print("wrote %s" % PAGE)


if __name__ == "__main__":
    main()
