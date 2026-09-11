# `entries` field reference

<!-- GENERATED FILE — do not edit. Regenerate with: make schema-emit -->

Source spec: `specs/openapi/aid-entries-2025.yaml`  
Evidence: `reports/schema-census/entries.census.json`  
Corpus: 896,589 documents from 11 Nightscout sites across 2 snapshots (2026-04-01, 2026-04-26).

**Documents** is the share of corpus documents carrying the field; 
**sites** is how many independent Nightscout instances were seen to write it. 
The second number matters more: one busy site can make a single client's 
private field look common.

**Handled by** lists projects whose source code serializes the field, from 
`reports/schema-census/attribution.json`. It is source evidence, not document 
provenance: a project that *reads* a field looks identical to one that 
*writes* it, and names too generic to attribute are left blank.

> This corpus is Loop-dominant (see the census `site_documents`). A field 
> marked universal here is universal *in this corpus*, which is not the same 
> as universal across the ecosystem.

## Universal — every site, effectively every document

| Field | Type | Documents | Sites | Handled by | Notes |
|---|---|---|---|---|---|
| `_id` | `string` | 100.0% | 11 | AndroidAPS, LoopFollow, Nightguard, NightscoutKit +7 | always returned |
| `date` | `number` | 100.0% | 11 |  | always returned |
| `dateString` | `string` | 100.0% | 11 | AndroidAPS, DiaBLE, LoopFollow, NightscoutKit +5 | always returned |
| `sgv` | `number` | 99.9% | 11 | AndroidAPS, DiaBLE, Loop, Nightguard +7 | always returned |
| `sysTime` | `string` | 100.0% | 11 | AndroidAPS, Nocturne, xDrip4iOS | always returned |
| `type` | `string` | 100.0% | 11 |  | always returned |
| `utcOffset` | `integer` | 100.0% | 11 | AndroidAPS, Nocturne, nightscout-reporter | always returned |

## Core — most sites, substantial share of documents

| Field | Type | Documents | Sites | Handled by | Notes |
|---|---|---|---|---|---|
| `device` | `string` | 93.6% | 11 |  |  |
| `direction` | `string` | 84.6% | 11 |  |  |
| `isCalibration` | `boolean` | 61.9% | 10 | NightscoutKit, Nocturne |  |
| `trend` | `integer` | 71.6% | 10 |  |  |
| `trendRate` | `number` | 46.0% | 10 | Loop, NightscoutKit, Nocturne, Trio |  |

## Common — at least three independent sites

| Field | Type | Documents | Sites | Handled by | Notes |
|---|---|---|---|---|---|
| `mbg` | `number` | 0.1% | 10 | Nightguard, NightscoutKit, Nocturne, xDrip4iOS |  |

## Vendor — one or two sites, but written consistently there

| Field | Type | Documents | Sites | Handled by | Notes |
|---|---|---|---|---|---|
| `filtered` | `number` | 12.9% | 2 | AndroidAPS, Nocturne, xDrip+, xDrip4iOS |  |
| `glucose` | `integer` | 6.4% | 1 | AndroidAPS, Loop, LoopFollow, NightscoutKit +5 | **not in spec** |
| `noise` | `integer` | 6.5% | 1 | AndroidAPS, Nocturne, xDrip+, xDrip4iOS |  |
| `unfiltered` | `number` | 12.9% | 2 | AndroidAPS, Nocturne, xDrip+, xDrip4iOS |  |

## Sparse — one or two sites, inconsistently

| Field | Type | Documents | Sites | Handled by | Notes |
|---|---|---|---|---|---|
| `delta` | `number` | 3.6% | 1 |  |  |
| `rssi` | `integer` | 3.6% | 1 | AndroidAPS, NightscoutKit, Nocturne, tconnectsync |  |

## Known quirks

Deviations from the schema that enough of the ecosystem exhibits that a reader has to handle them. Prevalence is measured, not asserted; see `specs/quirks/` for guidance on each.

| Quirk | Kind | Documents | Sites | Title |
|---|---|---|---|---|
| `QUIRK-ENTRIES-003` | undeclared-field | 71.6% | 10 | trend, trendRate and isCalibration are written but were undeclared |
| `QUIRK-ENTRIES-001` | type-union | 61.5% | 10 | date carries sub-millisecond precision as a fractional number |
| `QUIRK-ENTRIES-002` | enum-gap | 0.1% | 5 | direction carries NONE, which no declared enum listed |

## Declared in the spec, never observed

Either the corpus lacks a client that writes them, or the spec documents something that does not exist. API v3 metadata is expected here: the corpus was collected through `/api/v1/`.

| Field | Type |
|---|---|
| `app` | `string` |
| `identifier` | `string` |
| `intercept` | `number` |
| `isReadOnly` | `boolean` |
| `isValid` | `boolean` |
| `modifiedBy` | `string` |
| `scale` | `number` |
| `slope` | `number` |
| `srvCreated` | `integer` |
| `srvModified` | `integer` |
| `subject` | `string` |
| `units` | `string` |

