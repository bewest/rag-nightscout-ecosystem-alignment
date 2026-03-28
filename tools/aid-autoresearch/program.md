# AID Autoresearch

> Autonomous algorithm evaluation loop for the Nightscout AID ecosystem.
> Adapted from [karpathy/autoresearch](https://github.com/karpathy/autoresearch).

## Setup

1. Branch: `autoresearch/<date>-<algorithm>`
2. Read: conformance vectors, tolerance thresholds, algorithm source
3. Verify: `python3 tools/aid-autoresearch/validate_oref0.py` passes baseline
4. Initialize results.tsv

## What you CAN modify

- Algorithm parameters (ISF multipliers, safety margins, SMB logic)
- Algorithm decision logic in the runner under test
- Prediction curve calculations
- Runner configuration in `tools/aid-autoresearch/runners/`

## What you CANNOT modify

- Conformance test vectors in `conformance/t1pal/` (they are the ground truth)
- Tolerance thresholds (`conformance/t1pal/tolerances.json`)
- The scoring function (`tools/aid-autoresearch/algorithm_score.py`)
- This file (`program.md`)

## The metric

```bash
python3 tools/aid-autoresearch/algorithm_score.py --runner oref0 --vectors conformance/t1pal
```

The output is a single float 0.0-1.0. Higher is better.
Safety violations → instant 0.0 (hard constraint).

## Safety invariants (MUST NEVER be violated)

- BG < 54 mg/dL → must suspend delivery (rate = 0)
- BG < 70 mg/dL → must not increase delivery above basal
- IOB > max_iob → must not bolus
- No glucose data → must suspend
- These are tested by boundary-vectors.json — ALL 12 must pass

## Experiment loop

LOOP FOREVER:

1. Look at `results.tsv` — identify what's been tried, what the current best score is
2. Hypothesize a change to the algorithm (parameter tweak, logic change, etc.)
3. Implement the change in the algorithm runner or configuration
4. `git commit` the change
5. Run: `python3 tools/aid-autoresearch/algorithm_score.py --runner <runner> --vectors conformance/t1pal`
6. If score improved AND safety=pass: keep commit, log "keep" to results.tsv
7. If score worsened OR safety=fail: `git reset --hard HEAD~1`, log "discard"
8. NEVER STOP — the human will interrupt when ready

## Results tracking

Record every experiment in `results.tsv` (tab-separated):

```
commit	algorithm_score	safety_ok	pass_rate	divergence_u_hr	status	description
a1b2c3d	0.847200	true	0.84	0.12	keep	baseline oref0
b2c3d4e	0.863100	true	0.86	0.09	keep	increase ISF sensitivity
c3d4e5f	0.000000	false	0.92	0.05	discard	removed low glucose check (SAFETY FAIL)
```

## Critical difference from vanilla autoresearch

AID has **hard safety constraints** that ML training does not:

- **Performance regression** → discard and try something else
- **Safety violation** → discard, LOG THE VIOLATION, and add a regression test

The boundary vectors encode the non-negotiable safety invariants. NEVER keep a change
that fails any boundary test, regardless of how much it improves other metrics.
