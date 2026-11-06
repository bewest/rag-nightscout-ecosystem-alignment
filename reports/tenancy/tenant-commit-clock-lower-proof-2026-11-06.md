# Tenant commit clock: bounded lower-port proof — 2026-11-06

This immutable contributor record audits existing **reproduced** synthetic PostgreSQL captures. The report lane read the actual logs and anchored source; it started no services and did not rerun the measurements. The opt-in transaction clock has bounded lower-port and all-domain readiness evidence. Corrected full CLI/HTTP behavior and broader acceptance remain **UNMEASURED** in this record.

The [sanitized capture index](tenant-commit-clock-lower-proof-2026-11-06.json) records original-log SHA-256 digests, suite totals and cleanup outcomes, without credentials, connection URLs, private resource identities or raw logs. Local artifact locations are retained in `externals/work/HANDOFF-tenant-commit-clock-20261106.md`. Those private captures remain unchanged.

## Anchors and environment

| Scope | Exact CRM commit |
|---|---|
| Original product prototype | `3e76b2701538873e77c4bd461fbff3842fa9b443` |
| Initial lower-port fixture | `839260c81adb5f945e73ae9da7527fd36c575157` |
| Corrected lower-port fixture, same original product | `887c4aad76dc14b85eba5d909e6a7b71396cfdfe` |
| Portable all-domain readiness source correction | `c52887d7eea054b0570c8ba8ce1dbce373856f19` |
| Added actual all-domain regression test/fixture | `a8d9af9c9f1b4b227d8fc8feb3e23c2fa5139bbf` |
| Earlier failed HTTP startup candidate | `2619a439470b09db32c1a9ac815e9766a77fb2b4` |

Report preparation started from alignment `e739c46673bb7d908180dcabfa12ef5c8462a195`. Runtime captures identify PostgreSQL **16.15 (Debian 16.15-1.pgdg13+2)**, x86_64, GCC14.2.0/64-bit. The lane handoff records Node **v22.23.4**, also observed during this source-only audit. Each database campaign used one explicitly owned disposable test database, cached image with pulls disabled, private environment-only credentials and synthetic rows. The fixture uses real shipping storage/intent modules, two independent serving pools with max4 each, and serving statement_timeout10000ms. Initial admin observations were client_connection_check_interval0 and statement_timeout0; they establish no disconnect or crash-recovery bound.

## Original lower-port cohort

The actual PostgreSQL command at the corrected fixture head was:

```bash
# Supply NS_TEST_POSTGRES_ADMIN_URI privately for an owned disposable test DB.
NS_TENANT_COMMIT_CLOCK_TEST=1 node_modules/.bin/mocha --timeout 30000 tests/tenant-commit-clock-port.integration.test.js
```

**Reproduced:** `lower-port-rerun.log` has **8 passing**, and `lower-port-restored.log` has **8 passing** after controls/restoration. This is the same bounded cohort twice, with the original product source unchanged.

| Actual case | Bounded observation |
|---|---|
| Authored detached-counter alternative | A real counter committed before its data transaction allocates distinct stamps, yet the lower delayed commit becomes invisible behind the already observed higher exclusive cursor. This is an authored alternative-design control, not a selectable production backend. |
| Transaction clock fence | A real PostgreSQL lock wait is observed while the lower write is held; neither write nor its event is visible early. After release, the lower then higher rows and their stored stamps are ordered. |
| Actual rollback | An INSERT is visible inside the transaction before a forced error. Outside it, data and durable floor remain unchanged and no queued logical event escapes; a later write succeeds. |
| Cross-tenant progress | Tenant B completes on the **same max4 pool** while tenant A has one holder and one waiter. This measures a two-occupied-connection schedule, not saturated-pool fairness or latency. |
| Earlier legacy plan | After an intervening committed v3 cursor, two genuinely distinct preplanned legacy targets receive later authoritative stamps; identities, filters, domain dates and nested values remain intact. |
| Provisioning refusal | A positive readiness setup precedes missing, stale and unsafe-privilege refusals; readiness does not repair the floor. |
| Raw transaction ownership | A clock wrapper refuses to acquire a new commit boundary inside an unrelated raw transaction. |
| Existing bulk tie characterization | Two identifier-absent typed twins marked by one mutation share a stamp; an actual sorted LIMIT1 read followed by an exclusive cursor omits the tied second row. This is this cohort/schedule, not a universal statement about every history interface or paging policy. |

The first actual fixture attempt is preserved: **7 passing/1 failing**. The intended two new legacy readings had the same normalized time and type, so the existing planner correctly merged them into one target. Fixture commit `887c4aad76dc14b85eba5d909e6a7b71396cfdfe` separates the synthetic reading times by one second and asserts distinct planned filters. The product matching rule was unchanged. The earlier typed-twin seed correction likewise removed identifiers that would have made the raw-identity selector inapplicable. Neither fixture mismatch is evidence of a clock product defect.

## Actual lower-port semantic controls

Controls changed isolated archived source, not the canonical worktree. Each failed at the selected actual assertion; none was counted as a setup failure.

| Source change and selected check | Reproduced failure | Restoration |
|---|---|---|
| Remove clock-row FOR UPDATE; select “holds lower allocation through COMMIT” | **0 passing/1 failing**: no actual clock-row lock wait. Diagnostic settlements show the lower write rejected with “Tenant write clock floor was not updated”, while the higher write fulfilled and was the only stored row. The conditional floor update prevented the lower commit; this control does **not** demonstrate a missed late row. | Selected **1 passing**. |
| Bypass legacy server-date finalization; select “finalizes an earlier legacy plan” | **0/1**: actual postcursor rows are empty instead of the expected two distinct legacy targets. | Selected **1 passing**. |
| Publish immediately instead of queueing through afterCommit; select “rolls back actual data” | **0/1**: logical event count **1 rather than0** after an actual data rollback. | Complete restored cohort **8 passing**. |

These observations distinguish allocation/commit visibility, legacy finalization and publication timing. They do not establish exactly-once acknowledgement, delivery or recovery.

## All-domain readiness correction and real SQL proof

**Read-derived catalogue inventory:** entries, treatments, devicestatus and settings provide generated numeric srvModified columns; profile, food and activity do not. All seven persist an object JSONB document. The old readiness query assumed the physical column existed everywhere. The eight-case cohort above provisioned entries only and could not establish all-domain startup.

The correction reads numeric JSON values through a guarded CASE, excludes values outside `[0,8640000000000000)`, combines configured-domain maxima and takes the ceiling in one SQL statement per tenant under RLS. It does not add physical columns, drop domains, broaden privileges, repair floors or bypass admission. Single-statement query structure is source-derived; the following outcomes were measured against PostgreSQL.

At test head `a8d9af9c9f1b4b227d8fc8feb3e23c2fa5139bbf`, the same opt-in command was first selected with `--grep 'admits valid floors across all seven'`. All seven real migrations and serving grants completed. Replacing **only** the readiness module with old source, with an observational driver-error probe, reached the test body and failed: **0 passing/1 failing**, SQLSTATE **42703**, column **srvModified does not exist** (`old-query-driver-control.log`). This reproduces the query/schema incompatibility directly; it does not recover an unsanitized cause from the earlier HTTP log.

Restoring portable source and removing the probe gave selected **1 passing** (`new-query-positive.log`) and complete **9 passing** (`lower-nine-restored.log`). Source and fixture were compared byte-for-byte with canonical files after restoration. The selected case passed both alone and inside the full nine-case cohort:

- Every admitted catalogue is present, including the three without the optional generated column.
- A synthetic profile JSON numeric maximum103.25 requires floor104; floor103 refuses without repair.
- Numeric-looking strings, absent/null/boolean/array/object values, negatives and values at/above the upper range are ignored without unsafe casts; after valid values are removed, floor0 admits.
- Foreign tenant B maximum1000000 does not contaminate tenant A under actual RLS.
- Missing floor and unsafe clock-column privilege states refuse after a valid all-domain setup succeeds.

The three earlier lock/finalizer/publication controls were measured at the original-source fixture head; they were not rerun during this readiness-correction slot. They must not be represented as new controls on the corrected source.

## Source-contract checks and earlier CLI boundary

**Reproduced, source-only:** `tenant-clock-readiness-focused.log` reports **111 passing** across the source protocol, PostgreSQL collection-intent and v1 intent tests. `tenant-clock-readiness-source.log` reports **12 passing/9 pending**: the nine actual-port tests were disabled in this source-only invocation. In an isolated old-query source control, the emitted-SQL contract suite gave **4 passing/1 failing** (zero guarded extraction clauses versus seven required); restoration gave **5 passing**. These recording-connection checks are separate from actual PostgreSQL evidence.

The earlier actual CLI/HTTP attempt at `2619a439470b09db32c1a9ac815e9766a77fb2b4` produced **0 passing/2 failing**, child exit78 before readiness, with **zero HTTP proof bodies** reaching data assertions. Stderr retained a sanitized readiness/storage refusal; the second failure was teardown of the already failed worker. The later actual SQLSTATE42703 control supports the bounded readiness diagnosis. A corrected full configured CLI/HTTP rerun is **UNMEASURED here**. Resource identities remain private.

## Cleanup and remaining limits

Both completed lower-port and all-domain campaigns captured **owned_roles=0/owned_schemas=0**, followed by exact owned-container removal with anonymous-volume removal and independent absence confirmations. The first failed fixture campaign also records owned container/volume absence. This report audits those recorded outcomes; it issues no new Docker or database commands and performs no orphan/global cleanup.

Actual Mongo comparison remains **UNMEASURED**. Similarity of existing Mongo/PG timestamp assignment and history behavior is **read-derived**, not cross-backend proof. Raw import, mixed enabled/disabled writers, all legacy/HTTP paths, full CLI startup after correction, saturated pools, latency/throughput, cancellation/recovery bounds, full nonbrowser/browser suites and final prcheck acceptance are outside these captures. No universal all-history guarantee, per-row bulk uniqueness, new history policy, milestone promotion, merge or release is claimed. The prototype remains bounded branch work pending those gates.
