# nsschema — evidence-driven schema tooling

Turns real Nightscout documents into evidence about what the document
model actually is, reconciles that against `specs/openapi/`, and generates
the typed artifacts the modernization work needs from a single source.

## Why

`docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md` §6.4
identifies the problem this package exists to solve: a field's type is
currently declared, or implied, in four places that drift — the OpenAPI
spec, any boundary validator, a mongoose `Schema`, and the Postgres column
type. The fix is one source of truth with generated consumers. Before
committing to a source of truth, though, the spec has to be *right*: §6.5
found a real bug class caused by a hand-maintained field list diverging
from the data.

So: measure first, commit second.

## Pipeline

```
externals/ns-data/patients/*/raw/*.json   real documents, 11 sites
externals/ns-resync-2026-04-26/raw/*/*.json
                 │
                 ▼  census.py
reports/schema-census/<collection>.census.json      what exists, with counts
                 │
                 ▼  tiers.py + diff.py    (against specs/openapi/aid-*.yaml)
reports/schema-census/<collection>.reconcile.json   spec vs. reality
```

## Commands

```bash
make schema-census      # walk the corpus (~4 min, ~2.5 GB of JSON)
make schema-reconcile   # compare the census against specs/openapi/
make schema-test        # unit tests
```

Smoke run without the full corpus pass:

```bash
PYTHONPATH=tools python3 -m nsschema.census --collection entries --max-docs 5000
```

## Privacy

The corpus is real health data from consenting sites. `redact.py` is the
single chokepoint every recorded value passes through, and the census
records field *names*, *types*, *counts* and *numeric ranges* — never a
value from an identifying or free-text field, never a value from a
high-cardinality field, and never an unmasked digit run, URL or email. The
tests in `test_nsschema.py` assert this directly. Sites appear only under
the single-letter pseudonyms the collection pass assigned.

## Reading a census record

```json
{
  "path": "date",
  "docs_present": 896589,
  "doc_frequency": 1.0,
  "site_count": 11,
  "site_frequency": {"a": 1.0, "b": 1.0, ...},
  "types": {"integer": 345332, "number": 551257}
}
```

`types` is a union, deliberately. `integer` and `number` are counted
separately because JSON Schema `type: integer` rejects `1.5`, and this
corpus contains fields where the majority of values are fractional.

`doc_frequency` is the fraction of *documents* carrying the path, and
`site_frequency` the same fraction computed per site — one busy site
cannot make a vendor field look universal. `tiers.py` turns those two
numbers into a recommendation about how much a schema should commit to
the field.
