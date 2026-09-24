# nsprobe

Aggregate-only probes that a Nightscout data holder runs on their own data, to confirm or
correct the schema claims this repository measured on its own 11-site corpus. The data stays
with the holder. What comes back is counts, shares and site-counts in a fixed format that
`nsprobe compare` sets beside this repository's numbers.

- [`AGENTS.md`](AGENTS.md): instructions for a coding agent on the holder's machine,
  including the rules on what may leave it.
- [`questions.yaml`](questions.yaml): the 18 questions (Q00 to Q17), the claim each tests,
  what our corpus shows, and what an answer would change.
- `reports/nsprobe/baseline/`: the same probes run over this repository's corpus.
- Brief for data holders:
  [`docs/60-research/collaboration/external-data-validation-brief.md`](../../docs/60-research/collaboration/external-data-validation-brief.md).

## Commands

From the repository root:

```bash
PYTHONPATH=tools python3 -m nsprobe layout    --src RAW --dest CORPUS --key PRIVATE/key.json
PYTHONPATH=tools python3 -m nsprobe run       --root CORPUS --out OUT --contributor LABEL
PYTHONPATH=tools python3 -m nsprobe census    --root CORPUS --out OUT
PYTHONPATH=tools python3 -m nsprobe warehouse --config warehouse.yaml --out OUT
PYTHONPATH=tools python3 -m nsprobe check     OUT
PYTHONPATH=tools python3 -m nsprobe compare   OUT
```

Make targets: `nsprobe-test` (synthetic data), `nsprobe-baseline` (regenerates
`reports/nsprobe/baseline/` from `externals/ns-data/patients`).

## Modules

| Module | Does |
|---|---|
| `layout.py` | copies per-site exports into `<dest>/<api>/S###/<collection>.json`; writes the site key elsewhere |
| `sources.py` | reads that tree: v1 arrays, v3 `{status,result}` envelopes, NDJSON |
| `family.py` | classifies each document's writer (AAPS, Trio, iAPS, oref0 rig, Loop, xDrip, Share...) and names the rule that fired |
| `probes.py` | the raw-document probes, one pass over the corpus |
| `warehouse.py` | the same questions over flattened SQL tables, column names from YAML |
| `privacy.py` | the 3-site threshold for named values, and the output validator |
| `compare.py` | Markdown comparison with `reports/schema-census/` and the baseline |

`nsprobe census` runs the existing `nsschema` pipeline (census, reconcile, quirks,
dosing inputs) over the holder's corpus, through the `NSSCHEMA_CORPUS` override in
`tools/nsschema/corpus.py` and `replay.js`.
