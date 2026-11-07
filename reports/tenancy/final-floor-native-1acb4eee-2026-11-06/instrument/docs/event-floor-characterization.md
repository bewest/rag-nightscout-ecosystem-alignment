# PostgreSQL transaction FINAL-floor conformance preparation

SOURCE ONLY. Six native cases remain UNMEASURED. No database, Docker, network,
listener, full/browser/corpus or prcheck execution is part of preparation.

Standalone instrument outside default test tiers/corpus. It archives the entire
committed instrument head and requires exactly these five added files above
candidate `1acb4eee76adf229bfa04f0e9c1fbc51ba3edcc9`. Any other change refuses.
It also verifies the complete four-path gate/test-only difference from
`f2e7fdda11640311bd0508c94d1707a5bc26b4fa`: all product/schema/default inputs
remain identical, beyond explicit five core byte checks. No older source fallback.

The fixture uses actual dates.next(), clock decorator, PostgreSQL connection and
withCommitEvents, reviewed entries/clock catalogues, synthetic physical proof
marker INSERTs. This deliberately does not establish all canonical application
intent/no-op allocation policies. One max1 NOSUPERUSER/NOBYPASSRLS writer and
separate SELECT-only observer read real rows/floors before/after commit; role,
privilege and unbound forced-RLS calibration are asserted. Admin provisions and
cleans unique fixture schemas/roles only in an explicitly disposable database.

## Six native predictions (ALL UNMEASURED)

1. Nested s1 allocation, controlled no-op, settle, sibling s2, outer s3: no
   precommit events/visible rows/floor change; one commit gives physical rows
   s1/s2, independent stored floor s3, event stamps s3/s3/null/s3. No foreign rows.
   Physical row allocations and final event floor are separate assertions.
2. Fresh no-allocation transaction emits null; older row/floor remains unchanged.
3. Outer rollback removes rows/floor changes and all queued callbacks/events.
4. A/B/A on same actual backend isolates rows, tenant metadata and clock state;
   each event uses its own independent postcommit snapshot before next operation.
5. Delivery follows driver COMMIT acknowledgement; retained closed async context
   refuses currentStamp. Delivery-state value/error is independently recorded.
6. Clock-off write emits null without clock table advance. This does not prove
   an admitted mixed-clock deployment guarantee.

## Semantic controls

Unique mutations apply to scratch archive only, without forced assertions.
Positive requires 6 pass/0 fail/0 pending; each control exactly one named
ERR_ASSERTION, 0 pass/1 fail/0 pending, exit1. SQL/setup/import/timeout/TypeError,
pending and unrelated failures are rejected.

- stamp: omit actual final callback argument by replacing
  connection.afterCommit(fn) with connection.afterCommit(() => fn()). This exposes
  captured s1 instead of final s3. Require EVENT_FINAL_FLOOR_MISMATCH, actual s1
  versus independent stored s3, physical rows s1/s2, empty B, invisible precommit
  rows and all deliveries after COMMIT. Null-in-capture control is not reused:
  final callback could override it and make it vacuous.
- premature: immediate publication gives EVENT_BEFORE_COMMIT, count1 versus0,
  driver acknowledgement false, rolled-back physical rows empty.
- tenant: remember first binding; B event metadata A gives
  EVENT_TENANT_CAPTURE_MISMATCH while independent B physical row exists.

run.js --check falsifies unique boundaries, independent oracles and strict parser
with synthetic data only, including rejection of null/incorrect captured floor,
foreign effects, precommit delivery and inconsistent stored floor. Source checks
are not native evidence. Coordinator grants exact runtime/control sequence.

## Future granted invocation

Supply private NS_TEST_POSTGRES_ADMIN_URI for an owned disposable PG16 test-named
database and matching private dependencies. Runner does not provision services or
install/rebuild; scratch node_modules link resolves existing modules read-only.
Use committed INSTRUMENT head (candidate plus five files), not candidate alone:

    node scripts/event-floor-characterization/run.js --check
    node scripts/event-floor-characterization/run.js --ref <instrument-head> --out <fresh-positive>
    node scripts/event-floor-characterization/run.js --ref <instrument-head> --out <fresh-control> --control stamp
    node scripts/event-floor-characterization/run.js --ref <instrument-head> --out <fresh-restored>

Raw Mocha/native/operation/delivery/observer captures carry exact source refs.
Coordinator records exact current-run container/mount IDs and absence after
cleanup; never remove unknown services/volumes. No whole M1–M6 claim follows.
