"""nsprobe — aggregate-only probes a Nightscout data holder runs on their own data.

The alignment repository's schemas, quirks and parquet heuristics were
measured on a small corpus (11 sites, Loop-heavy, fetched through API v1).
nsprobe packages the questions that corpus cannot answer as probes another
data holder can run against a larger warehouse, returning only counts,
shares and site-counts in a fixed format this repository can merge.

Modules::

    layout.py     copy raw per-site exports into a pseudonymous corpus tree
    sources.py    read that tree: v1 arrays, v3 envelopes, NDJSON
    family.py     classify a document's writer (AAPS, Trio, oref0 rig, Loop...)
    privacy.py    suppression rules and the output validator
    probes.py     the raw-document probes, one per question
    warehouse.py  probes over a flattened SQL warehouse (column map in YAML)
    cli.py        nsprobe layout | run | census | warehouse | check | compare

The questions, and the claim in this repository each one tests, are in
``questions.yaml``. Instructions for a coding agent are in ``AGENTS.md``.
"""

FORMAT = "nsprobe-result/1"
