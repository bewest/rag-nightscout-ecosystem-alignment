# evaluator-smoke: statements and main-thread CPU per accepted write

*Contributor-facing. The evaluator's "smoke" tier of
[capacity-test-tiers](../../../docs/30-design/tenancy/multitenancy-decisions.md#capacity-test-tiers).
The baseline comparison is a figure, never a gate
([performance-signals-not-gates](../../../docs/30-design/tenancy/multitenancy-decisions.md#performance-signals-not-gates)).*

One command builds (or reuses) the image for a core commit, runs a small Compose multitenant
deployment through the [m7-joined runner](../m7-joined/RUNNER.md)'s smoke tier (16 tenants, K=1
evaluator, 180 s of realistic-v1 load at rate multiplier 24), and reports:

- evaluator SQL statements per accepted write, by database role (`nsdemo_evaluator`,
  `nsdemo_lifetime_evaluator`, `nsdemo_outbox`, `nsdemo_suppression`) and by phase (receipt,
  dispatch, settings, acquisition, completion, consumers, observe, txn-control, fences, registry,
  unattributed), with PostgreSQL executor ms per write;
- evaluator main-thread CPU ms per accepted write (`/proc/<pid>/task/<pid>/stat`, sampled each
  second through `docker exec`, interpolated at the same SQL window bounds);
- the same figures beside the committed [`baseline.json`](baseline.json).

The runner's own smoke verdict (stored counts, clinical witnesses, fixture ownership, viewer
bindings) stays strict and is reported next to the figures.

```bash
# from an alignment checkout whose externals/ holds cgm-remote-monitor-official and nightscout-deploy
# (or set NS_SMOKE_CORE_REPO / NS_SMOKE_DEPLOY_REPO)
python3 tools/mt-bench/evaluator-smoke/smoke.py run --core <commit|branch|clean worktree> \
  --out /mnt/data/nightscout-workspace/artifacts/<lane>/<new-run>
python3 tools/mt-bench/evaluator-smoke/smoke.py run --image <ref with core/deploy revision labels> --out <dir>
python3 tools/mt-bench/evaluator-smoke/smoke.py reduce <dir>/run                 # re-reduce a retained run
python3 tools/mt-bench/evaluator-smoke/smoke.py reduce <dir>/run --empty-rules   # negative control
```

`--out` is private (synthetic credentials) and must be outside any checkout. The image is
`ns-evaluator-smoke:<core12>-<deploy12>`, built like deploy's `tools/compose-overlay.sh` plus
`build.js --image` (core commit with `bindings/compose/multitenant` from the deploy commit, default
`f57a8c3`), and reused when its labels match. The Compose project is
`evaluator-m-smoke-<core10>`; the runner removes it and its volumes and records the cleanup readback.
The run refuses when the one-minute load average exceeds the CPU count.

**Phase rules.** `statement_phase.py` classifies statement text; they are the rules behind retained
evidence `evaluator-profile-20261119` and reproduce its 164.37 and 169.49 statements per write on
that run's retained bookends. Shapes several phases issue (BEGIN/COMMIT, fence locks and
`set_config`) are their own phases. A code change that adds new statement text shows as
`unattributed`; add a rule rather than reading a lower total as a saving.

**Limits.** Top-level statements only (not statements inside functions). Executor time is not
PostgreSQL CPU. Accepted writes are HTTP-accepted writes plus stored probe writes; idle tenants
owe no work, and time-only cycles (counted under `cycles`) add statements without writes. At 16
tenants each tenant writes every few seconds, so cycles rarely merge; the 1,000-tenant figures were
taken at about one write per tenant per 100 s.
Main-thread CPU at about 2.8 writes/s includes fixed per-second work (timers, health, realtime
hints) spread over few writes, so it is a figure for comparing commits at this workload, not a
cost model. The sampler's `docker exec` shell is an extra process in the evaluator container.

**Baseline (core `bee2589b6`, image `6c23df42a702`, three runs, 521 accepted writes each, about
283 s wall time per run):** 171.46–171.89 statements per accepted write, 3.91–4.04 executor ms per
write, 16.7–17.1 main-thread ms per write (two runs). Per role and phase: [`baseline.json`](baseline.json).
