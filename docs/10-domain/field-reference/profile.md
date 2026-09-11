# `profile` field reference

<!-- GENERATED FILE — do not edit. Regenerate with: make schema-emit -->

Source spec: `specs/openapi/aid-profile-2025.yaml`  
Evidence: `reports/schema-census/profile.census.json`  
Corpus: 202 documents from 11 Nightscout sites across 2 snapshots (2026-04-01, 2026-04-26).

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
| `defaultProfile` | `string` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +1 | identifying | always returned |
| `mills` | `integer`, `string` | 100.0% | 11 | AndroidAPS, Nightguard, NightscoutKit, Nocturne +2 | quasi-identifying | always returned |
| `startDate` | `string` | 100.0% | 11 | AndroidAPS, Loop, NightscoutKit, Nocturne +4 | quasi-identifying | always returned |
| `store` | `object` | 100.0% | 11 |  | descriptive | always returned |
| `store.{}` | `object` | 100.0% | 11 |  | descriptive |  |
| `store.{}.basal` | `array` | 100.0% | 11 | AndroidAPS, Loop, NightscoutKit, Nocturne +5 | descriptive |  |
| `store.{}.basal[]` | `object` | 100.0% | 11 | AndroidAPS, Loop, NightscoutKit, Nocturne +5 | descriptive |  |
| `store.{}.basal[].time` | `string` | 100.0% | 11 |  | quasi-identifying |  |
| `store.{}.basal[].timeAsSeconds` | `integer` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +2 | descriptive |  |
| `store.{}.basal[].value` | `number` | 100.0% | 11 |  | descriptive |  |
| `store.{}.carbratio` | `array` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +2 | descriptive |  |
| `store.{}.carbratio[]` | `object` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +2 | descriptive |  |
| `store.{}.carbratio[].time` | `string` | 100.0% | 11 |  | quasi-identifying |  |
| `store.{}.carbratio[].timeAsSeconds` | `integer` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +2 | descriptive |  |
| `store.{}.carbratio[].value` | `number` | 100.0% | 11 |  | descriptive |  |
| `store.{}.carbs_hr` | `number`, `string` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +2 | descriptive |  |
| `store.{}.delay` | `integer`, `string` | 100.0% | 11 | AndroidAPS, Loop, LoopFollow, NightscoutKit +5 | descriptive |  |
| `store.{}.dia` | `number` | 100.0% | 11 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +5 | descriptive |  |
| `store.{}.sens` | `array` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +3 | descriptive |  |
| `store.{}.sens[]` | `object` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +3 | descriptive |  |
| `store.{}.sens[].time` | `string` | 100.0% | 11 |  | quasi-identifying |  |
| `store.{}.sens[].timeAsSeconds` | `integer` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +2 | descriptive |  |
| `store.{}.sens[].value` | `number` | 100.0% | 11 |  | descriptive |  |
| `store.{}.target_high` | `array` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +3 | descriptive |  |
| `store.{}.target_high[]` | `object` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +3 | descriptive |  |
| `store.{}.target_high[].time` | `string` | 100.0% | 11 |  | quasi-identifying |  |
| `store.{}.target_high[].timeAsSeconds` | `integer` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +2 | descriptive |  |
| `store.{}.target_high[].value` | `number` | 100.0% | 11 |  | descriptive |  |
| `store.{}.target_low` | `array` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +3 | descriptive |  |
| `store.{}.target_low[]` | `object` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +3 | descriptive |  |
| `store.{}.target_low[].time` | `string` | 100.0% | 11 |  | quasi-identifying |  |
| `store.{}.target_low[].timeAsSeconds` | `integer` | 100.0% | 11 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +2 | descriptive |  |
| `store.{}.target_low[].value` | `number` | 100.0% | 11 |  | descriptive |  |
| `store.{}.timezone` | `string` | 100.0% | 11 | AndroidAPS, Loop, LoopFollow, NightscoutKit +5 | quasi-identifying |  |
| `store.{}.units` | `string` | 100.0% | 11 |  | descriptive |  |
| `units` | `string` | 100.0% | 11 |  | descriptive | always returned |

## Core — most sites, substantial share of documents

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `enteredBy` | `string` | 99.0% | 10 | AndroidAPS, LoopFollow, Nightguard, NightscoutKit +6 | identifying |  |
| `loopSettings` | `object` | 99.0% | 10 | NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `loopSettings.bundleIdentifier` | `string` | 99.0% | 10 | NightscoutKit, Nocturne, cgm-remote-monitor | identifying |  |
| `loopSettings.deviceToken` | `string` | 99.0% | 10 | Loop, NightscoutKit, Nocturne, Trio +1 | secret |  |
| `loopSettings.dosingEnabled` | `boolean` | 99.0% | 10 | Loop, NightscoutKit, Nocturne, Trio +1 | descriptive |  |
| `loopSettings.dosingStrategy` | `string` | 99.0% | 10 | Loop, NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `loopSettings.maximumBasalRatePerHour` | `number` | 99.0% | 10 | Loop, NightscoutKit, Nocturne, Trio +1 | descriptive |  |
| `loopSettings.maximumBolus` | `number` | 99.0% | 10 | Loop, NightscoutKit, Nocturne, Trio +1 | descriptive |  |
| `loopSettings.minimumBGGuard` | `number` | 99.0% | 10 | Loop, NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `loopSettings.overridePresets` | `array` | 99.0% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne +2 | descriptive |  |
| `loopSettings.overridePresets[]` | `object` | 99.0% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne +2 | descriptive |  |
| `loopSettings.overridePresets[].duration` | `integer` | 99.0% | 10 |  | descriptive |  |
| `loopSettings.overridePresets[].insulinNeedsScaleFactor` | `number` | 89.1% | 9 | Loop, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `loopSettings.overridePresets[].name` | `string` | 99.0% | 10 |  | identifying |  |
| `loopSettings.overridePresets[].symbol` | `string` | 99.0% | 10 | Loop, NightscoutKit, Nocturne, Trio +1 | quasi-identifying |  |
| `loopSettings.overridePresets[].targetRange` | `array` | 69.3% | 7 | NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `loopSettings.overridePresets[].targetRange[]` | `number` | 69.3% | 7 | NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `loopSettings.preMealTargetRange` | `array` | 89.1% | 9 | Loop, NightscoutKit, Nocturne, Trio +1 | descriptive |  |
| `loopSettings.preMealTargetRange[]` | `number` | 89.1% | 9 | Loop, NightscoutKit, Nocturne, Trio +1 | descriptive |  |
| `loopSettings.scheduleOverride` | `object` | 61.4% | 9 | Loop, NightscoutKit, Nocturne, Trio | descriptive |  |
| `loopSettings.scheduleOverride.duration` | `integer` | 61.4% | 9 |  | descriptive |  |
| `loopSettings.scheduleOverride.insulinNeedsScaleFactor` | `number` | 57.9% | 9 | Loop, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `loopSettings.scheduleOverride.name` | `string` | 59.4% | 9 |  | identifying |  |
| `loopSettings.scheduleOverride.symbol` | `string` | 59.4% | 9 | Loop, NightscoutKit, Nocturne, Trio +1 | quasi-identifying |  |

## Common — at least three independent sites

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `loopSettings.scheduleOverride.targetRange` | `array` | 25.7% | 6 | NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `loopSettings.scheduleOverride.targetRange[]` | `number` | 25.7% | 6 | NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |

## Vendor — one or two sites, but written consistently there

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `created_at` | `string` | 10.9% | 2 | AndroidAPS, LoopFollow, Nightguard, NightscoutKit +8 | quasi-identifying |  |

## Rare — fewer than ten documents in the whole corpus

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `srvModified` | `integer` | 1.0% | 1 | AndroidAPS, Nocturne, cgm-remote-monitor | quasi-identifying |  |
| `store.{}.startDate` | `string` | 1.0% | 1 | AndroidAPS, Loop, NightscoutKit, Nocturne +4 | quasi-identifying |  |

## Known quirks

Deviations from the schema that enough of the ecosystem exhibits that a reader has to handle them. Prevalence is measured, not asserted; see `specs/quirks/` for guidance on each.

| Quirk | Kind | Documents | Sites | Title |
|---|---|---|---|---|
| `QUIRK-PROFILE-003` | unit-mismatch | 100.0% | 11 | glucose units have four spellings and no spec matched the data |
| `QUIRK-PROFILE-001` | type-union | 99.0% | 10 | mills is a string, not the declared epoch integer |
| `QUIRK-PROFILE-002` | type-union | 99.0% | 10 | numeric profile settings are written as strings |
| `QUIRK-PROFILE-004` | undeclared-field | 99.0% | 10 | Loop flattens 26 paths of its own settings into the profile document |

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

