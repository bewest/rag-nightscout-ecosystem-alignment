# Bounded M1 entries vectors on7015 — 2026-11-06

Reproduced on exact application `7015fbae42e5c3e2f26acf79488e5a7328ff3b29`.
This capsule closes two bounded native sampling uncertainties; it does not promote
M1 or replace the separate comprehensive campaign. [Summary](summary.json) and
[hash references](artifact-index.json) retain sanitized aggregates only.

| Executed phase | Pass / pending / fail | Physical result |
|---|---:|---|
| Ordinary two new vectors | 2 / 0 / 0 | Tied paging and supplier-to-PG import/rollback/rerun pass. |
| Paging comparator reversal | 0 / 0 / 1 | Exact `M1_PAGING_ORDER` assertion; actual final identity sort direction reverses while stored A/B rows remain unchanged. |
| Defective supplied target | 0 / 0 / 1 | Exact `M1_IMPORT_FIDELITY`; successful importer receipt masks one missing physical row, independently detected. |
| Fresh ordinary restoration | 2 / 0 / 0 | New process and owned fixtures; both ordinary vectors pass. |

Paging establishes twelve tied identities per tenant across four tenant/order
schedules, exact complete identity order against Mongo and independent stored
rows, exhausted final page and unchanged tenant-local values. The control reaches
twenty actual final-comparator argument flips and reverses observed SQL order.
It is an archived test-instance sort-argument ablation, not a production edit.

Import reaches a real later-page INSERT: three rows are visible inside its
transaction, two to an independent reader, and two earlier committed rows remain
after rollback. Rerun/history produces four A rows and preserves B's one row;
complete replay preserves logical JSON/null/array/source/history fidelity. The
row-loss control leaves three A rows while the importer still reports four
baseline and two history documents. This is **defective-target/oracle
sensitivity, not a production importer ablation**. It proves page rollback and
safe one-shot rerun, not whole-import atomicity or external transport.

Independent ownership/birth observation and exact absence inspection verified
seven owned containers, ten volumes and five Node process identities absent.
Pre/post container, volume and network sets are identical; unknown baselines
were preserved. No timeout, signal, pending case or wrong-layer/setup failure
satisfied either control. Runtime was released after cleanup verification.

Source crosswalk `922b938fca880ad6a2b55752f896d7ef7415bc8c` and preparation
`2ab6712ec0a1ea51915d31dd4c9d473c5ec1e90e` remain source-derived. The crosswalk
maps admitted entries/common properties and explicit capability distinctions;
it does not claim the global generic PostgreSQL fixture suite ran. JSONB logical
equality and reviewed unsupported shapes remain explicit; numeric budgets stay
in Batch C. Shared frontend coverage is credited without duplicating every
generic collection vector.

Only these new vectors and controls/restoration ran. No full M1–M4 promotion,
comprehensive/full/browser/corpus/prcheck, all-client, lifecycle or production
claim follows. Full raw rows, resource/process identities, credentials, URIs and
logs remain private; the capsule publishes only aggregates and SHA256 references.
