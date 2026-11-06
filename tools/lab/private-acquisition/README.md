# Private acquisition extraction controls

Contributor-facing. Read-only archived checks for the bounded private-context,
cache and loader extraction. The production callers retain bounds, frame mode,
statistics/error handling, typed union and side-effect policies. No common
revision, stronger snapshot consistency or evaluator admission is asserted.

Use matching private dependencies and an explicit CRM object database:

```bash
export NS_REST_GATE_REPO=/path/to/owned/crm
export NS_REST_GATE_DEPENDENCIES=/path/to/owned/crm/node_modules
node tools/queue/gates/multitenant-next-slices.js --suite frame-acquisition --ref COMMIT
node tools/queue/gates/multitenant-next-slices.js --suite frame-acquisition --ref COMMIT --control cache
node tools/queue/gates/multitenant-next-slices.js --suite frame-acquisition --ref COMMIT
node tools/queue/gates/multitenant-next-slices.js --suite frame-concurrency --ref COMMIT
```

The positive acquisition fixture exercises real Mongo/PG bounded reads, selected
clinical output, future/statistics/typed-union policies, caller-cache ownership
and tenant scope. The concurrency fixture retains the measured atomic-writer
mixed-read schedule, complete read-error responses and owned-port egress guard.

The cache control selects its exact mutation by archived source presence:

- Without `lib/data/private-acquisition.js`, replace the historical views cache
  allocation with the supplied resident cache, causing actual acquisition writes
  to leak into it.
- With the extracted helper, insert the actual acquired SGVs into the supplied
  resident cache at successful completion. This intentionally breaks the same
  observable ownership property without adding a production cache-injection API.

Both must fail the exact untouched caller-cache assertion in the actual PG
acquisition case, then pass after scratch cleanup. Missing or ambiguous source
anchors fail `CONTROL-INVALID`; that is an instrument setup error, not a semantic
red control. The gate never modifies accepted worktrees or their git index.

Other controls remain in the existing instrument: tenant binding, input bound,
clinical setter, partial-read refusal and read-egress. Each requires a semantic
assertion failure and restored positives. Independent evaluator adaptation needs
its own matching lockfile, archived profile replay, full/browser suites and final
prcheck. Historical results and new extraction acceptance are recorded separately
by the programme coordinator; no measurement is claimed by this README.
