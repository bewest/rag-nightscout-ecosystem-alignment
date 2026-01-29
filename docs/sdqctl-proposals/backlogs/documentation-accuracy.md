# Documentation Accuracy Backlog

> **Domain**: Bottom-up accuracy verification of documentation claims  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Created**: 2026-01-29  
> **Purpose**: Systematic verification from evidence → mappings → analyses → proposals → gaps → traceability

---

## Verification Philosophy

Bottom-up approach ensures claims are grounded in evidence:

```
Level 1: Evidence Sources     (externals/*, source code)
    ↓
Level 2: Mappings             (mapping/*/README.md, nightscout-fields.md)
    ↓
Level 3: Deep Dive Analysis   (docs/10-domain/*-deep-dive.md)
    ↓  
Level 4: Gap Identification   (traceability/*-gaps.md)
    ↓
Level 5: Requirements         (traceability/*-requirements.md)
    ↓
Level 6: Proposals/Designs    (docs/sdqctl-proposals/*.md)
```

---

## Active Review Queue

### Level 1: Evidence Source Verification ✅ COMPLETE

| # | Item | Priority | Status | Result |
|---|------|----------|--------|--------|
| 1 | Verify CGM protocol code refs | P2 | ✅ Done | 91% valid (356/391) |
| 2 | Verify algorithm source refs | P2 | ✅ Done | Via #1 |
| 3 | Verify Nightscout API source refs | P2 | ✅ Done | Via #1 |
| 4 | Verify connector bridge refs | P2 | ✅ Done | Via #1 |

**Finding**: Active docs have 100% valid refs; 35 broken are in archives or intentional examples.

### Level 2: Mapping Accuracy Verification

| # | Item | Priority | Domain | Status |
|---|------|----------|--------|--------|
| 5 | Audit mapping/xdrip-android/nightscout-sync.md | P2 | cgm-sources | ✅ **100% accurate** |
| 6 | Audit mapping/aaps/nsclient-schema.md | P2 | nightscout-api | ✅ **100% accurate** |
| 7 | Audit mapping/loop/sync-identity-fields.md | P2 | sync-identity | ✅ **100% accurate** |
| 8 | Audit mapping/trio/nightscout-sync.md | P2 | nightscout-api | ✅ **100% accurate** |
| 9 | Audit terminology-matrix.md (10% sample) | P3 | cross-project | ✅ **100% accurate** |

**Finding (2026-01-29)**: xDrip and AAPS mappings verified against source:
- xDrip: UploaderQueue bitfields, SGV fields, treatment fields all match source
- AAPS: RemoteTreatment.kt, RemoteEntry.kt, EventType.kt all match schema doc

**Finding (2026-01-29)**: Loop and Trio mappings verified against source:
- Loop: DoseEntry.swift:24 syncIdentifier, ObjectIdCache.swift structure, 24h cache lifetime all verified
- Trio: NightscoutAPI.swift SHA-1 auth, NightscoutStatus.swift OpenAPSStatus fields (iob, suggested, enacted) verified

**Finding (2026-01-29)**: Terminology matrix 10% sample (15 terms) verified:
- HeartRate fields: beatsPerMinute, duration, device, utcOffset, isValid (HeartRate.kt:21-31)
- AAPS insulinEndTime (ms) verified (ProfileSealed.kt:237)
- TrendArrow enum: DOUBLE_DOWN, SINGLE_DOWN, FortyFiveDown (TrendArrow.kt:10-12)
- oref0 curve models: rapid-acting, ultra-rapid (profile/index.js:62)
- oref0 prediction arrays: IOBpredBGs, COBpredBGs, UAMpredBGs, ZTpredBGs (determine-basal.js:442-445)
- Nightscout direction values: Flat, FortyFiveUp (fixtures verified)
- secp256r1 curve name (Curve.java:24)

### Level 3: Deep Dive Claim Verification

| # | Item | Priority | Domain | Status |
|---|------|----------|--------|--------|
| 10 | Verify cgm-data-sources-deep-dive.md claims | P2 | cgm-sources | ✅ **100% accurate** |
| 11 | Verify algorithm-comparison-deep-dive.md claims | P2 | aid-algorithms | ✅ **100% accurate** |
| 12 | Verify devicestatus-deep-dive.md claims | P2 | nightscout-api | ✅ **100% accurate** |
| 13 | Verify entries-deep-dive.md claims | P2 | nightscout-api | ✅ **100% accurate** |
| 14 | Verify treatments-deep-dive.md claims | P2 | nightscout-api | ✅ **100% accurate** |
| 15 | Verify pump-communication-deep-dive.md claims | P3 | pumps | ✅ **100% accurate** |
| 16 | Verify libre-protocol-deep-dive.md claims | P2 | cgm-sources | ✅ **100% accurate** |
| 17 | Verify g7-protocol-specification.md claims | P1 | cgm-sources | ✅ **100% accurate** |

**Finding (2026-01-29)**: CGM data sources deep dive verified:
- xDrip+: 26 data source types (DexCollectionType.java enum)
- xDrip+: Ob1 collector for Dexcom (Ob1G5StateMachine, Ob1G5CollectionService)
- xDrip+: NSFollow, SHFollow follower types (SourceWizard.java:60-61)
- Loop: CGMBLEKit and G7SensorKit exist
- xDrip4iOS: Dexcom, Libre, Generic CGM categories
- LibreLinkUp: /llu/connections endpoint confirmed

**Finding (2026-01-29)**: Algorithm comparison deep dive verified:
- oref0: 4 prediction arrays (IOB/COB/UAM/ZT) at determine-basal.js:442-445
- oref0: SMB function at determine-basal.js:51, Autosens at :128,:249
- AAPS: Dynamic ISF (TDD-based) at OpenAPSSMBPlugin.kt:268
- Loop: Retrospective Correction at LoopMath.swift:16-17
- Loop: Automatic Bolus option at LoopDataManager.swift:1819
- Trio: JavaScript calls at Script.swift:9, OpenAPS.swift:803

**Finding (2026-01-29)**: DeviceStatus deep dive verified:
- Loop: `loop` top-level object, device format `loop://`, override field present
- Trio: `openaps` top-level, device = "Trio" (NightscoutTreatment.local)
- AAPS: `openaps` top-level, device format `openaps://`, pump.reservoir/clock fields
- oref0: predBGs with IOB/COB/UAM/ZT arrays at determine-basal.js:657-690

**Finding (2026-01-29)**: Entries deep dive verified:
- xDrip+: `calculated_value` for glucose (BgReading.java:119), `dg_slope` for trend
- Loop: `HKQuantity` for glucose, `provenanceIdentifier` for device, `GlucoseTrend` enum
- AAPS: `value` field (GlucoseValue.kt:40), `trendArrow` enum
- Nightscout: entry types sgv/mbg/cal confirmed in data-layer-audit.md

**Finding (2026-01-29)**: Treatments deep dive verified:
- Loop: `deliveredUnits`, `syncIdentifier`, `automatic` boolean (DoseEntry.swift)
- AAPS: `amount` field, Bolus.Type enum (NORMAL/SMB/PRIMING), interfaceIDs.nightscoutId
- xDrip+: `uuid` for sync identity (Treatments.java:297, NightscoutUploader.java:782)
- SMB mapping: AAPS SMB → eventType "Correction Bolus" (BolusExtension.kt:28)

**Finding (2026-01-29)**: Libre protocol deep dive verified:
- Libre 1: NFC unencrypted (Libre.swift:91-93 encryptedFram empty for libre1)
- Libre 2: Encrypted FRAM + BLE (Libre.swift:86,93, OOP.swift:390)
- Libre 3: ECDH + AES-CCM (Libre3.swift:1011-1012, Crypto.swift:11-19)
- PatchInfo bytes: 0xDF→libre1, 0x9D→libre2, 0x76→libre2Gen2 (Libre.swift:11-18)
- NFC command 0xA1 for patchInfo (NFC.swift:55-56,280)
- IC Manufacturer: 0x07 (TI) vs 0x7a (Abbott) (Abbott.swift:59, Libre2Gen2.swift:131)
- 60 min warmup period (Console.swift:190)

**Finding (2026-01-29)**: Pump communication deep dive verified:
- Omnipod Eros: 433.91 MHz RF (PodComms.swift:560)
- Medtronic: 916.x MHz US, 868.x MHz EU (PumpOpsSession.swift:795,797)
- RileyLink: Submodule at RileyLinkKit (gitmodules:13-15)
- Loop PumpManager: Protocol at PumpManager.swift:67 with enactBolus(:170), enactTempBasal(:186)
- PumpManagerStatus: BasalDeliveryState/BolusState enums (PumpManagerStatus.swift:38-60)
- AAPS Pump: Interface at Pump.kt:19 with deliverBolus, connect/disconnect

### Level 4: Gap Verification

| # | Item | Priority | Domain | Status |
|---|------|----------|--------|--------|
| 18 | Verify GAP-CGM-* accuracy | P2 | cgm-sources | ✅ GAP-BLE-001/002 confirmed open |
| 19 | Verify GAP-ALG-* accuracy | P2 | aid-algorithms | ✅ **100% accurate** (7 claims verified) |
| 20 | Verify GAP-API-* accuracy | P2 | nightscout-api | ✅ **100% accurate** (6 claims verified) |
| 21 | Verify GAP-SYNC-* accuracy | P2 | sync-identity | ✅ **100% accurate** (9 claims verified) |
| 22 | Verify GAP-TREAT-* accuracy | P2 | treatments | ✅ **100% accurate** (11 claims verified) |
| 23 | Verify GAP-CONNECT-* accuracy | P2 | connectors | ✅ **100% accurate** (8 claims verified) |

### Level 5: Requirements Traceability

| # | Item | Priority | Domain | Verification Method | Status |
|---|------|----------|--------|---------------------|--------|
| 24 | Audit REQ-SYNC-* → scenario coverage | P2 | sync-identity | Run `python tools/verify_assertions.py` | ✅ 83% covered (15/18) |
| 25 | Audit REQ-TREAT-* → scenario coverage | P2 | treatments | Verify each REQ has test scenario | ✅ 100% covered (7/7) |
| 26 | Audit REQ-CONNECT-* completeness | P2 | connectors | Ensure all 28 GAPs have REQs | ✅ 100% complete (28/28) |
| 27 | Audit REQ-API-* → OpenAPI alignment | P2 | nightscout-api | Check specs match requirements | ✅ 63% specced (22/35) |

### Level 6: Proposal Coherence

| # | Item | Priority | Domain | Verification Method |
|---|------|----------|--------|---------------------|
| 28 | Audit algorithm-conformance-suite.md | P2 | aid-algorithms | Verify proposal vs actual runners |
| 29 | Audit statistics-api-proposal.md | P2 | nightscout-api | Check endpoint specs vs actual needs |
| 30 | Audit lsp-integration-proposal.md | P3 | tooling | Verify LSP claims |
| 31 | Audit nocturne-modernization-analysis.md | P2 | connectors | Cross-check with nocturne source |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Item #23: GAP-CONNECT-* verification | 2026-01-29 | **100% accurate** - 8 claims verified (v1 API only, no tests, hardcoded IDs) |
| Item #22: GAP-TREAT-* verification | 2026-01-29 | **100% accurate** - 11 claims verified (override gaps, remote cmd, SMB type) |
| Item #21: GAP-SYNC-* verification | 2026-01-29 | **100% accurate** - 9 claims verified (ObjectIdCache, v1 API, TZ gaps) |
| Item #20: GAP-API-* verification | 2026-01-29 | **100% accurate** - 6 claims verified (v1/v3 diff, dedup, auth, iOS adoption) |
| Item #19: GAP-ALG-* verification | 2026-01-29 | **100% accurate** - 7 claims verified (conformance, 85 vectors, 30.6% pass) |
| Item #10: CGM data sources deep dive | 2026-01-29 | **100% accurate** - 8 major claims verified |
| Item #11: Algorithm comparison deep dive | 2026-01-29 | **100% accurate** - 7 major claims verified |
| Item #9: Terminology matrix sampling | 2026-01-29 | **100% accurate** - 15 terms verified across 6 repos |
| Item #7-8: Loop + Trio mappings | 2026-01-29 | **100% accurate** - syncIdentifier, OpenAPSStatus verified |
| Item #5-6: Mapping verification | 2026-01-29 | **100% accurate** - xDrip + AAPS mappings verified |
| Item #17: G7 protocol claims | 2026-01-29 | **100% accurate** - All opcodes, UUIDs, curves verified vs source |
| Item #1-4: Source refs | 2026-01-29 | **91% valid** (356/391), 2 intentional example refs |
| Broken refs fix (LSP claim verification) | 2026-01-29 | 3 refs fixed, 92% valid |
| Initial cohesiveness audit proposal | 2026-01-29 | Queued to this backlog |

**Level 2 Complete**: 5/5 mapping items verified (100%)
**Level 3 Progress**: 3/8 deep dive items verified (37.5%)

### Verification Details: Terminology Matrix (2026-01-29)

| Term/Field | Source | Status |
|------------|--------|--------|
| HeartRate.beatsPerMinute | `HeartRate.kt:25` | ✅ Verified |
| HeartRate.duration | `HeartRate.kt:21` | ✅ Verified |
| HeartRate.utcOffset | `HeartRate.kt:28` | ✅ Verified |
| AAPS insulinEndTime (ms) | `ProfileSealed.kt:237` | ✅ Verified |
| TrendArrow.DOUBLE_DOWN | `TrendArrow.kt:12` | ✅ Verified |
| TrendArrow.FortyFiveDown | `TrendArrow.kt:10` | ✅ Verified |
| oref0 rapid-acting curve | `profile/index.js:62` | ✅ Verified |
| oref0 IOBpredBGs array | `determine-basal.js:443` | ✅ Verified |
| oref0 COBpredBGs array | `determine-basal.js:442` | ✅ Verified |
| oref0 UAMpredBGs array | `determine-basal.js:444` | ✅ Verified |
| oref0 ZTpredBGs array | `determine-basal.js:445` | ✅ Verified |
| Nightscout direction "Flat" | `api3/doc/formats.md:31` | ✅ Verified |
| secp256r1 curve | `Curve.java:24` | ✅ Verified |

### Verification Details: Mappings (2026-01-29)

**xDrip nightscout-sync.md**:
| Claim | Source | Status |
|-------|--------|--------|
| UploaderQueue bitfields | `UploaderQueue.java:75-79` | ✅ Verified |
| NightscoutUploader.java ~1470 lines | `NightscoutUploader.java` | ✅ 1469 lines |
| SGV fields (sgv, direction, date, filtered) | `NightscoutUploader.java:666-689` | ✅ Verified |
| Treatment fields (eventType, carbs, insulin) | `NightscoutUploader.java:779-782` | ✅ Verified |

**AAPS nsclient-schema.md**:
| Claim | Source | Status |
|-------|--------|--------|
| RemoteTreatment.kt fields | `RemoteTreatment.kt:18-79` | ✅ Verified |
| RemoteEntry.kt SGV fields | `RemoteEntry.kt:15-34` | ✅ Verified |
| EventType enum values | `EventType.kt:27-36` | ✅ Verified |

**Loop sync-identity-fields.md**:
| Claim | Source | Status |
|-------|--------|--------|
| DoseEntry.syncIdentifier | `DoseEntry.swift:24` | ✅ Verified |
| StoredGlucoseSample.syncIdentifier | `StoredGlucoseSample.swift:18` | ✅ Verified |
| ObjectIdCache structure | `ObjectIdCache.swift:11,50,65` | ✅ Verified |
| 24h cache lifetime | `NightscoutService.swift:27` | ✅ Verified |

**Trio nightscout-sync.md**:
| Claim | Source | Status |
|-------|--------|--------|
| SHA-1 api-secret header | `NightscoutAPI.swift:57` | ✅ Verified |
| OpenAPSStatus fields (iob, suggested, enacted) | `NightscoutStatus.swift:11-14` | ✅ Verified |
| NightscoutManager uploadStatus | `NightscoutManager.swift:392-480` | ✅ Verified |

### Verification Details: G7 Protocol (2026-01-29)

| Claim | Source | Status |
|-------|--------|--------|
| Service UUID `F8083532-...` | `DiaBLE/Dexcom.swift:51` | ✅ Verified |
| Characteristic 3535 (Auth) | `DiaBLE/DexcomG7.swift:54-58` | ✅ Verified |
| Characteristic 3534 (Control) | `DiaBLE/DexcomG7.swift:59-64` | ✅ Verified |
| 26 opcodes defined | `DiaBLE/DexcomG7.swift:20-47` | ✅ Verified |
| secp256r1 curve | `xDrip/libkeks/Curve.java:24` | ✅ Verified |
| J-PAKE auth flow | `xDrip/libkeks/Calc.java` | ✅ Verified |
| G7SensorKit files | `LoopWorkspace/G7SensorKit/...` | ✅ All 7 files exist |

---

## Tooling Gaps & Proposals

When verification is not possible with current tools, document here for sdqctl team:

### Currently Missing Tools

| Need | Current State | Proposal |
|------|---------------|----------|
| Cross-file claim verification | Manual grep | Extend verify_refs.py with claim patterns |
| Gap freshness check | No tool | `tools/verify_gap_freshness.py` - check if gap still exists |
| Mapping completeness | No tool | `tools/verify_mapping_coverage.py` - fields in source vs mapping |
| Terminology spot-check | No tool | `tools/sample_terminology.py` - random sample verification |

### Proposed Tool: `verify_gap_freshness.py`

**Purpose**: Check if documented gaps still exist in source code.

**Example**:
```bash
python tools/verify_gap_freshness.py --gap GAP-G7-001
# Output: GAP-G7-001: STILL OPEN - No G7 support in xDrip+
#         Evidence: grep "G7\|DexcomG7" externals/xDrip returns 0 matches
```

**Needed by**: Gap verification (items 18-23)

### Proposed Tool: `verify_mapping_coverage.py`

**Purpose**: Check that mapping docs cover fields actually used in source.

**Example**:
```bash
python tools/verify_mapping_coverage.py mapping/xdrip/nightscout-fields.md
# Output: Coverage: 87%
#         Missing from doc: transmitterBattery, sensorState
#         Extra in doc (not in source): rawNoise
```

**Needed by**: Mapping verification (items 5-9)

### Proposed Tool: `sample_terminology.py`

**Purpose**: Random sample verification of terminology matrix.

**Example**:
```bash
python tools/sample_terminology.py --sample-size 20
# Output: Sampling 20 terms from terminology-matrix.md...
#         ✓ ISF: Found in Loop (InsulinSensitivity.swift:45)
#         ✓ COB: Found in AAPS (CobInfo.kt:12)
#         ✗ UAM: Not found in nightguard (expected: n/a, claim: supports)
#         Accuracy: 95% (19/20)
```

**Needed by**: Terminology verification (item 9)

---

## Verification Commands Quick Reference

```bash
# Level 1: Source refs
python tools/verify_refs.py --json > traceability/refs-validation.json

# Level 2-3: Claim verification (manual + grep)
grep -r "syncIdentifier" externals/LoopWorkspace --include="*.swift" | head

# Level 4: Gap coverage
python tools/gen_coverage.py --json > traceability/coverage-analysis.json

# Level 5: Requirements traceability
python tools/verify_assertions.py

# Level 6: Cross-reference
make traceability
```

---

## Integration with sdqctl Workflows

```yaml
# Proposed: accuracy-audit.conv workflow
REFCAT:
  - docs/10-domain/*-deep-dive.md
  - mapping/*/README.md
  - traceability/*-gaps.md

GOAL: |
  Verify accuracy of claims in REFCAT files:
  1. Identify 3-5 specific claims with code refs
  2. Verify each claim against source
  3. Report accuracy percentage
  4. Flag any inaccuracies for correction

VERIFY: refs
```

---

## References

- [audit-verification-tooling-proposal.md](../audit-verification-tooling-proposal.md) - Tool designs
- [VERIFICATION-DIRECTIVES.md](../VERIFICATION-DIRECTIVES.md) - sdqctl verify commands
- [traceability/refs-validation.md](../../../traceability/refs-validation.md) - Latest validation report
