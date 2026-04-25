# EXP-2990: Loop SMB-gating code lookup (marker)

**Date**: 2026-04-23
**Audience**: open-source AID code authors.
**Scope**: trace the source-level gates in Loop / LoopAlgorithm that
produce >98% SMB suppression at 70-100 mg/dL among Loop_AB_ON peers
c, d, e, g (vs outlier patient i). Cite file:line for each gate and
map to the data signature.
**What this is NOT**: not a runtime trace; not a re-derivation of
EXP-2987's behavioral results; not a recommendation for Loop's
defaults.

---

## Headline

**POSITIVE.** The dominant gate is **G4** in
`externals/LoopAlgorithm/Sources/LoopAlgorithm/LoopAlgorithm.swift:419-423`:

```swift
if case .aboveRange(min: let min, correcting: _, minTarget: let minTarget, units: _) = correction,
    min.quantity < minTarget
{
    deliveryMax = 0
}
```

When current BG sits in 70-100 mg/dL with a typical 100 mg/dL
correction-range floor, the predicted minimum almost always dips below
that floor — even if eventual glucose forecasts a rise. `deliveryMax`
is forced to 0 and `asPartialBolus` returns 0 ⇒ SMB suppressed. This
single rule maps cleanly to the observed >99% peer-suppression of
*eligible* cells (no override, no recent carbs, IOB below patient-95th
percentile).

A secondary gate, **G1** (suspend-threshold short-circuit at
`DoseMath.swift:207-210`), trips whenever any predicted value falls
below the user's suspend threshold (default 67-80 mg/dL) — common in
the 70-100 band.

---

## All five suppression gates (full deep-dive in `docs/10-domain/`)

| ID | Gate | File:lines |
|----|------|------------|
| G1 | Suspend-threshold short-circuit | `LoopAlgorithm/.../DoseMath.swift:207-210` |
| G2 | `.entirelyBelowRange` short-circuit | `LoopAlgorithm/.../DoseMath.swift:269-283` |
| G3 | `.inRange` (no correction) | `LoopAlgorithm/.../DoseMath.swift:293-295` |
| G4 | **Predicted-min < minTarget zero-clamp** | `LoopAlgorithm/.../LoopAlgorithm.swift:419-423` |
| G5 | GBAF 0.20 floor + pump rounding | `Loop/.../GlucoseBasedApplicationFactorStrategy.swift:14-41` |

Plus the IOB-headroom amplifier
(`LoopAlgorithm.swift:415-417`): when active IOB ≥ `maxBolus * 2`,
deliveryMax floors at 0 regardless of glucose state.

Full context, hypothesis testing, and AID-author actions are in
`docs/10-domain/loop-smb-gating-deep-dive-2026-04-23.md`.

---

## Implication for the patient-i mystery

Of the four EXP-2987 levers ruled out, none touched G4. The remaining
patient-i-vs-peers asymmetry is now narrowed to **G1 + G4 + maxBolus**
configuration — the "policy conservatism" dial that EXP-2991 quantifies
empirically and EXP-2993 stratifies outcomes against.

---

## Verdict

POSITIVE — single dominant code gate identified
(`LoopAlgorithm.swift:419-423`), mapped to data signature, with full
five-gate enumeration and AID-author actions in the deep-dive.
