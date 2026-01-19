# Code Reference Validation Report

Generated: 2026-01-19T19:27:05.821566+00:00

## Summary

| Metric | Count |
|--------|-------|
| Total References | 326 |
| Valid | 289 |
| Unknown Alias | 6 |
| Repository Missing | 0 |
| File Not Found | 16 |
| Path Not Found | 15 |

**37 broken references found.**

## Broken References

### Path Not Found (15)

- `mapping/cross-project/terminology-matrix.md` line 347: ``loop:Loop/Models/TemporaryScheduleOverride.swift``
  - Path not found: Loop/Models/TemporaryScheduleOverride.swift
- `mapping/cross-project/terminology-matrix.md` line 348: ``aaps:database/entities/ProfileSwitch.kt``
  - Path not found: database/entities/ProfileSwitch.kt
- `mapping/cross-project/terminology-matrix.md` line 349: ``trio:FreeAPS/Sources/Models/Override.swift``
  - Path not found: FreeAPS/Sources/Models/Override.swift
- `mapping/cross-project/terminology-matrix.md` line 1113: ``aaps:plugins/main/src/main/kotlin/.../smsCommunicator/``
  - Path not found: plugins/main/src/main/kotlin/.../smsCommunicator/
- `mapping/cross-project/terminology-matrix.md` line 1675: ``loopcaregiver:LoopCaregiverKit/Sources/.../Nightscout/OTPManager.swift``
  - Path not found: LoopCaregiverKit/Sources/.../Nightscout/OTPManager.swift
- `mapping/cross-project/terminology-matrix.md` line 1676: ``loopcaregiver:LoopCaregiverKit/Sources/.../Nightscout/NightscoutDataSource.swift``
  - Path not found: LoopCaregiverKit/Sources/.../Nightscout/NightscoutDataSource.swift
- `mapping/cross-project/terminology-matrix.md` line 1677: ``loopcaregiver:LoopCaregiverKit/Sources/.../Models/DeepLinkParser.swift``
  - Path not found: LoopCaregiverKit/Sources/.../Models/DeepLinkParser.swift
- `mapping/cross-project/terminology-matrix.md` line 1678: ``loopcaregiver:LoopCaregiverKit/Sources/.../Models/RemoteCommands/Action.swift``
  - Path not found: LoopCaregiverKit/Sources/.../Models/RemoteCommands/Action.swift
- `docs/_generated/refs-summary.md` line 25: ``loop:Loop/Models/Override.swift#L10-L50``
  - Path not found: Loop/Models/Override.swift
- `docs/10-domain/algorithm-comparison-deep-dive.md` line 487: ``loop:Loop/Managers/LoopDataManager.swift``
  - Path not found: Loop/Managers/LoopDataManager.swift
- `docs/10-domain/insulin-curves-deep-dive.md` line 280: ``aaps:plugins/insulin/src/main/kotlin/.../InsulinOrefBasePlugin.kt``
  - Path not found: plugins/insulin/src/main/kotlin/.../InsulinOrefBasePlugin.kt
- `docs/10-domain/insulin-curves-deep-dive.md` line 319: ``aaps:plugins/insulin/src/main/kotlin/.../InsulinOrefFreePeakPlugin.kt``
  - Path not found: plugins/insulin/src/main/kotlin/.../InsulinOrefFreePeakPlugin.kt
- `docs/10-domain/insulin-curves-deep-dive.md` line 414: ``aaps:plugins/aps/src/main/kotlin/.../OpenAPSSMBPlugin.kt``
  - Path not found: plugins/aps/src/main/kotlin/.../OpenAPSSMBPlugin.kt
- `docs/10-domain/devicestatus-deep-dive.md` line 796: ``loop:Loop/Models/StoredDosingDecision.swift``
  - Path not found: Loop/Models/StoredDosingDecision.swift
- `specs/openapi/aid-devicestatus-2025.yaml` line 144: `loop:NightscoutServiceKit/Extensions/StoredDosingDecision.swift`
  - Path not found: NightscoutServiceKit/Extensions/StoredDosingDecision.swift

### File Not Found (16)

- `mapping/cross-project/aid-controller-sync-patterns.md` line 461: ``trio:NightscoutTreatment.swift#L31``
  - File not found: NightscoutTreatment.swift
- `mapping/cross-project/aid-controller-sync-patterns.md` line 462: ``trio:NightscoutAPI.swift#L296-298``
  - File not found: NightscoutAPI.swift
- `mapping/cross-project/aid-controller-sync-patterns.md` line 463: ``loop:DoseEntry.swift#L39``
  - File not found: DoseEntry.swift
- `mapping/cross-project/aid-controller-sync-patterns.md` line 464: ``loop:DoseEntry.swift#L30-31``
  - File not found: DoseEntry.swift
- `mapping/cross-project/aid-controller-sync-patterns.md` line 465: ``aaps:InterfaceIDs.kt``
  - File not found: InterfaceIDs.kt
- `mapping/cross-project/aid-controller-sync-patterns.md` line 466: ``aaps:InterfaceIDs.kt#pumpId,pumpType,pumpSerial``
  - File not found: InterfaceIDs.kt
- `docs/README.md` line 252: ``loop:LoopKit/LoopKit/InsulinMath.swift#L45-L67``
  - File not found: LoopKit/LoopKit/InsulinMath.swift
- `docs/10-domain/entries-deep-dive.md` line 228: ``loop://iPhone``
  - File not found: //iPhone
- `docs/10-domain/algorithm-comparison-deep-dive.md` line 150: ``loop:LoopKit/LoopKit/InsulinKit/ExponentialInsulinModelPreset.swift``
  - File not found: LoopKit/LoopKit/InsulinKit/ExponentialInsulinModelPreset.swift
- `docs/10-domain/devicestatus-deep-dive.md` line 838: ``loop:NightscoutService/NightscoutServiceKit/NightscoutClient.swift``
  - File not found: NightscoutService/NightscoutServiceKit/NightscoutClient.swift
- `docs/60-research/controller-registration-protocol-proposal.md` line 122: ``loop:DoseEntry.swift#L39``
  - File not found: DoseEntry.swift
- `docs/60-research/controller-registration-protocol-proposal.md` line 123: ``aaps:InterfaceIDs.kt``
  - File not found: InterfaceIDs.kt
- `docs/60-research/controller-registration-protocol-proposal.md` line 124: ``trio:NightscoutTreatment.swift#L31``
  - File not found: NightscoutTreatment.swift
- `docs/60-research/controller-registration-protocol-proposal.md` line 132: ``loop://iPhone``
  - File not found: //iPhone
- `docs/60-research/controller-registration-protocol-proposal.md` line 133: ``openaps://phoneModel``
  - File not found: //phoneModel
- `docs/60-research/controller-registration-protocol-proposal.md` line 135: ``openaps://hostname``
  - File not found: //hostname

### Unknown Alias (6)

- `mapping/loopcaregiver/authentication.md` line 110: ``caregiver://``
  - Unknown alias 'caregiver'. Known aliases: aaps, crm, diable, loop, loopcaregiver, loopfollow, nightguard, nr, ns-connect, ns-gateway, ns-reporter, openaps, oref0, trio, xdrip, xdrip-js, xdrip4ios
- `mapping/loopcaregiver/authentication.md` line 423: ``caregiver://requestWatchConfiguration``
  - Unknown alias 'caregiver'. Known aliases: aaps, crm, diable, loop, loopcaregiver, loopfollow, nightguard, nr, ns-connect, ns-gateway, ns-reporter, openaps, oref0, trio, xdrip, xdrip-js, xdrip4ios
- `docs/cgm-remote-monitor-analysis-2026-01-18.md` line 6: ``https://github.com/bewest/cgm-remote-monitor-1.git``
  - Unknown alias 'https'. Known aliases: aaps, crm, diable, loop, loopcaregiver, loopfollow, nightguard, nr, ns-connect, ns-gateway, ns-reporter, openaps, oref0, trio, xdrip, xdrip-js, xdrip4ios
- `docs/_generated/refs-summary.md` line 21: ``alias:path/to/file.ext#anchor``
  - Unknown alias 'alias'. Known aliases: aaps, crm, diable, loop, loopcaregiver, loopfollow, nightguard, nr, ns-connect, ns-gateway, ns-reporter, openaps, oref0, trio, xdrip, xdrip-js, xdrip4ios
- `docs/10-domain/insulin-curves-deep-dive.md` line 148: ``xDrip:app/src/main/java/com/eveningoutpost/dexdrip/insulin/LinearTrapezoidInsulin.java``
  - Unknown alias 'xDrip'. Known aliases: aaps, crm, diable, loop, loopcaregiver, loopfollow, nightguard, nr, ns-connect, ns-gateway, ns-reporter, openaps, oref0, trio, xdrip, xdrip-js, xdrip4ios
- `docs/10-domain/insulin-curves-deep-dive.md` line 227: ``xDrip:app/src/main/res/raw/insulin_profiles.json``
  - Unknown alias 'xDrip'. Known aliases: aaps, crm, diable, loop, loopcaregiver, loopfollow, nightguard, nr, ns-connect, ns-gateway, ns-reporter, openaps, oref0, trio, xdrip, xdrip-js, xdrip4ios

## Known Aliases

| Alias | Repository |
|-------|------------|
| `aaps` | See workspace.lock.json |
| `crm` | See workspace.lock.json |
| `diable` | See workspace.lock.json |
| `loop` | See workspace.lock.json |
| `loopcaregiver` | See workspace.lock.json |
| `loopfollow` | See workspace.lock.json |
| `nightguard` | See workspace.lock.json |
| `nr` | See workspace.lock.json |
| `ns-connect` | See workspace.lock.json |
| `ns-gateway` | See workspace.lock.json |
| `ns-reporter` | See workspace.lock.json |
| `openaps` | See workspace.lock.json |
| `oref0` | See workspace.lock.json |
| `trio` | See workspace.lock.json |
| `xdrip` | See workspace.lock.json |
| `xdrip-js` | See workspace.lock.json |
| `xdrip4ios` | See workspace.lock.json |
