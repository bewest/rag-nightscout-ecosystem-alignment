# EXP-2847 + Audition Matrix Productionization Report (2026-04-22)

**Stream**: B (operational/audition only — not biological estimation)

## Headline

The audition matrix synthesis (audition-matrix-2026-04-22.md) is now
encoded as a callable production module
(`tools/cgmencode/production/audition_matrix.py`). A focused
correction-ISF audit (EXP-2847) provides quantitative grounding for
the flat-low-recovery archetype embodied by patient `b`.

## EXP-2847 — Correction-ISF Re-Audit for Flat + Low-Recovery Patients

**Question**: Does observed correction-event ISF show a systematic gap
from scheduled ISF for the flat-phenotype + low-recovery audition
flag, distinguishable from the rest of the cohort?

**Method**: For each patient, find correction-only events (bolus ≥ 0.5 U,
BG ≥ 180, no carbs in prior 30 min or following 3 h). Observed ISF =
(BG_start − BG_min over next 3 h) / bolus. Compare median observed vs
scheduled ISF.

**Result**:
- N events: 13,810; per-patient coverage: 16/17 phenotype patients.
- Patient `b` (Loop, flat, recovery=0.0, only triple-flag in cohort):
  observed median 77 vs scheduled 90 → **−14% gap (under-correction)**.
- All other patients (n=15) cluster at median **+36% gap (over-correction)**.

**Interpretation**:
The audition signal is the GAP DIRECTION, not the absolute observed
value (Stream B charter — observed embeds controller compensation).
Patient `b` is a clear and stable outlier in the OPPOSITE direction
from the cohort: corrections under-deliver the predicted drop. This is
consistent with a tighter scheduled ISF being warranted, OR with site
degradation (also flagged for `b`: −31.5% effective ISF over cannula
age). The audition matrix recommends auditing site rotation FIRST
because a settings change cannot fix a hardware/wear cause.

**Charter compliance**: Recommendation is the Stream B gap, not a
biological ISF claim. No EGP estimation. Confidence grade B.

## Productionized Audition Matrix

`production/audition_matrix.py` exposes:
- `AuditionInputs` — per-patient inputs (controller, smb_capable,
  phenotype, recovery, isf_gap_pct, post_high, wear_isf_drop_pct)
- `classify_triage_flags(inputs) -> List[AuditionFlag]` — the 4-factor
  triage classifier with severity grades
- `generate_audition_recommendations(inputs, profile) ->
  List[SettingsRecommendation]` — Stream B audition recs consumable
  by the existing `recommender.generate_recommendations` orchestrator

The function emits route-aware recommendations:
- Loop/AAPS WITHOUT SMB → basal-route schedule edits
- Trio (uniformly SMB-capable), or Loop/OpenAPS WITH SMB → ISF-route edits
- Down-shifters → dawn window (00–06)
- Up-shifters → afternoon window (12–18)
- Flat + low recovery → whole-day audit + site-degradation gating

### Test coverage

`production/test_audition_matrix.py` — 8 tests, all passing:
1. Patient `b` archetype emits the expected three high-severity flags
2. Well-controlled patient produces zero flags
3. Down-shifter produces a dawn-window recommendation
4. SMB-capable up-shifter routes through ISF (not basal)
5. Negative ISF gap → under-correction recommendation, magnitude
   bounded, suggested value attached from profile
6. Profile attachment correctly computes basal suggested value
7. No profile leaves zero values (graceful)
8. Site-degradation rec is lower-confidence and whole-day-affecting

## Deliverables

| File | Purpose |
|------|---------|
| `tools/cgmencode/exp_flat_isf_audit_2847.py` | EXP-2847 driver |
| `externals/experiments/exp-2847_flat_isf_audit.json` | Output (gitignored) |
| `externals/experiments/exp-2847_correction_events.parquet` | Events table |
| `docs/60-research/figures/exp-2847_flat_isf_audit.png` | Audition chart |
| `tools/cgmencode/production/audition_matrix.py` | Production module |
| `tools/cgmencode/production/test_audition_matrix.py` | Unit tests |
| `docs/60-research/exp-2847-and-audition-prod-report-2026-04-22.md` | This report |

## Findings invariants (carry forward, updated)

- Patient `b` is the ONLY flat-low-recovery patient in the cohort with
  sufficient correction events; the audition signal direction (−14%
  gap) is opposite to the cohort (+36% gap) and stable across N=692
  events
- The audition matrix is now a production module — not just analysis
- Charter G-compliance: Stream B, profile-vs-actual gap recommendations,
  no biology claims, route-aware (controller × SMB capability)
- Next experiments (EXP-2848+) can layer additional audition factors
  without touching the recommender wiring

## Next

1. Wire `generate_audition_recommendations` into the recommender
   orchestrator (separate change — keeps this commit focused on the
   audition module + tests)
2. EXP-2848: looser n_trans criterion to recover transition data for
   the 4 flat patients without coverage
3. Cohort-level chart of ISF gap distribution vs phenotype +
   controller cells
