# Quirks registry

A *quirk* is a way real Nightscout documents deviate from the schema, that
enough of the ecosystem does that a reader has to handle it.

Not a bug report and not a wishlist. Each entry names a deviation, states
how much of the corpus exhibits it, says which projects produce it, and
says what a conforming reader should do. Prevalence is **measured**, not
asserted: `make schema-quirks` replays every quirk's detector over the
corpus and rewrites the `measured` block. An entry whose detector finds
nothing is reported, not silently kept.

```bash
make schema-quirks           # measure every quirk against the corpus
make schema-quirks-check     # fail if a registry claim no longer matches
```

## Why a registry rather than schema changes

Some of these can be fixed in the schema — a declared type widened, an enum
extended — and
[the 2025.2.0 spec revision](../openapi/aid-entries-2025.yaml) did exactly
that where it was safe. But widening a type records *that* two shapes exist,
not *why*, *who* writes each, *how common* each is, or *what to do with
them*. A reader implementing `entries.date` needs to know that a fractional
value is normal and should be rounded, not merely that `number` is allowed.

The registry is also where a deviation lives when the schema should *not*
change: a sentinel value, a case mismatch that should be normalized at the
boundary, or two structurally different shapes for the same concept.

## Fields

| Field | Meaning |
|---|---|
| `id` | Stable identifier, `QUIRK-<COLLECTION>-<NNN>` |
| `title` | One line, stating the deviation |
| `status` | `proposed` (suspected, not yet measured), `active` (measured in the corpus), `historical` (no recent write and no live instance of an affected version), `retired` (also no stored record depends on its mapping) — see [Lifecycle](#lifecycle-d20) |
| `collection` | `entries`, `treatments`, `devicestatus`, `profile`, `settings`, `declarations` |
| `applies_to` | `documents` (default) or `declarations` (D20 rule 1) |
| `path` | Dotted census path the quirk applies to |
| `kind` | `type-union`, `nullability`, `enum-gap`, `case-mismatch`, `unit-mismatch`, `shape-divergence`, `sentinel`, `undeclared-field`, `id-form`, `slot-name` |
| `detect` | Declarative predicate — see below |
| `reader_guidance` | What a conforming reader must do |
| `writer_guidance` | What a conforming writer should do instead |
| `attribution` | Projects with source evidence, from `reports/schema-census/attribution.json` |
| `affects` | Optional (D20 rule 1): `[{vendor, product, versions, versionSource, evidence}]` — see below |
| `mapping` | Optional: what a hub does to a document the entry describes (`action`, `flag`, `erasesEvidence`), recorded on the stored record as `quirksApplied` (D20 rule 3) |
| `declaration` | For `applies_to: declarations`: the declared `member` (`slot`), its `value`, and the `sameAs` the catalogue maps it to |
| `measured` | Generated: documents, share, sites, snapshots |
| `references` | Code locations, PRs, spec sections |

## Detectors

A detector is a small declarative object, not code, so the registry stays
data:

```yaml
detect:
  path: date            # census path, relative to the document root
  test: is-fractional   # see the table below
```

| `test` | True when the value at `path` is… |
|---|---|
| `exists` | present |
| `absent` | missing |
| `is-null` | JSON null |
| `is-fractional` | a number with a non-zero fractional part |
| `is-string` | a JSON string |
| `is-number` | a JSON number |
| `is-object` | a JSON object |
| `equals` | equal to `value` |
| `in` | one of `values` |
| `not-in` | not one of `values`, ignoring nulls |
| `matches` | a string matching the regex in `pattern` |

Entries are validated at load against [`quirk.schema.json`](quirk.schema.json).

## Versions (D20)

[D20](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16)
(maintainer, 2026-10-16) lets an entry name what it affects. The member is additive: an entry
without it keeps its project-level `attribution`.

```yaml
affects:
  - vendor: LoopKit          # a registration's metadata.vendor
    product: Loop            # and metadata.product
    versions:
      range: ">=3.2.3 <3.14" # only where the corpus or source shows it, else:
      # unmeasured: why the versions are not known
      seen:                  # versions the evidence shows; not a range
        - {version: 3.14.8, claim: read-derived, ref: <file:line>, commit: <sha>}
    versionSource:           # where make schema-quirks reads a version
      collection: devicestatus
      path: loop.version
      window_minutes: 60
    evidence:
      - {claim: measured, ref: <how>}
```

A range is `*`, or whitespace-separated comparators (`=`, `>=`, `>`, `<=`, `<`) that must all
hold, over the vendor's own version strings: dot-separated parts, numeric parts compared as
numbers and before text. Several `affects` items are alternatives.

`versionSource` in the entry's own collection reads the version from the same document. In
another collection it reads the nearest document on the same site within `window_minutes`;
`quirks.json` labels those counts `co-occurrence`, which is not attribution, and none of them is
copied into `versions.range`.

Every claim in `affects` says whether it is `measured` or `read-derived`, with a file and line
and a commit for source.

## Declarations (D20 rule 2)

An entry with `applies_to: declarations` maps a declared value for the versions it affects,
for example a slot name that means a slot in the well-known catalogue's shared slot list
(`declaration: {member: slot, value: <name>, sameAs: <shared slot>}`). The catalogue publishes it
as a `wellKnown.mappings[]` entry of the hub's capability document; versions released after
registration declare `sameAs` themselves. The hub records each mapping it applies
(`quirksApplied`). The corpus has no declarations, so these entries are measured by a hub's
recorded mappings, and `make schema-quirks` reports them unmeasured. None is listed yet: which
slots share a meaning is for the controller authors to confirm (`PROPOSAL-REG-CONTROLLERS`).

## Lifecycle (D20)

`proposed` → `active` → `historical` → `retired`. `make schema-quirks` writes, for each entry
with `affects` (or a `historical` or `retired` status), which statuses the measurement
supports and why not the others; `make schema-quirks-check` fails a `historical` or `retired`
claim it does not support. A `proposed` entry never fails.

| status | the measurement must show |
|---|---|
| `proposed` | nothing |
| `active` | documents in the corpus, and the entry's `expect` block |
| `historical` | no recent document; zero live instances of an affected version in a hub's instance listing (`--instances`, de-identified: `[{vendor, product, version, live}]`); and a detector whose evidence the hub's `mapping` does not erase |
| `retired` | historical's conditions, and no stored document left that depends on the mapping |

**Recent** is declared and measured: a document is recent when its own time (`date`, `mills`,
`created_at`, `dateString` or `timestamp`) is within `RECENT_DAYS` (365) of the newest snapshot's
collection date, `--recent-days` to change it. The window is relative to the corpus, not the wall
clock, so a re-run over the same corpus gives the same answer.

An entry whose `mapping.erasesEvidence` is true (the hub rewrites the stored document, as
`UUID_HANDLING` does) cannot become `historical` from the corpus: a mapped write no longer shows
the quirk, so only the hub's recorded mappings count recent writes.
