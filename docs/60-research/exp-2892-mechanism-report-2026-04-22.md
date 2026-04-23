# EXP-2892 — Protection-Mechanism Signature by Lineage

**Date:** 2026-04-22
**Stream:** Mechanism decomposition of EXP-2891's lineage effect
**Status:** Root cause of conservative-oref0 exposure identified —
**channel utilization** (not ceiling) is the differentiator.

## 1. Question

EXP-2891 showed three distinct lineage signatures.  Is the failure
of conservative-oref0 users (protection 0.125) caused by
  (a) low basal-cut ceiling (conservative setting → small cut
      magnitude even at 100% utilization), or
  (b) low utilization of the available ceiling (algorithm fails
      to respond aggressively when BG falls)?

The distinction matters: (a) is a user-settings problem, (b) is an
algorithm problem.

## 2. Method

Decompose each descent event into two protective channels, both
expressed in mg/dL via ISF_pop = 50:

    channel_A (basal-cut) = (sched − actual)·duration · ISF
    ceiling_A            = sched · duration · ISF        (max possible)
    channel_B (IOB-shed) = (iob_start − iob_nadir) · ISF

    utilization_A = channel_A / ceiling_A

## 3. Results

### 3.1  Utilization by lineage × tercile

| Lineage  | conservative | moderate | aggressive |
| -------- | ------------ | -------- | ---------- |
| **oref1**  | **0.923** | 0.914 | 0.930 |
| Loop     | 0.863 | 0.907 | 0.954 |
| unknown  | 0.902 | — | 0.911 |
| **oref0**  | **0.198** | 0.649 | 0.747 |

**oref1 runs ~92% basal-cut utilization at every aggressiveness
level.**  Loop and unknown cluster similarly high.  oref0 is
qualitatively different: 20% utilization at conservative, rising
to 75% at aggressive — **it never reaches the oref1 pattern**.

### 3.2  Ceiling vs utilization — the decisive contrast

At the conservative tier, `ceiling_A` is essentially identical
across lineages (oref0 = 16.9 mg/dL, oref1 = 17.9, Loop = 29.8).
The user setting provides the same maximum protection *capacity*.
What differs is how much of that capacity is used:

| Tier = conservative | ceiling_A | cut_A (used) | util | prot |
| ------------------- | --------- | ------------ | ---- | ---- |
| oref1               | 17.9      | 16.4         | 92 % | 0.63 |
| oref0               | 16.9      | 3.4          | 20 % | 0.13 |

Same ceiling; oref0 leaves 80% of the protective channel unused.

### 3.3  IOB-shed (channel B)

Conservative-tier IOB shed: oref1 = 34.9, oref0 = 6.07.  At the
*same user-aggressiveness tier*, oref1 sheds **5.7×** more IOB
during descents.  SMB-off / zero-temp / suspension logic engages
much more aggressively on oref1.

### 3.4  Correlation caveat

Across the cohort, ρ(ceiling_A, protection) = 0.15 (n.s.),
ρ(utilization, protection) = 0.17 (n.s.), ρ(shed_B, protection) =
0.10 (n.s.).  The signal is **categorical, not scalar** —
utilization separates oref0-conservative (0.20) from everyone else
(0.86–0.92) but within each lineage the protection–utilization
relationship is weak because other factors dominate.

Interpretation: lineage chooses the *operating point* on the
utilization curve; within a lineage, utilization is approximately
flat and protection varies with other factors (phenotype, TOD,
meal context).

## 4. Mechanism synthesis

| Lineage | Basal-cut utilization | IOB-shed magnitude | Characterisation |
| ------- | --------------------- | ------------------ | ---------------- |
| oref1   | ~92 %, tercile-independent | large, tercile-independent | **Responsive algorithm**; protection ≈ ceiling-limited |
| Loop    | 86–95 %, rises with aggressiveness | largest absolute; rises steeply | Responsive; protection also grows with scheduled basal |
| unknown | ~91 %, tercile-independent | moderate | Likely oref1-class (AAPS or late Trio) |
| oref0   | **20 % at conservative**, rises to 75 % | very small at conservative (6 mg/dL) | **Under-responsive algorithm**, not a ceiling problem |

The conservative-oref0 failure is an **algorithm** failure, not a
settings failure.  Increasing scheduled basal would raise the
ceiling, but it wouldn't fix the 20% utilization rate — the
algorithm doesn't engage the basal-cut channel quickly enough
during descent.

## 5. Actionable advice — refined from EXP-2891

### 5.1  For oref0 maintainers / forks

The conservative-user exposure has a specific mechanism: **the
basal-cut logic doesn't fire quickly enough when BG drops from
a low-basal baseline.**  Plausible root causes:

- `microbolus` threshold too tight (legacy default assumes
  reasonably-sized basal to cut against)
- Zero-temp fallback absent or gated on higher BG thresholds
- Prediction window too short — doesn't see the descent in time

Backport candidates from oref1:
- `smb_delivery_ratio` downscaling during descent
- `maxSMBBasalMinutes` hard cap
- `enableUAM`-style reactive carb/descent detection

Feasibility: these are porting targets, not rewrites.  A
utilization-curve plot (EXP-2892's fig. 1) across a legacy-oref0
test cohort would validate any backport.

### 5.2  For conservative oref0 users

Protection deficit will not be fixed by tuning settings more
aggressively on the same algorithm.  Utilization is the limiter.
Migration to AAPS/Trio (oref1) or Loop gives a step-change
improvement (0.13 → 0.63+).

### 5.3  For Loop users at conservative settings

Utilization is already high (86%); protection gains from
aggressiveness (0.49 → 0.58) come from ceiling increase rather
than utilization increase.  This is a gentler dose-response than
oref0 but still not flat like oref1.

## 6. Caveats

- Uniform ISF = 50; EXP-2890 confirmed rank-stability under the
  30–100 sweep, so utilization ratios (which cancel ISF) are
  particularly robust.
- Duration estimate uses average descent slope; a short,
  steep-then-flat descent would be mis-attributed.
- `channel_B` (IOB-shed) is a post-hoc metric; it does not
  separate SMB-off from prior-IOB-drift.  A refinement would use
  5-min temp-basal rate trace (available in treatments.json for
  some patients).

## 7. Methodology contribution

EXP-2892 illustrates **decomposition-into-channels** as a
technique for distinguishing settings-limited from
algorithm-limited outcomes.  Add to the deconfounding toolkit as
technique §2.10: "capacity vs utilization decomposition for
outcomes gated by a scheduled-resource ceiling."

## 8. Next

- **EXP-2893**: extend channel decomposition to the hyper-ceiling
  (SMB magnitude vs SMB ceiling) — completes the bidirectional
  mechanism map
- **Vignette: `odc-86025410`** — concrete safety story for a
  conservative-oref0 user with 58% observed severe hypo rate and
  20% utilization

## 9. Artifacts

- `tools/cgmencode/exp_mechanism_2892.py`
- `externals/experiments/exp-2892_mechanism.parquet`
- `externals/experiments/exp-2892_mechanism_summary.json`
- `docs/60-research/figures/exp-2892_mechanism.png`
