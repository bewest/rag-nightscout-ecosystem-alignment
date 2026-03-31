# ML Pipeline Gaps

Gap tracking for the ML composition architecture. See `docs/architecture/ml-composition-architecture.md` for design context and `docs/60-research/ml-technique-catalog.md` for technique details.

**ID convention**: `GAP-ML-NNN`

---

## Resolved

### GAP-ML-001: No bridge between SIM-* vectors and cgmencode format

**Description**: Physics simulation output (SIM-*.json) could not be ingested by cgmencode training pipeline.

**Resolution** (2026-04): `tools/cgmencode/sim_adapter.py` bridges SIM-*/TV-* conformance vectors → 8-feature training tensors. Supports both cgmsim and UVA/Padova output.

### GAP-ML-002: cgmencode trained on ~1,000 vectors from single patient

**Description**: All models underfit; no generalization evidence.

**Resolution** (2026-04): Latin Hypercube parameter sweep (`tools/cgmencode/generate_training_data.py`) generates 50+ diverse patient profiles. 3,500 cgmsim + 2,400 UVA/Padova vectors validated. Transformer AE generalizes to 2.12 MAE across diverse patients.

---

## Immediate (blocks near-term progress)

### GAP-ML-003: No override event labels in any dataset

**Description**: Cannot train decision models (Layer 4) without labeled override events.

**Affected Systems**: Decision classifier, policy layer

**Impact**: Blocks all Layer 4 work.

**Remediation**: Extract from Nightscout treatment logs where `eventType` contains override-like actions (Eating Soon, Exercise, custom notes). Even noisy labels suffice for Stage 1.

### GAP-ML-004: Conditioned Transformer produces point estimates only

**Description**: No uncertainty quantification for safety-critical dosing decisions.

**Affected Systems**: Safety evaluation, policy layer

**Impact**: Cannot compute P(hypo | dose) needed for safety floor constraint.

**Remediation**: Add Monte Carlo dropout, ensemble, or pair with fixed Diffusion model. Alternatively, train Conditioned VAE that provides distributional output.

---

## Medium-Term (needed for anticipatory management)

### GAP-ML-005: No explicit event classifier

**Description**: No model predicts *when* an override should occur (meal/exercise/sleep detection).

**Impact**: Cannot infer "Eating Soon" without button press.

**Remediation**: Start with XGBoost on tabular features → upgrade to TCN/Transformer on cgmencode embeddings.

### GAP-ML-006: No temporal state tracker (ISF/CR drift)

**Description**: Cannot detect "insulin resistance trending up" over days/weeks.

**Impact**: System treats physiological parameters as static.

**Remediation**: Start with online Kalman filter over daily ISF/CR estimates; compare to oref0 autosens.

### GAP-ML-007: No context signal ingestion

**Description**: Pattern recognition limited to glucose-insulin-carbs. No calendar, weekday, travel, activity signals.

**Impact**: Cannot learn "Tuesday lunch at work" patterns.

**Remediation**: Extend 8-feature vector or add side-channel conditioning.

### GAP-ML-008: Statistical fingerprinting pipeline not implemented

**Description**: Cannot calibrate physics engine against real population distributions.

**Impact**: Physics-ML residual approach (architecture §2) blocked.

**Remediation**: Build fingerprint extraction → Wasserstein/DTW/ACF distance computation → parameter optimization loop. Lower priority since §8.2 residual approach bypasses explicit calibration.

---

## Longer-Term (autonomous optimization)

### GAP-ML-009: No policy layer for override selection

**Description**: System can predict events but not recommend actions.

**Remediation**: Progressive approach — supervised imitation → contextual bandits → constrained offline RL.

### GAP-ML-010: No safety constraint framework for learned policies

**Description**: RL/bandit could suggest dangerous overrides without physics guard.

**Remediation**: Safety floor architecture: physics check → uncertainty check → controller agreement → human approval.

### GAP-ML-011: No feedback loop from override acceptance/rejection

**Description**: Models cannot improve from user behavior.

**Remediation**: Log accept/reject decisions → retrain event classifier and policy.

### GAP-ML-012: Diffusion implementation simplified

**Description**: Forward process is `x + noise`, not proper DDPM β-schedule. Uncertainty estimates meaningless.

**Affected Systems**: Risk quantification, safety evaluation

**Remediation**: Implement proper linear/cosine β-schedule noise process.
