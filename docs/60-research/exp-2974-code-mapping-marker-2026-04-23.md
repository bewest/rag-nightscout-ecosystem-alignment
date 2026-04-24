# EXP-2974 — Code-side SMB emission policy mapping (marker)

## Scope
Marker for EXP-2974 number reservation. The substantive deliverable
is the domain deep-dive at:

  `docs/10-domain/smb-emission-policy-deep-dive-2026-04-23.md`

## What this is NOT
Not a data analysis. Not a per-patient finding.

## Summary
EXP-2974 is a **source-code lookup**, not a data experiment. It
maps the data-side findings of EXP-2966 / EXP-2971 / EXP-2972 /
EXP-2973 to the specific code paths in
`externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift`,
`externals/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift`,
`externals/LoopWorkspace/Loop/Loop/Models/GlucoseBasedApplicationFactorStrategy.swift`,
`externals/AndroidAPS/plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/DetermineBasalSMB.kt`,
and `externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/aps/SMBDefaults.kt`.

See the deep-dive for the full mapping, lever-priority list, and
file:line citations.

## Provenance
- Date: 2026-04-23
- No script (code-only deliverable).
