# `devicestatus` field reference

<!-- GENERATED FILE — do not edit. Regenerate with: make schema-emit -->

Source spec: `specs/openapi/aid-devicestatus-2025.yaml`  
Evidence: `reports/schema-census/devicestatus.census.json`  
Corpus: 702,254 documents from 11 Nightscout sites across 2 snapshots (2026-04-01, 2026-04-26).

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
| `created_at` | `string` | 100.0% | 11 | always returned |
| `device` | `string` | 100.0% | 11 | always returned |
| `uploader` | `object` | 100.0% | 11 | always returned |
| `uploader.battery` | `integer` | 100.0% | 11 |  |
| `utcOffset` | `integer` | 100.0% | 11 | always returned |

## Core — most sites, substantial share of documents

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `loop` | `object` | 85.1% | 10 |  |
| `loop.automaticDoseRecommendation` | `object` | 26.1% | 10 |  |
| `loop.automaticDoseRecommendation.bolusVolume` | `number` | 26.1% | 10 |  |
| `loop.automaticDoseRecommendation.timestamp` | `string` | 26.1% | 10 |  |
| `loop.cob` | `object` | 85.1% | 10 |  |
| `loop.cob.cob` | `number` | 85.1% | 10 |  |
| `loop.cob.timestamp` | `string` | 85.1% | 10 |  |
| `loop.enacted` | `object` | 57.7% | 10 |  |
| `loop.enacted.bolusVolume` | `number` | 57.7% | 10 |  |
| `loop.enacted.duration` | `number` | 57.7% | 10 |  |
| `loop.enacted.rate` | `number` | 57.7% | 10 |  |
| `loop.enacted.received` | `boolean` | 57.7% | 10 |  |
| `loop.enacted.timestamp` | `string` | 57.7% | 10 |  |
| `loop.iob` | `object` | 85.1% | 10 |  |
| `loop.iob.iob` | `number` | 85.1% | 10 |  |
| `loop.iob.timestamp` | `string` | 85.1% | 10 |  |
| `loop.name` | `string` | 85.1% | 10 |  |
| `loop.predicted` | `object` | 85.0% | 10 |  |
| `loop.predicted.startDate` | `string` | 85.0% | 10 |  |
| `loop.predicted.values` | `array` | 85.0% | 10 |  |
| `loop.predicted.values[]` | `number` | 85.0% | 10 |  |
| `loop.recommendedBolus` | `number` | 85.0% | 10 |  |
| `loop.timestamp` | `string` | 85.1% | 10 |  |
| `loop.version` | `string` | 85.1% | 10 |  |
| `override` | `object` | 85.1% | 10 |  |
| `override.active` | `boolean` | 85.1% | 10 |  |
| `override.timestamp` | `string` | 85.1% | 10 |  |
| `pump` | `object` | 95.6% | 10 |  |
| `pump.bolusing` | `boolean` | 85.1% | 10 |  |
| `pump.clock` | `string` | 95.6% | 10 |  |
| `pump.manufacturer` | `string` | 83.8% | 10 |  |
| `pump.model` | `string` | 83.8% | 10 |  |
| `pump.pumpID` | `string` | 85.1% | 10 |  |
| `pump.reservoir` | `number` | 14.5% | 10 |  |
| `pump.secondsFromGMT` | `integer` | 85.1% | 10 |  |
| `pump.suspended` | `boolean` | 85.1% | 10 |  |
| `uploader.name` | `string` | 85.1% | 10 |  |
| `uploader.timestamp` | `string` | 85.1% | 10 |  |

## Common — at least three independent sites

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `loop.automaticDoseRecommendation.tempBasalAdjustment` | `object` | 6.1% | 10 |  |
| `loop.automaticDoseRecommendation.tempBasalAdjustment.duration` | `number` | 6.1% | 10 |  |
| `loop.automaticDoseRecommendation.tempBasalAdjustment.rate` | `number` | 6.1% | 10 |  |
| `loop.failureReason` | `string` | 2.4% | 10 |  |
| `override.currentCorrectionRange` | `object` | 9.2% | 9 |  |
| `override.currentCorrectionRange.maxValue` | `number` | 9.2% | 9 |  |
| `override.currentCorrectionRange.minValue` | `number` | 9.2% | 9 |  |
| `override.duration` | `number` | 4.8% | 9 |  |
| `override.multiplier` | `number` | 7.5% | 9 |  |
| `override.name` | `string` | 8.9% | 9 |  |
| `pump.reservoir_display_override` | `string` | 0.6% | 10 |  |
| `pump.reservoir_level_override` | `integer` | 0.6% | 10 |  |

## Vendor — one or two sites, but written consistently there

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `openaps` | `object` | 10.5% | 1 |  |
| `openaps.enacted` | `object` | 10.5% | 1 |  |
| `openaps.enacted.COB` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.CR` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.IOB` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.ISF` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.TDD` | `number` | 10.4% | 1 | **not in spec** |
| `openaps.enacted.bg` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.current_target` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.deliverAt` | `string` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.duration` | `integer` | 10.5% | 1 |  |
| `openaps.enacted.eventualBG` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.expectedDelta` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.id` | `string` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.insulinForManualBolus` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.insulinReq` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.manualBolusErrorString` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.minDelta` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.predBGs` | `object` | 10.5% | 1 |  |
| `openaps.enacted.predBGs.IOB` | `array` | 10.5% | 1 |  |
| `openaps.enacted.predBGs.IOB[]` | `integer` | 10.5% | 1 |  |
| `openaps.enacted.predBGs.ZT` | `array` | 10.5% | 1 |  |
| `openaps.enacted.predBGs.ZT[]` | `integer` | 10.5% | 1 |  |
| `openaps.enacted.rate` | `number` | 10.5% | 1 |  |
| `openaps.enacted.reason` | `string` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.received` | `boolean` | 10.5% | 1 |  |
| `openaps.enacted.reservoir` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.sensitivityRatio` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.temp` | `string` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.threshold` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.enacted.timestamp` | `string` | 10.5% | 1 |  |
| `openaps.iob` | `object` | 10.5% | 1 |  |
| `openaps.iob.activity` | `number` | 10.5% | 1 |  |
| `openaps.iob.basaliob` | `number` | 10.5% | 1 |  |
| `openaps.iob.bolusinsulin` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.iob.bolusiob` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.iob.iob` | `number` | 10.5% | 1 |  |
| `openaps.iob.iobWithZeroTemp` | `object` | 10.5% | 1 | **not in spec** |
| `openaps.iob.iobWithZeroTemp.activity` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.iob.iobWithZeroTemp.basaliob` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.iob.iobWithZeroTemp.bolusinsulin` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.iob.iobWithZeroTemp.bolusiob` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.iob.iobWithZeroTemp.iob` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.iob.iobWithZeroTemp.netbasalinsulin` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.iob.iobWithZeroTemp.time` | `string` | 10.5% | 1 | **not in spec** |
| `openaps.iob.lastBolusTime` | `integer` | 10.5% | 1 |  |
| `openaps.iob.lastTemp` | `object` | 10.5% | 1 |  |
| `openaps.iob.lastTemp.date` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.iob.lastTemp.duration` | `number` | 10.5% | 1 |  |
| `openaps.iob.lastTemp.rate` | `number` | 10.5% | 1 |  |
| `openaps.iob.lastTemp.started_at` | `string` | 10.5% | 1 |  |
| `openaps.iob.lastTemp.timestamp` | `string` | 10.5% | 1 | **not in spec** |
| `openaps.iob.netbasalinsulin` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.iob.time` | `string` | 10.5% | 1 | **not in spec** |
| `openaps.suggested` | `object` | 10.5% | 1 |  |
| `openaps.suggested.COB` | `integer` | 10.5% | 1 |  |
| `openaps.suggested.CR` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.IOB` | `number` | 10.5% | 1 |  |
| `openaps.suggested.ISF` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.TDD` | `number` | 9.9% | 1 | **not in spec** |
| `openaps.suggested.bg` | `integer` | 10.5% | 1 |  |
| `openaps.suggested.current_target` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.deliverAt` | `string` | 10.5% | 1 |  |
| `openaps.suggested.duration` | `integer` | 10.5% | 1 |  |
| `openaps.suggested.eventualBG` | `integer` | 10.5% | 1 |  |
| `openaps.suggested.expectedDelta` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.id` | `string` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.insulinForManualBolus` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.insulinReq` | `number` | 10.5% | 1 |  |
| `openaps.suggested.manualBolusErrorString` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.minDelta` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.predBGs` | `object` | 10.5% | 1 |  |
| `openaps.suggested.predBGs.IOB` | `array` | 10.5% | 1 |  |
| `openaps.suggested.predBGs.IOB[]` | `integer` | 10.5% | 1 |  |
| `openaps.suggested.predBGs.ZT` | `array` | 10.5% | 1 |  |
| `openaps.suggested.predBGs.ZT[]` | `integer` | 10.5% | 1 |  |
| `openaps.suggested.rate` | `number` | 10.5% | 1 |  |
| `openaps.suggested.reason` | `string` | 10.5% | 1 |  |
| `openaps.suggested.received` | `boolean` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.reservoir` | `number` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.sensitivityRatio` | `number` | 10.5% | 1 |  |
| `openaps.suggested.temp` | `string` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.threshold` | `integer` | 10.5% | 1 | **not in spec** |
| `openaps.suggested.timestamp` | `string` | 9.9% | 1 |  |
| `openaps.version` | `string` | 10.5% | 1 | **not in spec** |
| `pump.battery` | `object` | 11.8% | 2 |  |
| `pump.battery.display` | `boolean` | 10.3% | 1 |  |
| `pump.battery.percent` | `integer` | 11.6% | 2 |  |
| `pump.battery.string` | `string` | 10.5% | 1 |  |
| `pump.status` | `object` | 10.5% | 1 |  |
| `pump.status.bolusing` | `boolean` | 10.5% | 1 |  |
| `pump.status.status` | `string` | 10.5% | 1 |  |
| `pump.status.suspended` | `boolean` | 10.5% | 1 |  |
| `pump.status.timestamp` | `string` | 10.5% | 1 |  |
| `uploader.isCharging` | `boolean` | 10.5% | 1 |  |
| `uploader.type` | `string` | 4.4% | 1 |  |

## Sparse — one or two sites, inconsistently

| Field | Type | Documents | Sites | Notes |
|---|---|---|---|---|
| `openaps.enacted.carbsReq` | `integer` | 0.4% | 1 | **not in spec** |
| `openaps.enacted.predBGs.COB` | `array` | 7.2% | 1 |  |
| `openaps.enacted.predBGs.COB[]` | `integer` | 7.2% | 1 |  |
| `openaps.enacted.predBGs.UAM` | `array` | 9.1% | 1 |  |
| `openaps.enacted.predBGs.UAM[]` | `integer` | 9.1% | 1 |  |
| `openaps.enacted.units` | `number` | 2.6% | 1 |  |
| `openaps.recommendedBolus` | `number` | 5.9% | 1 | **not in spec** |
| `openaps.suggested.carbsReq` | `integer` | 0.4% | 1 | **not in spec** |
| `openaps.suggested.predBGs.COB` | `array` | 7.2% | 1 |  |
| `openaps.suggested.predBGs.COB[]` | `integer` | 7.2% | 1 |  |
| `openaps.suggested.predBGs.UAM` | `array` | 9.1% | 1 |  |
| `openaps.suggested.predBGs.UAM[]` | `integer` | 9.1% | 1 |  |
| `openaps.suggested.units` | `number` | 2.5% | 1 |  |
| `pump.bolusIncrement` | `number` | 5.9% | 1 | **not in spec** |

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

