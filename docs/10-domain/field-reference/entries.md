# `entries` field reference

<!-- GENERATED FILE — do not edit. Regenerate with: make schema-emit -->

Source spec: `specs/openapi/aid-entries-2025.yaml`  
Evidence: `reports/schema-census/entries.census.json`  
Corpus: 896,589 documents from 11 Nightscout sites across 2 snapshots (2026-04-01, 2026-04-26).

**Documents** is the share of corpus documents carrying the field; 
**sites** is how many independent Nightscout instances were seen to write it. 
The second number matters more: one busy site can make a single client's 
private field look common.

> This corpus is Loop-dominant (see the census `site_documents`). A field 
> marked universal here is universal *in this corpus*, which is not the same 
> as universal across the ecosystem.

## Universal — every site, effectively every document

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `_id` | `string` | 100.0% | 11 | always returned |
| `date` | `number` | 100.0% | 11 | always returned |
| `dateString` | `string` | 100.0% | 11 | always returned |
| `sgv` | `number` | 99.9% | 11 | always returned |
| `sysTime` | `string` | 100.0% | 11 | always returned |
| `type` | `string` | 100.0% | 11 | always returned |
| `utcOffset` | `integer` | 100.0% | 11 | always returned |

## Core — most sites, substantial share of documents

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `device` | `string` | 93.6% | 11 |  |
| `direction` | `string` | 84.6% | 11 |  |
| `isCalibration` | `boolean` | 61.9% | 10 | **not in spec** |
| `trend` | `integer` | 71.6% | 10 | **not in spec** |
| `trendRate` | `number` | 46.0% | 10 | **not in spec** |

## Common — at least three independent sites

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `mbg` | `number` | 0.1% | 10 |  |

## Vendor — one or two sites, but written consistently there

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `filtered` | `number` | 12.9% | 2 |  |
| `glucose` | `integer` | 6.4% | 1 | **not in spec** |
| `noise` | `integer` | 6.5% | 1 |  |
| `unfiltered` | `number` | 12.9% | 2 |  |

## Sparse — one or two sites, inconsistently

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `delta` | `number` | 3.6% | 1 |  |
| `rssi` | `integer` | 3.6% | 1 |  |

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

