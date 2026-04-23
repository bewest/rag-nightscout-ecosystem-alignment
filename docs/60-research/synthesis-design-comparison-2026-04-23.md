# Synthesis: AID Controller Design Comparison (Apr 2026)

**Date:** 2026-04-23
**Scope statement (binding):** This is **scientific characterisation
of AID controller design choices for open-source AID author
audiences**. It is NOT therapy advice, NOT a per-patient
device-migration recommendation, and NOT a claim of one AID being
"better" for any individual. Patient choice and autonomy depend
on many factors (device access, regulatory, ergonomics, support
ecosystem, feature preferences) outside the scope of any
outcome-numbers analysis.

**Cohort:** 19 patients with lineage-known data — 7 Loop (iOS),
9 oref1 (modern AAPS / Trio), 3 oref0 (legacy openaps/AAPS). All
oref0 cells in derived analyses are n=1–3.

**Source:** `externals/ns-parquet/training/grid.parquet` 5-min cells
(944k rows after lineage filter), `externals/experiments/exp-2891_simpson_dose_response.parquet`
for lineage/cf labels. EXP-2916 through EXP-2927.

---

## 1. Headline outcomes table

| Lineage | n | TIR    | TBR  | TAR    | Fasted-dawn 03:00 hyper | Overnight severe-hypo (low_cf) |
|---------|--:|-------:|-----:|-------:|------------------------:|-------------------------------:|
| Loop    | 7 | 66.1 % | 3.88 | 30.04 %| **12.51 %**             | 0.44 % (n=1)                   |
| oref0   | 3 | 73.7 % | 5.27 | 20.99 %|  5.25 %                 | **4.18 %**                     |
| **oref1** | 9 | **82.6 %** | **3.64** | **13.78 %** | **1.53 %** | 0.61 %                |

oref1 Pareto-dominates Loop on TIR/TBR/TAR pooled (EXP-2925).
The dominance survives Guard #6 cf-conditioning at every tertile
where comparison is possible (EXP-2924, EXP-2925, EXP-2927).

---

## 2. Mechanism stack

| Design feature                    | Loop OFF | Loop ON  | oref0    | oref1    |
|-----------------------------------|---------:|---------:|---------:|---------:|
| Brake-only basal cuts             | yes      | yes      | yes      | yes      |
| Fast basal-cut latency (≤0 min)   | **yes**  | no       | **no (10 min)** | yes |
| SMB as correction                 | no       | partial  | yes      | yes      |
| Pre-emptive autobolus             | no       | **yes**  | no       | partial  |
| Dynamic ISF                       | no       | no       | no       | **yes**  |
| UAM detection                     | no       | no       | partial  | **yes**  |
| **Fasted-dawn hyper %**           | 17.0     | 10.7     | 5.3      | **1.5**  |
| **Pooled TIR %**                  | (split)  | (split)  | 73.7     | **82.6** |

"Loop is two designs" (EXP-2919/2921): autobolus on/off produce
divergent fingerprints (3× latency difference, 2× dawn-hyper
difference). Cross-design tables that aggregate Loop conflate
two distinct policies.

---

## 3. The four design-level findings (with confirmation layers)

### Finding A — Dawn fingerprint (dynamic-ISF lever)

**Loop fasted-dawn 03:00 hyper = 12.51 %; oref1 = 1.53 % (8× gap).**

| Layer | Source       | Evidence |
|-------|--------------|----------|
| 1 — Single-mechanism isolation | EXP-2923  | fasted-only filter rules out meal carry-over |
| 2 — cf-conditioning Guard #6  | EXP-2924  | mid_cf 14.17 pp [12.47, 15.90]; high_cf 4.33 pp [0.04, 8.62] |
| 3 — Decomposition with state  | EXP-2922  | autobolus halves the gap proportionally in BOTH states |

**Causal interpretation:** Brake-only loops cannot address EGP
rises by definition. Dynamic-ISF widens overnight sensitivity
and pre-emptively raises insulin demand against EGP. This is
the cleanest single-mechanism design comparison in this workspace.

### Finding B — Post-prandial gap (UAM/SMB lever; dose-shape mechanism)

**Loop PP TIR = 48.64 %; oref1 PP TIR = 75.81 % (27 pp gap).**

| Layer | Source     | Evidence |
|-------|------------|----------|
| 1 — Pooled state TIR | EXP-2927 | 48.64 vs 75.81 % at PP |
| 2 — cf-conditioning  | EXP-2927 | mid_cf +27.80 pp [+7.93, +46.32]; high_cf +18.48 pp [+0.06, +37.55] |
| 3 — Comparator cell  | EXP-2927 | oref0 PP TIR 70.47 % — UAM+SMB stack alone is competitive |
| 4 — Autobolus split  | EXP-2929 | Loop_AB_OFF PP TIR = 32.14 %; ON = 55.23 %. Autobolus closes 53 % (23.10 of 43.67 pp) of the gap; residual 20.57 pp [+7.02, +36.28] |
| 5 — Dose-shape mechanism | EXP-2930 | First-SMB latency identical (oref1 10 min vs Loop_AB_ON 12 min). oref1 front-loads dose: **2.2× in 0-30 min, 6.6× in 30-60 min**. Loop catches up corrective at 120-240 min into already-elevated BG |

**Causal interpretation:** Half of Loop post-prandial cells are
out of range. The mechanism is **dose shape, not cadence or
first-fire timing** — both designs fire 4-7 SMBs per meal at
the same first-fire latency. oref1's UAM detector + dynamic-ISF
loads insulin during the early absorption phase; Loop autobolus
fires when prediction crosses target (typically 30-90 min post-meal)
and back-loads correction into already-elevated BG. **This is the
larger absolute lever** — bigger than the dawn fingerprint.

**Decomposed causal chain (closed by EXP-2930):**
- ~53 % of the brake-only PP gap is closable by enabling autobolus
  (Loop_AB_OFF → Loop_AB_ON, no UAM needed).
- Remaining ~47 % requires a **glucose-appearance / UAM-style
  detector** that does not depend on prediction crossing target,
  plus **dynamic-ISF widening during early absorption** to
  amplify the auto-correction dose.

### Finding C — Overnight basal-cut latency (oref0 weakness)

**oref0 midnight severe-hypo = 4.18 %; oref1 = 0.61 % (~7×, non-overlapping CIs).**

| Layer | Source      | Evidence |
|-------|-------------|----------|
| 1 — Latency by design | EXP-2918  | oref0 median latency 10 min vs Loop/oref1 0 min |
| 2 — Outcome by design | EXP-2920  | midnight peak hypo 4.66 % oref0 vs 1.27 % oref1 |
| 3 — cf-conditioned    | EXP-2925  | low_cf cell oref0 4.18 % CI[1.94, 6.58] vs oref1 0.61 % CI[0.42, 0.80] |

**Causal interpretation:** oref0's slower basal-cut decision
policy translates to ~7× higher overnight severe-hypo incidence
under matched cf load. **Lowest-hanging design fix for legacy
code.** Note: oref0 is otherwise competitive (PP TIR 70.47 %,
fasted-dawn 5.25 %) — its design weakness is temporally specific.

### Finding D — Loop autobolus is two designs

**Autobolus halves dawn-hyper but doesn't change morning hypo
or basal-cut latency.**

| Layer | Source     | Evidence |
|-------|------------|----------|
| 1 — Latency split | EXP-2919 | OFF mean 9.3 min, ON mean 31.0 min |
| 2 — TOD hyper     | EXP-2921 | OFF 30.65 % at 04:00, ON 14.30 % at 03:00 |
| 3 — State decomp  | EXP-2922 | autobolus reduces hyper ~40 % in BOTH fasted and PP |

**Implication:** Cross-design tables that aggregate Loop conflate
two policies. Future comparisons should split (or note Loop
results carry hidden subgroup variance ~2×).

---

## 4. AID-author priority order

Suggested by absolute TIR delta in this cohort:

1. **UAM detection + SMB-as-correction during absorption.**
   Largest TIR delta (~27 pp PP). Addresses the dominant
   out-of-range burden.
2. **Dynamic-ISF for dawn EGP.** Cleanest causal isolation;
   smaller absolute effect (~17 pp fasted) but distinct
   physiologic lever.
3. **Improve basal-cut latency.** Smallest absolute TIR effect
   but the lowest-effort fix in legacy oref0/openaps codebases
   and the highest-impact safety improvement (overnight severe
   hypo).
4. **For Loop-style brake-only loops: enable autobolus.**
   Halves dawn 03:00 hyper and closes ~53 % of the PP TIR gap
   (EXP-2929). Does not address the residual UAM/dynamic-ISF lever
   (~47 % of PP gap remains; ~16 pp fasted gap unchanged).
5. **Dose shape, not cadence.** Both autobolus and oref1-UAM fire
   ~5 SMBs per meal at the same first-fire latency (EXP-2930).
   The lever is **front-loaded delivery during early absorption**
   (oref1 delivers 2.2× the dose in 0-30 min and 6.6× in 30-60 min
   post-meal), which requires UAM-style appearance detection and
   dynamic-ISF widening — not "fire SMBs more often."

---

## 5. Methodological invariants codified by this arc

1. **Cross-AID comparisons are scientific characterisation, not
   therapy advice** (binding scope statement). Audition flags
   must NOT recommend changing AID systems.
   See `exp-2916-design-gap-2026-04-23.md`.
2. **Default Guard #6 (cf-conditioning):** any cross-design claim
   must be tested after matching/stratifying on patient cf load.
   Toolkit §4.6.
3. **Default Guard #7 (load-mediation, EXP-2912/2913):** when
   correlating cf with physiology outcomes, also report against
   `cf × (1 − protection)` to detect coverage-distribution artefacts.
   Toolkit §4.7.
4. **Small-n bootstrap caveat (EXP-2917):** paired CIs against
   n=1 cells are degenerate (zero-width) and inherit only the
   multi-patient side's variance. Always flag with † and corroborate
   with mechanism stack. Toolkit §2.8 (extended).
5. **3D mechanism stack template** (EXP-2892 + 2916 + 2918): when
   cell n is small, three independent dimensions of the same
   design decision-policy gap (utilisation × magnitude × latency)
   substitute for inferential CI.
6. **Loop is two effective designs.** Always consider splitting
   Loop by autobolus on/off in cross-design analyses.

---

## 6. Cohort and statistical caveats

- 19 patients total, 7/9/3 split by lineage. All oref0 cells in
  finer breakdowns are n=1–3.
- Hour-of-day not TZ-normalised. Patient-local clock as recorded.
- `time_since_carb_min` capped at 360 — long fasts all bin into
  ≥300 min.
- `cf_severe` tertiles defined on overall cf, not state-windowed.
- All statistics are observational, not interventional. No patient
  was randomised to a design.

The single largest data-quality improvement available is **AAPS
data ingestion (EXP-2908)** — only path to widening the oref-family
patient base and resolving all n=1 oref0 cells with honest CIs.

---

## 7. Experiment index for this arc

| EXP    | Title | Result |
|--------|-------|--------|
| 2916   | Design gap (cell-level) | oref0/oref1/Loop protection deltas |
| 2917   | Bootstrap CIs | mid_cf and high_cf gaps significant |
| 2917b  | Forest plot | n=1 cells flagged; visual companion |
| 2918   | Basal-cut latency | oref0 only design with non-zero median |
| 2919   | Loop autobolus split | OFF 9.3 min vs ON 31.0 min |
| 2920   | TOD profiles | Loop dawn-hyper 18.93 % at 03:00 |
| 2921   | Loop autobolus × TOD | autobolus halves dawn-hyper |
| 2922   | Fasted vs PP (Loop) | dawn signature is real, not meal carry-over |
| 2923   | Fasted vs PP (cross-design) | 8× fasted-dawn gap Loop vs oref1 |
| 2924   | Guard #6 confirmation | 8× gap survives cf-matching |
| 2925   | Hypo symmetry | oref1 Pareto-dominates; no hypo trade |
| 2927   | TIR decomposition | PP gap > fasted gap (1.4–1.7×) |
| 2929   | Loop autobolus × PP TIR | autobolus closes 53 % of PP gap; FASTED unchanged |
| 2930   | SMB temporal alignment | identical first-fire latency; oref1 front-loads dose 2.2-6.6× |
| Toolkit | Guard #7 (load-mediation), §2.8 small-n caveat | new methodological additions |

---

## 8. Outstanding questions (next R&D batch)

- **EXP-2931 candidate:** Apply Guard #7 retroactively to
  EXP-2912 stacker phenotype claim.
- **EXP-2932 candidate:** post-meal TBR by design — does oref1's
  front-loaded dose carry hypo cost? ("no free lunch" check at
  meal-window granularity).
- **AAPS ingestion (EXP-2908):** the only structural fix for
  small-n oref0 cells.
- **Per-patient TZ normalisation:** removes the local-clock
  caveat from all TOD findings.
