# EXP-2919 — Loop autobolus on/off latency split

**Date:** 2026-04-23 (overnight)
**Source:** `tools/cgmencode/exp_loop_autobolus_split_2919.py`
**Scope:** Design-level characterisation. NOT therapy advice. Same
binding scope as EXP-2916/2918.

## Question

EXP-2918 found Loop's per-patient response rate ranges from 27 % to
99 %. Hypothesis: this internal heterogeneity is explained by Loop's
optional **automatic-bolus** feature (EXP-2894). If autobolus is
enabled, the controller may substitute SMBs for deep basal cuts.

## Method

Derived autobolus configuration from `bolus_smb` column in the
training grid: total SMB units > 0 ⇒ enabled. Joined with EXP-2918
per-event latency. Compared latency and response rate by config.

## Loop autobolus mapping (n=7)

| Patient | Autobolus | SMB/day | Tier         |
|---------|-----------|--------:|--------------|
| a       | OFF       | 0       | conservative |
| f       | OFF       | 0       | moderate     |
| c       | ON        | 16.1    | aggressive   |
| d       | ON        | 13.1    | conservative |
| e       | ON        | 22.3    | aggressive   |
| g       | ON        | 9.6     | moderate     |
| i       | ON        | 34.1    | aggressive   |

5 enabled / 2 disabled — matches EXP-2894 split.

## Headline (counter-hypothesis CONFIRMED)

| Config       | n events | Median lat | **Mean lat** | Std |
|--------------|---------:|-----------:|-------------:|----:|
| Autobolus OFF| 1 319    | 0 min      | **9.3 min**  | 30  |
| Autobolus ON | 2 669    | 0 min      | **31.0 min** | 49  |

**Loop with autobolus DISABLED gets ~3× faster mean basal-cut
latency.** Direction is consistent with the design intuition: when
the controller has a positive-bolus channel available, it leans on
SMBs first and basal-cut becomes a secondary, slower defence.
When the channel is disabled, basal-cut is the only safety route
and it fires faster.

## Per-patient response rate

| Patient | Config | Response rate |
|---------|--------|--------------:|
| f       | OFF    | 98.9 %        |
| g       | ON     | 85.1 %        |
| i       | ON     | 63.8 %        |
| a       | OFF    | 44.7 %        |
| c       | ON     | 43.1 %        |
| e       | ON     | 35.4 %        |
| d       | ON     | 27.5 %        |

Response-rate heterogeneity exists in BOTH groups and does NOT split
cleanly by config (a-disabled has 45 %, similar to c-enabled 43 %).
The design-level signal is in the **mean latency**, not the
binary response rate.

## Design-level interpretation (for AID authors)

Loop's basal-cut **timing** is configuration-dependent:
- With autobolus ON, basal-cut is the secondary safety net; it
  arrives later because SMBs handle initial response.
- With autobolus OFF, basal-cut is primary; arrives faster.

This corroborates the EXP-2894 finding that "Loop is two designs in
one" depending on user configuration. Cross-design comparisons
involving Loop should split by autobolus config when possible.

## Implication for EXP-2916/2918 framing

The "Loop" lineage in design-comparison work is itself a mixture of
two effective designs. With n=2 OFF and n=5 ON, the mixture is
dominated by ON. Future cell means could split Loop into two
sub-designs for cleaner comparison.

## Caveats

- n=2 (OFF) vs n=5 (ON) — comparison is suggestive, not statistical.
- Other controller heterogeneity sources (correction-bolus
  preferences, override usage, target settings) not controlled.
- bolus_smb derivation from training grid only; some patients may
  have config flux during the window (treated as constant here).

## Linked artefacts

- `externals/experiments/exp-2919_summary.json`
- `externals/experiments/exp-2919_loop_autobolus_split.parquet`
- `docs/60-research/exp-2894-loop-autobolus-2026-04-22.md` (parent)
- `docs/60-research/exp-2918-basal-cut-latency-2026-04-23.md` (parent)

## Next

- EXP-2917 bootstrap design-cell CIs (Loop split by autobolus
  could be a sub-recommendation)
- AAPS data ingestion to widen oref-family base
