# c23 complete native operation-window acceptance

**Reproduced:** the complete 21-criterion matrix passed on `c23cf1f35d819738842041babc0aef2dbde96c21`, tree `761d763fbff124cdba7bcb8a87177fed7352ee25`. [Machine summary](summary.json) retains every criterion, measurements, release verdict and private-artifact digests. The single run completed all criteria in order; results were not combined across attempts.

The matrix ran four actual separate CLI roles against synthetic PostgreSQL, MongoDB and Vault fixtures. It covered ordinary logical restore; HTTP response-lifetime draining; rollback suspension; actual unsafe-clock API startup refusal; fresh shared API/realtime/evaluator restarts after rollback, DATA acknowledgement uncertainty and unresolved orphan refusal; B HTTP/realtime/evaluator progress while A remained unavailable; A recovery-state preservation; real COMMIT acknowledgement loss; invalidation acknowledgement loss; killed-backend orphan durability; same-PID/different-birth refusal; and independent final database-backend release. The source preserves the operator's unresolved-orphan boundary; this run does not approve clearance or reopening.

There were 27 role births and 199 driver PostgreSQL clients, maximum three concurrently in the driver. Across processes, 886 clients were recorded; asynchronous samples do not establish a global concurrency peak. The enforced conservative concurrent ceiling was 108. Actor evidence was complete, forbidden egress was zero, and the parent exited with driver zero and no execution or cleanup errors.

The independent lead repeated fresh exact inventory and original selected static-metadata comparisons and found all 28 driver/role births, process-group descendants and private sockets absent. This scope does not assert unchanged complete configuration, full endpoint equality or global quiescence. Three owned containers and five owned volumes were removed.

Command, after a separate exact single-use lead grant:

```bash
python3 externals/work/m6-joined-restart-lockfix-prep-20261107/parent.py externals/work/m6-acceptance-continuation-20261107/native-c23-full21-grant.json
```

Packet index: `e866693a9a583f343c47d1ae073af73a0ff48185752b22c5adaefca031c064f7`. Before execution the lead verified 2,087 packet members and 11,293 external runtime files and reran actual selected-source mutation/read protocols, distinct storage-identity controls, factory-composition omission/red/restoration and negative-process backend-release controls. These controls retain their source/protocol scope; the native matrix above supplies the actual runtime evidence.

The earlier a1 runs remain incomplete with their separate instrument-error and row-lock-refusal attribution. This successful run does not identify their missing original blocker. Cold Compose UI/API/restore, client compatibility, final full/default-browser/enabled corpus and final prcheck remain separate. No M6, production, default, real identity, provider or device admission is claimed.
