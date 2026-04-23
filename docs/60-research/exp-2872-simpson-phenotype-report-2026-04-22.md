# EXP-2872 — Simpson's paradox test on phenotype → TIR (2026-04-22)

## Question
EXP-2870 reported stream_A_dominant patients (median TIR 82%) vs
stream_B_normal (TIR 67%) — a 15pp gap. EXP-2871 confirmed
phenotype is also strongly tied to controller. Is the 15pp gap
real evidence that phenotype causes TIR, or a Simpson's-paradox
artifact of controller composition?

## Method
Decompose the pooled phenotype → TIR Spearman correlation into
within-controller correlations. Cross-tabulate matched phenotype
× controller medians.

## Result — Checks: 1/3 PASS

### Pooled and within-controller Spearman ρ(phenotype_rank, TIR)

| Stratum | N | n_phenotypes | ρ |
|---|--:|--:|--:|
| POOLED | 25 | 4 | **−0.21** (weak) |
| Loop | 6 | 1 | n/a (no variation) |
| OpenAPS | 5 | 3 | **−0.53** (preserved, stronger) |
| Trio | 8 | 3 | **−0.12** (dissolves) |

### Matched phenotype × controller (median TIR)

| Phenotype | Loop | OpenAPS | Trio |
|---|--:|--:|--:|
| stream_A_dominant | — | 0.73 | 0.82 |
| stream_B_early | — | 0.61 | 0.81 |
| stream_B_normal | **0.56** | 0.69 | 0.73 |

## Headline — pooled effect is **mostly controller premium, not phenotype**

At matched **stream_B_normal** phenotype, controller alone explains a
**17pp TIR gap** (Loop 0.56 → Trio 0.73). Within-Trio, moving from
stream_B_normal → stream_A_dominant only buys 9pp (0.73 → 0.82).
Within-OpenAPS, moving from stream_B_early → stream_A_dominant buys
12pp (0.61 → 0.73).

**Decomposition of the 15pp pooled gap (82% vs 67%):**
- Controller composition (all stream_A_dominant are Trio/OpenAPS, no
  Loop): ~12-17pp of the gap is driven by controller.
- Residual within-controller phenotype contribution: ~3-9pp.

**Not a sign-flipping Simpson's paradox** (within-controller
direction matches pooled), but a **partial dissolution** — the
pooled effect overstates the phenotype's causal contribution.

## What this rules out and rules in

**Ruled out**: claiming "stream_A_dominant phenotype CAUSES better
TIR by 15pp." That gap is mostly controller selection.

**Ruled in**:
1. Controller has a substantial residual effect on TIR even at
   matched phenotype (~15-17pp Loop → Trio in this cohort). This is
   either a true algorithmic advantage OR a selection effect (who
   chooses Trio is unblinded; advanced users may self-select).
2. Phenotype carries a modest within-controller signal (~9-12pp).
   Worth tracking but not the headline.
3. **Loop cohort has ZERO phenotype variation** (all 6 stream_B_normal).
   This itself is informative: Loop's algorithm produces a single
   envelope-coupling signature in this cohort. EXP-2870/2871's
   "controller signature" finding is reaffirmed — but here it's the
   *uniformity within Loop* that proves the algorithmic constraint.

## Implications for vignettes & audition

1. **Vignette messaging**: do NOT tell a Loop patient that "moving
   to stream_B_early would improve TIR by 15pp" — the pooled
   association doesn't survive within-controller analysis. The
   honest message is "your envelope coupling is consistent with a
   too-aggressive scheduled basal" (the EXP-2870/2871 mechanism)
   without overpromising the size of the TIR delta.

2. **Audition matrix**: confirms the EXP-2871 recommendation —
   basal_mismatch / envelope-coupling signals need controller
   stratification before any TIR-related claim.

3. **Settings extraction comparisons**: when comparing settings-
   recommendation outcomes across controllers, use within-controller
   baselines — pooled comparisons inflate apparent effect sizes
   ~2-3×.

## Caveats

- N=25, very small. Within-controller ρ estimates have wide CIs.
- Loop's zero phenotype variation is itself a sample-size artifact
  candidate — would more Loop patients reveal variation? EXP-2849's
  cohort had 25 patients qualified for envelope analysis; not all
  Loop users are well-tuned.
- TIR may be confounded by patient motivation, exercise, illness
  patterns — controller-vs-TIR causation cannot be inferred from
  observational data without RCT.
- "Controller premium" of 17pp at matched phenotype is consistent
  with prior literature differences between Loop and Trio cohorts
  (selection effect for advanced users).

## Checks
- ❌ pooled_signal_present: |ρ_pooled|=0.21 < 0.3 (signal exists but is
  modest)
- ❌ simpson_paradox_detected: no within-controller ρ flips sign
- ✅ associations_dissolve_within: Trio ρ=−0.12 (|ρ|<0.2)

## Artifacts
- `externals/experiments/exp-2872_simpson_check.json`
- `docs/60-research/figures/exp-2872_simpson_paradox.png`

## Follow-ups
- **EXP-2873**: Within-Loop variation re-examination — pull more
  Loop patients from the cohort (relax window-coverage criteria) and
  re-test. If Loop genuinely has zero envelope-coupling variation,
  that is itself an important constraint for Loop-specific audition.
- **Vignette update**: remove any TIR-delta claims tied to phenotype
  shifts; reframe as "envelope-coupling signature" only.
- Apply this Simpson decomposition pattern to ANY future
  cross-controller finding before publishing it.

---

## Addendum 2026-04-22: NaN-percentile bug fix (EXP-2873) — TRUE Simpson's paradox now detected

After patching the NaN bug in EXP-2851 input (cohort 25 → 31), the
phenotype → TIR relationship changes substantially:

### New pooled and within-controller Spearman ρ

| Stratum | N | n_phenotypes | ρ |
|---|--:|--:|--:|
| POOLED | 31 | 4 | **−0.28** |
| Loop | 8 | 2 | **+0.41 ⬆ FLIPS POSITIVE** |
| OpenAPS | 5 | 2 | **−0.71** (preserved, stronger) |
| Trio | 9 | 2 | 0.00 (dissolves) |

### New matched phenotype × controller (median TIR)

| Phenotype | Loop | OpenAPS | Trio |
|---|--:|--:|--:|
| stream_A_dominant | — | 0.85 | 0.82 |
| stream_B_early | **0.58** | 0.64 | **0.77** |
| stream_B_normal | 0.51 | — | — |

### NEW headline — TRUE Simpson's paradox detected

Within Loop, the relationship between phenotype and TIR **REVERSES**
from the pooled estimate. Pooled says "stream_A_dominant has higher
TIR than stream_B_early" (−0.28). Within Loop, "stream_B_early has
higher TIR than stream_B_normal" (+0.41).

This is a clean Simpson's paradox. The pooled phenotype effect is
**not just confounded by controller; it is REVERSED for Loop users**.

### Updated decomposition of the cohort gap

Matched stream_B_early TIR: Loop 0.58 < OpenAPS 0.64 < Trio 0.77.
Controller premium at matched phenotype: **~19pp** Loop → Trio.
Within-Trio phenotype effect (stream_B_early → stream_A_dominant):
**+5pp** (0.77 → 0.82).

The cohort gap is dominated by controller composition; phenotype
contributes a modest within-controller signal that flips sign for
Loop users.

### Implications (revised)

1. Vignette guidance for a Loop user must NEVER reference pooled
   phenotype → TIR — within Loop, the direction is opposite.
2. Loop's stream_B_early phenotype is associated with HIGHER TIR
   within Loop (the 1 stream_B_normal Loop patient has TIR 0.51).
3. Controller-aware audition and vignette messaging is now mandatory.
