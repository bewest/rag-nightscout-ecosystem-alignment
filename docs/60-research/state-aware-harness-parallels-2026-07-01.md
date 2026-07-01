# State-Aware Agent Harnesses: Parallels and Opportunities (2026-07-01)

**Source**: [How Candidly built state-aware agent harnesses with LangSmith](https://www.langchain.com/blog/how-candidly-built-state-aware-agent-harnesses-with-langsmith) (LangChain blog, guest post by Candidly).

**Scope**: Assess parallels between Candidly's IO-HMM/state-aware harness architecture and our own research/decision-support tooling (`tools/cgmencode`, MLflow tracking, `autoresearch_agent.py`, `clinical_decision_policy.py`), and identify concrete, adapted opportunities.

**Status update (2026-07-01, later)**: Sections 1-5 below are the original parallel analysis. Section 6 records a scope refinement made through follow-up discussion, and the first concrete build (`therapy_trajectory_state.py`) that came out of it. The refinement changes the primary target from the autoresearch-session angle (§3.1) to per-patient therapy trajectories — see §6 for why, and for what was actually built.

---

## 1. What Candidly Built (Recap)

Candidly's AI financial planner ("Cait") was originally evaluated only *ex post*: did the conversation resolve or get abandoned? They moved from that end-of-conversation grade to a **turn-level state estimate** the agent can act on mid-conversation:

1. Built a hybrid (rules + LLM-judge) pipeline to label conversation outcomes, tracked in LangSmith, calibrated to 92.3% agreement with humans.
2. Trained a classifier on lightweight per-turn features (Q/A alignment, topic continuity, message length, caps ratio) that separated resolved vs abandoned conversations at 0.90 AUC — proving the outcome is *learnable from the trace*.
3. Fit an **Input-Output Hidden Markov Model (IO-HMM)** over thousands of conversations, with a key architectural choice: **user-side signals are emissions** (used to infer state) and **agent-side features are transition inputs** (the levers the system controls). This recovered 4 interpretable engagement states (Engaged, Detailed, Guided, Disengaging) with very different resolution rates (~78% down to ~30%).
4. Showed that the *same* agent behavior helps in one state and hurts in another — a finding invisible in a pooled/average effect.
5. Wired the state model into the harness: state inferred every turn, a **versioned policy** per state (prompt/tool change) recorded in LangSmith, **offline replay verification** before shipping, and **randomized assignment** between existing behavior and the new policy to get exogenous variation, since responses aren't otherwise randomly assigned.
6. Argued the same recipe generalizes to any multi-turn agent with (a) an outcome only observed at the end, (b) turn-level signals computable from the trace, and (c) agent-controlled behaviors — explicitly citing coding agents and sub-agent orchestrators (e.g., "tests failing in new ways vs the same way every time," "edits circling the same files") as places a latent-state read could trigger re-planning instead of blindly continuing.

The throughline: **evaluation becomes a control signal, not just a grade** — it has to be readable *before* the outcome is realized.

---

## 2. Where We Already Have the Same Ingredients

We don't have a live conversational agent, but we have two structurally similar systems with the same three ingredients Candidly names (delayed outcome, in-trace turn-level signals, controllable behavior):

| System | Delayed outcome | Turn-level trace signals (analog of "emissions") | Controllable behavior (analog of "transition inputs") |
|---|---|---|---|
| `autoresearch_agent.py` research sessions | Whether a research direction becomes a promoted, validated candidate (weeks/many plans later) | Per-plan `evidence_coverage`, `retrieval_diversity`, `counter_causal_count`, `readiness_score` (`autoresearch_agent.py:2055` `evaluate_research_plan`) | Which direction/command is prioritized next (`_prioritize_command`, `autoresearch_agent.py:1667`) |
| `ClinicalDecisionPolicy` recommendation cards | Realized 2-week TIR/hypo-hyper shift after a settings change (`clinical_decision_report.py`) | Per-patient phenotype/controller signals (`patient_phenotyper.py`, `controller_dynamics_facts_loader.py`), confidence/effect-size gates (`clinical_decision_policy.py:115` `passes_change_gate`) | Which domain (basal/ISF/CR) is changed, titration clamp, deconfounded-credit toggles (`clinical_decision_policy.py:184` `credited_confidence`) |

Both already do a *version* of Candidly's emission/transition-input separation, just framed causally rather than as an HMM: `deconfounding.py` and `clinical_rules.py:28` explicitly separate **patient-side physiological signal** from **controller-side masking behavior** (Loop/AAPS/Trio dampening apparent effect). That is the same conceptual split Candidly uses (user behavior reveals state; agent/controller behavior is confounded with the lever), just applied to insulin controllers instead of chat responses.

MLflow is our LangSmith: `mlflow_utils.py` already gives us run-level provenance, tags, and artifact logging, and the promotion ladder proposed in `docs/60-research/mlflow-experience-report-2026-06-27.md:233-252` (`research` → `candidate` → `guarded-production-metadata` → `recommendation-gate` → `production-reference`) is structurally identical to Candidly's "versioned policy regime... recorded on the turn."

---

## 3. Concrete Gaps and Opportunities

### 3.1 Autoresearch: from ex-post readiness score to a mid-session control signal (highest-value parallel)

Today, `evaluate_research_plan()` (`autoresearch_agent.py:2055`) computes `readiness_score` **after** a single plan is fully built — evidence retrieved, hypotheses drafted, counter-causal audit run once. This is exactly Candidly's *starting point* (an ex-post label), not yet their end state (a turn-level control signal read mid-generation).

We already store a memory that captures the underlying need almost verbatim:

> "For autoresearch in this repo, prioritize detecting and counter-acting counter-causal reasoning so the harness can redirect research toward cleaner causal lines."

Candidly's coding-agent example is a near-literal match: *"tests failing in new ways... versus the same way every time; edits circling the same files without shrinking the problem; review comments getting shorter and more corrective... An agent stuck in a bad state should stop, re-plan, or ask a question rather than push another patch."* Our `_counter_causal_audit()` (`autoresearch_agent.py:1646`) already flags counter-causal risk **within one plan**, but nothing currently tracks whether **successive** plans/directions in a session are converging (new evidence, shrinking counter-causal findings, rising readiness) or circling (same counter-causal category recurring, shrinking evidence diversity, oscillating readiness).

**Opportunity (P0)**: Add a lightweight *session-level* state layer around `build_research_plan()`:
- Persist per-call summaries (`readiness_score`, `counter_causal_count` by category, `evidence_refs` set, `retrieval_diversity_score`) across a sequence of calls in a research session (MLflow nested run or a simple session log next to `externals/experiments/autoresearch/`).
- Compute simple trend features turn-over-turn: is evidence diversity shrinking? Is the same counter-causal category (e.g. "collider", "counterfactual vs observed") recurring without a new `reasoning_correction`? Is `readiness_score` flat or oscillating across 2+ calls?
- Feed those trend features into `_prioritize_command()` so a "circling" session gets a stronger redirect (e.g., force a different `DirectionSpec`, or emit a `needs-human-review` status) instead of only auditing the current plan in isolation.

This does not require an IO-HMM. Start with deterministic rule thresholds on the features above (mirrors Candidly's own path: they first proved the signal was learnable from simple features before fitting the heavier state model). Only fit a real state model once enough labeled sessions accumulate (see §3.4).

### 3.2 Clinical decision policy: state-conditioned gates instead of one global threshold

Candidly's central empirical finding — *the same agent behavior helps in one state and hurts in another, and pooling cancels the effect* — is a direct warning for `ClinicalDecisionPolicy`. Today `min_confidence_for_change`, `deconfounded_isf_confidence_cap`, and `deconfounded_cr_confidence_cap` (`clinical_decision_policy.py:50,106-108`) are **global constants** applied identically regardless of patient regime, even though we already compute per-patient regime signals elsewhere (phenotype terciles, controller lineage/aggressiveness in `patient_phenotyper.py`, `controller_dynamics_facts_loader.py`).

**Opportunity (P1)**: Before tightening or loosening any single global gate based on aggregate validation results, check whether the effect is regime-dependent (e.g. does a looser gate help high-data-fidelity patients but increase risk for sparse-data or highly-controller-masked patients?). If so, condition the gate on the existing phenotype/controller signals rather than searching for one global number — this is exactly the failure mode ("pooled effect cancels") Candidly documents.

### 3.3 Offline replay verification before promoting policy changes

Candidly requires: replay a proposed policy on a held-out dataset, regenerate the response, and score it with evaluators *before* it becomes an experiment arm. We have the building blocks (`experiments_validated.py`, `forward_simulator.py`, `prediction_validator.py`) but no standard "replay this `ClinicalDecisionPolicy` config change against a fixed held-out patient-day set and diff the resulting recommendation cards" harness.

**Opportunity (P1)**: Formalize a small replay utility: given a policy config diff, run it against a frozen cohort, diff domain recommendations/confidence/justifications against the previous config, and require an explicit check that only the intended change occurred (e.g., "ISF gate loosened only where expected, no unintended CR flips"). Log both runs to MLflow so the diff itself is a tracked artifact — this is cheap given `mlflow_utils.py` already exists, and it's the natural next rung on the promotion ladder in the MLflow experience report.

### 3.4 Closing the loop: record realized outcomes against the original recommendation

Candidly puts the inferred state, prompt version, experiment arm, outcome, and resolution "on the same trace." Our `clinical_decision_report.py` already *projects* a 2-week outcome, but nothing currently writes the **realized** 2-week outcome back against the original MLflow run once it's observable. Without that link, we can never fit anything like Candidly's state model, because there's no labeled trajectory data to fit it from — we'd be stuck at their "ex-post readiness label" stage indefinitely.

**Opportunity (P2, longer horizon)**: When a later analysis run re-processes a patient whose settings changed N weeks ago, look up the originating recommendation-card MLflow run (already git/workspace-tagged per `mlflow_utils.py:112` `default_tags`) and log the realized TIR/hypo/hyper delta as a follow-up metric on that same run. Only after this exists for enough patients does it make sense to consider fitting any state model (even a simple regime classifier, not necessarily a full IO-HMM) over patient trajectories, using patient-side therapy-fidelity/data-quality signals as emissions and advisor/controller behavior as transition inputs — reusing the emission/transition split we already apply in `deconfounding.py`.

### 3.5 What does *not* transfer directly

- **No live conversational end user.** There's no per-turn human response to steer mid-stream the way Cait steers a chat; our closest analog is a multi-call research *session* (autoresearch) or a report-generation *session* (decision support), not a chat.
- **No ethical randomized A/B on patients** outside a formal trial. Candidly's randomized-assignment step (needed because responses aren't otherwise randomly assigned) has no direct equivalent here. Our existing substitute — leave-patient-out cross-validation and controller-lineage stratification (Loop vs AAPS vs Trio as a natural, not randomized, source of variation) — is the appropriate stand-in and should keep being treated as such rather than as a literal substitute for randomization.
- **Small-n regime.** Candidly fit an IO-HMM over thousands of conversations. Our patient cohorts and autoresearch sessions are far smaller; a full HMM would likely overfit or fail to converge to a stable regime (their own report: a 5-state model "did not recover a consistent, usable regime" even with thousands of conversations). Rule-based/heuristic trend features (§3.1) are the right starting point, matching the MLflow promotion ladder's own preference for `research` → `candidate` before anything production-facing.

---

## 4. Prioritized Recommendations

| Priority | Action | Effort | Builds on |
|---|---|---|---|
| P0 | Add session-level trend tracking (evidence diversity, recurring counter-causal category, readiness monotonicity) to `autoresearch_agent.py` and feed it into `_prioritize_command` | Small | `evaluate_research_plan`, `_counter_causal_audit`, existing MLflow spans |
| P0 | Tag recommendation-card and report artifacts with the producing advisor's MLflow run id + promotion stage (research/candidate/guarded-production-metadata/recommendation-gate/production-reference) | Small | `mlflow_utils.py`, `clinical_decision_report.py` |
| P1 | Audit whether `ClinicalDecisionPolicy` gate effects are regime-dependent before further global threshold tuning; condition gates on existing phenotype/controller signals if so | Medium | `patient_phenotyper.py`, `controller_dynamics_facts_loader.py`, `clinical_decision_policy.py` |
| P1 | Build a replay-and-diff harness for policy config changes against a frozen cohort, logged to MLflow | Medium | `experiments_validated.py`, `forward_simulator.py` |
| P2 | Record realized (not just projected) 2-week outcomes back onto the originating MLflow run to enable future trajectory labeling | Medium-Large | `mlflow_utils.py` tagging, `clinical_decision_report.py` |
| P2 | Only after P2 outcome-linking accumulates: consider a lightweight regime classifier (not a full IO-HMM) over patient trajectories | Large, deferred | `deconfounding.py` emission/transition split |

---

## 5. Bottom Line

Candidly's core move — replacing an ex-post grade with a turn-level state estimate that is legible *before* the outcome is known, and separating "signal used to read state" from "behavior used to move it" — is directly applicable to `autoresearch_agent.py`'s multi-call research sessions and, more speculatively, to how `ClinicalDecisionPolicy` gates could become regime-aware instead of globally thresholded. We already have the prerequisite infrastructure (MLflow provenance, a promotion ladder, an existing causal emission/transition-style split in the deconfounding work) to adopt the *cheap* parts of this pattern now (§3.1, §3.2 rule-based version) without needing Candidly's full IO-HMM, and a clear, low-risk path (§3.3–§3.4) toward eventually being able to fit one if the data warrants it.

---

## 6. Scope Refinement and First Build: Per-Patient Therapy Trajectory State

Follow-up discussion challenged §3.1's autoresearch-session framing directly: **the real analog to Candidly's "conversation with a delayed outcome" is a patient's multi-day therapy trajectory, not our internal research-tooling loop.** A patient's sequence of therapy-review cycles (decision -> observed response -> next decision) has a genuine delayed outcome that matters to our actual mission (glycemic control, reduced friction, safety), where the autoresearch angle only affects our own research velocity. Decision, recorded here for traceability:

> **Per-patient therapy-trajectory state is the primary target going forward. Autoresearch session-tracking (§3.1, the first P0 row in §4) is dropped from active work** — it doesn't move any clinical outcome, and the counter-causal-audit gap it would have addressed remains only a documented, not urgent, opportunity. §3.2-§3.4 (regime-conditioned gates, replay harness, outcome-linking) still apply, now understood as downstream consumers of the trajectory-state harness built below rather than a separate track.

### 6.1 Design decisions (and why)

**Turn granularity — fixed 72-hour sequential windows, not calendar weekday/weekend blocks.** A turn needs to be long enough to see a within-turn trend (each daily basal segment repeats ~3x in 72h) but short enough to still be state-like rather than a whole-history average — this also roughly matches practical titration guidance already used elsewhere in this repo ("check every few days," not every two weeks). Weekday/weekend was deliberately **not** used as a hard turn boundary, because that would presuppose day-type is the regime that matters rather than letting the data show it, and it would make turns unequal length (5-day vs 2-day), complicating any count-based feature. Instead, `weekend_day_fraction` is carried as a continuous per-turn feature.

**Outcome label — a cheap, rule-based ADA-threshold proxy, not unsupervised discovery (yet).** Candidly *discovered* 4 states via EM/IO-HMM fitting over thousands of conversations. We do not have that scale: roughly 20-30 patients x 40-60 turns each, and turns within a patient are highly autocorrelated (not independent draws), so naive clustering risks discovering "which patient this is" rather than a transferable regime — the same Simpson's-paradox/confounding risk this repo already treats carefully elsewhere (`deconfounding.py`, controller-lineage stratification). Candidly's own report is a warning sign here too: even with thousands of conversations, a 5-state model "did not recover a consistent, usable regime." **Unsupervised state discovery is deferred, not abandoned** — see §6.4 for what would need to be true first. What was built instead: continuous emission features stored per turn (so a future clustering/HMM pass can reuse them directly) plus an interpretable 5-value rule-based label (`improving` / `stable_good` / `stable_poor` / `worsening` / `unknown`) derived from the *next* turn's realized ADA-threshold trend, safety-first (a follow-up turn that breaches ADA hypoglycemia targets is always `worsening`, even if TIR nominally rose).

**Emission features — reuse validated physiology research rather than inventing new proxies.** Beyond the surface glycemic/activity features (TIR/TBR/TAR/CV, data completeness, meal/bolus/override/exercise activity), four already-researched physiology signals were folded in directly:

| Feature family | Source | What it captures |
|---|---|---|
| Supply/demand flux (EGP proxy) | `metabolic_engine.compute_metabolic_state()` (EXP-1771/1772) | hepatic production, carb absorption, insulin demand, net flux |
| Insulin "wall"/overflow saturation | `clinical_rules.detect_insulin_saturation()` (EXP-2660/2662) | insulin delivered but glucose not responding (the closest validated proxy for an "overflowing" supply-vs-demand state) |
| Glycogen-loading proxy (empty vs full) | trailing 48h carbs (EXP-2622/2627: r=-0.303 with subsequent overnight drift) | low-carb history -> rising overnight BG ("emptier" stores); high-carb -> falling ("fuller") |
| CGM/infusion-site wear & longevity | `cage_hours`/`sage_hours` (already in the grid) + `WearFactsLoader` EXP-2863 `p_site_degradation` | site-age effects on effectiveness |

Note: `types.OvernightDriftAssessment` declares `carbs_48h_g`/`glycogen_note` fields, but no current production function appears to populate them — the module computes its own trailing-48h carbs sum directly rather than depending on that dataclass. The EXP-2863 site-degradation probability is per-patient (static), not per-turn, so it's joined as a constant covariate across a patient's turns rather than a turn-varying feature.

### 6.2 What was built

| Deliverable | Location | Purpose |
|---|---|---|
| Turn/feature/label harness | `tools/cgmencode/production/therapy_trajectory_state.py` | Loads a patient's grid, segments into 72h turns, computes ~25 continuous emission features per turn (glycemic, activity, flux/EGP, saturation, glycogen proxy, site wear), and a rule-based outcome label |
| Unit tests | `tools/cgmencode/production/test_therapy_trajectory_state.py` | 16 tests on synthetic grids covering turn segmentation, feature computation, all 5 label branches (including the safety-priority rule), and end-to-end graceful degradation when profile columns are absent |
| Cohort CLI + MLflow logging | `tools/cgmencode/run_therapy_trajectory_state.py` | `python -m tools.cgmencode.run_therapy_trajectory_state [--patient-ids ...] [--turn-hours 72]` — writes a labeled-turn parquet as a tracked MLflow evidence artifact (`task_type=therapy-trajectory-state`), with summary metrics (state distribution, mean TIR by state, saturation-level distribution) |

Verified against real longitudinal data (patients a-d, `externals/ns-parquet/training`, ~180 days each -> 60 turns/patient): the harness runs end-to-end, all 16 unit tests plus the full existing 1103-test production unit suite pass with no regressions, and the MLflow run records successfully (`n_patients`, `n_turns`, `n_physiology_available` metrics; `therapy_trajectory_state/summary.json` artifact). An early, non-causal sanity check on 4 patients: mean TIR was highest in `stable_good` turns (79.2%) and lowest in `stable_poor` (55.2%), consistent with the label scheme being behaviorally coherent; the `weekend_day_fraction`-vs-TIR correlation was negligible (0.012) in this small sample — not evidence either way yet, just a first look.

### 6.3 What this enables next (not yet built)

This harness is infrastructure, not a policy change. It directly unblocks the downstream P1/P2 items from §4 that were previously blocked on having any per-turn trajectory data at all:

- **Regime-dependence audit for `ClinicalDecisionPolicy` gates (§3.2)**: now possible to check, per saturation/flux/glycogen regime, whether a fixed gate threshold's effect is regime-dependent before further global tuning.
- **Outcome-linking (§3.4)**: the label scheme here is itself a backtested proxy for "did the next turn's realized outcome look like the projection." The same join pattern (patient + turn window -> realized ADA metrics) is what would be needed to reconcile `ClinicalDecisionReport`'s *projected* 2-week outcome against a *realized* one.
- **Replay-and-diff harness (§3.3)**: this cohort table is a ready-made frozen evaluation set for replaying policy config changes against real historical trajectories.

### 6.4 What would need to be true before attempting unsupervised state discovery

Recorded explicitly so this isn't attempted prematurely:

1. Enough labeled turns across enough *distinct* patients (not just enough total turns) that leave-**patient**-out cross-validation is viable — leave-turn-out would leak patient identity into "discovered" states.
2. A candidate range of state counts (e.g. k=2..6) evaluated by BIC/held-out fit *and* interpretability, the same two-sided check Candidly used, given their own experience that more states did not always mean a better model.
3. Controller-lineage (Loop/AAPS/Trio) treated as a stratification variable or explicit covariate during fitting, not left for the clustering to absorb — otherwise "discovered" states risk encoding controller identity rather than a transferable behavioral regime, mirroring this repo's existing Simpson's-paradox concerns in the deconfounding work.
4. A concrete comparison target: any discovered clustering should be checked against the cheap rule-based label from §6.1 as a baseline — it should recover at least as much predictive/actionable signal, not just be "different."
