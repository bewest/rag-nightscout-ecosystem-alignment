# `devicestatus` field reference

<!-- GENERATED FILE — do not edit. Regenerate with: make schema-emit -->

Source spec: `specs/openapi/aid-devicestatus-2025.yaml`  
Evidence: `reports/schema-census/devicestatus.census.json`  
Corpus: 702,254 documents from 11 Nightscout sites across 2 snapshots (2026-04-01, 2026-04-26).

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
| `created_at` | `string` | 100.0% | 11 | AndroidAPS, LoopFollow, Nightguard, NightscoutKit +8 | quasi-identifying | always returned |
| `device` | `string` | 100.0% | 11 |  | descriptive | always returned |
| `uploader` | `object` | 100.0% | 11 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive | always returned |
| `uploader.battery` | `integer` | 100.0% | 11 |  | descriptive |  |
| `utcOffset` | `integer` | 100.0% | 11 | AndroidAPS, Nocturne, nightscout-reporter | quasi-identifying | always returned |

## Core — most sites, substantial share of documents

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `loop` | `object` | 85.1% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne +1 | descriptive |  |
| `loop.automaticDoseRecommendation` | `object` | 26.1% | 10 | Loop, NightscoutKit, Nocturne, Trio | descriptive |  |
| `loop.automaticDoseRecommendation.bolusVolume` | `number` | 26.1% | 10 | NightscoutKit, Nocturne | descriptive |  |
| `loop.automaticDoseRecommendation.timestamp` | `string` | 26.1% | 10 |  | quasi-identifying |  |
| `loop.cob` | `object` | 85.1% | 10 | AndroidAPS, Loop, LoopFollow, Nightguard +3 | descriptive |  |
| `loop.cob.cob` | `number` | 85.1% | 10 | AndroidAPS, Loop, LoopFollow, Nightguard +3 | descriptive |  |
| `loop.cob.timestamp` | `string` | 85.1% | 10 |  | quasi-identifying |  |
| `loop.enacted` | `object` | 57.7% | 10 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +1 | descriptive |  |
| `loop.enacted.bolusVolume` | `number` | 57.7% | 10 | NightscoutKit, Nocturne | descriptive |  |
| `loop.enacted.duration` | `number` | 57.7% | 10 |  | descriptive |  |
| `loop.enacted.rate` | `number` | 57.7% | 10 |  | descriptive |  |
| `loop.enacted.received` | `boolean` | 57.7% | 10 | NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `loop.enacted.timestamp` | `string` | 57.7% | 10 |  | quasi-identifying |  |
| `loop.iob` | `object` | 85.1% | 10 | AndroidAPS, Loop, LoopFollow, Nightguard +7 | descriptive |  |
| `loop.iob.iob` | `number` | 85.1% | 10 | AndroidAPS, Loop, LoopFollow, Nightguard +7 | descriptive |  |
| `loop.iob.timestamp` | `string` | 85.1% | 10 |  | quasi-identifying |  |
| `loop.name` | `string` | 85.1% | 10 |  | identifying |  |
| `loop.predicted` | `object` | 85.0% | 10 | LoopFollow, NightscoutKit, Nocturne | descriptive |  |
| `loop.predicted.startDate` | `string` | 85.0% | 10 | AndroidAPS, Loop, NightscoutKit, Nocturne +4 | quasi-identifying |  |
| `loop.predicted.values` | `array` | 85.0% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne | descriptive |  |
| `loop.predicted.values[]` | `number` | 85.0% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne | descriptive |  |
| `loop.recommendedBolus` | `number` | 85.0% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne +1 | descriptive |  |
| `loop.timestamp` | `string` | 85.1% | 10 |  | quasi-identifying |  |
| `loop.version` | `string` | 85.1% | 10 |  | descriptive |  |
| `override` | `object` | 85.1% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne +1 | descriptive |  |
| `override.active` | `boolean` | 85.1% | 10 | Loop, LoopFollow, NightscoutKit, Nocturne +2 | descriptive |  |
| `override.timestamp` | `string` | 85.1% | 10 |  | quasi-identifying |  |
| `pump` | `object` | 95.6% | 10 | AndroidAPS, LoopFollow, Nightguard, NightscoutKit +3 | descriptive |  |
| `pump.bolusing` | `boolean` | 85.1% | 10 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `pump.clock` | `string` | 95.6% | 10 |  | quasi-identifying |  |
| `pump.manufacturer` | `string` | 83.8% | 10 | Loop, NightscoutKit, Nocturne, Trio | descriptive |  |
| `pump.model` | `string` | 83.8% | 10 |  | descriptive |  |
| `pump.pumpID` | `string` | 85.1% | 10 | Loop, NightscoutKit, Trio | identifying |  |
| `pump.reservoir` | `number` | 14.5% | 10 | AndroidAPS, Loop, LoopFollow, Nightguard +4 | descriptive |  |
| `pump.secondsFromGMT` | `integer` | 85.1% | 10 | NightscoutKit | quasi-identifying |  |
| `pump.suspended` | `boolean` | 85.1% | 10 | AndroidAPS, Loop, NightscoutKit, Nocturne +2 | descriptive |  |
| `uploader.name` | `string` | 85.1% | 10 |  | identifying |  |
| `uploader.timestamp` | `string` | 85.1% | 10 |  | quasi-identifying |  |

## Common — at least three independent sites

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `loop.automaticDoseRecommendation.tempBasalAdjustment` | `object` | 6.1% | 10 | NightscoutKit | descriptive |  |
| `loop.automaticDoseRecommendation.tempBasalAdjustment.duration` | `number` | 6.1% | 10 |  | descriptive |  |
| `loop.automaticDoseRecommendation.tempBasalAdjustment.rate` | `number` | 6.1% | 10 |  | descriptive |  |
| `loop.failureReason` | `string` | 2.4% | 10 | LoopFollow, NightscoutKit, Nocturne | quasi-identifying |  |
| `override.currentCorrectionRange` | `object` | 9.2% | 9 | LoopFollow, NightscoutKit, Nocturne | descriptive |  |
| `override.currentCorrectionRange.maxValue` | `number` | 9.2% | 9 | Loop, LoopFollow, NightscoutKit, Nocturne +1 | descriptive |  |
| `override.currentCorrectionRange.minValue` | `number` | 9.2% | 9 | Loop, LoopFollow, NightscoutKit, Nocturne +1 | descriptive |  |
| `override.duration` | `number` | 4.8% | 9 |  | descriptive |  |
| `override.multiplier` | `number` | 7.5% | 9 | LoopFollow, NightscoutKit, Nocturne | descriptive |  |
| `override.name` | `string` | 8.9% | 9 |  | identifying |  |
| `pump.reservoir_display_override` | `string` | 0.6% | 10 | AndroidAPS, NightscoutKit, Nocturne | descriptive |  |
| `pump.reservoir_level_override` | `integer` | 0.6% | 10 | NightscoutKit, Nocturne | descriptive |  |

## Vendor — one or two sites, but written consistently there

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `openaps` | `object` | 10.5% | 1 | AndroidAPS, LoopFollow, Nocturne, cgm-remote-monitor +1 | descriptive |  |
| `openaps.enacted` | `object` | 10.5% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +1 | descriptive |  |
| `openaps.enacted.COB` | `integer` | 10.5% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive | **not in spec** |
| `openaps.enacted.CR` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.enacted.IOB` | `number` | 10.5% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive | **not in spec** |
| `openaps.enacted.ISF` | `integer` | 10.5% | 1 | LoopFollow, Trio, oref0, xDrip4iOS | descriptive | **not in spec** |
| `openaps.enacted.TDD` | `number` | 10.4% | 1 | Trio, nightscout-reporter, xDrip4iOS | descriptive | **not in spec** |
| `openaps.enacted.bg` | `integer` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.enacted.current_target` | `integer` | 10.5% | 1 | LoopFollow, xDrip4iOS | descriptive | **not in spec** |
| `openaps.enacted.deliverAt` | `string` | 10.5% | 1 | LoopFollow, Nocturne, cgm-remote-monitor | quasi-identifying | **not in spec** |
| `openaps.enacted.duration` | `integer` | 10.5% | 1 |  | descriptive |  |
| `openaps.enacted.eventualBG` | `integer` | 10.5% | 1 | AndroidAPS, LoopFollow, Nocturne, cgm-remote-monitor +1 | descriptive | **not in spec** |
| `openaps.enacted.expectedDelta` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.enacted.id` | `string` | 10.5% | 1 |  | identifying | **not in spec** |
| `openaps.enacted.insulinForManualBolus` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.enacted.insulinReq` | `number` | 10.5% | 1 | Nocturne, cgm-remote-monitor, xDrip4iOS | descriptive | **not in spec** |
| `openaps.enacted.manualBolusErrorString` | `integer` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.enacted.minDelta` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.enacted.predBGs` | `object` | 10.5% | 1 | AndroidAPS, LoopFollow, Nocturne, Trio +1 | descriptive |  |
| `openaps.enacted.predBGs.IOB` | `array` | 10.5% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.enacted.predBGs.IOB[]` | `integer` | 10.5% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.enacted.predBGs.ZT` | `array` | 10.5% | 1 |  | descriptive |  |
| `openaps.enacted.predBGs.ZT[]` | `integer` | 10.5% | 1 |  | descriptive |  |
| `openaps.enacted.rate` | `number` | 10.5% | 1 |  | descriptive |  |
| `openaps.enacted.reason` | `string` | 10.5% | 1 |  | identifying | **not in spec** |
| `openaps.enacted.received` | `boolean` | 10.5% | 1 | NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `openaps.enacted.reservoir` | `number` | 10.5% | 1 | AndroidAPS, Loop, LoopFollow, Nightguard +4 | descriptive | **not in spec** |
| `openaps.enacted.sensitivityRatio` | `number` | 10.5% | 1 | AndroidAPS, LoopFollow, Nocturne, oref0 | descriptive | **not in spec** |
| `openaps.enacted.temp` | `string` | 10.5% | 1 | AndroidAPS, Loop, NightscoutKit, Nocturne +4 | quasi-identifying | **not in spec** |
| `openaps.enacted.threshold` | `integer` | 10.5% | 1 | Loop, Nocturne, Trio, xDrip+ | descriptive | **not in spec** |
| `openaps.enacted.timestamp` | `string` | 10.5% | 1 |  | quasi-identifying |  |
| `openaps.iob` | `object` | 10.5% | 1 | AndroidAPS, Loop, LoopFollow, Nightguard +7 | descriptive |  |
| `openaps.iob.activity` | `number` | 10.5% | 1 | AndroidAPS, Nocturne, cgm-remote-monitor, oref0 | descriptive |  |
| `openaps.iob.basaliob` | `number` | 10.5% | 1 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +1 | descriptive |  |
| `openaps.iob.bolusinsulin` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.iob.bolusiob` | `number` | 10.5% | 1 | Nocturne | descriptive | **not in spec** |
| `openaps.iob.iob` | `number` | 10.5% | 1 | AndroidAPS, Loop, LoopFollow, Nightguard +7 | descriptive |  |
| `openaps.iob.iobWithZeroTemp` | `object` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.iob.iobWithZeroTemp.activity` | `number` | 10.5% | 1 | AndroidAPS, Nocturne, cgm-remote-monitor, oref0 | descriptive | **not in spec** |
| `openaps.iob.iobWithZeroTemp.basaliob` | `number` | 10.5% | 1 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor +1 | descriptive | **not in spec** |
| `openaps.iob.iobWithZeroTemp.bolusinsulin` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.iob.iobWithZeroTemp.bolusiob` | `number` | 10.5% | 1 | Nocturne | descriptive | **not in spec** |
| `openaps.iob.iobWithZeroTemp.iob` | `number` | 10.5% | 1 | AndroidAPS, Loop, LoopFollow, Nightguard +7 | descriptive | **not in spec** |
| `openaps.iob.iobWithZeroTemp.netbasalinsulin` | `number` | 10.5% | 1 | AndroidAPS, Nocturne, cgm-remote-monitor, oref0 | descriptive | **not in spec** |
| `openaps.iob.iobWithZeroTemp.time` | `string` | 10.5% | 1 |  | quasi-identifying | **not in spec** |
| `openaps.iob.lastBolusTime` | `integer` | 10.5% | 1 | Nocturne, cgm-remote-monitor | quasi-identifying |  |
| `openaps.iob.lastTemp` | `object` | 10.5% | 1 |  | descriptive |  |
| `openaps.iob.lastTemp.date` | `integer` | 10.5% | 1 |  | quasi-identifying | **not in spec** |
| `openaps.iob.lastTemp.duration` | `number` | 10.5% | 1 |  | descriptive |  |
| `openaps.iob.lastTemp.rate` | `number` | 10.5% | 1 |  | descriptive |  |
| `openaps.iob.lastTemp.started_at` | `string` | 10.5% | 1 | Nocturne, oref0 | quasi-identifying |  |
| `openaps.iob.lastTemp.timestamp` | `string` | 10.5% | 1 |  | quasi-identifying | **not in spec** |
| `openaps.iob.netbasalinsulin` | `number` | 10.5% | 1 | AndroidAPS, Nocturne, cgm-remote-monitor, oref0 | descriptive | **not in spec** |
| `openaps.iob.time` | `string` | 10.5% | 1 |  | quasi-identifying | **not in spec** |
| `openaps.suggested` | `object` | 10.5% | 1 | AndroidAPS, LoopFollow, Nocturne, cgm-remote-monitor | descriptive |  |
| `openaps.suggested.COB` | `integer` | 10.5% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.suggested.CR` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.suggested.IOB` | `number` | 10.5% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.suggested.ISF` | `integer` | 10.5% | 1 | LoopFollow, Trio, oref0, xDrip4iOS | descriptive | **not in spec** |
| `openaps.suggested.TDD` | `number` | 9.9% | 1 | Trio, nightscout-reporter, xDrip4iOS | descriptive | **not in spec** |
| `openaps.suggested.bg` | `integer` | 10.5% | 1 |  | descriptive |  |
| `openaps.suggested.current_target` | `integer` | 10.5% | 1 | LoopFollow, xDrip4iOS | descriptive | **not in spec** |
| `openaps.suggested.deliverAt` | `string` | 10.5% | 1 | LoopFollow, Nocturne, cgm-remote-monitor | quasi-identifying |  |
| `openaps.suggested.duration` | `integer` | 10.5% | 1 |  | descriptive |  |
| `openaps.suggested.eventualBG` | `integer` | 10.5% | 1 | AndroidAPS, LoopFollow, Nocturne, cgm-remote-monitor +1 | descriptive |  |
| `openaps.suggested.expectedDelta` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.suggested.id` | `string` | 10.5% | 1 |  | identifying | **not in spec** |
| `openaps.suggested.insulinForManualBolus` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.suggested.insulinReq` | `number` | 10.5% | 1 | Nocturne, cgm-remote-monitor, xDrip4iOS | descriptive |  |
| `openaps.suggested.manualBolusErrorString` | `integer` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.suggested.minDelta` | `number` | 10.5% | 1 |  | descriptive | **not in spec** |
| `openaps.suggested.predBGs` | `object` | 10.5% | 1 | AndroidAPS, LoopFollow, Nocturne, Trio +1 | descriptive |  |
| `openaps.suggested.predBGs.IOB` | `array` | 10.5% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.suggested.predBGs.IOB[]` | `integer` | 10.5% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.suggested.predBGs.ZT` | `array` | 10.5% | 1 |  | descriptive |  |
| `openaps.suggested.predBGs.ZT[]` | `integer` | 10.5% | 1 |  | descriptive |  |
| `openaps.suggested.rate` | `number` | 10.5% | 1 |  | descriptive |  |
| `openaps.suggested.reason` | `string` | 10.5% | 1 |  | identifying |  |
| `openaps.suggested.received` | `boolean` | 10.5% | 1 | NightscoutKit, Nocturne, cgm-remote-monitor | descriptive | **not in spec** |
| `openaps.suggested.reservoir` | `number` | 10.5% | 1 | AndroidAPS, Loop, LoopFollow, Nightguard +4 | descriptive | **not in spec** |
| `openaps.suggested.sensitivityRatio` | `number` | 10.5% | 1 | AndroidAPS, LoopFollow, Nocturne, oref0 | descriptive |  |
| `openaps.suggested.temp` | `string` | 10.5% | 1 | AndroidAPS, Loop, NightscoutKit, Nocturne +4 | quasi-identifying | **not in spec** |
| `openaps.suggested.threshold` | `integer` | 10.5% | 1 | Loop, Nocturne, Trio, xDrip+ | descriptive | **not in spec** |
| `openaps.suggested.timestamp` | `string` | 9.9% | 1 |  | quasi-identifying |  |
| `openaps.version` | `string` | 10.5% | 1 |  | quasi-identifying | **not in spec** |
| `pump.battery` | `object` | 11.8% | 2 |  | descriptive |  |
| `pump.battery.display` | `boolean` | 10.3% | 1 |  | descriptive |  |
| `pump.battery.percent` | `integer` | 11.6% | 2 |  | descriptive |  |
| `pump.battery.string` | `string` | 10.5% | 1 | Loop, Trio, oref0 | quasi-identifying |  |
| `pump.status` | `object` | 10.5% | 1 |  | descriptive |  |
| `pump.status.bolusing` | `boolean` | 10.5% | 1 | AndroidAPS, NightscoutKit, Nocturne, cgm-remote-monitor | descriptive |  |
| `pump.status.status` | `string` | 10.5% | 1 |  | quasi-identifying |  |
| `pump.status.suspended` | `boolean` | 10.5% | 1 | AndroidAPS, Loop, NightscoutKit, Nocturne +2 | descriptive |  |
| `pump.status.timestamp` | `string` | 10.5% | 1 |  | quasi-identifying |  |
| `uploader.isCharging` | `boolean` | 10.5% | 1 | AndroidAPS, LoopFollow, Nocturne | descriptive |  |
| `uploader.type` | `string` | 4.4% | 1 |  | quasi-identifying |  |

## Sparse — one or two sites, inconsistently

| Field | Type | Documents | Sites | Handled by | Sensitivity | Notes |
|---|---|---|---|---|---|---|
| `openaps.enacted.carbsReq` | `integer` | 0.4% | 1 | Nocturne | descriptive | **not in spec** |
| `openaps.enacted.predBGs.COB` | `array` | 7.2% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.enacted.predBGs.COB[]` | `integer` | 7.2% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.enacted.predBGs.UAM` | `array` | 9.1% | 1 | Nocturne, Trio, cgm-remote-monitor | descriptive |  |
| `openaps.enacted.predBGs.UAM[]` | `integer` | 9.1% | 1 | Nocturne, Trio, cgm-remote-monitor | descriptive |  |
| `openaps.enacted.units` | `number` | 2.6% | 1 |  | descriptive |  |
| `openaps.recommendedBolus` | `number` | 5.9% | 1 | Loop, LoopFollow, NightscoutKit, Nocturne +1 | descriptive | **not in spec** |
| `openaps.suggested.carbsReq` | `integer` | 0.4% | 1 | Nocturne | descriptive | **not in spec** |
| `openaps.suggested.predBGs.COB` | `array` | 7.2% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.suggested.predBGs.COB[]` | `integer` | 7.2% | 1 | AndroidAPS, LoopFollow, NightscoutKit, Nocturne +3 | descriptive |  |
| `openaps.suggested.predBGs.UAM` | `array` | 9.1% | 1 | Nocturne, Trio, cgm-remote-monitor | descriptive |  |
| `openaps.suggested.predBGs.UAM[]` | `integer` | 9.1% | 1 | Nocturne, Trio, cgm-remote-monitor | descriptive |  |
| `openaps.suggested.units` | `number` | 2.5% | 1 |  | descriptive |  |
| `pump.bolusIncrement` | `number` | 5.9% | 1 | LoopFollow, Nocturne, Trio | descriptive | **not in spec** |

## Known quirks

Deviations from the schema that enough of the ecosystem exhibits that a reader has to handle them. Prevalence is measured, not asserted; see `specs/quirks/` for guidance on each.

| Quirk | Kind | Documents | Sites | Title |
|---|---|---|---|---|
| `QUIRK-DEVICESTATUS-001` | shape-divergence | 85.1% | 10 | pump status exists in two incompatible shapes, flat and nested |
| `QUIRK-DEVICESTATUS-002` | shape-divergence | 10.5% | 1 | nested pump.status shape |
| `QUIRK-DEVICESTATUS-003` | shape-divergence | 10.5% | 1 | battery state is written as `string`, not the declared `status` |
| `QUIRK-DEVICESTATUS-005` | type-union | 10.2% | 1 | oref0 lastTemp.duration is fractional minutes |
| `QUIRK-DEVICESTATUS-004` | sentinel | 9.8% | 1 | reservoir uses 0xDEADBEEF as an unknown-value sentinel |

## Declared in the spec, never observed

Either the corpus lacks a client that writes them, or the spec documents something that does not exist. API v3 metadata is expected here: the corpus was collected through `/api/v1/`.

| Field | Type |
|---|---|
| `configuration` | `object` |
| `identifier` | `string` |
| `isCharging` | `boolean` |
| `isValid` | `boolean` |
| `mills` | `integer` |
| `openaps.iob.bolussnooze` | `number` |
| `openaps.suggested.targetBG` | `integer` |
| `openaps.suggested.tick` | `string` |
| `openaps.suggested.variable_sens` | `number` |
| `pump.battery.status` | `string` |
| `pump.battery.voltage` | `number` |
| `pump.extended` | `object` |
| `srvCreated` | `integer` |
| `srvModified` | `integer` |
| `uploader.batteryVoltage` | `number` |
| `uploaderBattery` | `integer` |

