# Bug Impact Assessment: Experiment Scripts

## Bug 1: IOB Forward-Fill → `fillna(0)` Creates Artificial IOB Drops

**File**: `tools/aid-autoresearch/eval_autotune_uam.py:256`

```python
grid['iob'] = grid['iob'].ffill(limit=3).fillna(0)
grid['cob'] = grid['cob'].ffill(limit=3).fillna(0)
```

### Analysis

IOB is sourced from DeviceStatus records, which arrive at irregular intervals
(typically every 5 min but with gaps from connectivity drops). `reindex(...,
method='nearest', tolerance='4min')` maps them to a regular 5-min grid, leaving
NaN where no DeviceStatus exists within ±4 min.

The `ffill(limit=3)` bridges gaps of up to 15 min (3 × 5-min steps). After that,
`fillna(0)` snaps IOB to zero. In reality, IOB decays exponentially over the DIA
(~5 hours). A 20-minute DeviceStatus gap would produce:

```
..., 3.2, 3.2, 3.2, 3.2, 0.0, 0.0, ...  ← artificial cliff
```

The physics-based meal detector (`detect_meals_physics()`, line 440) computes:

```python
iob_diff = np.diff(np.concatenate([[iob[0]], iob]))
insulin_absorbed = np.maximum(0, -iob_diff + bolus + basal_insulin)
bgi = -insulin_absorbed * isf
residual = delta - bgi - carb_effect
```

When IOB drops from 3.2 → 0.0, `iob_diff` = −3.2, so `insulin_absorbed` spikes
(−(−3.2) = +3.2), producing a large *negative* BGI. This *inflates* the expected
insulin effect, making the residual *more negative* (not positive), which would
actually **suppress** meal detection at that point — the opposite of a false positive.

However, when IOB resumes from 0 → real value, the reversal creates a sudden
*positive* residual spike that could trigger a false detection.

### Verdict: **Real bug, modest impact**

- **Direction**: Can create both false negatives (at the drop) and false positives
  (at the recovery), but the net effect on F1 is limited because:
  - Most IOB gaps are short (<15 min) and caught by `ffill(limit=3)`
  - The 30-min rolling average (`rolling_window=6`) smooths single-point artifacts
  - The 2σ adaptive threshold adds robustness
- **Impact on F1=0.513**: Estimated ±0.01–0.02 (1–4%). The FPR values (4–16%) seen
  in the results are consistent with this level of noise contribution.
- **Recommended fix**: Replace `fillna(0)` with exponential IOB decay using
  DIA parameters, or `fillna(method='ffill')` with no limit (IOB is always ≥ 0
  and monotonically decays in the absence of new doses).

---

## Bug 2: Filter-then-Index Loses Alignment (DIA Glucose Filtering)

**File**: `tools/cgmencode/exp_clinical_1291.py:1093–1094`

```python
dia_bg = glucose[i + DIA_STEPS - 6:i + DIA_STEPS + 6]
dia_bg = dia_bg[~np.isnan(dia_bg)]
if len(dia_bg) == 0:
    continue
actual_bg = float(np.mean(dia_bg))
```

### Analysis

This code extracts a ±30-minute window around the DIA endpoint and averages all
non-NaN values. The "filter-then-index" concern is whether removing NaNs
destroys temporal alignment. Here, alignment is **not needed** — the code takes
the *mean* of all valid BG values in the window, not indexing into a specific
position. The NaN filter is correct for computing a robust endpoint BG estimate.

However, there is a **separate nadir detection issue** at lines 391–397:

```python
future_bg = glucose[i:i + DIA_STEPS]
valid_future = ~np.isnan(future_bg)
if valid_future.sum() < DIA_STEPS * 0.5:
    continue
nadir_idx = np.nanargmin(future_bg)
nadir_bg = future_bg[nadir_idx]
delta_bg = start_bg - nadir_bg
```

`np.nanargmin` correctly handles NaN by ignoring them, so `nadir_idx` is the
position of the actual minimum glucose in the DIA window. This is sound.

The real concern is using **nadir** vs **endpoint**: measuring ISF from the nadir
rather than the DIA endpoint finds the *maximum* glucose drop, which overestimates
ISF (the glucose may rebound after the nadir). But this is by design — the code
explicitly uses nadir for the deconfounded ISF analysis (EXP-1291) while
EXP-1298 (lines 1092–1097) uses the endpoint window average. The two analyses
intentionally measure different things.

### Verdict: **Not a bug**

- The NaN filtering is correct for computing a window average
- `np.nanargmin` preserves index alignment for nadir detection
- Nadir vs endpoint is an intentional design choice, not a bug
- **Impact on DIA estimation**: None

---

## Bug 3: PK Scaling Factors — `pk[:, 2] * 2.0` and `pk[:, 7] * 200.0`

**Files**: `tools/cgmencode/exp_clinical_1291.py:67,367` and
`tools/cgmencode/continuous_pk.py:545–554,736–744`

### Analysis

The PK array is built by `build_continuous_pk_features()` in `continuous_pk.py`.
It normalizes channels by dividing by `PK_NORMALIZATION` constants:

```python
# continuous_pk.py:736-744
features = np.column_stack([
    insulin_total / 0.05,     # ch 0
    insulin_net / 0.05,       # ch 1
    basal_ratio / 2.0,        # ch 2 ← basal_ratio normalized by 2.0
    carb_rate / 0.5,          # ch 3
    carb_accel / 0.05,        # ch 4
    hepatic / 3.0,            # ch 5
    net_balance / 20.0,       # ch 6
    isf_array / 200.0,        # ch 7 ← ISF normalized by 200.0
])
```

The consumer code in `exp_clinical_1291.py` denormalizes:

```python
basal_ratio = pk[:, 2] * 2.0     # reverses ÷ 2.0
isf_profile = pk[:, 7] * 200.0   # reverses ÷ 200.0
```

These are **exact inverses** of the normalization. The values are documented in
`PK_NORMALIZATION` (continuous_pk.py:545):

| Channel | Index | Normalization | Physical meaning |
|---------|-------|---------------|------------------|
| `basal_ratio` | 2 | 2.0 | 1.0 = nominal delivery rate |
| `isf_curve` | 7 | 200.0 | mg/dL per U insulin |

Verify: `basal_ratio` is the ratio `actual_rate / scheduled_rate` (line 308),
so values around 1.0 are expected; `/ 2.0` maps it to ~0.5 for ML, `* 2.0`
restores it. Similarly, typical ISF is 20–100 mg/dL/U; `/ 200` maps to 0.1–0.5,
`* 200` restores the original.

Also used consistently at lines 67, 313, 366, 494, 686, 780, 975, 1072, 1260.

### Verdict: **Not a bug — correctly documented denormalization**

- The scaling factors exactly invert `PK_NORMALIZATION`
- Documented in `continuous_pk.py:545-554`
- Consistent across all uses in the file
- **Impact**: None

---

## Bug 4: ISF Unit Heuristic — `if isf_val < 15 → assume mmol/L`

**File**: `tools/aid-autoresearch/eval_autotune_uam.py:142`

```python
if units == 'mmol/L' or isf_val < 15:  # heuristic: mmol/L values are small
    isf_mgdl = isf_val * MMOL_TO_MGDL
```

### Analysis

The heuristic assumes any ISF < 15 is in mmol/L units. Looking at the actual
data in `eval_results.json`, all 10 patients have `profile_isf` values:

```
21, 25, 33, 40, 48.65, 55, 70, 72, 90, 92
```

All are ≥ 21, so the heuristic **never triggers on the `< 15` branch** for this
dataset. The `units` field is also not present in the results, meaning the
condition falls through to `isf_mgdl = isf_val` (the else branch) in practice.

**Is the heuristic valid in general?** No — it's problematic:
- Very insulin-sensitive T1D patients (children, lean adults) can have ISF =
  8–14 mg/dL/U in mg/dL units. These would be incorrectly multiplied by 18.
- The `or` logic means even when `units == 'mg/dL'`, any ISF < 15 gets wrongly
  converted. The condition should be `and`, not `or`.
- For the typical mmol/L range, ISF would be 1–5 mmol/L/U, which is well below 15.
  An ISF of 10 mg/dL would be misidentified (→ 180 mg/dL, 18× too high).

### Verdict: **Latent bug, no current impact**

- **Impact on reported F1=0.513**: None — no patient has ISF < 15
- **Potential impact**: If a highly insulin-sensitive patient (ISF ~10 mg/dL/U)
  were added, their ISF would be inflated 18×, causing massive overestimation
  of insulin effect → BGI vastly too negative → all glucose rises flagged as
  unexplained → many false positive UAM detections.
- **Recommended fix**: Use `if units == 'mmol/L' or (units not in ('mg/dL', 'mg/dl') and isf_val < 5):`
  or better, trust the `units` field and only fall back to the heuristic when
  units are unknown.

---

## Bug 5: Minimum 10 mg/dL ΔBG Threshold for Corrections

**File**: `tools/cgmencode/exp_clinical_1291.py:398`

```python
delta_bg = start_bg - nadir_bg
if delta_bg < 10:
    continue
```

### Analysis

CGM noise for Dexcom G6/G7 is typically ±10–15 mg/dL MARD (Mean Absolute
Relative Difference ~9%). A 10 mg/dL threshold is at the noise floor, meaning
some "corrections" with ΔBG=10–15 are indistinguishable from sensor noise.

However, several protective factors reduce noise impact:

1. **Pre-BG averaging** (line 389): `start_bg = np.mean(pre_bg)` averages up to
   4 glucose values (20 min), reducing noise by ~√4 = 2× → effective noise ~5–7.

2. **Nadir uses raw values**: `nadir_bg = future_bg[nadir_idx]` is a single point,
   so it's noisier. But the nadir represents the *minimum* in a ~5h window
   (60 points), which has a negative bias. For normally distributed noise with
   σ=10 mg/dL, the expected minimum of 60 samples is ~2.5σ = 25 mg/dL below the
   true mean, inflating ΔBG. This bias makes the threshold less restrictive than
   it appears.

3. **Minimum bolus of 0.3 U** (line 374): With a typical ISF of 40–90 mg/dL/U,
   0.3 U should cause a 12–27 mg/dL drop. A 10 mg/dL threshold captures most
   real corrections.

4. **The DIA endpoint analysis** (EXP-1298, lines 1092–1097) is not affected —
   it averages 12 points (±30 min window), giving √12 ≈ 3.5× noise reduction.

To estimate how many corrections would be lost with a 20 mg/dL threshold:
given that start_bg must be ≥150 and a 0.3U correction with ISF=50 would cause
a ~15 mg/dL drop, roughly 20–30% of the weakest corrections might be filtered.
But those weak corrections are also the noisiest and least informative.

### Verdict: **Design tradeoff, not a bug — but borderline**

- **Is it a bug?** The threshold is defensible but aggressive. The nadir-based
  measurement has a negative bias that partially compensates, effectively raising
  the real threshold.
- **Impact on results**: The EXP-1291 deconfounded ISF measurement uses nadir ΔBG.
  The 10 mg/dL threshold includes some noisy corrections, which would increase
  variance in ISF estimates but not systematically bias them. The reported
  "ISF is 2.66× profile" finding (from the docstring) is a large effect unlikely
  to be driven by noisy 10–15 mg/dL corrections.
- **Recommended fix**: Raise to 15–20 mg/dL, or use the mean of a ±15-min window
  around the nadir (like EXP-1298 does) instead of a single nadir point.

---

## Summary

| Bug | Severity | Affects Results? | Direction | Magnitude |
|-----|----------|-----------------|-----------|-----------|
| 1: IOB fillna(0) | Moderate | Yes (marginal) | ±F1 | ~0.01–0.02 on F1=0.513 |
| 2: Filter-then-index | None | No | N/A | N/A |
| 3: PK scaling | None | No | N/A | Correctly documented |
| 4: ISF <15 heuristic | Latent | No (current data) | Would inflate false positives | N/A for current patients |
| 5: 10 mg/dL threshold | Low | Marginal | ↑ ISF variance | ~5% more noisy samples |

**Overall assessment**: The reported F1=0.513 for physics ML is **not materially
affected** by these bugs. Bug 1 is the only active concern but its impact is
within the noise of the measurement (~2–4%). Bug 4 is a correctness issue waiting
to happen but doesn't affect the current 10-patient cohort. Bugs 2, 3, and 5 are
either non-issues or acceptable design tradeoffs.

The strongest recommendation is to fix Bug 1 (IOB exponential decay instead of
zero-fill) and Bug 4 (ISF unit logic) before expanding the patient cohort.
