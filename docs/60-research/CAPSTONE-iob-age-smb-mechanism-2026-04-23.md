# IOB-Age and SMB-Emission Mechanism: A Comparative Study of AID Controllers

**Date**: 2026-04-23
**Audience**: open-source AID code authors (Loop, Trio, AAPS, OpenAPS,
xDrip+, Nightscout) and AID researchers building per-design audition,
Insights, or guard-rail features.

> **What this is NOT**
>
> - This is **not** therapy advice. It is **not** a recommendation for
>   any individual patient to switch settings, switch AID, or change
>   their care plan.
> - This is **not** a recommendation of one AID over another. The
>   results characterise *mechanisms* the controllers use; they do
>   not rank controllers as "better" for users.
> - This is **not** a clinical study. It is observational analysis of
>   a 19-patient cohort with known `algorithm_mode` (24 total in the
>   parquet that ships with `tools/cgmencode`; 5 excluded for
>   unknown-mode), intended to inform code-level design and audition
>   heuristics.
> - All controller-emitted variables (basal cuts, SMB delivery, IOB
>   trajectory) are subject to reverse-causation when used as
>   regression predictors. Within-patient claims are confined to the
>   hypo channel where reverse-causation does not apply (EXP-2954);
>   between-design claims are explicitly framed as such.

---

## Cohort

| algorithm_mode | n | source |
|---|---:|---|
| Loop-AB-ON     | 5 | iOS Loop with auto-bolus enabled (c, d, e, g, i) |
| Loop-AB-OFF    | 2 | iOS Loop, temp-basal only (a, f) |
| Trio-oref1     | 9 | Trio (iOS, oref1 lineage) |
| AAPS-oref0     | 3 | AAPS-Android, oref0-algorithm (no SMB; relabelled EXP-2986) |
| (excluded: unknown-mode) | 5 | telemetry insufficient to assign mode |

**Cohort gap**: AAPS-oref1 = 0 patients. Trio-vs-AAPS platform isolation
within oref1 cannot be performed with this cohort (EXP-2986/2989/2992).

**Window classes used in the framework**:
- **PP** — post-prandial: cells within 0–180 min after a carbs entry.
- **Sustained-high** — BG > 200 mg/dL with no carbs in prior 120 min.
- **Hypo descent** — pre-nadir descent into BG < 70 mg/dL, with the
  nadir cell anchoring the window.

---

## Section 1 — Framework summary

The IOB-age framework, in one paragraph:

> **The same IOB value can be a hazard or a buffer depending on its
> age relative to the response window.** Fresh IOB (recently delivered,
> pre-peak action) drives BG down regardless of basal-cut posture.
> Stale IOB (post-peak, gracefully decaying) is a buffer rather than
> a driver. Controllers that **predict-and-fire on rising velocity
> early** age their IOB before the BG response window arrives — IOB
> is near peak action when needed (PP TIR, sustained-high recovery)
> and past peak action when defended against (hypo descent). Controllers
> that fire *reactively* — even with aggressive basal cuts — have
> *fresh* IOB at the moment they need to defend against hypoglycaemia,
> and reactive cutting cannot substitute. This single principle unifies
> the three independent window-class outcomes (PP TIR, sustained-high
> recovery, hypo descent TBR) that previously appeared to be unrelated.

Why it matters for AID design: the framework promotes
**predictive-emission timing** (lever 3 below) above the more obvious
**defensive basal cutting** (lever 5) in the design priority order.
It also reframes the Loop-vs-Trio question from "which is more
aggressive?" to "which mechanism does each design use to achieve a
similar overall SMB delivery, and what guard-rails does each
mechanism need?" (See Section 3.)

---

## Section 2 — 34 evidence lines

Compact roll-up of the synthesis Section 9 evidence lines plus the
two added by this capstone batch.

### Between-design lines

| # | Line | Source |
|---|---|---|
| 1 | Cross-cohort match (oref0 ≈ Loop-AB-OFF at no-SMB floor) — selection-bias rejected | EXP-2942 |
| 2 | Variance decomposition η² = 0.640 design-dominated | EXP-2943 |
| 3 | True-IOB sustained-high mechanism (iob_delta gap +1.18 U) | EXP-2944 |
| 4 | IOB-timing PP cross-window (Loop iob-vs-bg-peak lead −35 vs Trio −55 min) | EXP-2946 |
| 5 | Hypo IOB-age (Loop more cuts/decay yet 2× severe-hypo) | EXP-2947 |
| 6 | Uniform biexponential action-curve replicates iob_delta gap independent of grid bookkeeping (p = 9.5e-21) | EXP-2950 |

### Within-patient (gold-standard) lines

| # | Line | Source |
|---|---|---|
| 7 | 19/19 patients negative slope on `bg_min ~ synth_act_entry` at hypo (sign p = 1.9e-06; 15/19 individually p < 0.05) | EXP-2954 |
| 8 | Action-curve sensitivity sweep: 9/9 combos peak{60,75,90}×DIA{240,300,360} confirm ordering at sustained-high | EXP-2957 |

### Mechanism decomposition lines

| # | Line | Source |
|---|---|---|
| 9 | Forward velocity-coupling at PP — pooled total slope oref1 1.36 vs Loop_AB_ON 0.62 (initial finding, later corrected) | EXP-2960 |
| 10 | Velocity-coupling persists outside meals — controller property, not meal-detection artefact | EXP-2961 |
| 11 | Per-patient PP coupling sign-test p = 0.0039; pooled headline corrected | EXP-2962 |
| 12 | oref0 anomaly resolved — single-patient bolus-channel artefact | EXP-2963 |
| 13 | **SMB-channel velocity-coupling near-tie at PP** (Loop +0.380 vs Trio +0.361, CIs overlap); the +0.62 vs +1.36 difference lived in the user-bolus channel | EXP-2964 |
| 14 | Per-patient SMB-channel near-tie at PP confirmed (MWU p = 0.36) | EXP-2969 |
| 15 | Sustained-high mean dose Loop ≈ 2.06 U vs Trio ≈ 1.26 U / 60-min window | EXP-2970 |
| 16 | BG-band sweet spot 70–100 mg/dL (no-carb context) | EXP-2966 |
| 17 | Loop > Trio SMB slope at every BG band, no-carb pooled, disjoint CIs (per-patient still underpowered) | EXP-2966 |
| 18 | Lever decomposition: **Trio = frequency lever** (em_rate scales 0.048→0.097 with velocity, ~flat magnitude); **Loop = magnitude lever** (mean_em scales 0.19→0.36 U with velocity, ~flat em_rate) | EXP-2972, EXP-2973 |
| 19 | U-shape positive curvature confirmed for both designs in no-carb context | EXP-2975 |
| 20 | U-shape persists across meal context (PP also U-shaped) | EXP-2976 |

### Outcome-linkage lines

| # | Line | Source |
|---|---|---|
| 21 | Mechanism→outcome direction: magnitude → faster recovery + higher overshoot, frequency → slower + tighter (single-patient Loop arm caveat) | EXP-2979 |
| 22 | EXP-2979 directional claim is `i`-driven; band-representativeness re-validates direction | EXP-2985 |
| 23 | Within-Loop_AB_ON: **conservative Pareto-dominates aggressive** on every outcome axis; trade-off hypothesis REJECTED | EXP-2993 |

### Robustness / null lines

| # | Line | Source |
|---|---|---|
| 24 | Per-patient sustained-high Trio em_rate audit: 9/9 fire SMB; no patient has gate-off pattern | EXP-2978 |
| 25 | No empirical IOB-stacking ceiling for Trio in observed range; existing `maxIOB` already gates the danger zone | EXP-2983 |
| 26 | Loop_AB_ON SMB-at-low-BG is policy-bimodal: 4/5 suppress, 1 (`i`) fires aggressively | EXP-2981 |

### Code-path mapping lines

| # | Line | Source |
|---|---|---|
| 27 | Code mapping: oref1 `enable_smb()` + `SMBInterval=3min`; Loop `partialApplicationFactor` × `partialDose`; full file:line refs | EXP-2974 → `docs/10-domain/smb-emission-policy-deep-dive-2026-04-23.md` |
| 28 | Loop SMB suppression at 70–100 maps to Gate G4 (`LoopAlgorithm.swift:419-423`) and Gate G1 (`DoseMath.swift:207-210`) | EXP-2990 → `docs/10-domain/loop-smb-gating-deep-dive-2026-04-23.md` |

### Honest-reversal lines

| # | Line | Source |
|---|---|---|
| 29 | Within-patient PP signal collapses with multi-factor (carbs + bg_entry); IOB-age claim narrowed to hypo channel | EXP-2955 |
| 30 | EXP-2960 was driven by the USER-bolus channel; controller-channel comparison is a near-tie at PP | EXP-2964 |
| 31 | Linear PAF cap sweep does not reduce overshoot in endogenous-rise stratum — wrong lever | EXP-2982 |
| 32 | "OpenAPS / oref0 (legacy)" arm is actually AAPS-platform / oref0-algorithm; platform ≠ algorithm | EXP-2986 (+ schema fix EXP-2992) |

### New lines added by this capstone batch

| # | Line | Source |
|---|---|---|
| 33 | Patient `g` sweet-spot is reproducible across 27 weeks (TIR CV 0.14, overshoot std 0.06); distinguishing settings signature is observable on tunable pump axes (`bolus_smb_p95` ≈ 0.55 vs peer 0.95; `basal_frac_of_tdd` ≈ 0.06 vs peer 0.26) — tunable target rather than idiosyncratic | EXP-2994 |
| 34 | EXP-2886 phenotype clusters partially align with `algorithm_mode` (Cramér's V 0.56). `braking_ratio` is mostly algorithm-driven (η² 0.65; within-mode std 0.10–0.32 vs overall ≈ 1.0); `stack_score` and `hidden_leverage` are genuine patient heterogeneity that cross-cuts mode (η² 0.04, 0.09); `counter_reg_intercept` weakly aligns (η² 0.22) | EXP-2995 |

**Evidence-line count: 34** (was 32 before this batch).

---

## Section 3 — Mechanism decomposition (Loop vs Trio)

Two SMB-equipped controllers achieve **comparable directional
SMB-on-velocity behaviour** at the 70–100 mg/dL no-carb sweet spot
via **complementary mechanisms**.

### Loop = magnitude lever

- Per-event SMB size scales with rising velocity:
  `mean_em = 0.19 → 0.36 U` from stable to rising (1.9× scaling).
- Emission rate is approximately constant
  (`em_rate ~ 0.039` cells/cycle).
- U-shape vertex at BG ≈ 214 mg/dL, sharp curvature
  (`c = +9.4e-6`, `z = +9.2`), with meaningful re-engagement at
  260–300 mg/dL.

Code path (citation file:line):

- `externals/LoopAlgorithm/Sources/LoopAlgorithm/DoseMath.swift:101`:
  `units = (predictedBG − target) / ISF` carries momentum directly
  into the SMB magnitude — magnitude scaling is *mechanical*, not a
  separate heuristic.
- `externals/LoopAlgorithm/.../GlucoseBasedApplicationFactorStrategy.swift:14`:
  `partialApplicationFactor` ∈ {0.20, 0.40, 0.80} attenuates the
  per-cycle dose. In Constant mode it is fixed at 0.40; in GBAF mode
  it slides with predicted BG.
- `externals/LoopAlgorithm/Sources/LoopAlgorithm/LoopAlgorithm.swift:419-423`
  (Gate G4): if `correction == .aboveRange` AND predicted minimum <
  `correctionRange.lowerBound`, then `deliveryMax = 0` ⇒ SMB suppressed.
  This gate is the *dominant* SMB suppressor at 70–100 mg/dL among
  Loop_AB_ON peers (EXP-2990).
- `externals/LoopAlgorithm/.../DoseMath.swift:207-210`
  (Gate G1): short-circuits to `.suspend` if any predicted value falls
  below `suspendThreshold`.

### Trio = frequency lever

- Emission rate scales with rising velocity:
  `em_rate = 0.048 → 0.097` from falling to rising (2.0× scaling).
- Per-event SMB size is approximately constant
  (`mean_em ~ 0.169 U`).
- U-shape vertex at BG ≈ 347 mg/dL (out of practical range), nearly
  monotonically decreasing slope from 85 to 280 mg/dL
  (`c = +2.8e-6`, `z = +3.15`).

Code path (citation file:line):

- `externals/AndroidAPS/.../DetermineBasalSMB.kt:1101`: `SMBInterval =
  3 min` cycle-frequency floor.
- `externals/AndroidAPS/.../DetermineBasalSMB.kt:66`: `enable_smb()`
  gate requires `enableSMB_always` in no-carb context.
- `externals/AndroidAPS/.../DetermineBasalSMB.kt:1065`:
  `microBolus = min(insulinReq/2, basal × maxSMBBasalMinutes / 60)`
  — hard `/2` per-event ceiling and a basal-rate-derived absolute
  cap.

### Side-by-side numbers

| | Loop AB-ON | Trio-oref1 |
|---|---:|---:|
| em_rate (no-carb 70–100, cells/cycle)            | 0.039 | 0.080 |
| mean per-event SMB size                          | 0.244 U | 0.169 U |
| total per-cell SMB delivery                      | 0.0094 U | 0.0135 U |
| sustained-high mean dose / 60-min window         | ~2.06 U | ~1.26 U |
| velocity scaling channel                         | magnitude | frequency |
| U-shape vertex                                   | 214 mg/dL | 347 mg/dL |

The total per-cell SMB delivery (0.0094 vs 0.0135 U) is within
1.4× — comparable. Loop achieves it with fewer-but-bigger events,
Trio with more-and-smaller events. **Per-mechanism guard-rails differ**
(Section 6).

### Cross-reference deep-dives

- `docs/10-domain/smb-emission-policy-deep-dive-2026-04-23.md` —
  five-gate enumeration, IOB-headroom amplifier, full code refs.
- `docs/10-domain/loop-smb-gating-deep-dive-2026-04-23.md` —
  G1–G5 enumeration with example traces.

---

## Section 4 — Outcome linkage

### Mechanism → outcome direction

EXP-2979 confirms the directional prediction at the rising-70-100
stratum (no carbs, BG climbing into the sweet spot):

| Design | per-event SMB | TTT median | overshoot 60-min | hypo 60-min |
|---|---:|---:|---:|---:|
| Loop AB-ON (single-patient, `i`) | 0.40 U | 10 min | **10.7%** | 12.7% |
| Trio-oref1 (pooled)              | 0.15 U | 15 min | 3.5%      | **18.4%** |

**Magnitude → faster return-to-target + higher overshoot.**
**Frequency → slower return-to-target + higher hypo exposure.**

Caveat: the Loop arm is single-patient (`i`); 4 of 5 Loop_AB_ON peers
have Gate G4 / G1 effectively suppressing SMB at this band, so the
direction is mechanism-consistent but not population-validated within
Loop. EXP-2985 confirms `i` is band-representative of Loop_AB_ON SMB
behaviour at all bands where peers do fire.

### Within-design Pareto frontier (EXP-2993)

The strongest within-design result. Among the 5 Loop_AB_ON peers,
stratified by EXP-2991's four-proxy `conservatism_score`:

| Tertile | overshoot | TTT_median | TAR_frac |
|---|---:|---:|---:|
| aggressive (i, e)   | 0.255 | 67.5 | 0.278 |
| mid (g)             | 0.210 | 50.0 | 0.191 |
| conservative (c, d) | 0.275 | 53.8 | 0.227 |

Spearman ρ(conservatism, TTT_median) = **−0.82**.

**There is no Pareto-front trade-off.** Conservative Loop_AB_ON
delivers comparable-or-lower overshoot AND faster recovery AND lower
TAR. The "aggressive dial" is *strictly Pareto-dominated* by the
conservative dial in this cohort. The `g` (mid-tertile) sweet spot
is reproducible across 27 weeks (EXP-2994; TIR CV 0.14).

This refutes the previously-implicit framing that aggressive AB-ON
trades overshoot risk for recovery speed. It does not.

---

## Section 5 — AID-author lever priority order (FINAL)

Replacing all prior versions in the synthesis (§13 etc.). Code-path
file:line provided where applicable.

| Rank | Lever | Channel | Code citation | Notes |
|---:|---|---|---|---|
| 1 | `correctionRange.lowerBound` and `suspendThreshold` (Loop) — Gate G4/G1 | SMB gate | `LoopAlgorithm.swift:419-423`; `DoseMath.swift:207-210` | Highest-priority lever for user-facing documentation; explains 99% peer-suppression of SMB at 70–100 mg/dL (EXP-2990). |
| 2 | `enable_smb()` + `enableSMB_always` (Trio/oref1) | SMB rate | `DetermineBasalSMB.kt:66` | Frequency-lever's enable gate; off in no-carb context unless `enableSMB_always`. (Cohort = Trio only; AAPS-oref1 untested.) |
| 3 | Predict-and-fire on rising velocity early (UAM / AB on momentum) | SMB | both designs | Single design principle that unifies PP TIR + sustained-high recovery + hypo defence (within-patient validated at hypo, EXP-2954). |
| 4 | `SMBInterval` cycle-frequency ceiling (Trio/oref1) | SMB freq | `DetermineBasalSMB.kt:1101` | 3-min minimum in oref1; Loop uses cycle-only (5 min). Tuning lever for the *frequency* mechanism. (Cohort = Trio only.) |
| 5 | `partialApplicationFactor` / GBAF (Loop) | SMB magnitude | `GlucoseBasedApplicationFactorStrategy.swift:14`; `DoseMath.swift:101` | 0.20/0.40/0.80 attenuator; combined with pump rounding can convert near-zero corrections to literal zeros. Tuning lever for the *magnitude* mechanism. |
| 6 | `maxSMBBasalMinutes` / `maxBolus`-derived caps | SMB ceiling | `SMBDefaults.kt`; `LoopDataManager.swift:1840` | Tertiary; backstop rather than primary tuning. |
| 7 | Basal-cut latency (defence-side) | basal | both | Demoted from primary to **secondary** by EXP-2954/2947. Reactive cutting cannot substitute for predict-and-fire-early; Loop_AB_ON cuts in 96.1% of pre-hypo cells yet has 2× severe hypo. |
| 8 | Per-mechanism guard-rails (NEW) | varies | n/a | Magnitude designs need an **overshoot governor**; frequency designs need an **IOB-stacking governor**. See Section 6. |

---

## Section 6 — Counter-recommendations (what NOT to tune)

1. **Don't increase basal-cut aggressiveness beyond ~91%.** Loop_AB_ON
   already cuts in 96.1% of pre-hypo cells and *loses* the BG outcome
   (2× severe hypo). Reactive cutting cannot age IOB that is fresh
   at the moment it needs to be old (EXP-2947, EXP-2954).
2. **Don't increase total dose magnitude within a design.** Within-
   design dose tertile is flat for both PP TIR (EXP-2946) and
   sustained-high recovery (EXP-2944, Loop tertile flat).
3. **Don't make a Loop-style design frequency-emit, or vice versa.**
   The two designs achieve similar total SMB delivery with
   complementary mechanisms; converting between them isn't a
   well-defined operation, and the per-mechanism guard-rails would
   be wrong for the converted design (EXP-2972/2973).
4. **Don't assume "conservative" = "slower", and don't frame it
   that way in UI or docs.** EXP-2993 refutes the trade-off for
   Loop_AB_ON on a 5-patient cohort: conservative is uniformly
   better on every outcome axis tested. User-facing copy that
   labels conservative settings as "safer but slower" creates a
   false trade-off perception that the data does not support.
5. **Don't build a single "AB-aggressiveness" knob.** Aggressiveness
   is multi-dimensional (cap, gate, fraction); a single knob would
   force a particular combination on all users. Surface the
   four-proxy conservatism score (EXP-2991) and its individual
   axes instead.
6. **Don't tune `partialApplicationFactor` to fix endogenous-rise
   overshoot.** EXP-2982: linear PAF cap sweep (1.0 → 0.2) *does
   not reduce* overshoot in the rising-70-100 stratum because the
   rise is endogenous (carb residual / dawn / counter-reg), not
   insulin-stacking. PAF is a tool against insulin-stacking
   overshoot, not endogenous-rise overshoot.
7. **Don't tune `maxIOB` to prevent hypo in the Trio mode.**
   EXP-2983: no empirical IOB-stacking ceiling for Trio in observed
   range (ρ(mean_IOB, hypo_rate) = −0.33, p = 0.38). Existing Trio
   caps already gate the danger zone; the hypo-prevention lever is
   *suppression at low BG*, not *lower maxIOB*.
8. **Don't apply identical guard-rails to both designs.** Magnitude
   designs (Loop) need an **overshoot governor** — post-SMB cool-down
   or predict-aware sizing cap when projected post-SMB BG > 180
   (EXP-2979). Frequency designs (Trio) need an **IOB-stacking
   governor** — frequency back-off (not just magnitude back-off)
   when IOB is high. The failure modes differ; the safety controls
   should too.

---

## Section 7 — Honest reversals & methodology lessons

In chronological order, with the lesson each one teaches.

| EXP | Reversal | Methodology lesson |
|---|---|---|
| 2955 | Within-patient PP signal collapses when carbs + bg_entry are added as covariates. Lever (3) at PP became a between-design claim only. | Single-predictor within-patient regression can hide meal-context confounders; multi-factor was required. |
| 2964 | EXP-2960's "+1.36 vs +0.62 U per mg/dL/min" lived primarily in the USER-bolus channel. The controller-channel comparison is a near-tie. | Channel-decomposition (controller vs user) is mandatory before claiming a controller difference from velocity-coupling regressions. |
| 2982 | Linear PAF cap sweep does not reduce overshoot in the endogenous-rise stratum. PAF is the wrong lever there. | "Smaller dose → less overshoot" intuition fails when the rise is not driven by the dose under analysis. |
| 2986 / 2992 | The "OpenAPS / oref0 (legacy)" arm is actually AAPS-platform / oref0-algorithm. Platform ≠ algorithm. | Schema columns must distinguish (controller, lineage, ∃ bolus_smb > 0); inferring algorithm from platform produces mis-labels. |
| 2993 | Within-Loop_AB_ON: aggressive does not trade off against conservative; conservative Pareto-dominates. | The trade-off framing (aggressive = faster, conservative = safer) was ungrounded in the data. |
| 2995 | EXP-2886's `braking_ratio` phenotype is mostly an algorithm signature (η² 0.65), not a patient property. | Phenotype-axis claims need a confounding-by-algorithm test before being attributed to patient physiology. |

---

## Section 8 — Cohort gaps & future work

1. **AAPS-oref1 patient acquisition (BLOCKING).** EXP-2986 fixed the
   AAPS labelling bug; EXP-2989 / EXP-2992 confirmed the cohort has
   zero AAPS-oref1 patients (3 ODC patients run AAPS-platform with
   oref0-algorithm, no SMB). Trio-vs-AAPS platform isolation within
   oref1 cannot be performed until additional ODC / AAPS-NS patients
   are added.
2. **Trio-vs-AAPS-oref1 platform isolation (DEFERRED).** Once the
   AAPS-oref1 arm exists, EXP-2989's planned design becomes runnable:
   compare iOS-Trio vs Android-AAPS scheduling differences (BLE
   timing, Doze, BackgroundTasks vs AlarmManager) at fixed
   oref1-algorithm.
3. **iOS Loop FreeAPS-X variant (UNTESTED).** The cohort has zero
   FreeAPS-X patients; the Loop-side findings should not be assumed
   to transfer to FreeAPS-X without test.
4. **Larger N for per-design per-patient sign tests.** Multiple
   per-patient MWU tests in the synthesis (Trio vs Loop_AB_ON SMB
   slope at PP, at sustained-high, etc.) sit at p ∈ [0.15, 0.36]
   with n = 5 vs 9. Doubling the per-design n would let several
   directional findings cross to per-patient significance.
5. **Multi-patient validation of EXP-2979 within Loop_AB_ON.** The
   directional outcome-linkage finding rests on a single Loop
   patient (`i`). Extending to other Loop_AB_ON SMB-firing
   configurations is a primary follow-up.
6. **Counter-regulation HAAF-feedback chain (open).** EXP-2887
   rejected the strong-form mediation; EXP-2995 confirms only
   modest η² (0.225). Larger N + autonomic-function workup could
   close.

### Upstream actions requiring user input

These are NOT autonomous follow-ups; they require user decision:

- **AAPS outreach**: prepare data-sharing request to OpenAPS / AAPS
  community for AAPS-oref1 patient parquets.
- **Upstream issue prep**: EXP-2986 documented a labelling bug that
  could be filed against the upstream `tools/ns2parquet` repo if
  it is shared with downstream users.
- **Loop / Trio Insights surfacing**: code-author-facing
  recommendations to Loop and Trio maintainers about the
  conservatism dial and per-mechanism guard-rails should be raised
  upstream (issue or RFC) by a human.

---

## Section 9 — Provenance

### EXP-NNNN markdown reports (this campaign)

All files in `docs/60-research/`. Selected, in narrative order:

| Stage | EXPs | Title prefix |
|---|---|---|
| Phenotype / cohort | 2886, 2887 | phenotype-synthesis-report, mediation-rejection |
| IOB-age framework | 2944, 2946, 2947, 2949, 2950, 2953, 2954, 2957 | iob-timing, pp-iob-timing, hypo-iob-decay, iob-age-operationalisation, uniform-action-curve, hypo-uniform-curve, within-patient-iob-age, action-curve-sensitivity |
| Within-window scoping | 2955, 2958, 2959 | within-patient-pp-iob-age, smb-during-rising, per-patient-peak |
| Velocity-coupling | 2960, 2961, 2962, 2963 | uam-velocity-coupling, velocity-coupling-sustained-high, per-patient-velocity-coupling, oref0-anomaly-investigation |
| Mechanism decomposition | 2964, 2965, 2966, 2969, 2970, 2971 | smb-basal-decomp (PP / sustained-high), bg-band-velocity-sweep, per-patient-smb-velocity-pp, per-patient-sweet-spot |
| Frequency-vs-magnitude | 2972, 2973, 2974, 2975, 2976 | emission-decomposition, velocity-stratified-sweet-spot, code-mapping-marker, u-shape, pp-u-shape |
| Calibration / audit | 2977, 2978 | loop-paf-calibration, oref1-smb-audit |
| Outcome linkage | 2979, 2980, 2981, 2982, 2983, 2984, 2985 | outcome-linkage, trio-vs-aaps, patient-i-audit, loop-overshoot-governor, trio-iob-governor, aaps-scoping, overshoot-all-bands |
| Pipeline fixes | 2986, 2992 | aaps-labeling-fix-applied, schema (algorithm_mode column) |
| Peer-suppression | 2987, 2988 | peer-suppression-levers, earlier-dosing-rejected |
| Loop SMB gating | 2990 | loop-smb-gating |
| Conservatism / within-design | 2991, 2993 | policy-conservatism, within-loopabon |
| **This batch (capstone)** | 2994, 2995 | patient-g-sweet-spot, phenotype-restratification |

### Code-path deep-dives at `docs/10-domain/`

- `smb-emission-policy-deep-dive-2026-04-23.md` — five-gate enumeration of SMB emission across Loop and oref1.
- `loop-smb-gating-deep-dive-2026-04-23.md` — G1–G5 deep-dive with example traces.
- `temp-basal-vs-smb-comparison.md` — supporting reference.

### Master synthesis document

- `docs/60-research/synthesis-design-comparison-2026-04-23.md` Section 9
  ("Finding E — UNIFIED IOB-AGE FRAMEWORK") — rolling synthesis with
  per-batch addenda. Section 9's evidence-line tally was 32 prior to
  this capstone batch; this capstone references 34 lines (the
  additions are EXP-2994 patient-`g` reproducibility and EXP-2995
  phenotype confounding test).

### Cohort parquet

- `externals/experiments/exp-2891_simpson_dose_response.parquet` —
  per-patient summary cohort, now carrying `algorithm_mode` (added
  by EXP-2992).
- `externals/ns-parquet/training/grid.parquet` — 5-min cell grid
  used for window-class operationalisation.

### Reusable templates

- `tools/cgmencode/exp_*.py` — all analytical scripts. Pattern is:
  read cohort parquet, derive window class, compute per-design /
  per-patient metric, write `*_summary.json` + parquet output to
  `externals/experiments/` (gitignored), print a tail-readable
  summary.
- `tools/cgmencode/exp_within_loopabon_2993.py` is a good reference
  for within-design tertile stratification.
- `tools/cgmencode/exp_phenotype_restratification_2995.py` is a
  good reference for ANOVA-style η² + within-mode-std confounding
  tests.

---

*End of capstone. For per-experiment detail, follow the EXP-NNNN
links above. For source-code lever-tuning detail, follow the
`docs/10-domain/*-deep-dive-2026-04-23.md` documents.*
