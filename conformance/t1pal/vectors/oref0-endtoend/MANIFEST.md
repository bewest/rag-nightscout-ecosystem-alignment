# oref0 End-to-End Test Vector Manifest

> Generated 2025-07-14 — Audit of TV-001 through TV-108

## Summary

| Metric | Value |
|--------|-------|
| Total vectors | 100 |
| Natural (captured) | 78 (TV-001 – TV-086) |
| Synthetic (generated) | 22 (TV-087 – TV-108) |
| Missing IDs | TV-003, TV-033–035, TV-037, TV-057, TV-061, TV-071 |
| Natural BG range | 70.5 – 218 mg/dL (mean 128.0) |
| Synthetic BG range | 55 – 300 mg/dL |
| Natural IOB range | −0.530 – 2.996 U |
| Synthetic IOB range | −1.000 – 2.000 U |

---

## Natural Vectors (TV-001 – TV-086)

All 78 natural vectors have `category: "basal-adjustment"` and were extracted from
real AAPS `ReplayApsResultsTest` fixtures (October–January 2023-24), except TV-086
which comes from the `bewest/openaps-example` repository (July 2016).

Each natural vector contains:

- **Internally consistent inputs**: glucose, delta, IOB, activity all captured from
  the same algorithm invocation on a real phone.
- **Verified originalOutput**: the `originalOutput` field contains the actual oref0
  result computed by AAPS at that timestamp, with matching `predBGs` trajectories.
- **Ground-truth reliable**: safe to use as oracle comparisons in cross-validation.

### Special note: TV-086

TV-086 is the only natural vector with nonzero `bolusIob` (2.052 U) and the highest
total IOB (2.996 U). It uses different targets (min\_bg 106, max\_bg 125 vs the usual
91 or 99). It has **no originalOutput** field — it was extracted from raw OpenAPS
data without a captured algorithm result.

| ID | Filename | BG | Delta | IOB | EventualBG | Scenario |
|----|----------|----|-------|-----|------------|----------|
| TV-001 | TV-001-2023-10-28_133013.json | 90.8 | +6.95 | −0.53 | 154 | Rising from normal, negative basal IOB |
| TV-002 | TV-002-2023-10-28_133514.json | 89.3 | +5.59 | −0.50 | 143 | Rising from normal, negative basal IOB |
| TV-004 | TV-004-2023-10-28_134513.json | 90.8 | +12.39 | −0.52 | 164 | Fast rise from normal |
| TV-005 | TV-005-2023-10-28_135013.json | 86.2 | +8.81 | −0.49 | 145 | Moderate rise from low-normal |
| TV-006 | TV-006-2023-10-28_135514.json | 129.2 | +27.12 | −0.45 | 295 | Rapid rise approaching high |
| TV-007 | TV-007-2023-10-28_140013.json | 133.8 | +17.38 | −0.42 | 260 | Continued high rise |
| TV-008 | TV-008-2023-10-28_140514.json | 155.9 | +16.28 | −0.39 | 274 | High and rising |
| TV-009 | TV-009-2023-10-28_141014.json | 174.4 | +19.71 | −0.36 | 305 | High and rising fast |
| TV-010 | TV-010-2023-10-28_141513.json | 189.3 | +16.07 | −0.33 | 301 | High plateau |
| TV-011 | TV-011-2023-10-28_142013.json | 192.5 | +7.08 | −0.30 | 248 | High, rise slowing |
| TV-012 | TV-012-2023-10-28_142513.json | 211.2 | +13.55 | −0.27 | 302 | Very high |
| TV-013 | TV-013-2023-10-28_143013.json | 194.0 | −5.20 | −0.24 | 258 | High, starting to fall |
| TV-014 | TV-014-2023-10-28_143514.json | 207.0 | +2.91 | −0.22 | 234 | High, near flat |
| TV-015 | TV-015-2023-10-28_144013.json | 184.8 | −10.50 | −0.19 | 202 | High, falling |
| TV-016 | TV-016-2023-10-28_145014.json | 173.3 | −5.74 | −0.15 | 156 | Falling from high |
| TV-017 | TV-017-2023-10-29_191512.json | 111.5 | +12.40 | −0.28 | 80 | In-range, rising, negative longAvg |
| TV-018 | TV-018-2023-10-29_192012.json | 88.4 | −4.39 | −0.36 | 47 | Low-normal, falling |
| TV-019 | TV-019-2023-10-29_192512.json | 77.0 | −15.31 | −0.43 | 42 | Low, falling fast |
| TV-020 | TV-020-2023-10-31_042017.json | 197.4 | +29.49 | +0.31 | 340 | High, rapid rise, positive IOB |
| TV-021 | TV-021-2023-10-31_042517.json | 180.0 | +1.15 | +0.35 | 165 | High, near flat, positive IOB |
| TV-022 | TV-022-2023-10-31_043017.json | 209.4 | +13.81 | +0.39 | 270 | Very high, rising |
| TV-023 | TV-023-2023-10-31_043517.json | 188.4 | −4.18 | +0.42 | 218 | High, slight fall |
| TV-024 | TV-024-2023-10-31_044017.json | 172.5 | −17.59 | +0.46 | 165 | High, falling fast |
| TV-025 | TV-025-2023-10-31_044516.json | 181.4 | +0.62 | +0.41 | 172 | High, flat |
| TV-026 | TV-026-2023-10-31_045017.json | 146.2 | −20.52 | +0.44 | 81 | Mid-range, dropping fast |
| TV-027 | TV-027-2023-10-31_045517.json | 147.6 | −10.78 | +0.39 | 81 | Mid-range, dropping |
| TV-028 | TV-028-2023-10-31_050018.json | 142.1 | −3.22 | +0.34 | 74 | Mid-range, slight fall |
| TV-029 | TV-029-2023-10-31_050517.json | 95.1 | −33.18 | +0.29 | −18 | Crash: normal BG, massive drop |
| TV-030 | TV-030-2023-10-31_051017.json | 95.8 | −15.19 | +0.24 | −2 | Near-low, fast fall |
| TV-031 | TV-031-2023-10-31_051517.json | 91.0 | −2.95 | +0.18 | 4 | Normal BG, slow fall |
| TV-032 | TV-032-2023-10-31_052017.json | 93.2 | −0.13 | +0.14 | 76 | Near-normal, flat |
| TV-036 | TV-036-2023-10-31_054018.json | 87.7 | +15.64 | −0.04 | 164 | Low-normal, rising fast |
| TV-038 | TV-038-2023-10-31_055017.json | 98.1 | +14.87 | −0.04 | 178 | In-range, rising |
| TV-039 | TV-039-2023-10-31_055518.json | 128.7 | +31.77 | +0.01 | 276 | Rapid rise, near-zero IOB |
| TV-040 | TV-040-2023-10-31_060018.json | 145.5 | +21.41 | +0.05 | 271 | Rising, low IOB |
| TV-041 | TV-041-2023-10-31_060518.json | 142.2 | +3.44 | +0.10 | 156 | Mid-range, slow rise |
| TV-042 | TV-042-2023-10-31_061018.json | 170.8 | +17.96 | +0.14 | 260 | High, rising |
| TV-043 | TV-043-2023-10-31_061519.json | 150.5 | −4.02 | +0.18 | 134 | Mid-range, slight fall |
| TV-044 | TV-044-2023-10-31_062018.json | 194.3 | +22.44 | +0.18 | 295 | High, rapid rise |
| TV-045 | TV-045-2023-10-31_062518.json | 171.6 | −0.51 | +0.22 | 154 | High, flat |
| TV-046 | TV-046-2023-10-31_063018.json | 168.8 | −9.41 | +0.26 | 183 | High, falling |
| TV-047 | TV-047-2023-10-31_063519.json | 199.4 | +19.42 | +0.25 | 263 | High, rising |
| TV-048 | TV-048-2023-10-31_064018.json | 198.7 | +9.69 | +0.29 | 233 | High, slow rise |
| TV-049 | TV-049-2023-10-31_064519.json | 188.2 | −7.23 | +0.33 | 189 | High, slight fall |
| TV-050 | TV-050-2023-10-31_065018.json | 153.1 | −26.91 | +0.31 | 111 | Mid-range, fast fall |
| TV-051 | TV-051-2023-10-31_065518.json | 146.1 | −16.35 | +0.27 | 93 | Mid-range, falling |
| TV-052 | TV-052-2023-10-31_070019.json | 142.6 | −4.68 | +0.22 | 84 | Mid-range, slight fall |
| TV-053 | TV-053-2023-10-31_070518.json | 128.9 | −10.31 | +0.18 | 60 | In-range, falling |
| TV-054 | TV-054-2023-10-31_071018.json | 78.3 | −38.25 | +0.13 | −37 | Low, crash in progress |
| TV-055 | TV-055-2023-10-31_071519.json | 105.5 | +1.30 | +0.09 | 35 | In-range, barely rising |
| TV-056 | TV-056-2023-10-31_072019.json | 92.3 | +0.21 | +0.04 | 23 | Normal, flat |
| TV-058 | TV-058-2023-10-31_073019.json | 75.0 | −0.28 | −0.04 | 30 | Low, flat |
| TV-059 | TV-059-2023-10-31_073519.json | 76.3 | +6.34 | −0.08 | 99 | Low, recovering |
| TV-060 | TV-060-2023-10-31_074019.json | 70.5 | −3.45 | −0.08 | 51 | Low, still falling |
| TV-062 | TV-062-2023-10-31_075019.json | 85.3 | +11.22 | −0.15 | 149 | Low-normal, rising |
| TV-063 | TV-063-2023-10-31_075519.json | 109.4 | +22.36 | −0.11 | 226 | In-range, rapid rise |
| TV-064 | TV-064-2023-12-23_030034.json | 121.0 | −18.44 | +0.51 | 6 | In-range, fast fall, high IOB |
| TV-065 | TV-065-2023-12-23_030536.json | 119.0 | −8.33 | +0.47 | 34 | In-range, falling |
| TV-066 | TV-066-2023-12-23_031036.json | 101.0 | −13.33 | +0.42 | −6 | Normal, fast fall |
| TV-067 | TV-067-2023-12-23_031536.json | 94.0 | −9.50 | +0.38 | −40 | Normal, falling |
| TV-068 | TV-068-2023-12-23_032036.json | 90.0 | −6.39 | +0.34 | −3 | Normal, falling |
| TV-069 | TV-069-2023-12-23_032535.json | 87.0 | −3.72 | +0.29 | 39 | Low-normal, slowing fall |
| TV-070 | TV-070-2023-12-23_033036.json | 78.0 | −6.78 | +0.25 | −10 | Low, falling |
| TV-072 | TV-072-2024-01-05_110247.json | 129.0 | −11.83 | +0.43 | 31 | In-range, falling, IOB active |
| TV-073 | TV-073-2024-01-05_110747.json | 105.0 | −19.39 | +0.37 | −43 | Normal, crash risk |
| TV-074 | TV-074-2024-01-05_111248.json | 95.0 | −14.22 | +0.32 | −13 | Normal, fast fall |
| TV-075 | TV-075-2024-01-05_111747.json | 90.0 | −8.50 | +0.27 | 0 | Normal, falling to zero |
| TV-076 | TV-076-2024-01-05_112247.json | 86.0 | −4.94 | +0.21 | −2 | Low-normal, falling |
| TV-077 | TV-077-2024-01-05_112745.json | 78.0 | −6.56 | +0.16 | 7 | Low, falling |
| TV-078 | TV-078-2024-01-05_113245.json | 82.0 | −0.22 | +0.12 | 78 | Low-normal, flat |
| TV-079 | TV-079-2024-01-05_113747.json | 71.0 | −6.50 | +0.07 | 37 | Low, falling |
| TV-080 | TV-080-2024-01-05_114246.json | 71.0 | −2.61 | +0.03 | 68 | Low, slow fall |
| TV-081 | TV-081-2024-01-05_114747.json | 77.0 | +2.44 | −0.02 | 103 | Low, recovering |
| TV-082 | TV-082-2024-01-05_115511.json | 93.0 | +7.67 | −0.03 | 148 | Normal, rising |
| TV-083 | TV-083-2024-01-05_115754.json | 93.0 | +7.67 | +0.00 | 162 | Normal, rising (high target 120) |
| TV-084 | TV-084-2024-01-06_174057.json | 82.0 | +10.50 | +0.12 | 140 | Low-normal, rising |
| TV-085 | TV-085-2024-01-06_174548.json | 98.0 | +14.56 | +0.14 | 180 | Normal, rising fast |
| TV-086 | TV-086-openaps-example-2016-07-10.json | 218.0 | −9.00 | +3.00 | — | High, falling, high IOB+bolus (historical) |

---

## Synthetic Vectors (TV-087 – TV-108)

All 22 synthetic vectors are **parametric variants of TV-001**. They modify only
`glucoseStatus.glucose`, `iob.iob`, `iob.basalIob`, and `mealData.mealCOB` while
leaving **all other fields unchanged** from TV-001.

### Boundary Conditions Tested

| ID | Filename | BG | IOB | COB | Scenario |
|----|----------|----|-----|-----|----------|
| TV-087 | TV-087-synthetic.json | 65 | +0.50 | 0 | Hypoglycemia with positive IOB |
| TV-088 | TV-088-synthetic.json | 55 | +0.80 | 0 | Severe hypo with high IOB |
| TV-089 | TV-089-synthetic.json | 250 | −0.50 | 0 | Hyperglycemia with negative IOB |
| TV-090 | TV-090-synthetic.json | 300 | 0.00 | 0 | Severe hyper baseline |
| TV-091 | TV-091-synthetic.json | 120 | +2.00 | 0 | In-range with high IOB |
| TV-092 | TV-092-synthetic.json | 100 | 0.00 | 30 | In-range with COB |
| TV-093 | TV-093-synthetic.json | 180 | +0.50 | 50 | High with IOB and COB |
| TV-094 | TV-094-synthetic.json | 70 | 0.00 | 20 | Low-normal with COB |
| TV-095 | TV-095-synthetic.json | 140 | −1.00 | 0 | Slightly high, negative IOB |
| TV-096 | TV-096-synthetic.json | 80 | +1.50 | 0 | Low-normal, high IOB |
| TV-097 | TV-097-synthetic.json | 200 | +0.20 | 10 | Hyper with some IOB and COB |
| TV-098 | TV-098-synthetic.json | 110 | 0.00 | 0 | Stable in-range |
| TV-099 | TV-099-synthetic.json | 95 | +0.30 | 15 | Low-normal with IOB + COB |
| TV-100 | TV-100-synthetic.json | 170 | −0.30 | 0 | High-normal, neg IOB |
| TV-101 | TV-101-synthetic.json | 130 | +0.70 | 25 | Mid-range, IOB + COB |
| TV-102 | TV-102-synthetic.json | 85 | +0.10 | 5 | Low-normal, light IOB + COB |
| TV-103 | TV-103-synthetic.json | 220 | +1.00 | 0 | Hyper, high IOB |
| TV-104 | TV-104-synthetic.json | 75 | 0.00 | 40 | Low-normal, high COB |
| TV-105 | TV-105-synthetic.json | 160 | +0.50 | 20 | High-normal, moderate IOB + COB |
| TV-106 | TV-106-synthetic.json | 90 | +0.40 | 0 | At target, moderate IOB |
| TV-107 | TV-107-synthetic.json | 105 | 0.00 | 10 | At target, light COB |
| TV-108 | TV-108-synthetic.json | 115 | −0.20 | 0 | In-range, negative IOB |

---

## Consistency Issues in Synthetic Vectors

### Issue 1: Stale `originalOutput` (all 22 vectors)

Every synthetic vector carries TV-001's original `originalOutput` unchanged:
`originalOutput.bg = 90.8`, `originalOutput.eventualBG = 154`. This does **not**
correspond to the modified inputs. All vectors except TV-106 are flagged
`originalPredBGsStale: true`.

**Verdict**: The stale flag is correctly set. The `originalOutput` and `predBGs`
trajectories cannot be used as ground truth for these vectors.

### Issue 2: `activity` not updated when IOB changed (all 22 vectors)

All synthetic vectors inherit `iob.activity = −0.0041` from TV-001, regardless of
the modified IOB value. In oref0, `activity` represents the current insulin
absorption rate and should be proportional to IOB. Specific mismatches:

| Vector | IOB | Activity | Problem |
|--------|-----|----------|---------|
| TV-087 | +0.50 | −0.0041 | Positive IOB, negative activity |
| TV-088 | +0.80 | −0.0041 | Positive IOB, negative activity |
| TV-091 | +2.00 | −0.0041 | High positive IOB, negative activity |
| TV-096 | +1.50 | −0.0041 | High positive IOB, negative activity |
| TV-090 | 0.00 | −0.0041 | Zero IOB, nonzero activity |
| TV-092 | 0.00 | −0.0041 | Zero IOB, nonzero activity |
| TV-098 | 0.00 | −0.0041 | Zero IOB, nonzero activity |

**Verdict**: This is a **bug in the vector generator**. The activity field should
have been recomputed or zeroed when IOB was modified. This means the BGI
(blood glucose impact) computed by oref0 will be inconsistent with the stated IOB,
potentially causing the algorithm to make different rate decisions than intended.

### Issue 3: `iobWithZeroTemp` not updated (all 22 vectors)

The nested `iob.iobWithZeroTemp` object retains TV-001's values (iob: −0.53,
basaliob: −0.53, activity: −0.0041) even when the parent IOB fields were changed.
oref0 uses `iobWithZeroTemp` in several safety checks. Having it diverge from the
main IOB by >2 U (e.g., TV-091: iob=2.0 vs iobWithZeroTemp.iob=−0.53) may
trigger unexpected safety behavior.

**Verdict**: **Bug**. The `iobWithZeroTemp` should track the modified IOB values.

### Issue 4: `expected` values are formula-derived, not algorithm-verified

The `expected.rate` values in synthetic vectors appear to be rough estimates
(e.g., TV-093: rate=1.955, TV-095: rate=1.615, TV-097: rate=1.7425) rather than
actual oref0 outputs. Meanwhile `expected.iob` is always −0.53 (TV-001's value)
and `expected.eventualBG` is always 154 (TV-001's value) — both stale.

**Verdict**: The `expected` fields are **unreliable** for synthetic vectors. Only
`expected.rate` appears to have been modified; `expected.iob` and
`expected.eventualBG` were not updated.

### Issue 5: Delta/avgDelta don't reflect BG change (design choice)

All synthetic vectors use TV-001's delta (+6.95), shortAvgDelta (+4.73), and
longAvgDelta (−4.91). Combined with extreme BG values this produces unusual
but not impossible scenarios (e.g., BG=55 rising at +7 mg/dL/5min implies
previous reading ~48). This is arguably intentional — testing algorithm response
to a specific BG level with a fixed trend — but means these are not internally
coherent replay scenarios.

**Verdict**: Intentional design trade-off, but limits the vectors' utility for
testing prediction curves (since the glucose history is absent).

### Issue 6: TV-106 missing `parametricVariantOf`

TV-106 lacks the `parametricVariantOf` metadata field and does not have
`originalPredBGsStale: true`, despite being structurally identical to the
other synthetic vectors.

**Verdict**: Metadata oversight. TV-106 should be tagged like the others.

---

## Cross-Validation Recommendations

### Tier 1: Ground-Truth Reliable (78 vectors)

**TV-001 through TV-085**: Use for oracle-based cross-validation. The
`originalOutput` was captured from the same algorithm run that produced the inputs.
Safe to compare adapter outputs against `expected` and `originalOutput.predBGs`.

### Tier 2: Ground-Truth Reliable with Caveats (1 vector)

**TV-086**: Real data but **no `originalOutput`**. Can be used for smoke-testing
adapters (does it run without crashing on high-IOB + bolus input?) but cannot
verify correctness against an oracle.

### Tier 3: Boundary Smoke Tests Only (22 vectors)

**TV-087 through TV-108**: Use **only** for verifying that adapters:
- Don't crash on extreme inputs (BG 55–300, IOB −1 to +2)
- Produce directionally correct results (rate=0 for hypos, high rate for hypers)
- Respect safety limits (maxBasal, low glucose suspend)

**Do NOT use for**:
- Numerical accuracy comparison (stale `expected` and `originalOutput`)
- Prediction curve validation (no valid `predBGs`)
- IOB/activity consistency checks (mismatched activity field)

### Suggested Tags for Filtering

| Tag | Vectors | Purpose |
|-----|---------|---------|
| `natural` | TV-001 – TV-085 | Ground-truth cross-validation |
| `historical` | TV-086 | Smoke test (no oracle) |
| `synthetic` | TV-087 – TV-108 | Boundary-condition smoke tests |
| `hypo` | TV-087, TV-088, TV-094, TV-096, TV-104 | Low BG behavior |
| `hyper` | TV-089, TV-090, TV-097, TV-103 | High BG behavior |
| `high-iob` | TV-091, TV-096, TV-103 | IOB > 1.0 U |
| `with-cob` | TV-092–094, TV-097, TV-099, TV-101, TV-102, TV-104, TV-105, TV-107 | Active carbs on board |

---

## Tool Filtering Status

### Current state

The `lib/vector-loader.js` already supports `{ category, ids, limit }` filtering.
However, **neither `prediction-alignment.js` nor `convergence-loop.js` exposes
these options** in their CLI argument parsers.

### What's needed

1. Add `--category <name>` flag to both `prediction-alignment.js` and
   `convergence-loop.js`, passing it through to `loadVectors()`.
2. Add `--exclude-category <name>` for negative filtering (e.g.,
   `--exclude-category synthetic`).
3. Add `--ids TV-001,TV-002,...` for explicit vector selection.
4. Update Makefile `xval-*` targets to default to
   `--exclude-category synthetic` for accuracy runs, and
   `--category synthetic` for smoke-test runs.

### Workaround (current)

Use `--limit N` where N ≤ 78 (vectors are sorted by ID, so natural vectors load
first). This is fragile and will break if vector ordering changes.

---

## File Inventory

```
conformance/t1pal/vectors/oref0-endtoend/
├── MANIFEST.md                              ← this file
├── TV-001-2023-10-28_133013.json            natural
├── TV-002-2023-10-28_133514.json            natural
├── TV-004-2023-10-28_134513.json            natural
├── TV-005-2023-10-28_135013.json            natural
├── TV-006-2023-10-28_135514.json            natural
├── TV-007-2023-10-28_140013.json            natural
├── TV-008-2023-10-28_140514.json            natural
├── TV-009-2023-10-28_141014.json            natural
├── TV-010-2023-10-28_141513.json            natural
├── TV-011-2023-10-28_142013.json            natural
├── TV-012-2023-10-28_142513.json            natural
├── TV-013-2023-10-28_143013.json            natural
├── TV-014-2023-10-28_143514.json            natural
├── TV-015-2023-10-28_144013.json            natural
├── TV-016-2023-10-28_145014.json            natural
├── TV-017-2023-10-29_191512.json            natural
├── TV-018-2023-10-29_192012.json            natural
├── TV-019-2023-10-29_192512.json            natural
├── TV-020-2023-10-31_042017.json            natural
├── TV-021-2023-10-31_042517.json            natural
├── TV-022-2023-10-31_043017.json            natural
├── TV-023-2023-10-31_043517.json            natural
├── TV-024-2023-10-31_044017.json            natural
├── TV-025-2023-10-31_044516.json            natural
├── TV-026-2023-10-31_045017.json            natural
├── TV-027-2023-10-31_045517.json            natural
├── TV-028-2023-10-31_050018.json            natural
├── TV-029-2023-10-31_050517.json            natural
├── TV-030-2023-10-31_051017.json            natural
├── TV-031-2023-10-31_051517.json            natural
├── TV-032-2023-10-31_052017.json            natural
├── TV-036-2023-10-31_054018.json            natural
├── TV-038-2023-10-31_055017.json            natural
├── TV-039-2023-10-31_055518.json            natural
├── TV-040-2023-10-31_060018.json            natural
├── TV-041-2023-10-31_060518.json            natural
├── TV-042-2023-10-31_061018.json            natural
├── TV-043-2023-10-31_061519.json            natural
├── TV-044-2023-10-31_062018.json            natural
├── TV-045-2023-10-31_062518.json            natural
├── TV-046-2023-10-31_063018.json            natural
├── TV-047-2023-10-31_063519.json            natural
├── TV-048-2023-10-31_064018.json            natural
├── TV-049-2023-10-31_064519.json            natural
├── TV-050-2023-10-31_065018.json            natural
├── TV-051-2023-10-31_065518.json            natural
├── TV-052-2023-10-31_070019.json            natural
├── TV-053-2023-10-31_070518.json            natural
├── TV-054-2023-10-31_071018.json            natural
├── TV-055-2023-10-31_071519.json            natural
├── TV-056-2023-10-31_072019.json            natural
├── TV-058-2023-10-31_073019.json            natural
├── TV-059-2023-10-31_073519.json            natural
├── TV-060-2023-10-31_074019.json            natural
├── TV-062-2023-10-31_075019.json            natural
├── TV-063-2023-10-31_075519.json            natural
├── TV-064-2023-12-23_030034.json            natural
├── TV-065-2023-12-23_030536.json            natural
├── TV-066-2023-12-23_031036.json            natural
├── TV-067-2023-12-23_031536.json            natural
├── TV-068-2023-12-23_032036.json            natural
├── TV-069-2023-12-23_032535.json            natural
├── TV-070-2023-12-23_033036.json            natural
├── TV-072-2024-01-05_110247.json            natural
├── TV-073-2024-01-05_110747.json            natural
├── TV-074-2024-01-05_111248.json            natural
├── TV-075-2024-01-05_111747.json            natural
├── TV-076-2024-01-05_112247.json            natural
├── TV-077-2024-01-05_112745.json            natural
├── TV-078-2024-01-05_113245.json            natural
├── TV-079-2024-01-05_113747.json            natural
├── TV-080-2024-01-05_114246.json            natural
├── TV-081-2024-01-05_114747.json            natural
├── TV-082-2024-01-05_115511.json            natural
├── TV-083-2024-01-05_115754.json            natural
├── TV-084-2024-01-06_174057.json            natural
├── TV-085-2024-01-06_174548.json            natural
├── TV-086-openaps-example-2016-07-10.json   natural (no oracle)
├── TV-087-synthetic.json                    synthetic
├── TV-088-synthetic.json                    synthetic
├── TV-089-synthetic.json                    synthetic
├── TV-090-synthetic.json                    synthetic
├── TV-091-synthetic.json                    synthetic
├── TV-092-synthetic.json                    synthetic
├── TV-093-synthetic.json                    synthetic
├── TV-094-synthetic.json                    synthetic
├── TV-095-synthetic.json                    synthetic
├── TV-096-synthetic.json                    synthetic
├── TV-097-synthetic.json                    synthetic
├── TV-098-synthetic.json                    synthetic
├── TV-099-synthetic.json                    synthetic
├── TV-100-synthetic.json                    synthetic
├── TV-101-synthetic.json                    synthetic
├── TV-102-synthetic.json                    synthetic
├── TV-103-synthetic.json                    synthetic
├── TV-104-synthetic.json                    synthetic
├── TV-105-synthetic.json                    synthetic
├── TV-106-synthetic.json                    synthetic
├── TV-107-synthetic.json                    synthetic
└── TV-108-synthetic.json                    synthetic
```
