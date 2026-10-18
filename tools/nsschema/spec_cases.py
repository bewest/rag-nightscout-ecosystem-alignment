"""Generate the tables inside a platform specification.

A layer specification under docs/30-design/platform/spec/ carries generated
blocks between markers named <layer>-<block>:

    <!-- BEGIN GENERATED: registration-cases (tools/nsschema/spec_cases.py) -->
    <!-- END GENERATED: registration-cases -->

`cases` rows come from the case files themselves (title, control, expected
status, outcome and reason codes); `kinds` rows come from the well-known
registrations in specs/sync/registrations/; `primitives` and `proposed` rows
come from the observation catalogue, specs/sync/primitives.yaml. None can drift
from its source.

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

REGISTRATIONS = ROOT / "specs" / "sync" / "registrations"
PRIMITIVES = ROOT / "specs" / "sync" / "primitives.yaml"

# Which cases each specification's table covers: whole directories, or a list.
LAYERS = {
    "records": {"primitives": PRIMITIVES, "proposed": PRIMITIVES},
    "sync-transport": {"cases": [("sync-transport/", CASES / "sync-transport")]},
    "authority": {"cases": [
        "pattern:owner-*", "pattern:blocked-*", "pattern:released-*", "pattern:retire-*",
        "pattern:update-*", "pattern:accepted-api-secret-single", "pattern:not-authorised",
        "pattern:accepted-first-to-claim", "pattern:rejected-namespace-*",
        "pattern:namespace-claimed-after-free",
        "pattern:instances/*not-registration-owner*", "pattern:instances/owner-*",
        "pattern:instances/rebind-*", "pattern:instances/listing-shows-*",
        "pattern:instances/instance-create-other-subject",
        "pattern:instances/instance-renew-transferred-command-sink",
        "pattern:instances/command-after-rebind-*",
        "pattern:instances/command-not-routed-to-other-subject-simulator",
    ]},
    "registration": {"cases": [("", CASES), ("instances/", CASES / "instances"), ("quirks/", CASES / "quirks")]},
    "state-intent": {
        "kinds": ["loop", "trio", "androidaps"],
        "cases": [
            "instances/definition-version-conflict",
            "instances/definition-same-meaning",
            "instances/product-update-version-conflict",
            "instances/product-update-new-version",
            "instances/definition-wellknown-ref",
            "instances/definition-wellknown-copy-conflicts",
            "instances/instance-not-a-command-channel",
            "quirks/same-as-definition-accepted",
            "quirks/same-as-without-slot",
            "quirks/names-alike-do-not-contend",
            "quirks/equal-names-unlisted-do-not-contend",
            "quirks/catalogue-mapping-applied",
            "quirks/catalogue-mapping-version-outside",
            "quirks/catalogue-mapping-version-unknown",
            "quirks/same-as-typed-write-declared",
            ("active-state/", CASES / "active-state"),
        ],
    },
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


def case_paths(spec):
    for item in spec:
        if isinstance(item, str) and item.startswith("pattern:"):
            prefix, _, glob = item[len("pattern:"):].rpartition("/")
            folder = CASES / prefix if prefix else CASES
            for path in sorted(folder.glob(glob + ".yaml")):
                yield (prefix + "/" if prefix else ""), path
            continue
        if isinstance(item, tuple):
            prefix, folder = item
            for path in sorted(folder.glob("*.yaml")):
                yield prefix, path
        else:
            prefix, _, _ = item.rpartition("/")
            yield (prefix + "/" if prefix else ""), CASES / ("%s.yaml" % item)


def term(value):
    if isinstance(value, dict) and "value" in value:
        return "%s: %s" % (value["value"], value.get("controllerTerm", ""))
    return "" if value is None else str(value)


def declared(span, member):
    """null in the grammar means "not published"; absent means not declared."""
    if member not in span:
        return "undeclared"
    return "yes" if span[member] else "not published"


def kind_rows(controllers):
    out = ["| controller | kind | category | slot | coexists with | ended on the wire | requested | applied | initiators | accepts from hub |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for name in controllers:
        reg = yaml.safe_load((REGISTRATIONS / ("%s.yaml" % name)).read_text())
        product = reg["metadata"].get("product", name)
        for span in reg["spec"].get("stateSpans", []):
            wire = span.get("wire") or {}
            where = "`%s`" % wire["eventType"] if wire.get("eventType") else wire.get("collection")
            parts = [p for p in (where, term(wire.get("endedEncoding"))) if p]
            ended = ", ".join(parts) if wire else "not published"
            accepts = (span.get("acceptsFromHub") or {}).get("channels")
            out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                cell(product),
                cell((span.get("kind") or "—") + (" (%s)" % term(span["availability"]) if span.get("availability") else "")), cell(span.get("category", "")),
                cell(term(span.get("slot"))), cell(", ".join(span.get("coexistsWith") or []) or "—"),
                cell(ended), declared(span, "requested"), declared(span, "applied"),
                cell((span.get("initiators") or {}).get("vocabulary") or "—"),
                cell(", ".join(accepts) if accepts else "—")))
    return out


def primitive_rows(catalogue):
    out = ["| primitive | group | typed by | fields | measured | declared | what it is |",
           "|---|---|---|---:|---:|---:|---|"]
    for name, spec in yaml.safe_load(catalogue.read_text())["primitives"].items():
        grades = [f.get("evidence") for f in spec.get("fields", [])]
        out.append("| `%s` | %s | %s | %d | %d | %d | %s |" % (
            name, cell(spec.get("group", "")), cell(spec.get("typed_by", "")), len(grades),
            grades.count("measured"), grades.count("declared"), cell(spec.get("description", ""))))
    return out


def proposed_rows(catalogue):
    out = ["| field | input of | recorded today |", "|---|---|---|"]
    for item in yaml.safe_load(catalogue.read_text()).get("proposed_not_carried_by_any_primitive", []):
        out.append("| `%s` | %s | %s |" % (
            item["field"], cell(item.get("algorithm", "")), cell(item.get("status_today", ""))))
    return out


def rows(layer, block="cases"):
    if block == "kinds":
        return kind_rows(LAYERS[layer]["kinds"])
    if block == "primitives":
        return primitive_rows(LAYERS[layer][block])
    if block == "proposed":
        return proposed_rows(LAYERS[layer][block])
    out = ["| case | shows | expected | control |", "|---|---|---|---|"]
    for prefix, path in case_paths(LAYERS[layer]["cases"]):
        case = yaml.safe_load(path.read_text())
        response = (case.get("expected") or {}).get("response") or {}
        expected = " ".join(str(v) for v in (response.get("status"), response.get("outcome")) if v)
        reasons = sorted(codes(response, set()))
        if reasons:
            expected += "; " + ", ".join(reasons)
        if not expected and case.get("rules"):
            expected = "rules " + ", ".join(case["rules"])
        control = case.get("control")
        out.append("| `%s%s` | %s | %s | %s |" % (
            prefix, path.stem, cell(case.get("title", "")), cell(expected),
            "`%s`" % control if control else ""))
    return out


def render(layer, text):
    for block in LAYERS[layer]:
        begin = "<!-- BEGIN GENERATED: %s-%s (tools/nsschema/spec_cases.py) -->" % (layer, block)
        end = "<!-- END GENERATED: %s-%s -->" % (layer, block)
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
        if not pattern.search(text):
            raise SystemExit("no %s-%s markers in the specification" % (layer, block))
        text = pattern.sub(lambda _: "\n".join([begin] + rows(layer, block) + [end]), text)
    return text


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
