"""Generate the examples in the developer guides (SPEC-DEV-GUIDES).

A guide under docs/30-design/platform/guides/ shows requests, replies and documents copied from the
conformance cases, never typed by hand. Each example sits between markers naming the case, relative
to specs/sync/conformance/ (or a repository path starting `specs/`), and a dotted path into it:

    <!-- BEGIN GENERATED: guide-example instances/instance-create.yaml request.body -->
    <!-- END GENERATED: guide-example -->

A numeric part indexes a list (`steps.0.reply`); an empty path takes the whole file. The block is
written as YAML. `--check` fails when an example differs from its case.

    python3 -m tools.nsschema.guide_examples           # rewrite
    python3 -m tools.nsschema.guide_examples --check   # exit 1 if stale
"""
import argparse
import os
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(os.environ.get("NSSCHEMA_ROOT", pathlib.Path(__file__).resolve().parents[2]))
CASES = ROOT / "specs" / "sync" / "conformance"
GUIDES = ROOT / "docs" / "30-design" / "platform" / "guides"
BLOCK = re.compile(r"(<!-- BEGIN GENERATED: guide-example (\S+)(?: (\S+))? -->\n).*?"
                   r"(<!-- END GENERATED: guide-example -->)", re.S)


def case_path(ref):
    return ROOT / ref if ref.startswith("specs/") else CASES / ref


def extract(ref, pointer):
    path = case_path(ref)
    if not path.exists():
        raise SystemExit("guide example: no such case %s" % ref)
    node = yaml.safe_load(path.read_text())
    for part in (pointer or "").split(".") if pointer else []:
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise SystemExit("guide example: %s has no %s" % (ref, pointer))
    return node


def render(page):
    def block(m):
        body = yaml.safe_dump(extract(m.group(2), m.group(3)), sort_keys=False,
                              allow_unicode=True, width=100)
        return "%s```yaml\n%s```\n%s" % (m.group(1), body, m.group(4))
    return BLOCK.sub(block, page)


def pages():
    return sorted(GUIDES.glob("*.md"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    stale = []
    for path in pages():
        page = path.read_text()
        new = render(page)
        if new == page:
            continue
        if args.check:
            stale.append(path)
        else:
            path.write_text(new)
            print("wrote %s" % path)
    for path in stale:
        print("%s: an example differs from its case; run python3 -m tools.nsschema.guide_examples" % path)
    sys.exit(1 if stale else 0)


if __name__ == "__main__":
    main()
