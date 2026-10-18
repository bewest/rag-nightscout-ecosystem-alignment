"""Generate the conformance-case table inside a platform specification.

A layer specification under docs/30-design/platform/spec/ lists the cases that
check it between two markers:

    <!-- BEGIN GENERATED: registration-cases (tools/nsschema/spec_cases.py) -->
    <!-- END GENERATED: registration-cases -->

The rows come from the case files themselves (title, control, expected status,
outcome and reason codes), so the table cannot drift from the cases.

    python3 -m tools.nsschema.spec_cases registration           # rewrite
    python3 -m tools.nsschema.spec_cases registration --check   # exit 1 if stale
"""

import argparse
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ROOT / "specs" / "sync" / "conformance"
SPEC = ROOT / "docs" / "30-design" / "platform" / "spec"

# Which case directories each specification's table covers.
LAYERS = {
    "registration": [("", CASES), ("instances/", CASES / "instances"), ("quirks/", CASES / "quirks")],
}


def codes(node, found):
    """Collect reason codes anywhere under a response."""
    if isinstance(node, dict):
        if isinstance(node.get("code"), str):
            found.add(node["code"])
        for value in node.values():
            codes(value, found)
    elif isinstance(node, list):
        for value in node:
            codes(value, found)
    return found


def cell(text):
    return " ".join(str(text).split()).replace("|", "\\|")


def rows(layer):
    out = ["| case | shows | expected | control |", "|---|---|---|---|"]
    for prefix, folder in LAYERS[layer]:
        for path in sorted(folder.glob("*.yaml")):
            case = yaml.safe_load(path.read_text())
            response = (case.get("expected") or {}).get("response") or {}
            expected = " ".join(str(v) for v in (response.get("status"), response.get("outcome")) if v)
            reasons = sorted(codes(response, set()))
            if reasons:
                expected += "; " + ", ".join(reasons)
            control = case.get("control")
            out.append("| `%s%s` | %s | %s | %s |" % (
                prefix, path.stem, cell(case.get("title", "")), cell(expected),
                "`%s`" % control if control else ""))
    return out


def render(layer, text):
    begin = "<!-- BEGIN GENERATED: %s-cases (tools/nsschema/spec_cases.py) -->" % layer
    end = "<!-- END GENERATED: %s-cases -->" % layer
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise SystemExit("no %s-cases markers in the specification" % layer)
    return pattern.sub(lambda _: "\n".join([begin] + rows(layer) + [end]), text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("layer", choices=sorted(LAYERS))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--spec", type=pathlib.Path,
                        help="check or write this file instead (the negative control uses a broken copy)")
    args = parser.parse_args(argv)
    spec = (args.spec or SPEC / ("%s.md" % args.layer)).resolve()
    text = spec.read_text()
    new = render(args.layer, text)
    if args.check:
        if new != text:
            print("%s: the generated case table is stale; run python3 -m tools.nsschema.spec_cases %s"
                  % (spec, args.layer))
            return 1
        print("%s: case table current" % spec)
        return 0
    spec.write_text(new)
    print("wrote %s" % spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
