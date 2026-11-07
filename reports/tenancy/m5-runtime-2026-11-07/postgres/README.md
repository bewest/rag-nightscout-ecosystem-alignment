<a id="m5-postgres-runtime-record"></a>
# M5 bounded PostgreSQL recorded evidence

This bundle validates an archived synthetic measurement: initial ordinary **23**, **19 distinct controlled failures**, and fresh complete restoration **23**. It is **RECORDED-EVIDENCE**, not a fresh database run, current-HEAD acceptance, performance measurement, provider delivery, or complete M5/M6 acceptance. Public API/realtime recipient authority, broader roles and browser acceptance remain **UNMEASURED** here. The selected evaluator lifecycle and controlled UDS consumer boundary are included in the recorded PostgreSQL scope.

This accepted bounded archive is referenced by [R73](../../../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r73-durable-runtime-operations-batch). R73 owns the joined M5 functional-reference disposition; this PostgreSQL archive alone does not promote a milestone or establish current-HEAD/provider acceptance.

## Actual attribution and retained failures

| actual source | accepted recorded boundary | original verdict retained |
|---|---|---|
| `f4e3f7e7b9eab6388cee1fb3470d380506917e05` | ordinary 23; eight original semantic controls; independent authority-control regrade | stopped at `ALARM_REVOKED_AUTHORITY_ABLATION`; original campaign remains unaccepted |
| `353bb4445143bc85fe9f52e6ba3295247b23a96a` | nine further semantic controls; independently named JSONB admission-availability regrade | stopped at `CONSUMER_REQUIRED_PHASE_COUNT committed-before-verdict`; original later-revision assertion was not reached |
| `353bb4445143bc85fe9f52e6ba3295247b23a96a` | fresh full ordinary 23 restoration; four physical verifiers; independent cleanup | restoration accepted |
| `693ca4b82b9ba65bd93242018742f1e062b891e8` | no accepted control | old inner-await control timed out at60,000 ms before its boundary marker; **INVALID**, excluded from the 19 |

The authority regrade requires the actual revoked default level 1 request: exactly one tenantA/default/level 1 row, original60,000 ms interval, delivered=true, callback count 1, and aborted then committed transactions. The earlier verifier incorrectly expected two rows. This does not rewrite the stopped verdict.

The new `consumer-jsonb-admission-churn` contract uses the original comparator mutation and the observed earlier `M5_CONSUMER_COMMIT_BEFORE_SINK` assertion. It requires an exact cancelled attempt 1 with immutable original LOW reading of 50 payload/origin/config, producer revision 3, current eligible clinical output 1, no ACK, no handoff and a normal child exit. Source-protocol diagnosis reproduced revisions 1→2→3 across otherwise equivalent JSONB-key-order reads: the current-cycle guard correctly refuses mismatched producer revisions. The old intended later unchanged-revision assertion remains **not reached**, not reclassified as having run.

The invalid inner-await mutation lost the composition's private credential before the detached writer reached authority/COMMIT. Its replacement, `alarm-reply-before-commit`, removes the outer API ACK reply barrier while retaining the actual composition's writer await and credential cleanup. The recorded control reached the actual held transaction and one callback and no externally visible rows boundary.

There is no aggregate application head. The gate checks 38 committed source files at every declared head:37 original PostgreSQL causal files plus one explicitly bound forwarding-control source. These bytes are equivalent across the declared heads. Each phase retains its actual head/tree, exact selected titles, source archive hashes, controlled source patches and original report/raw-observation SHA256s.

## Run the recorded-evidence gate

With the pinned app objects available at the usual `externals/cgm-remote-monitor-official` repository:

```bash
node tools/queue/gates/m5-runtime-recorded.js
```

An alternate existing object repository can be selected without checking out a peer tree:

```bash
NS_M5_RECORDED_REPO="$APP_OBJECT_REPOSITORY" \
  node tools/queue/gates/m5-runtime-recorded.js
```

Missing source objects fail the gate. It uses `git show` and `git rev-parse`, builtin Node libraries and the four reused physical verifiers. It never fetches, installs dependencies, starts services, runs app jobs or writes a shipping worktree. The projection's canonical digest is `ede0cc342adcea042ba2e7a487eb4a0ec706e442777ce32584da886c5e8e1d6a`.

Authored corrupted-record controls recompute the projection digest before validation, so they reach semantic predicates rather than merely failing checksum validation:

```bash
node tools/queue/gates/m5-runtime-recorded.js --control physical
node tools/queue/gates/m5-runtime-recorded.js --control missing-phase
node tools/queue/gates/m5-runtime-recorded.js --control wrong-source
node tools/queue/gates/m5-runtime-recorded.js --control no-restoration
```

Expected exits: ordinary 0; each control 1; fresh unmodified gate 0. The physical control changes the captured acquired glucose mean from 166.5 to 222 while retaining the original physical rows and report with 23 passes. No original record or source is modified.

## Reproduce the public projection

The whitelist builder requires the exact immutable private synthetic capsules whose index hashes are declared in [plan.json](plan.json). Paths are explicit caller capabilities and are never serialized. It verifies every indexed input before exporting only reviewed semantic fields. It excludes credentials, connection values, arbitrary stdout/stderr, exception stacks and private filesystem paths. CLI stdout becomes only its actual bounded `Evaluator preview started` witness. Generated request/attempt UUIDs are synthetic ledger fences, not client or transport credentials. Typed number probes, actual physical rows and payloads remain intact.

```bash
node tools/queue/gates/_m5-runtime-recorded/build.cjs \
  --repo "$APP_OBJECT_REPOSITORY" \
  --initial "$INITIAL_SYNTHETIC_CAPSULE" \
  --continuation "$CONTINUATION_SYNTHETIC_CAPSULE" \
  --restoration "$RESTORATION_SYNTHETIC_CAPSULE" \
  --invalid-inner-await "$INVALID_SYNTHETIC_CAPSULE" \
  --out "$NEW_PROJECTION_FILE"
cmp reports/tenancy/m5-runtime-2026-11-07/postgres/projection.json "$NEW_PROJECTION_FILE"
```

The output path must be new. Two independent projections from the same capsules were byte-identical. Original private capsule and observer index hashes are preserved in the public data; the archival gate validates the public projection and its declared source/physical contracts, not the continuing existence of private capsules or fresh operating-system resource absence.

## Fresh ordinary reproduction — a separate operation

The shipping corpus CLI actually supports repeatable `--only` file substrings and `--record`; it does not provide an exact-test-title option. In a disposable app checkout at the pinned353 source, with matching installed dependencies and the measured local PostgreSQL image available, this supported command provisions and cleans its own shared PostgreSQL fixture:

```bash
env -u NS_TEST_POSTGRES_ADMIN_URI \
  NS_MULTITENANT_POSTGRES_IMAGE=sha256:066167ff39c2a612402ce99b734ea1cff92a9d1f2ac52f697a5f0384f0d88d6b \
  node scripts/test-multitenant.js \
    --only tenant-current-state-recovery-proof.integration.test.js \
    --only tenant-alarm-state.integration.test.js \
    --only tenant-notifications.integration.test.js \
    --only evaluator-consumers.integration.test.js \
    --record "$NEW_FRESH_RUN_RECORD"
```

This is a **broader fresh file-level reproduction**, including the additional current-state cases in the first file. It is not the archived exact 23-title selection and was not run for packaging. It requires an independently authorized disposable runtime environment. Exact archived selection, all 19 controlled source patch definitions and the invalid old mutation are in [plan.json](plan.json); the public gate does not pretend to execute them against a database.

## Recorded queue wiring

R73 wires the following recorded gate to `MT-RUNTIME-PLAN`, alongside the separately attributed joined-role record. Broader provider/operating contracts remain explicit:

```yaml
- run: node tools/queue/gates/m5-runtime-recorded.js
  kind: integration
  describe: >-
    RECORDED-EVIDENCE: validates the pinned synthetic PostgreSQL23/19/23
    record, per-phase source attribution, controlled physical observations,
    retained stops/regrades and recorded cleanup. No fresh native/currentHEAD
    or broader role/browser/provider acceptance.
```

Matching `queue/gate-controls.yaml` entry:

```yaml
- gate: node tools/queue/gates/m5-runtime-recorded.js
  control: node tools/queue/gates/m5-runtime-recorded.js --control physical
  positive-control: node tools/queue/gates/m5-runtime-recorded.js
  control-kind: integration
  proves: >-
    A rehashed recorded mean222 contradicts the independently captured
    two-reading166.5 bucket and fails EXPLICIT_ACQUISITION_FAILED; the
    unmodified archived record validates. Missing phase, wrong actual head
    and missing complete restoration independently refuse.
```

These entries validate recorded evidence, not a new native run. Historical R62/R67/R68 attribution remains in its records; current gates replay the R73 archives rather than rerun accepted leaf campaigns. Broader `no-gate` contracts are not replaced by test-tier counts.
