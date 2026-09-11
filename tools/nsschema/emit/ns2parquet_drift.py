"""ns2parquet_drift.py — does the analysis pipeline still match the wire?

``tools/ns2parquet/`` reads raw Nightscout documents and writes a
flattened, unit-normalized Parquet projection. Its field list and its type
assumptions are hand-written, which makes it the fifth independent
declaration of the document model and the one furthest from review.

This check does not regenerate it — the normalization is deliberate,
semantic work (durations to minutes, controller detection, SMB inference)
that a schema cannot express. It checks two things a schema *can* answer:

``never_mentioned``
    Fields the corpus shows are core or universal whose name does not
    appear anywhere in the pipeline source. The claim is deliberately at
    name level: normalize.py addresses documents through ``.get()``,
    subscripts, and varargs helpers such as
    ``_parse_ts(doc, "date", "dateString", "sysTime")``, so anything
    narrower produces false positives — an earlier, stricter version of
    this check reported fields as dropped that are read on the next line.
    A field whose name appears nowhere cannot be read; a field whose name
    appears might only be mentioned in a comment, so this under-reports
    rather than over-reports.
``type_risk``
    Fields the pipeline reads whose live type contradicts how it reads
    them — a fractional value read through an integer coercion, or a field
    that is null in most documents.
"""

import ast
import json
from pathlib import Path

from .. import corpus, specload

PIPELINE_FILES = ("normalize.py", "grid.py", "odc_loader.py")

# Tiers whose absence from the pipeline is worth reporting.
SIGNIFICANT = {"universal", "core"}

# Reads that coerce to a whole number; a fractional live value loses data.
INT_COERCIONS = {"_safe_int", "int"}


def read_keys(path: Path):
    """Every string literal in the module, tagged with how it is used.

    Mention is the unit of evidence, not the specific access form.
    """
    tree = ast.parse(path.read_text())
    keys = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            keys.setdefault(node.value, set()).add("mentioned")

    class Coercions(ast.NodeVisitor):
        def visit_Call(self, node):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in INT_COERCIONS:
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                        keys.setdefault(inner.value, set()).add("int-coerced")
            self.generic_visit(node)

    Coercions().visit(tree)
    return keys


def check(repo_root: Path, model_dir="specs/nsschema"):
    pipeline_dir = repo_root / "tools" / "ns2parquet"
    keys = {}
    for filename in PIPELINE_FILES:
        path = pipeline_dir / filename
        if path.is_file():
            for key, how in read_keys(path).items():
                keys.setdefault(key, set()).update(how)

    report = {
        "generated_by": "tools/nsschema/emit/ns2parquet_drift.py",
        "pipeline_files": list(PIPELINE_FILES),
        "distinct_keys_read": len(keys),
        "collections": {},
    }

    for collection in specload.ROOT_SCHEMA:
        model = json.loads((repo_root / model_dir / f"{collection}.model.json").read_text())
        children = {k: v for k, v in model["root"].get("children", {}).items()
                    if k not in ("[]", "{}")}
        never_mentioned, type_risk = [], []
        for name, node in sorted(children.items()):
            evidence = node.get("evidence")
            if not evidence:
                continue
            if name not in keys:
                if node.get("tier") in SIGNIFICANT:
                    never_mentioned.append({
                        "field": name,
                        "tier": node["tier"],
                        "doc_frequency": evidence["doc_frequency"],
                        "site_count": evidence["site_count"],
                    })
                continue
            how = keys[name]
            observed = evidence["observed_types"]
            if "int-coerced" in how and observed.get("number"):
                type_risk.append({
                    "field": name, "risk": "int-coerced",
                    "detail": f"{observed['number']:,} fractional values observed; "
                              "reading it as an integer loses precision",
                })
            if node.get("nullable"):
                type_risk.append({
                    "field": name, "risk": "nullable",
                    "detail": f"{observed.get('null', 0):,} null values observed "
                              f"({observed.get('null', 0) / max(evidence['docs_present'], 1):.0%} "
                              "of documents carrying the field)",
                })
        report["collections"][collection] = {
            "fields_observed": len([n for n in children.values() if n.get("evidence")]),
            "never_mentioned_significant_fields": never_mentioned,
            "type_risk": type_risk,
        }
    return report


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="reports/schema-census/ns2parquet-drift.json", type=Path)
    args = ap.parse_args(argv)
    root = corpus.repo_root()
    report = check(root)
    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=1) + "\n")
    for collection, info in report["collections"].items():
        print(f"{collection}: {len(info['never_mentioned_significant_fields'])} significant fields never mentioned, "
              f"{len(info['type_risk'])} type risks")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
