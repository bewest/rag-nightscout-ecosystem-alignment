# Focused control/recovery campaign — 2026-11-06

**Reproduced, initial failure retained:** application `1df25fba593df8899d2a9468a74dc10fc369470b` produced **56 passing / 0 pending / 5 failing** in one four-file campaign. This was a failed prediction, not acceptance. [Machine capsule and raw-artifact hashes](control-recovery-focused-1df25fba-2026-11-06.json).

```bash
TZ=UTC node scripts/test-multitenant.js \
  --only tenant-authorization-postgres --only tenant-credential-http \
  --only entries-importer-postgres --only tenant-durable-replay \
  --record <private-output>/focused.json
```

The native authority PostgreSQL and synthetic-token HTTP families passed 12 and 34 cases respectively. These totals include existing cases, rather than 46 new selected-policy cases. Populated recovery passed 3 and failed 4; durable replay passed 6 and failed 1; the existing import-target case passed.

The restore diagnostic supplied a valid 12,727-byte PGDMP buffer, but the helper configured stdin as `ignore`. Actual `pg_restore` reported `input file is too short (read 0, expected 5)`. The correction pipes only that restore invocation's input. Existing no-owner/no-ACL archive semantics, target re-provisioning, typed fidelity, tenant/privilege and ledger checks are retained. This remains a stopped-write laboratory reference, without a production backup/key-recovery claim.

The replay producer committed and was killed before publication as predicted. The failed oracle compared decoded ObjectId documents against raw PostgreSQL string identity fields. The correction independently reads `id_kind` and document values, decodes the expected rows through the existing identity codec, and checks exact recovered values/types. Flattened identities, swapped kind metadata and changed values must still fail.

Application `8713395992e07b4dd2cde61ee972e9a15c8ada8c` changes only four importer/replay fixture/test paths from the initial head; product modules are identical. One affected importer/replay campaign passed **15 / 0 / 0**, including all seven populated and seven replay cases. The unaffected 46 authority/HTTP cases were not repeated in that focused invocation. Separate pure affected checks passed 18 cases. The oracle ablation was red with one `Missing expected exception` assertion, followed by one restored passing case. The original valid-restore diagnostic failure is retained. The capsule lists immutable raw artifact hashes, all independently verified by the coordinator.

The focused repair slot ended at 21:36:21Z. Its exact owned diagnostic and affected-run containers and observed volume were verified absent; older unknown resources were preserved. Complete application acceptance, archived product-semantic controls and remote publication follow separately. No full M2/M5/M6 completion, selected-client compatibility, listener/provider selection or default enablement follows from this capture.
