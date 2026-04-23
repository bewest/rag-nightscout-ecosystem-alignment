# EXP-2893 — Hyper-Side Channel Decomposition (SMB vs Basal vs User Bolus)

**Date:** 2026-04-22
**Stream:** Mechanism decomposition, hyper-correction side
**Status:** Confirms the oref0 asymmetry: no SMB channel at all →
legacy oref0 users are effectively open-loop on corrections.

## 1. Question

EXP-2892 decomposed hypo protection into `basal-cut`+`IOB-shed`.
The natural counterpart: during BG ascents into hyper range, how
is correction-insulin distributed across
  C. SMB (automatic microbolus)
  D. excess basal (TBR above scheduled)
  E. user bolus
by lineage?

## 2. Method

Detect contiguous windows of `glucose > 180`, trace back to the
local-min glucose within 60 min prior.  Define ascent window from
that pre-min to the peak.  Sum each channel over the window in
units of insulin (U):

    smb_U          = sum(bolus_smb)
    user_bolus_U   = sum(bolus) − sum(bolus_smb)
    excess_basal_U = sum(max(actual_rate − sched_rate, 0) · dt)

Require rise ≥ 20 mg/dL and duration 15–240 min.

## 3. Results

### 3.1  Fraction of hyper-correction by channel

| Lineage  | SMB | excess basal | user bolus |
| -------- | --- | ------------ | ---------- |
| **oref0 (legacy)** | **0.000** | 0.112 | **0.888** |
| Loop (iOS) | 0.422 | 0.100 | 0.478 |
| oref1 (modern) | 0.471 | 0.004 | 0.525 |
| unknown  | 0.367 | 0.002 | 0.631 |

**oref0 patients deliver ZERO SMBs across the entire dataset
(n=3 patients, ~hundreds of events).**  Legacy OpenAPS simply
lacks the SMB capability; the automatic correction channel is
absent.

### 3.2  Magnitude per ascent event (U)

| Lineage  | SMB_U | excess_basal_U | user_bolus_U |
| -------- | ----- | -------------- | ------------ |
| oref0 (legacy) | 0.00 | 0.36 | 2.99 |
| Loop (iOS) | 2.63 | 0.58 | 3.08 |
| oref1 (modern) | 2.63 | 0.02 | 3.03 |
| unknown | 1.98 | 0.01 | 3.03 |

oref1's excess-basal contribution is ~0 because SMB absorbs the
correction; Loop runs a small residual excess basal (0.58 U/event
average) in addition to SMB-equivalents.

### 3.3  Lineage × tercile

No evidence of Simpson confound.  oref0's frac_smb = 0 at every
tercile; oref1's frac_smb is tercile-independent at ~0.43–0.55.

## 4. Mechanism synthesis — both sides together

| | Hypo protection (EXP-2892) | Hyper correction (EXP-2893) |
| - | ---------------------------- | --------------------------- |
| **oref0** | basal-cut utilization 20 % at conservative; no IOB-shed substitute | zero SMB; user bolus carries 89 % |
| **Loop** | basal-cut 86-95 %; rises with aggressiveness | SMB 42 %, small excess basal 10 %, user 48 % |
| **oref1** | basal-cut 92 % setting-independent; large IOB-shed | SMB 47 %, negligible excess basal, user 53 % |

oref0's conservative-user failure mode is now fully characterised:
- **Hypo side**: algorithm doesn't engage basal-cut (20 % utilization)
- **Hyper side**: algorithm has no SMB channel at all
- **Net**: the conservative-oref0 user is operating closer to
  open-loop than to a closed-loop AID.

## 5. Actionable advice — composed across 2891/2892/2893

### 5.1  For legacy-oref0 forks

Two channels are missing from the algorithm:
1. **SMB capability** entirely (backport from oref1).
2. **Basal-cut responsiveness** at conservative profiles
   (settings-agnostic suspension trigger).

Either fix independently provides some improvement; both together
close the lineage gap.

### 5.2  For users

Conservative oref0 users should understand their system: during
hyper events the algorithm will not bolus for them.  They must
manually correct.  Migration to AAPS/Trio gives automatic
correction for free.

### 5.3  For AID-author metric reporting

Publishing only “time in range” conceals algorithm-level
differences.  A transparent mechanism report would include:
- basal-cut utilization ratio (EXP-2892)
- SMB fraction of correction (EXP-2893)
- counterfactual protection (EXP-2889)
Each patient's AID performance can then be audited against the
cohort's channel distribution.

## 6. Caveats

- `bolus_smb` column must be correctly tagged; we verified it is
  zero for oref0 across every ascent (n>500 per patient) — unlikely
  to be a tagging artefact.
- Loop's `bolus_smb` captures Loop ≥ 3.x “automatic bolus”; prior
  Loop versions would show frac_smb = 0.  Cohort lineage labels
  collapse these.
- n = 3 oref0 patients limits across-lineage claims at tercile
  level.  Within-lineage claim (oref0 frac_smb = 0 always) is
  robust because it holds for every event in every patient.

## 7. Methodology note

EXP-2893 extends **technique §2.10 (capacity-vs-utilization)** to
the hyper side and reveals a stronger pattern: sometimes the
diagnosis is "channel absent," not "channel under-utilized."
Distinguishing these matters for remediation — absent-channel
requires a code change (port SMB logic), under-utilized channel
is a tuning change.

## 8. Next

- Vignette for `odc-86025410` — the conservative oref0 patient
  with 58 % observed severe-hypo rate and zero SMB correction
- EXP-2894 — does Loop's "automatic bolus" (frac_smb 0.42) behave
  more like SMB or more like basal?  Would inform Loop ↔ oref1
  comparability

## 9. Artifacts

- `tools/cgmencode/exp_hyper_channels_2893.py`
- `externals/experiments/exp-2893_hyper_channels.parquet`
- `externals/experiments/exp-2893_hyper_channels_summary.json`
- `docs/60-research/figures/exp-2893_hyper_channels.png`
