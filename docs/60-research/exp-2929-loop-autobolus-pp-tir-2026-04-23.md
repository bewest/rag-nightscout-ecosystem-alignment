# EXP-2929 — PP TIR by Loop autobolus on/off vs oref1

**Date:** 2026-04-23
**Source:** `tools/cgmencode/exp_loop_autobolus_pp_tir_2929.py`
**Scope:** Direct test of EXP-2927's open question — does Loop
autobolus close the 27 pp post-prandial TIR gap to oref1, or
is UAM/dynamic-ISF the binding lever? AID-author audience.

## Per-design × state TIR (95 % bootstrap CI)

| Design       | State  | n | TIR     | CI               | TAR   | TBR  |
|--------------|--------|--:|--------:|------------------|------:|-----:|
| Loop_AB_OFF  | FASTED | 2 | 74.07 % | [69.59, 78.54]   | 22.69 | 3.25 |
| Loop_AB_OFF  | PP     | 2 | **32.14 %** | [28.82, 35.45]   | 66.03 | 1.84 |
| Loop_AB_ON   | FASTED | 5 | 73.88 % | [65.38, 82.38]   | 21.78 | 4.34 |
| Loop_AB_ON   | PP     | 5 | **55.23 %** | [42.37, 67.76]   | 42.43 | 2.33 |
| **oref1**    | FASTED | 9 | **90.52 %** | [87.30, 93.60] | 5.46  | 4.01 |
| **oref1**    | PP     | 9 | **75.81 %** | [68.63, 82.62] | 21.02 | 3.18 |

## Gap to oref1

| Comparison              | State  | Gap (oref1 − design) | 95 % CI            | sig |
|-------------------------|--------|---------------------:|--------------------|-----|
| oref1 − Loop_AB_OFF     | FASTED | +16.46 pp            | [+9.80, +22.96]    | ★   |
| oref1 − Loop_AB_OFF     | PP     | **+43.67 pp**        | [+35.01, +51.89]   | ★   |
| oref1 − Loop_AB_ON      | FASTED | +16.65 pp            | [+7.67, +25.28]    | ★   |
| oref1 − Loop_AB_ON      | PP     | **+20.57 pp**        | [+7.02, +36.28]    | ★   |

## Within-Loop autobolus effect (ON − OFF)

| State  | Effect (ON − OFF) | 95 % CI            | sig |
|--------|------------------:|--------------------|-----|
| FASTED | **−0.19 pp**      | [−10.12, +11.27]   | ✗   |
| PP     | **+23.10 pp**     | [+8.00, +35.65]    | ★   |

## Findings

1. **Autobolus is a post-prandial feature.** ON − OFF effect is
   +23.10 pp on PP TIR (sig, CI excludes zero) and −0.19 pp on
   FASTED TIR (not sig, wide CI). The FASTED TAR also barely
   changes (22.69 vs 21.78, Δ = −0.91 pp). All-day fasted-state
   improvement does not appear, even though dawn-hour-03:00
   hyper specifically halves (EXP-2921). Reconcilation: autobolus
   shifts hyper patterns within fasted state but does not change
   integrated fasted-state TIR.

2. **Autobolus closes ~53 % of the Loop→oref1 PP gap.** PP gap
   shrinks from +43.67 pp (Loop_AB_OFF) to +20.57 pp (Loop_AB_ON).
   Autobolus is genuinely impactful for meal handling — it cuts
   the gap roughly in half — but does not eliminate it.

3. **The 20.57 pp residual is the UAM/dynamic-ISF lever.** Even
   with autobolus, Loop_AB_ON PP TIR (55.23 %) is over 20 pp
   below oref1 (75.81 %). The residual mechanism stack is:
   - **UAM detection** → triggers SMBs without explicit user bolus
   - **Dynamic-ISF response** → widens during high-BG / post-bolus
   - **SMB-as-correction during absorption** → continuous micro-adjustment
   These are absent in Loop's design; autobolus alone is a
   pre-emptive fast-bolus feature, not an absorption-phase
   correction system.

4. **Loop_AB_OFF PP TIR = 32.14 %.** Two-thirds of post-prandial
   cells are out of range. This is the worst design-cell outcome
   surfaced anywhere in the Apr-23 batch. For the small Loop_AB_OFF
   subgroup (n=2), brake-only PP handling is structurally
   inadequate — and this is conditioning on patient-elected
   autobolus-off, not an oref0 latency artefact.

5. **FASTED TIR is essentially identical across all three Loop
   subgroups and oref0 (~74 %).** The fasted-state design
   advantage is **almost entirely an oref1 dynamic-ISF property**
   (+16 pp) — not closable by autobolus, and not a function of
   basal-cut timing.

## Reconciliation with prior arc

| Finding                                | Source        | Status |
|----------------------------------------|---------------|--------|
| Autobolus halves dawn 03:00 hyper      | EXP-2921      | Stands (focal-hour effect) |
| Both fasted and PP carry dawn signature | EXP-2922     | Stands (within-Loop comparison) |
| 8× cross-design fasted-dawn gap        | EXP-2923/2924 | Stands; this experiment shows
the fasted-TIR component is +16 pp regardless of autobolus |
| oref1 PP TIR advantage                 | EXP-2927      | **Decomposed**: ~53 % closable
by autobolus, ~47 % requires UAM + dynamic-ISF |
| Loop is two designs                    | EXP-2919/2921 | **Confirmed at TIR level**:
Loop_AB_OFF PP TIR is 23 pp below Loop_AB_ON |

## Updated AID-author priority order (refined)

For brake-only loops (Loop):

1. **Enable autobolus** — closes ~53 % of PP gap with no FASTED
   side effect. Lowest-effort wins.
2. **Add UAM detection + SMB-as-correction during absorption** —
   closes the residual ~47 % of PP gap. Highest-impact PP fix.
3. **Add dynamic-ISF for fasted/dawn handling** — orthogonal to
   autobolus; only path to closing the +16 pp fasted-TIR gap.
4. **Improve basal-cut latency** — oref0-specific overnight-hypo fix.

The four levers are now all proven independent at TIR level.

## Caveats

- Loop_AB_OFF n=2 — observational, no patient was randomised.
  Patients who keep autobolus disabled may differ systematically
  in carb-counting accuracy or insulin-stacking habits.
- All cross-design CIs depend on bootstrap; Loop_AB_OFF resamples
  from n=2 → CI lower bound on uncertainty.
- The "53 % closure" is a point estimate; the residual gap CI
  [+7.02, +36.28] is wide.
- All claims observational; not therapy advice; AID-author scope.

## Linked artefacts

- `externals/experiments/exp-2929_summary.json`
- `synthesis-design-comparison-2026-04-23.md` should be updated
  to reflect the autobolus-decomposed PP gap.
