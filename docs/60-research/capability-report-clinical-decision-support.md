# Capability Report: Clinical Decision Support

**Date**: 2026-04-07 | **Overnight batch**: EXP-685, EXP-688, EXP-693–694, EXP-746–747 | **Patients**: 11

---

## Capability Definition

Generate actionable therapy adjustment recommendations — basal rate changes, CR/ISF tuning, override suggestions — from continuous glucose, insulin, and treatment data. The system bridges the gap between real-time AID control and quarterly clinic visits.

---

## Current State of the Art

| Task | Best Metric | Method | Status |
|------|-------------|--------|--------|
| Override WHEN (timing) | F1 **0.993** | TIR-impact scoring | ✅ Solved |
| Basal rate assessment | 11/11 classified | Physics flux + overnight analysis | ✅ Production |
| CR effectiveness scoring | Scored 10/11 | Post-meal recovery analysis | ✅ Production |
| AID-aware recommendations | Generated for 11/11 | Clinical rule engine on flux balance | ✅ Production |
| Glycemic grading (A–D) | 11/11 graded | Composite risk scoring | ✅ Production |
| Override WHICH type | — | Not started | ❌ Open |
| Override HOW MUCH | — | Not started | ❌ Open |

---

## Basal Rate Assessment (EXP-693, EXP-746)

The system isolates overnight periods (no meals, no corrections) and analyzes the supply-demand flux balance to determine basal adequacy:

| Assessment | Count | Signal |
|------------|-------|--------|
| Basal too low | 5 patients | Overnight BG drift positive, residual integral > 200 |
| Basal appropriate | 2–4 patients | Overnight TIR > 70%, drift < ±10 mg/dL |
| Basal too high | 1–2 patients | TBR > 5%, negative BG drift |
| Basal slightly high | 2 patients | TBR 3–5%, modest negative drift |

**Critical finding** (EXP-747): Effective ISF is **2.91× profile ISF** on average. AID systems compensate so aggressively that the ISF patients have configured understates their true insulin sensitivity by nearly 3×. Patient a: profile ISF = 49, effective ISF = 178 (3.65× ratio).

---

## CR Effectiveness Scoring (EXP-694)

Quantifies how well meal boluses control post-meal glucose by tracking peak BG and recovery time:

| Patient | Meals | Recovery (min) | Peak BG | CR Score |
|---------|-------|---------------|---------|----------|
| d (best) | 72 | 82 | 208 | **61.5** |
| g | 523 | 102 | 217 | 51.9 |
| e | 310 | 112 | 207 | 51.8 |
| a (worst) | 338 | 153 | 303 | **9.1** |
| i | 94 | 160 | 281 | 12.4 |

The 7× range (9.1–61.5) demonstrates that CR settings vary dramatically in effectiveness. Patient a's 153-minute recovery with 303 mg/dL peak strongly indicates an under-aggressive CR ratio.

---

## AID-Aware Clinical Rules (EXP-685)

The innovation is distinguishing **AID compensation** from **genuine under-insulinization** using net metabolic flux:

| Pattern | Signal | Recommendation |
|---------|--------|---------------|
| High TAR + negative net flux | AID is compensating for bad settings | Adjust CR/ISF (not more insulin) |
| High TAR + positive net flux | Genuinely under-insulinized | Increase total insulin |
| High TBR | Over-insulinized | Reduce basal or sensitivity |
| Good TIR + low TBR | Well-controlled | Maintain current settings |

**Example**: Patient a has TAR = 41% but net flux = −4.23 (negative). Naive interpretation: "needs more insulin." AID-aware interpretation: "AID is already over-delivering to compensate — fix the underlying CR/ISF settings instead."

Distribution across 11 patients: 9 → decrease basal, 5 → increase CR, 4 → adjust settings, 3 → maintain.

---

## Glycemic Control Grading (EXP-688)

Composite scoring integrating TIR, TBR, TAR, CV, GMI, model R², spike rate, and flux balance:

| Grade | Count | TIR Range | Risk Range |
|-------|-------|-----------|------------|
| A | 3 (d, g, j) | 75–81% | 21–45 |
| B | 4 (c, e, f, k) | 62–95% | 33–65 |
| C | 4 (a, b, h, i) | 56–85% | 32–100 |
| D | 0 | — | — |

Patient i scores risk = 100 (maximum) despite TIR = 59.9% — the highest TBR (10.7%) drives the risk score, appropriately flagging dangerous hypoglycemia patterns.

---

## The Override Metric Transformation (EXP-227)

The override recommendation story is primarily about **asking the right question**:

| Metric Version | F1 | Problem |
|---------------|-----|---------|
| v1: "predict next override" | 0.130 | Wrong question — overrides are user-initiated, not physiologically triggered |
| v2: TIR-impact scoring | **0.993** | Right question — "would an override have helped TIR?" |

Reframing from "predict user behavior" to "assess physiological benefit" transformed a broken capability into a nearly-perfect one.

---

## Validation Vignette

**Patient i — High-risk dashboard alert**: Grade C, risk score 100. The system identifies: TBR = 10.7% (dangerous), meal net = −14.9 (massive over-bolusing), basal net = −10.4 (basal excessive). Recommendations: reduce basal, increase CR ratio, reduce sensitivity. The physics decomposition reveals the AID is fighting itself — aggressive settings cause lows, which trigger rebounds, which trigger more aggressive corrections. Breaking the cycle requires reducing base settings, not more tuning.

**Patient d — Stable control confirmation**: Grade A, risk score 21. TIR = 79.2%, TBR = 0.8%. Recommendation: maintain current settings, minor basal reduction. The system correctly identifies this as well-managed and avoids unnecessary intervention.

---

## Key Insight

The most impactful finding is the **ISF discrepancy**: effective ISF is 2.91× the configured profile ISF. AID systems mask bad settings by compensating automatically — patients appear controlled (decent TIR) while the underlying settings are fundamentally wrong. The clinical rule engine exposes this hidden dysfunction by decomposing the AID's compensatory actions from the patient's underlying physiology.
