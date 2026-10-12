# hub-active-state — what each hub reports as active at t, for the same records

*Contributor-facing.* Queue item `LAB-HUB-ACTIVE-STATE`. Runs one synthetic record set through
cgm-remote-monitor and Nocturne and asks each, at fixed times, which temporary target, override
and profile is active. The cases are the ones in [landscape
§5](../../../docs/30-design/platform/nightscout-intent-workflow-landscape-2026-10-09.md#5-how-the-hubs-decide-what-is-active).
Results: [results/RESULTS.md](results/RESULTS.md). Synthetic data only.

## Files

| File | What it is |
|---|---|
| `records/make-records.js` → `records/cases.json` | the record set: 7 cases, a control for each, and perturbations (one input changed). Records are listed in arrival order |
| `crm-probe.js` | loads the records through cgm-remote-monitor's own `lib/data/ddata.js`, `lib/profilefunctions.js`, `lib/plugins/loop.js` and `lib/plugins/override.js`; the header lists the steps it reproduces from the server (upsert by `_id`, the dataloader sort, the sandbox profile set-up) and the one answer that is not executed tree code (overrides from treatments, which only the client renderer draws) |
| `nocturne-harness/` | a .NET console project. `run.sh` copies it into a Nocturne tree at `tests/Lab/HubActiveState/` and builds it there. It sends each record through `TreatmentDecomposer` / `DeviceStatusDecomposer` / `ProfileDecomposer` into a real `StateSpanService` + `StateSpanRepository` + `DeduplicationService` on SQLite (Nocturne's `TestDbContextFactory.CreateSqliteWithTenant`, as `StateSpanRepositoryTests` uses), then asks `GetActiveAtAsync`, `GetStateSpansAsync`, `ActiveProfileResolver` and `BasalRateResolver`. Repositories off the state-span path are mocked |
| `compare.js` | the table (`results/compare.md`); `--selftest` checks the comparator reports agreement for identical inputs and exactly one disagreement for one changed answer |
| `summary.js` | one line per case, query and ask from either hub's result file |
| `fetch-trees.sh` | downloads both hubs at the commits in RESULTS.md as GitHub archives |
| `run.sh` | runs everything |

## Run

Needs Node.js, the .NET 10 SDK and network access for NuGet. No database server: Nocturne runs on
in-memory SQLite.

```sh
tools/lab/hub-active-state/fetch-trees.sh /tmp/hub-trees
# reuse a node_modules from a cgm-remote-monitor checkout of the same package-lock.json with
#   CRM_NODE_MODULES=<path>/node_modules tools/lab/hub-active-state/fetch-trees.sh /tmp/hub-trees
tools/lab/hub-active-state/run.sh /tmp/hub-trees/crm-fade2299 /tmp/hub-trees/nocturne-42275c812
```

`run.sh` refuses to run if `records/cases.json` differs from what `make-records.js` writes. It
writes `results/crm.json`, `results/nocturne.json`, `results/nocturne-mockdedup.json` (the same run
with `IDeduplicationService` mocked) and `results/compare.md`; build and stderr logs go to a
temporary directory (`LOGS=` overrides), because they carry local paths. The Nocturne result files
contain time-based UUIDs and change on every run; `compare.md` does not.

To change a case, edit `make-records.js`, regenerate `cases.json` (`node make-records.js >
cases.json`) and rerun.
