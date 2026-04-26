# CLOSEOUT ADDENDUM — Autoresearch Phase 2 (2026-04-26)

**Branch**: `autoresearch/2026-04-24-cf-replay`
**Phase 2 commits**: 5 (EXP-3007 → EXP-3011)
**Predecessor**: `CLOSEOUT-autoresearch-2026-04-25.md` (Phase 1: EXP-3000-3006)

This addendum extends the original closeout with Phase 2 results, which moved from descent-side replay (Phase 1) to **ascent-side cf-replay** and produced the program's first **concrete, actionable controller-design recommendation**.

## Phase 2 commit history

| Commit | EXP | Headline |
|---|---|---|
| `cbce2b91` | 3007/3004 | Ascent extraction (17.9k events) reproduces capstone from raw grid; cf-replay reframes it as Loop=*recovery* lever, Trio=*prevention* lever |
| `00b70f1e` | 3008 | Magnitude-axis dose-response: per-controller slopes differ ~30× (Trio:AAPS); v2 scorer wired into autoresearch fitness |
| `288384e8` | 3009 | Timing-axis dose-response: claims free-lunch (timing > magnitude, no hypo penalty) |
| `c7d0bfb4` | 3010 | **Corrects EXP-3009**: honest hypo redistribution shows 1:0.7 trade ratio per axis |
| `6c4166a8` | 3011 | **Bivariate (T × M) Pareto frontier**: Loop and Trio both have strict-Pareto improvements via "fire earlier AND smaller" |

## The actionable recommendation

For both Loop and Trio, the cf-replay engine identifies a strict-Pareto-better operating point at (T = +30 min earlier, M = 0.5×):

| Controller | Δoversht | Δhypo |
|---|---:|---:|
| **Loop** | **−1.80 pp** | **−4.35 pp** |
| **Trio** | **−2.64 pp** | **−7.57 pp** |
| AAPS-oref0 | n/a (no SMB to retime) | — |

**Mechanism**: the current "later and bigger" SMB pattern is dominated on both overshoot and hypo because (a) late firing cannot fully realise insulin effect by peak time, leaving overshoot; (b) the over-large compensating dose then arrives in the post-peak window, deepening the trough. The "early and small" pattern resolves both failures simultaneously.

### Concrete code-level recommendations

| System | File | Change |
|---|---|---|
| **Loop** | `Loop/Models/GlucoseBasedApplicationFactorStrategy.swift` | Lower BG threshold of the 0.20-0.80 sliding scale; halve `partialApplicationFactor` |
| **Loop** | `LoopAlgorithm/LoopAlgorithm.swift:419-423` | Loosen the predicted-min < target-lower gate (currently forces deliveryMax=0) |
| **Trio** | `DetermineBasalSMB.kt:1052-1107` | `microBolus = floor(min(insulinReq/4, basal*15/60))` (was `/2` and `*30/60`) |
| **AAPS** | enable_smb gate (lines 66-103) | Switch oref0 → oref1 (no SMB at all in current cohort) |

## Self-correcting research demonstrated

EXP-3010 corrects EXP-3009 in flight; EXP-3011 then uses both (corrected accounting + magnitude axis from EXP-3008) to find the joint optimum that neither single-axis experiment could find. This is exactly the program design's intended behaviour — the git history preserves both the over-claim and the correction.

## Status of original Phase 1 + Phase 2 program

| Phase | EXP range | Status |
|---|---|---|
| Phase 1 — descent CF-replay maturation | EXP-3000 → 3006 | ✅ closed (prior closeout) |
| Phase 2 — ascent CF-replay + bivariate frontier | EXP-3007 → 3011 | ✅ closed (this addendum) |
| Phase 3 — open | EXP-3012+ | not started |

## Suggested Phase 3 directions (none in flight)

1. **Validation against held-out CGM**: pull a separate week of CGM per patient; check whether observed overshoot/hypo correlates with the Pareto-distance metric this engine assigns.
2. **Per-patient (T, M) recommendation** instead of per-controller — patients within Loop/Trio differ widely; some may already sit near the frontier.
3. **Replay against algorithm-tuner candidates from `aid-autoresearch`**: feed concrete oref0-config diffs to v2 scorer and rank.
4. **Add carb-absorption to the trough proxy** (EXP-3010 caveat) — currently absolute hypo levels are over-stated.
5. **Phenotype-conditional cf-replay** — does the (T=+30, M=0.5×) recommendation hold equally for high-IOB-age vs low-IOB-age patients (per the EXP-3006 generator)?

## Hand-off readiness

- All Phase 2 code committed; figures in `docs/60-research/figures/`; data parquets in `externals/experiments/` (gitignored, reproducible).
- Ledger TSV: 19 rows (Phase 1: 14, Phase 2 added 1 EXP-3004 + 3 v2-scorer demos + 1 EXP-3008 = 5).
- `cf_replay_score_v2.py` is the autoresearch hookup; takes `--smb-multiplier` and produces composite score.
- All 12 SQL todos = `done`.
- 2 pre-existing untracked verification files (`REVIEW_NOTES.md`, `VERIFICATION-CAPSTONE-2026-04-23.md`) still in working tree — different researcher, different EXP, no contamination, awaiting user direction on disposition.

Branch is `4 + 5 = 9` commits ahead of main on `autoresearch/2026-04-24-cf-replay`. Ready to merge or continue into Phase 3.
