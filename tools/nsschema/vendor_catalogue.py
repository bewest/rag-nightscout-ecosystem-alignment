#!/usr/bin/env python3
"""Vendor the well-known catalogue into cgm-remote-monitor as JSON.

Reads, from the alignment repository:
  specs/sync/registrations/{androidaps,loop,trio}.yaml  (not fixtures/)
  specs/sync/shared-slots.yaml
  specs/quirks/*.yaml          (entries with applies_to: declarations -> mappings)
  specs/sync/hub-capabilities.schema.json

Writes, into <crm>/lib/registration/catalogue/:
  <id>.json             one well-known registration, `document` is the YAML as JSON
  shared-slots.json     the shared slot list
  mappings.json         catalogue mappings (registration spec section 16, rule Q2)
and into <crm>/lib/registration/schemas/:
  hub-capabilities.schema.json, controller-state-model.schema.json (the grammar),
  controller-settings.schema.json (typeRef targets), controller-instance.schema.json,
  controller-state-model-strict.schema.json (the grammar closed, for rule G1)

Every file records where it came from: the source path and the last alignment
commit that touched it (`git log -1 -- <path>`), so regenerating at a later
alignment commit with unchanged sources gives identical bytes.

  python3 -I vendor_catalogue.py --alignment <repo> --crm <worktree>          # write
  python3 -I vendor_catalogue.py --alignment <repo> --crm <worktree> --check  # compare, exit 1 on any difference

The alignment repository is never needed at runtime (D12): crm reads only the
vendored JSON.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

import yaml

REPOSITORY = "bewest/rag-nightscout-ecosystem-alignment"
GENERATOR = "tools/nsschema/vendor_catalogue.py"
OUT = "lib/registration/catalogue"


class _Loader(yaml.SafeLoader):
    """SafeLoader that leaves timestamps as strings, so the JSON matches the text."""


_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _git(repo, *args):
    return subprocess.check_output(["git", "-C", repo] + list(args), text=True).strip()


def _source(repo, rel):
    commit = _git(repo, "log", "-1", "--format=%H", "--", rel)
    if not commit:
        sys.exit("not committed in the alignment repository: " + rel)
    dirty = _git(repo, "status", "--porcelain", "--", rel)
    if dirty:
        sys.exit("uncommitted changes in the alignment repository: " + rel)
    return {"repository": REPOSITORY, "path": rel, "commit": commit, "generator": GENERATOR}


def _load_yaml(repo, rel):
    with open(os.path.join(repo, rel), encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def _comment(rel):
    return ("Generated from the alignment repository's " + rel + " by " + GENERATOR
            + ". Do not edit; regenerate.")


def _dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def generate(repo):
    files = {}
    regs = sorted(glob.glob(os.path.join(repo, "specs/sync/registrations/*.yaml")))
    if not regs:
        sys.exit("no registrations under specs/sync/registrations/")
    for path in regs:
        rel = os.path.relpath(path, repo)
        rid = os.path.splitext(os.path.basename(path))[0]
        doc = _load_yaml(repo, rel)
        if doc.get("metadata", {}).get("tier") != "well-known":
            sys.exit(rel + " is not a well-known registration")
        files[rid + ".json"] = {"$comment": _comment(rel), "vendoredFrom": _source(repo, rel),
                                "id": rid, "document": doc}

    rel = "specs/sync/shared-slots.yaml"
    slots = _load_yaml(repo, rel)["slots"]
    files["shared-slots.json"] = {"$comment": _comment(rel), "vendoredFrom": _source(repo, rel),
                                  "slots": slots}

    mappings, sources = [], []
    for path in sorted(glob.glob(os.path.join(repo, "specs/quirks/*.yaml"))):
        rel = os.path.relpath(path, repo)
        sources.append(_source(repo, rel))
        for entry in (_load_yaml(repo, rel) or {}).get("quirks", []):
            if entry.get("applies_to") != "declarations":
                continue
            decl = entry["declaration"]
            if decl.get("member") != "slot" or "sameAs" not in decl:
                continue
            for aff in entry["affects"]:
                rng = aff["versions"].get("range")
                if rng is None:  # unmeasured: no range, so the hub applies no mapping
                    continue
                mappings.append({"quirk": entry["id"], "vendor": aff["vendor"],
                                 "product": aff["product"], "versions": rng,
                                 "slot": decl["value"], "sameAs": decl["sameAs"]})
    files["mappings.json"] = {"$comment": "Catalogue mappings (registration section 16, Q2) from the "
                              "alignment repository's specs/quirks/*.yaml entries with "
                              "applies_to: declarations, by " + GENERATOR + ". Do not edit; regenerate.",
                              "vendoredFrom": sources, "mappings": mappings}

    for name in SCHEMAS:
        rel = "specs/sync/" + name
        with open(os.path.join(repo, rel), encoding="utf-8") as fh:
            schema = json.load(fh)
        files["../schemas/" + name] = _with_comment(schema, rel, _source(repo, rel))

    # The grammar with every object closed (tools/nsschema/sync_model.py
    # strict_schema): the view a v1 reader uses to find members it does not
    # know (registration rule G1). Generated here so the hub keeps no copy of
    # the closing rule.
    rel = "specs/sync/controller-state-model.schema.json"
    sys.path.insert(0, repo)
    from tools.nsschema import sync_model
    with open(os.path.join(repo, rel), encoding="utf-8") as fh:
        strict = sync_model.strict_schema(json.load(fh))
    strict["$id"] = strict["$id"].replace(".json", "-strict.json")
    src = _source(repo, rel)
    src["transform"] = "tools/nsschema/sync_model.py strict_schema"
    files["../schemas/controller-state-model-strict.schema.json"] = _with_comment(strict, rel, src)
    return {name: _dump(obj) for name, obj in files.items()}


SCHEMAS = ["hub-capabilities.schema.json", "controller-state-model.schema.json",
           "controller-settings.schema.json", "controller-instance.schema.json"]


def _with_comment(schema, rel, src):
    head = [("$comment", _comment(rel) + " Source commit " + src["commit"] + "."
             + (" Transformed by " + src["transform"] + "." if "transform" in src else ""))]
    return dict(head + [(k, v) for k, v in schema.items() if k != "$comment"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--alignment", required=True)
    ap.add_argument("--crm", required=True)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = os.path.join(args.crm, OUT)
    files = generate(args.alignment)
    if args.check:
        bad = []
        present = {os.path.relpath(p, out) for p in glob.glob(os.path.join(out, "*.json"))
                   + glob.glob(os.path.join(out, "../schemas/*.json"))}
        present = {("../schemas/" + os.path.basename(p)) if p.startswith("..") else p for p in present}
        for name, text in sorted(files.items()):
            path = os.path.join(out, name)
            if not os.path.exists(path):
                bad.append("missing " + name)
                continue
            with open(path, encoding="utf-8") as fh:
                if fh.read() != text:
                    bad.append("differs " + name)
        for extra in sorted(present - set(files)):
            bad.append("not generated " + extra)
        for line in bad:
            print(line)
        print("vendored catalogue: " + ("DIFFERS" if bad else "matches") + " (" + str(len(files)) + " files)")
        sys.exit(1 if bad else 0)
    os.makedirs(out, exist_ok=True)
    os.makedirs(os.path.join(out, "../schemas"), exist_ok=True)
    for name, text in sorted(files.items()):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote " + os.path.join(OUT, name))


if __name__ == "__main__":
    main()
