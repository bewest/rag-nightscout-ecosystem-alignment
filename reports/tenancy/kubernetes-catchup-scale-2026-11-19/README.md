# Kubernetes fixed-target collector scaling

**Fixed on a local branch; Kubernetes runtime qualification remains UNMEASURED.**
This is a reproduced local observer experiment on frozen helper base
`2b05da9dd0dac2c80d49518d4ceb9e931521fca8`, with the collector/query changes in
this record's commit. The application and native input codec are unchanged.
The retained evidence identifier is
`kubernetes-capacity-20261118/catchup-scale/sql01`; raw rows and the receipt stay
outside Git. Source acceptance stays PENDING and capacity NOT_GRANTED.
The retained receipt SHA256 is
`7d8ea761142616aa04f55b7f98418fb37ea70d0986265c3728b348d0662c56c1`.

The collector previously issued one PostgreSQL exec per 64 tenants. It now
issues one all-roster progress SELECT inside the existing read-only transaction,
with the same owned-namespace and source/incarnation checks before and after.
The progress-only transport removes repeated constant reader metadata and JSON
field names. Its decoder restores every independently checked typed/state field
before calling the unchanged strict `completed-oracle.progressSnapshot`.
Clinical SELECTs, native source validation and the fixed-target `assess` function
are unchanged. Runtime inspection still covers every tenant in 128-tenant pages.

The whole round is now inside the selected round deadline, including inspection
and final census. Child SQL/exec timeouts receive the remaining time, SQL gets a
finite statement timeout, and the inspection helper's paging clock uses that
remaining round rather than its ordinary 15-second default. `drainObservation`
is a supported typed workload field. Its new `sqlMaxBytes` setting defaults to
16 MiB per round and can be selected explicitly alongside the existing total
`maxBytes`, query, round and interval budgets. Actual SQL and inspection cost
still counts against the total. Drain/work cutoffs and the clinical 120-second
deadline remain independent and unchanged.

## Reproduced differential measurement

One disposable networkless PostgreSQL fixture, version
`16.15 (Debian 16.15-1.pgdg13+2)`, image
`sha256:74d436cb49d3398cf7b5d7b33635d43623d9e4da4b93c22db453f7d5d81181b1`,
held 10,000 synthetic tenants. Declared fixture limits were 1 CPU, 1 GiB memory,
a 512 MiB temporary data filesystem and a 300-second container deadline, with
no host port or persistent volume. Exact-ID removal and a separate label
inventory measured cleanup ABSENT. Each representation ran twice on the same
fixture. The legacy reference read all rows even beyond the old cap to permit
an exact differential comparison; that does not relabel the old collector PASS.

| Tenants | Representation | SQL calls | SQL response bytes | Observer wall seconds, repeats | Python observer CPU seconds, repeats |
|---:|---|---:|---:|---|---|
| 1,000 | Legacy | 16 | 2,032,000 | 1.406608 / 1.434174 | 0.048122 / 0.052869 |
| 1,000 | Compact | 1 | 1,220,000 | 0.775054 / 0.781051 | 0.032212 / 0.028110 |
| 10,000 | Legacy | 157 | 20,320,000 | 13.434771 / 13.198851 | 0.542086 / 0.524610 |
| 10,000 | Compact | 1 | 12,200,000 | 4.500080 / 4.569133 | 0.348025 / 0.376107 |

Both repeats and representations produced identical strict snapshots:

| Tenants | Snapshot bytes | Canonical snapshot SHA256 |
|---:|---:|---|
| 1,000 | 585,457 | `428be2448e24733c66d569596e48c71d0bd92872b566e40b50adec64c7810926` |
| 10,000 | 5,850,457 | `fa379270cc9331aa862de52e68726ce1bff0063ead015331f69fa44d8786c81d` |

The unchanged fixed-target assessor classified all 1,000 / 10,000 rows COMPLETED.
All-writer WAL intake and slot ACK coverage remain UNMEASURED. The legacy 10k
response exceeded 16 MiB; the compact response stayed below the default budget
in this synthetic shape. A different source shape may select a larger budget.

Timing includes local SQL transport, decoding and strict Node snapshot creation.
It excludes Kubernetes transport, namespace census and runtime inspection.
Python CPU excludes PostgreSQL, Docker and Node children. The workstation was
shared; no quiet-host reservation or executor CPU measurement was made. These
figures support observer implementation, not workload capacity or a clinical
deadline distribution.

## Controls and remaining integration

At both populations, actual transactional mutations separately removed a tenant,
changed native source identity, changed native generation, changed restore
generation, corrupted the typed contract digest and removed native stream state.
Both readers refused with the same code; rollback restored the exact original
snapshot. A write inside `BEGIN READ ONLY` refused. The retained receipt contains
15 control results, including the two all-tenant assessor results.

Focused tests also refuse missing capture, stuck tenants, foreign ownership,
runtime reset, missing jobs, invalid observer selections, oversized SQL and round
overrun during inspection. A selected 32 MiB SQL budget admits the synthetic
17 MiB response that the default budget refuses. Actual branch ablations make
the configured-round, whole-round, storage-basis and raw-first criteria red, then
restore green. The real inspection helper's default paging deadline refuses a
long synthetic multi-page read; its selected remaining deadline passes, and an
ablation that restores the fixed default makes that criterion red. Disposable
cache generation retains the existing permissive semantics; it is distinct from
runtime identity and native source generation. Existing native/due/restore
assessor controls remain in the focused suite. The final focused run passed
100 Python tests across the collector, adapter, common projection, workload,
shared catch-up, shared storage collector and phase-window suites, plus both
native/progress Node control files. Logs are retained alongside `sql01`.

Reproduction command, with an explicit new output directory:

```sh
python3 tools/mt-bench/kubernetes/catchup_scale_control.py \
  --output <new-absolute-output-directory> --node <pinned-node> \
  --postgres-image sha256:74d436cb49d3398cf7b5d7b33635d43623d9e4da4b93c22db453f7d5d81181b1
```

The owner of future entered Kubernetes points must integrate the helper after
the current point closes, select a round budget that includes measured census
and inspection cost, and run a small actual native control before a fresh larger
point. No entered helper was changed. This lane ran no Kubernetes action, source
application change, provider action, publication or Git push. Populations beyond
the existing strict progress selector's 10,000-tenant limit were not tested.

`make queue-check` passed schema/coverage/generated views and failed on three
pre-existing references: the absent `dc795bd1-acceptance/test-all-and-browser.txt`
named by both queue files, and `projection.json` named by the old PostgreSQL
report. Those source files are unchanged from the frozen head, and both targets
are absent at that head. The unrelated evidence links remain unchanged.
