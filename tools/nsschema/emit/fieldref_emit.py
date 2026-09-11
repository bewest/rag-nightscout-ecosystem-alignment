"""fieldref_emit.py — a human-readable field reference from the model.

The audience is a contributor deciding what to write into a Nightscout
document, or a reviewer deciding whether a proposed schema change is safe.
Both need the same three facts about every field: what type it holds, how
much of the ecosystem actually uses it, and **which projects handle it** —
none of which was written down in one place.

Each row carries the evidence rather than an assertion, so a reader can
disagree with the tiering without re-deriving the measurement. Attribution
comes from ``reports/schema-census/attribution.json`` (source-code evidence,
not document provenance) and quirks from
``reports/schema-census/quirks.json``.
"""

import json

TIER_NOTE = {
    "universal": "every site, effectively every document",
    "core": "most sites, substantial share of documents",
    "common": "at least three independent sites",
    "vendor": "one or two sites, but written consistently there",
    "sparse": "one or two sites, inconsistently",
    "rare": "fewer than ten documents in the whole corpus",
}
ORDER = ("universal", "core", "common", "vendor", "sparse", "rare")


def _children(node):
    return {k: v for k, v in node.get("children", {}).items() if k not in ("[]", "{}")}


def _flatten(node, prefix=""):
    out = []
    for name, child in sorted(node.get("children", {}).items()):
        if name == "[]":
            path = f"{prefix}[]"
        elif name == "{}":
            path = f"{prefix}.{{}}"
        else:
            path = f"{prefix}.{name}" if prefix else name
        out.append((path, child))
        out.extend(_flatten(child, path))
    return out


def _types(node):
    types = list(node["types"])
    if node.get("nullable"):
        types.append("null")
    return ", ".join(f"`{t}`" for t in types) or "—"


def _attribution_index(attribution):
    """Leaf field name -> the projects with strong source evidence."""
    if not attribution:
        return {}
    return {f["name"]: f for f in attribution.get("fields", [])}


def _projects_for(path, index):
    entry = index.get(path.split(".")[-1].rstrip("[]"))
    if not entry or entry.get("low_confidence"):
        return ""
    projects = entry.get("attributed_to") or []
    if not projects:
        return ""
    shown = projects[:4]
    more = f" +{len(projects) - 4}" if len(projects) > 4 else ""
    return ", ".join(shown) + more


def emit(model, census_meta, attribution=None, quirks=None):
    collection = model["collection"]
    index = _attribution_index(attribution)
    rows_by_tier = {tier: [] for tier in ORDER}
    undeclared_only = []

    for path, node in _flatten(model["root"]):
        evidence = node.get("evidence")
        tier = node.get("tier")
        if not evidence:
            if node.get("declared"):
                undeclared_only.append((path, node))
            continue
        sites = evidence["site_count"]
        freq = evidence["doc_frequency"]
        marks = []
        if not node.get("declared"):
            marks.append("**not in spec**")
        if node.get("required_read"):
            marks.append("always returned")
        if node.get("nullable"):
            marks.append("nullable")
        rows_by_tier.setdefault(tier, []).append(
            f"| `{path}` | {_types(node)} | {freq:.1%} | {sites} | "
            f"{_projects_for(path, index)} | {node.get('sensitivity', '?')} | "
            f"{' · '.join(marks)} |"
        )

    lines = [
        f"# `{collection}` field reference",
        "",
        "<!-- GENERATED FILE — do not edit. Regenerate with: make schema-emit -->",
        "",
        f"Source spec: `specs/openapi/{model['source_spec']}`  ",
        f"Evidence: `{model['census']}`  ",
        f"Corpus: {census_meta['documents']:,} documents from "
        f"{len(census_meta['sites'])} Nightscout sites across "
        f"{len(census_meta['snapshots'])} snapshots "
        f"({', '.join(census_meta['snapshots'])}).",
        "",
        "**Documents** is the share of corpus documents carrying the field; ",
        "**sites** is how many independent Nightscout instances were seen to write it. ",
        "The second number matters more: one busy site can make a single client's ",
        "private field look common.",
        "",
        "**Sensitivity** is the derived label (`secret`, `identifying`, ",
        "`quasi-identifying`, `descriptive`) that projections strip by; see ",
        "`specs/sync/sensitivity.yaml`. It is derived from the redaction policy and ",
        "the census, not asserted, and an unlabelled field defaults to `identifying`.",
        "",
        "**Handled by** lists projects whose source code serializes the field, from ",
        "`reports/schema-census/attribution.json`. It is source evidence, not document ",
        "provenance: a project that *reads* a field looks identical to one that ",
        "*writes* it, and names too generic to attribute are left blank.",
        "",
        "> This corpus is Loop-dominant (see the census `site_documents`). A field ",
        "> marked universal here is universal *in this corpus*, which is not the same ",
        "> as universal across the ecosystem.",
        "",
    ]

    for tier in ORDER:
        rows = rows_by_tier.get(tier) or []
        if not rows:
            continue
        lines += [
            f"## {tier.title()} — {TIER_NOTE[tier]}",
            "",
            "| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |",
            "|---|---|---|---|---|---|---|",
            *rows,
            "",
        ]

    collection_quirks = [q for q in (quirks or []) if q["collection"] == collection]
    if collection_quirks:
        lines += [
            "## Known quirks",
            "",
            "Deviations from the schema that enough of the ecosystem exhibits that "
            "a reader has to handle them. Prevalence is measured, not asserted; see "
            "`specs/quirks/` for guidance on each.",
            "",
            "| Quirk | Kind | Documents | Sites | Title |",
            "|---|---|---|---|---|",
        ]
        for quirk in sorted(collection_quirks, key=lambda q: -q["share"]):
            lines.append(
                f"| `{quirk['id']}` | {quirk['kind']} | {quirk['share']:.1%} | "
                f"{quirk['sites']} | {quirk['title']} |"
            )
        lines.append("")

    if undeclared_only:
        lines += [
            "## Declared in the spec, never observed",
            "",
            "Either the corpus lacks a client that writes them, or the spec "
            "documents something that does not exist. API v3 metadata is expected "
            "here: the corpus was collected through `/api/v1/`.",
            "",
            "| Field | Type |",
            "|---|---|",
            *[f"| `{p}` | {_types(n)} |" for p, n in undeclared_only],
            "",
        ]

    return "\n".join(lines) + "\n"


def _read_optional(path):
    return json.loads(path.read_text()) if path.is_file() else None


def main(argv=None):
    import argparse
    from pathlib import Path
    from .. import corpus, specload

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-dir", default="specs/nsschema", type=Path)
    ap.add_argument("--census-dir", default="reports/schema-census", type=Path)
    ap.add_argument("--out", default="docs/10-domain/field-reference", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    attribution = _read_optional(root / args.census_dir / "attribution.json")
    quirk_report = _read_optional(root / args.census_dir / "quirks.json")
    quirks = (quirk_report or {}).get("results", [])
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    for collection in (args.collections or list(specload.ROOT_SCHEMA)):
        model = json.loads((root / args.model_dir / f"{collection}.model.json").read_text())
        census = json.loads((root / args.census_dir / f"{collection}.census.json").read_text())
        dest = out_dir / f"{collection}.md"
        dest.write_text(emit(model, census, attribution, quirks))
        print(f"{collection}: -> {dest.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
