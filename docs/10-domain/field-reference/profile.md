# `profile` field reference

<!-- GENERATED FILE — do not edit. Regenerate with: make schema-emit -->

Source spec: `specs/openapi/aid-profile-2025.yaml`  
Evidence: `reports/schema-census/profile.census.json`  
Corpus: 202 documents from 11 Nightscout sites across 2 snapshots (2026-04-01, 2026-04-26).

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
| `defaultProfile` | `string` | 100.0% | 11 | always returned |
| `mills` | `integer`, `string` | 100.0% | 11 | always returned |
| `startDate` | `string` | 100.0% | 11 | always returned |
| `store` | `object` | 100.0% | 11 | always returned |
| `store.{}` | `object` | 100.0% | 11 |  |
| `store.{}.basal` | `array` | 100.0% | 11 |  |
| `store.{}.basal[]` | `object` | 100.0% | 11 |  |
| `store.{}.basal[].time` | `string` | 100.0% | 11 |  |
| `store.{}.basal[].timeAsSeconds` | `integer` | 100.0% | 11 |  |
| `store.{}.basal[].value` | `number` | 100.0% | 11 |  |
| `store.{}.carbratio` | `array` | 100.0% | 11 |  |
| `store.{}.carbratio[]` | `object` | 100.0% | 11 |  |
| `store.{}.carbratio[].time` | `string` | 100.0% | 11 |  |
| `store.{}.carbratio[].timeAsSeconds` | `integer` | 100.0% | 11 |  |
| `store.{}.carbratio[].value` | `number` | 100.0% | 11 |  |
| `store.{}.carbs_hr` | `number`, `string` | 100.0% | 11 |  |
| `store.{}.delay` | `integer`, `string` | 100.0% | 11 |  |
| `store.{}.dia` | `number` | 100.0% | 11 |  |
| `store.{}.sens` | `array` | 100.0% | 11 |  |
| `store.{}.sens[]` | `object` | 100.0% | 11 |  |
| `store.{}.sens[].time` | `string` | 100.0% | 11 |  |
| `store.{}.sens[].timeAsSeconds` | `integer` | 100.0% | 11 |  |
| `store.{}.sens[].value` | `number` | 100.0% | 11 |  |
| `store.{}.target_high` | `array` | 100.0% | 11 |  |
| `store.{}.target_high[]` | `object` | 100.0% | 11 |  |
| `store.{}.target_high[].time` | `string` | 100.0% | 11 |  |
| `store.{}.target_high[].timeAsSeconds` | `integer` | 100.0% | 11 |  |
| `store.{}.target_high[].value` | `number` | 100.0% | 11 |  |
| `store.{}.target_low` | `array` | 100.0% | 11 |  |
| `store.{}.target_low[]` | `object` | 100.0% | 11 |  |
| `store.{}.target_low[].time` | `string` | 100.0% | 11 |  |
| `store.{}.target_low[].timeAsSeconds` | `integer` | 100.0% | 11 |  |
| `store.{}.target_low[].value` | `number` | 100.0% | 11 |  |
| `store.{}.timezone` | `string` | 100.0% | 11 |  |
| `store.{}.units` | `string` | 100.0% | 11 |  |
| `units` | `string` | 100.0% | 11 | always returned |

## Core — most sites, substantial share of documents

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `enteredBy` | `string` | 99.0% | 10 |  |
| `loopSettings` | `object` | 99.0% | 10 |  |
| `loopSettings.bundleIdentifier` | `string` | 99.0% | 10 |  |
| `loopSettings.deviceToken` | `string` | 99.0% | 10 |  |
| `loopSettings.dosingEnabled` | `boolean` | 99.0% | 10 |  |
| `loopSettings.dosingStrategy` | `string` | 99.0% | 10 |  |
| `loopSettings.maximumBasalRatePerHour` | `number` | 99.0% | 10 |  |
| `loopSettings.maximumBolus` | `number` | 99.0% | 10 |  |
| `loopSettings.minimumBGGuard` | `number` | 99.0% | 10 |  |
| `loopSettings.overridePresets` | `array` | 99.0% | 10 |  |
| `loopSettings.overridePresets[]` | `object` | 99.0% | 10 |  |
| `loopSettings.overridePresets[].duration` | `integer` | 99.0% | 10 |  |
| `loopSettings.overridePresets[].insulinNeedsScaleFactor` | `number` | 89.1% | 9 |  |
| `loopSettings.overridePresets[].name` | `string` | 99.0% | 10 |  |
| `loopSettings.overridePresets[].symbol` | `string` | 99.0% | 10 |  |
| `loopSettings.overridePresets[].targetRange` | `array` | 69.3% | 7 |  |
| `loopSettings.overridePresets[].targetRange[]` | `number` | 69.3% | 7 |  |
| `loopSettings.preMealTargetRange` | `array` | 89.1% | 9 |  |
| `loopSettings.preMealTargetRange[]` | `number` | 89.1% | 9 |  |
| `loopSettings.scheduleOverride` | `object` | 61.4% | 9 |  |
| `loopSettings.scheduleOverride.duration` | `integer` | 61.4% | 9 |  |
| `loopSettings.scheduleOverride.insulinNeedsScaleFactor` | `number` | 57.9% | 9 |  |
| `loopSettings.scheduleOverride.name` | `string` | 59.4% | 9 |  |
| `loopSettings.scheduleOverride.symbol` | `string` | 59.4% | 9 |  |

## Common — at least three independent sites

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `loopSettings.scheduleOverride.targetRange` | `array` | 25.7% | 6 |  |
| `loopSettings.scheduleOverride.targetRange[]` | `number` | 25.7% | 6 |  |

## Vendor — one or two sites, but written consistently there

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `created_at` | `string` | 10.9% | 2 |  |

## Rare — fewer than ten documents in the whole corpus

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `srvModified` | `integer` | 1.0% | 1 |  |
| `store.{}.startDate` | `string` | 1.0% | 1 |  |

## Declared in the spec, never observed

Either the corpus lacks a client that writes them, or the spec documents something that does not exist. API v3 metadata is expected here: the corpus was collected through `/api/v1/`.

| Field | Type |
|---|---|
| `identifier` | `string` |
| `isValid` | `boolean` |
| `srvCreated` | `integer` |
| `store.{}.insulinCurve` | `string` |
| `store.{}.insulinPeakTime` | `integer` |
| `utcOffset` | `integer` |

