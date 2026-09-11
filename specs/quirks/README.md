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
| `status` | `active` (measured in the corpus), `historical` (fixed upstream, still in stored data), `proposed` (suspected, not yet measured) |
| `collection` | `entries`, `treatments`, `devicestatus`, `profile`, `settings` |
| `path` | Dotted census path the quirk applies to |
| `kind` | `type-union`, `nullability`, `enum-gap`, `case-mismatch`, `unit-mismatch`, `shape-divergence`, `sentinel`, `undeclared-field` |
| `detect` | Declarative predicate — see below |
| `reader_guidance` | What a conforming reader must do |
| `writer_guidance` | What a conforming writer should do instead |
| `attribution` | Projects with source evidence, from `reports/schema-census/attribution.json` |
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
