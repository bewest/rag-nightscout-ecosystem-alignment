# `treatments` field reference

<!-- GENERATED FILE — do not edit. Regenerate with: make schema-emit -->

Source spec: `specs/openapi/aid-treatments-2025.yaml`  
Evidence: `reports/schema-census/treatments.census.json`  
Corpus: 369,419 documents from 11 Nightscout sites across 2 snapshots (2026-04-01, 2026-04-26).

**Documents** is the share of corpus documents carrying the field; 
**sites** is how many independent Nightscout instances were seen to write it. 
The second number matters more: one busy site can make a single client's 
private field look common.

**Sensitivity** is the derived label (`secret`, `identifying`, 
`quasi-identifying`, `descriptive`) that projections strip by; see 
`specs/sync/sensitivity.yaml`. It is derived from the redaction policy and 
the census, not asserted, and an unlabelled field defaults to `identifying`.

**Handled by** lists projects whose source code serializes the field, from 
`reports/schema-census/attribution.json`. It is source evidence, not document 
provenance: a project that *reads* a field looks identical to one that 
*writes* it, and names too generic to attribute are left blank.

> This corpus is Loop-dominant (see the census `site_documents`). A field 
> marked universal here is universal *in this corpus*, which is not the same 
> as universal across the ecosystem.

## Universal — every site, effectively every document

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `_id` | `string` | 100.0% | 11 | AndroidAPS, LoopFollow, Nightguard, NightscoutKit +7 | identifying | always returned |
| `carbs` | `null`, `number`, `null` | 100.0% | 11 | AndroidAPS, Loop, LoopFollow, Nightguard +8 | descriptive | always returned · nullable |
| `created_at` | `string` | 100.0% | 11 | AndroidAPS, LoopFollow, Nightguard, NightscoutKit +8 | quasi-identifying | always returned |
| `enteredBy` | `string` | 100.0% | 11 | AndroidAPS, LoopFollow, Nightguard, NightscoutKit +6 | identifying | always returned |
| `eventType` | `string` | 100.0% | 11 | AndroidAPS, LoopFollow, Nightguard, NightscoutKit +6 | descriptive | always returned |
| `insulin` | `null`, `number`, `null` | 100.0% | 11 | AndroidAPS, Loop, LoopFollow, Nightguard +9 | descriptive | always returned · nullable |
| `utcOffset` | `integer` | 100.0% | 11 | AndroidAPS, Nocturne, nightscout-reporter | quasi-identifying | always returned |

## Core — most sites, substantial share of documents

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `absolute` | `number` | 54.9% | 10 | AndroidAPS, Loop, LoopFollow, NightscoutKit +5 | descriptive |  |
| `amount` | `number` | 45.7% | 10 |  | descriptive |  |
| `automatic` | `boolean` | 81.3% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne +1 | descriptive |  |
| `duration` | `number` | 91.0% | 10 |  | descriptive |  |
| `insulinType` | `string` | 80.4% | 10 | Loop, NightscoutKit, Nocturne, Trio | descriptive |  |
| `programmed` | `number` | 35.3% | 10 | Loop, NightscoutKit, Nocturne, Trio +1 | descriptive |  |
| `rate` | `number` | 54.9% | 10 |  | descriptive |  |
| `syncIdentifier` | `string` | 83.0% | 10 | Loop, NightscoutKit, Nocturne, Trio +1 | identifying |  |
| `temp` | `string` | 46.0% | 10 | AndroidAPS, Loop, NightscoutKit, Nocturne +4 | descriptive |  |
| `timestamp` | `number`, `string` | 84.4% | 10 |  | quasi-identifying |  |
| `type` | `string` | 35.3% | 10 |  | descriptive |  |
| `unabsorbed` | `number` | 35.3% | 10 | Loop, NightscoutKit, Nocturne, Trio | descriptive |  |

## Common — at least three independent sites

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `absorptionTime` | `integer` | 1.8% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne +1 | descriptive |  |
| `correctionRange` | `array` | 0.5% | 7 | LoopFollow, NightscoutKit, Nocturne, nightscout-reporter | descriptive |  |
| `correctionRange[]` | `number` | 0.5% | 7 | LoopFollow, NightscoutKit, Nocturne, nightscout-reporter | descriptive |  |
| `foodType` | `string` | 2.2% | 10 | Loop, NightscoutKit, Nocturne, Trio | quasi-identifying |  |
| `insulinNeedsScaleFactor` | `number` | 0.7% | 9 | Loop, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `notes` | `string` | 0.7% | 10 |  | identifying |  |
| `reason` | `string` | 1.1% | 10 |  | identifying |  |
| `remoteAddress` | `string` | 0.0% | 3 | Loop, NightscoutKit, Trio | identifying | **not in spec** |
| `userEnteredAt` | `string` | 1.8% | 10 | NightscoutKit | quasi-identifying |  |
| `userLastModifiedAt` | `string` | 0.0% | 5 | NightscoutKit | quasi-identifying |  |

## Vendor — one or two sites, but written consistently there

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `id` | `string` | 15.1% | 1 |  | identifying | **not in spec** |

## Sparse — one or two sites, inconsistently

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `fat` | `number` | 2.4% | 1 | AndroidAPS, Nocturne | descriptive |  |
| `glucose` | `number` | 0.0% | 1 | AndroidAPS, Loop, LoopFollow, NightscoutKit +5 | descriptive |  |
| `glucoseType` | `string` | 0.0% | 1 | AndroidAPS, NightscoutKit, Nocturne, tconnectsync +1 | quasi-identifying |  |
| `identifier` | `string` | 0.0% | 1 | AndroidAPS, Loop, Nightguard, NightscoutKit +2 | identifying |  |
| `protein` | `number` | 2.4% | 1 | AndroidAPS, Nocturne | descriptive |  |
| `targetBottom` | `number` | 0.0% | 1 | AndroidAPS, LoopFollow, Nightguard, Nocturne | descriptive |  |
| `targetTop` | `number` | 0.0% | 1 | AndroidAPS, LoopFollow, Nightguard, Nocturne | descriptive |  |
| `units` | `string` | 0.0% | 1 |  | quasi-identifying | **not in spec** |

## Rare — fewer than ten documents in the whole corpus

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `durationType` | `string` | 0.0% | 1 | LoopFollow, NightscoutKit, Nocturne | quasi-identifying | **not in spec** |
| `endmills` | `integer` | 0.0% | 1 | Nocturne | quasi-identifying | **not in spec** |
| `mills` | `integer` | 0.0% | 1 | AndroidAPS, Nightguard, NightscoutKit, Nocturne +2 | quasi-identifying | **not in spec** |

## Known quirks

Deviations from the schema that enough of the ecosystem exhibits that a reader has to handle them. Prevalence is measured, not asserted; see `specs/quirks/` for guidance on each.

| Quirk | Kind | Documents | Sites | Title |
|---|---|---|---|---|
| `QUIRK-TREATMENTS-001` | nullability | 95.8% | 11 | carbs and insulin are present-but-null on most treatments |
| `QUIRK-TREATMENTS-003` | type-union | 84.4% | 10 | timestamp is an ISO 8601 string, not the declared epoch integer |
| `QUIRK-TREATMENTS-002` | nullability | 60.7% | 11 | insulin is present-but-null on most treatments |
| `QUIRK-TREATMENTS-004` | case-mismatch | 35.3% | 10 | bolus subtype is written lower-case as `normal` |
| `QUIRK-TREATMENTS-005` | enum-gap | 1.0% | 2 | eventType carries values absent from every declared enum |

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

