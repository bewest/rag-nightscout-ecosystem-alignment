# nsschema — evidence-driven schema tooling

Turns real Nightscout documents into evidence about what the document
model actually is, reconciles that against `specs/openapi/`, and generates
the typed artifacts the modernization work needs from a single source.

## Why

`docs/30-design/tenancy/nightscout-multitenancy-discussion-2026-09-09.md` §6.4
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

### The collections with no corpus

The server opens nine collections. Four of them (`entries`, `treatments`,
`devicestatus`, `profile`) are censused and specified, and their models come
out of the pipeline above. The other five have never been measured:

| collection | reached by | why there is no census |
|---|---|---|
| `food` | v1 + v3 | no snapshot ever fetched it |
| `activity` | v1 only (not in v3's `enabledCollections`) | likewise |
| `settings` | v3 only, `api:settings:admin` | see the warning below |
| `auth_roles` | admin API | the corpus is public REST reads |
| `auth_subjects` | admin API | likewise — and a census of it would be a census of bearer tokens |

> `reports/schema-census/settings.census.json` is **not** a census of the
> `settings` collection. `corpus.py` collects it from each snapshot's
> `settings.json`, which is a capture of the `GET /api/v1/status.json`
> response — its twelve top-level fields are the `info` object built in
> `lib/api/status.js`. That evidence is modelled as
> `specs/nsschema/status.model.json`. The `settings` collection itself is
> unmeasured, and nothing in cgm-remote-monitor writes a document to it.

`code_model.py` models those five by reading cgm-remote-monitor's source with
`jsread.py` — the record templates, the index lists, the default-role literal
— and marks everything it produces `provenance: "code"` with `measured:
false` and no `evidence` block anywhere. It also emits
`specs/nsschema/server-indexes.json`, every field the server builds a MongoDB
index on, which `model.py` reads so that an indexed field no spec declares
(`NSCLIENT_ID`, `date` on treatments and devicestatus, `created_at` on
entries) still gets a node.

**Read `provenance` before you trust a node.** `measured` means the census
counted it in real deployments; `declared` means an OpenAPI document names
it; `code` means it was read out of the server source and nobody has ever
measured it.

```
externals/work/crm-seam (or cgm-remote-monitor-official)
                 │
                 ▼  jsread.py + code_model.py
specs/nsschema/{food,activity,settings,auth_roles,auth_subjects}.model.json
specs/nsschema/server-indexes.json                  ─┐
                                                     ▼  model.py
                        the four evidence models, supplemented
```

## Commands

```bash
make schema-census      # walk the corpus (~4 min, ~2.5 GB of JSON)
make schema-reconcile   # compare the census against specs/openapi/
make schema-code-model  # models read from the server source
make schema-model       # merge spec + evidence (needs server-indexes.json)
make schema-code-drift  # fail if the server source no longer says what the
                        # code-derived models record
make schema-verify      # fail if an emitted artifact drifted from its model
make schema-test        # unit tests
```

`schema-code-model` and `schema-code-drift` need a cgm-remote-monitor
checkout. They look in `externals/work/crm-seam` then
`externals/cgm-remote-monitor-official`, and honour `NSSCHEMA_SERVER_SOURCE`
or `--source`. `--cross-check` requires every available checkout to declare
the same field set. Nothing else in the pipeline needs the source:
`server-indexes.json` is committed, so `make schema-model` reproduces the
same bytes with or without `externals/` present.

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

## Protecting files already in the repo

`redact.py` governs what the census emits. Two more tools govern what is
already committed:

```bash
make schema-scan-pii     # report personal data in captured-document files
make schema-sanitize     # mask it, shape-preserving and deterministic
```

`scan_pii.py` grades findings `credential` / `identity` / `quasi-identifier`
and prints **paths and counts, never values** — a report about a leak should
not be a second copy of it. `tools/nsschema/pii-baseline.tsv` records the
findings that have been reviewed and accepted, so the scanner fails on new
leaks rather than on the known state of the repo.

What the accepted baseline contains, and why each class is acceptable:

| Class | Example paths | Why accepted |
|---|---|---|
| Masked values that still *look* like what they replaced | `deviceToken`, `_id`, `syncIdentifier`, `pumpID`, `teamID` | The scanner cannot tell a masked token from a real one by shape. That is the point: parsers cannot either. |
| Algorithm output | `openaps.suggested.reason`, `expected.reason`, `comparison.reason` | oref0's own reasoning string, and the value conformance tests assert on. |
| Test-vector documentation | `testCases[].id`, `metadata.name`, `test_cases[].notes` | Human-readable case names and notes. Masking them destroys the vector and protects nobody. |
| Product and schema vocabulary | `loop.name`, `enteredBy`, `title`, `$id` | Distribution names, client names, JSON Schema keywords. |
| Synthetic fixture values | `installation_id` | Hand-written telemetry fixtures. |

`sanitize.py` masks deterministically and shape-preservingly, so cross-file
joins and format-sensitive parsers keep working; its docstring records
exactly what it leaves alone — timestamps, therapy schedules, algorithm
reason strings — and why. Those are judgement calls, written down so they
can be disputed rather than discovered.

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
