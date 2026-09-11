# `treatments` field reference

<!-- GENERATED FILE — do not edit. Regenerate with: make schema-emit -->

Source spec: `specs/openapi/aid-treatments-2025.yaml`  
Evidence: `reports/schema-census/treatments.census.json`  
Corpus: 369,419 documents from 11 Nightscout sites across 2 snapshots (2026-04-01, 2026-04-26).

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
| `carbs` | `number`, `null` | 100.0% | 11 | always returned · nullable |
| `created_at` | `string` | 100.0% | 11 | always returned |
| `enteredBy` | `string` | 100.0% | 11 | always returned |
| `eventType` | `string` | 100.0% | 11 | always returned |
| `insulin` | `number`, `null` | 100.0% | 11 | always returned · nullable |
| `utcOffset` | `integer` | 100.0% | 11 | always returned |

## Core — most sites, substantial share of documents

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `absolute` | `number` | 54.9% | 10 |  |
| `amount` | `number` | 45.7% | 10 | **not in spec** |
| `automatic` | `boolean` | 81.3% | 10 |  |
| `duration` | `number` | 91.0% | 10 |  |
| `insulinType` | `string` | 80.4% | 10 |  |
| `programmed` | `number` | 35.3% | 10 |  |
| `rate` | `number` | 54.9% | 10 |  |
| `syncIdentifier` | `string` | 83.0% | 10 |  |
| `temp` | `string` | 46.0% | 10 |  |
| `timestamp` | `integer`, `string` | 84.4% | 10 |  |
| `type` | `string` | 35.3% | 10 |  |
| `unabsorbed` | `number` | 35.3% | 10 |  |

## Common — at least three independent sites

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `absorptionTime` | `integer` | 1.8% | 10 |  |
| `correctionRange` | `array` | 0.5% | 7 | **not in spec** |
| `correctionRange[]` | `number` | 0.5% | 7 | **not in spec** |
| `foodType` | `string` | 2.2% | 10 |  |
| `insulinNeedsScaleFactor` | `number` | 0.7% | 9 | **not in spec** |
| `notes` | `string` | 0.7% | 10 |  |
| `reason` | `string` | 1.1% | 10 |  |
| `remoteAddress` | `string` | 0.0% | 3 | **not in spec** |
| `userEnteredAt` | `string` | 1.8% | 10 | **not in spec** |
| `userLastModifiedAt` | `string` | 0.0% | 5 | **not in spec** |

## Vendor — one or two sites, but written consistently there

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `id` | `string` | 15.1% | 1 | **not in spec** |

## Sparse — one or two sites, inconsistently

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `fat` | `number` | 2.4% | 1 |  |
| `glucose` | `number` | 0.0% | 1 |  |
| `glucoseType` | `string` | 0.0% | 1 |  |
| `identifier` | `string` | 0.0% | 1 |  |
| `protein` | `number` | 2.4% | 1 |  |
| `targetBottom` | `number` | 0.0% | 1 |  |
| `targetTop` | `number` | 0.0% | 1 |  |
| `units` | `string` | 0.0% | 1 | **not in spec** |

## Rare — fewer than ten documents in the whole corpus

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `durationType` | `string` | 0.0% | 1 | **not in spec** |
| `endmills` | `integer` | 0.0% | 1 | **not in spec** |
| `mills` | `integer` | 0.0% | 1 | **not in spec** |

## Declared in the spec, never observed

Either the corpus lacks a client that writes them, or the spec documents something that does not exist. API v3 metadata is expected here: the corpus was collected through `/api/v1/`.

| Field | Type |
|---|---|
| `app` | `string` |
| `bolusType` | `string` |
| `device` | `string` |
| `isBasalInsulin` | `boolean` |
| `isReadOnly` | `boolean` |
| `isValid` | `boolean` |
| `modifiedBy` | `string` |
| `percent` | `number` |
| `percentage` | `integer` |
| `profile` | `string` |
| `profileJson` | `string` |
| `pumpId` | `integer` |
| `pumpSerial` | `string` |
| `pumpType` | `string` |
| `srvCreated` | `integer` |
| `srvModified` | `integer` |
| `subject` | `string` |
| `timeshift` | `integer` |

