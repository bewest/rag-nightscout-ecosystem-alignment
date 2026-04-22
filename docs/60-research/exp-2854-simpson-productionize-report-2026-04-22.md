# EXP-2854 — Simpson Flag is Independent of Phenotype; Productionize Direct Flag (2026-04-22)

**Stream**: B (operational)
**Predecessors**: EXP-2853 (Simpson decomposition), EXP-2850 (cluster characterization)
**Productionized**: ✅

## Headline

The EXP-2853 Simpson-paradox flag is **independent of phenotype,
controller, and SMB capability**. The phenotype-based
`window_dependence_warning` we shipped after EXP-2850 catches only
**2/9** of the actually-Simpson patients — the proxy is too coarse.

We now route the direct flag through the audition matrix, with the
phenotype proxy as fallback when the direct measurement is missing.

## Cross-tab

| Factor      | Group       | n  | Simpson+ | Frac |
|-------------|-------------|----|---------:|-----:|
| Controller  | Loop        | 6  | 2 | 33% |
|             | OpenAPS     | 5  | 1 | 20% |
|             | Trio        | 6  | 2 | 33% |
| Phenotype   | down_shift  | 6  | 1 | 17% |
|             | flat        | 5  | 2 | 40% |
|             | **up_shift** | 6 | 2 | **33%** |
| SMB capable | False       | 17 | 5 | 29% |
|             | True        | 12 | 4 | 33% |

**No factor exceeds 23pp spread.** Simpson is uncorrelated with the
audition-matrix's existing factors → it carries independent
information.

## Implication: phenotype proxy was wrong

EXP-2850's logic ("up_shift patients are window-sensitive") was based
on a 4-window subset (n=4 up_shift). It was a directional hint, not
a reliable predictor:
- 2/6 up_shift patients ARE Simpson — but
- 7/9 Simpson patients are NOT up_shift (4 unknown phenotype, 2 flat,
  1 down_shift)

The phenotype proxy missed **78% (7/9) of Simpson cases**.

## Production change

`AuditionInputs` gains optional `simpson_paradox: Optional[bool]`.

Decision logic in `classify_triage_flags`:
- If `simpson_paradox is True`: emit `window_dependence_warning` at
  **medium** severity with EXP-2853 rationale.
- If `simpson_paradox is None` AND `phenotype == up_shift`: fall
  back to phenotype proxy at **low** severity.
- If `simpson_paradox is False`: suppress (even if `up_shift`).

Two new tests (override + explicit-false suppression) — 14/14
audition tests pass.

## Visualization

Reuses EXP-2853 chart (Simpson scatter); no new chart needed for this
ID since it's a productionization step, not a new measurement.

## Findings invariants (carry forward)

- **EXP-2853 Simpson flag is independent of phenotype/controller/SMB.**
  Treat it as a fifth, orthogonal audition input.
- The phenotype-up_shift proxy catches only 22% (2/9) of Simpson
  patients — keep as fallback only.
- Direct flag is **medium severity**; phenotype fallback is **low**.
- Suppression on Simpson=False is required so good phenotype-up_shift
  patients (no actual sign mismatch) don't get spuriously flagged.

## Deliverables

| File | Change |
|------|--------|
| `tools/cgmencode/production/audition_matrix.py` | New `simpson_paradox` field + decision logic |
| `tools/cgmencode/production/test_audition_matrix.py` | 2 new tests |
| (analysis script not separately committed — single inline pandas call) |

## Next experiments

- **EXP-2855**: per-patient time-of-day Simpson decomposition (does
  the reactive vs structural balance shift across dawn/midday/evening?
  could refine TOD windows per Simpson direction).
- **EXP-2856**: stability test — recompute Simpson flag over
  rolling 30-day windows; how stable is the per-patient classification?
  This determines audition refresh cadence.
